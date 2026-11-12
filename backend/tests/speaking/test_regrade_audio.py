"""HTTP regression tests using synthetic audio and stub graders, no providers."""

import asyncio
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ielts_agent.agents.speaking.exam_api import install_exam_routes
from ielts_agent.agents.speaking.sessions import SessionStore, finish


TEXT = "I learned programming with my friends because we wanted to build useful things."


class RegradeAudioTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = SessionStore(Path(temp.name) / "sessions.sqlite3")
        self.scope = patch("ielts_agent.agents.speaking.exam_api.store", self.store)
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.offline = patch.dict("os.environ", {"SPEAKING_QUESTION_MODEL": ""})
        self.offline.start()
        self.addCleanup(self.offline.stop)
        app = FastAPI()
        def process(*args):
            return {"transcript": TEXT, "words": [], "audio_seconds": 0.1, "metrics": {}}
        install_exam_routes(app, Path.cwd(), process, {".wav"}, 24 * 1024 * 1024,
                            asyncio.Semaphore(1), lambda content: (0.1, np.zeros(1600)))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        output = BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x00\x00" * 1600)
        self.audio = output.getvalue()

    def new(self):
        response = self.client.post("/api/exam/sessions", json={"mode": "voice", "save_audio": False})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def voice(self, data, request_id):
        s = data["session"]
        response = self.client.post(f"/api/exam/sessions/{s['id']}/voice",
            files={"audio": ("answer.wav", self.audio, "audio/wav")},
            data={"question_id": s["current_question"]["question_id"], "version": s["version"], "request_id": request_id})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def finished(self, reviewed=False):
        data = self.voice(self.new(), "1")
        sid = data["session"]["id"]
        with self.store.connection() as db:
            state = self.store.read(db, sid)
            finish(state)
            assessment = {**state["assessment"], "run_id": "old-run", "status": "final" if reviewed else "provisional"}
            state["assessment"] = assessment
            old = {"assessment": assessment, "graders": [{"valid": True}, {"valid": True}], "retryable": False}
            db.execute("INSERT INTO grading VALUES (?,?)", (sid, json.dumps(old)))
            if reviewed:
                db.execute("INSERT INTO reviews VALUES (?,?)", (sid, json.dumps({"action": "approve", "note": "old review"})))
            self.store.write(db, state)
        return sid, old

    def replacement(self, old):
        result = deepcopy(old)
        result["assessment"].update(run_id="new-run", status="provisional")
        return result

    def test_normal_grade_returns_cache_but_force_runs_and_archives_review(self):
        sid, old = self.finished(reviewed=True)
        with patch("ielts_agent.agents.speaking.exam_api.grade_session", return_value=self.replacement(old)) as grader:
            cached = self.client.post(f"/api/exam/sessions/{sid}/assessment")
            self.assertEqual(cached.json()["assessment"]["run_id"], "old-run")
            grader.assert_not_called()
            updated = self.client.post(f"/api/exam/sessions/{sid}/assessment", json={"force": True})
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["assessment"]["run_id"], "new-run")
            grader.assert_called_once()
        history = self.client.get(f"/api/exam/sessions/{sid}/assessment-history").json()["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["teacher_review"]["note"], "old review")
        self.assertEqual(history[0]["assessment"]["run_id"], "old-run")
        with self.store.connection() as db:
            self.assertIsNone(db.execute("SELECT content FROM reviews WHERE session_id=?", (sid,)).fetchone())

    def test_failed_regrade_preserves_previous_score_and_teacher_review(self):
        sid, old = self.finished(reviewed=True)
        for retryable in (True, False):
            failed = {"assessment": {"grading_errors": ["test failure"]}, "graders": [], "retryable": retryable}
            with patch("ielts_agent.agents.speaking.exam_api.grade_session", return_value=failed):
                result = self.client.post(f"/api/exam/sessions/{sid}/assessment", json={"force": True}).json()
            self.assertTrue(result["regrade_failed"])
            self.assertEqual(result["assessment"], old["assessment"])
            restored = self.client.get(f"/api/exam/sessions/{sid}").json()["session"]
            self.assertEqual(restored["last_grading_attempt"]["status"], "failed")
            self.assertEqual(restored["last_grading_attempt"]["errors"], ["test failure"])
        with self.store.connection() as db:
            self.assertIsNotNone(db.execute("SELECT content FROM reviews WHERE session_id=?", (sid,)).fetchone())
        self.assertEqual(self.client.get(f"/api/exam/sessions/{sid}/assessment-history").json()["history"], [])

    def test_concurrent_teacher_decision_prevents_regrade_overwrite(self):
        sid, old = self.finished()
        def grade(*args):
            with self.store.connection() as db:
                db.execute("INSERT INTO reviews VALUES (?,?)", (sid, json.dumps({"note": "concurrent review"})))
            return self.replacement(old)
        with patch("ielts_agent.agents.speaking.exam_api.grade_session", side_effect=grade):
            response = self.client.post(f"/api/exam/sessions/{sid}/assessment", json={"force": True})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.post(f"/api/exam/sessions/{sid}/assessment").json()["assessment"]["run_id"], "old-run")

    def test_force_still_requires_finished_session(self):
        sid = self.new()["session"]["id"]
        with patch("ielts_agent.agents.speaking.exam_api.grade_session") as grader:
            self.assertEqual(self.client.post(f"/api/exam/sessions/{sid}/assessment", json={"force": True}).status_code, 409)
            grader.assert_not_called()

    def preference(self, data, enabled):
        s = data["session"]
        return self.client.post(f"/api/exam/sessions/{s['id']}/audio-preference", json={"enabled": enabled, "version": s["version"]})

    def test_audio_consent_only_applies_to_future_answers_and_survives_reload(self):
        data = self.voice(self.new(), "1")
        self.assertIsNone(data["answers"][0]["audio_uri"])
        data = self.preference(data, True).json()
        data = self.voice(data, "2")
        self.assertIsNone(data["answers"][0]["audio_uri"])
        uri = data["answers"][1]["audio_uri"]
        response = self.client.get(uri + "?download=true")
        self.assertEqual(response.content, self.audio)
        self.assertIn('attachment; filename="speaking-answer.wav"', response.headers["content-disposition"])
        data = self.preference(data, False).json()
        data = self.voice(data, "3")
        self.assertIsNone(data["answers"][2]["audio_uri"])
        self.assertEqual(self.client.get(uri).content, self.audio)
        sid = data["session"]["id"]
        self.assertEqual(self.client.get(f"/api/exam/sessions/{sid}").json()["answers"][1]["audio_uri"], uri)
        self.assertEqual(self.client.get(f"/api/exam/sessions/{sid}/attempt-audio").status_code, 404)

    def test_complete_saved_audio_downloads_as_wav(self):
        data = self.preference(self.new(), True).json()
        data = self.voice(data, "1")
        sid = data["session"]["id"]
        response = self.client.get(f"/api/exam/sessions/{sid}/attempt-audio")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["content-disposition"])
        with wave.open(BytesIO(response.content)) as wav:
            self.assertEqual(wav.getnframes(), 1600)

    def test_audio_preference_rejects_stale_version_and_finished_session(self):
        data = self.new()
        self.assertEqual(self.preference(data, True).status_code, 200)
        self.assertEqual(self.preference(data, False).status_code, 409)
        sid, old = self.finished()
        response = self.client.post(f"/api/exam/sessions/{sid}/audio-preference", json={"enabled": True, "version": 0})
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
