"""Database-design.docx contract checks and complete export integration tests."""

from .fixtures_audio import audio_fixture
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import unittest
import os
from unittest.mock import patch
from uuid import uuid4
import wave
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from ielts_agent.agents.speaking.database import TABLE_MODELS, export_database, validate_export
from ielts_agent.agents.speaking.grading import grade_session
from ielts_agent.agents.speaking.grading import load_descriptors
from ielts_agent.agents.speaking.assessment import empty_assessment
from ielts_agent.agents.speaking.server import app
from ielts_agent.agents.speaking.sessions import SessionStore

ROOT = Path(__file__).resolve().parents[3]
TEXT = "I learned programming at university because it helps me solve difficult problems with my friends."


def setUpModule():
    # ielts_agent.agents.speaking.server loads .env on import, so a configured question
    # model would make these session flows call Groq for real. The optional LLM
    # paths are exercised with stub callers instead.
    global _OFFLINE
    _OFFLINE = patch.dict(os.environ, {"SPEAKING_QUESTION_MODEL": "",
                                       "SPEAKING_GRADER_MODEL": "test-grader-model"})
    _OFFLINE.start()


def tearDownModule():
    _OFFLINE.stop()


class DatabaseExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SessionStore(Path(self.temp.name) / "sessions.sqlite3")
        patcher = patch("ielts_agent.agents.speaking.exam_api.store", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def new(self, mode="text", save_audio=False, **extra):
        extra.setdefault("kind", "mock" if mode == "voice" else "practice")
        r = self.client.post("/api/exam/sessions", json={"mode": mode, "save_audio": save_audio, **extra})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def submit(self, data, text=TEXT):
        s = data["session"]
        r = self.client.post(f"/api/exam/sessions/{s['id']}/text", json={"question_id": s["current_question"]["question_id"], "version": s["version"], "request_id": str(s["version"]), "text": text})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def export(self, data):
        r = self.client.get(f"/api/exam/sessions/{data['session']['id']}/export")
        self.assertEqual(r.status_code, 200, r.text)
        validate_export(r.json())
        return r.json()

    def test_record_columns_match_source_document_tables(self):
        # Independent source of truth: table headers in the supplied Word file.
        # Tài liệu thiết kế không nằm trong repo; trỏ SPEAKING_DB_DESIGN_DOCX tới
        # file database-design.docx để chạy phép đối chiếu này.
        design = Path(os.environ.get("SPEAKING_DB_DESIGN_DOCX") or ROOT / "database-design.docx")
        if not design.exists():
            self.skipTest("thiếu database-design.docx; đặt SPEAKING_DB_DESIGN_DOCX tới file đó")
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(design) as source:
            doc = ET.fromstring(source.read("word/document.xml"))
        field_sets = []
        for table in doc.findall(".//w:tbl", ns):
            rows = table.findall("w:tr", ns)
            if not rows:
                continue
            first = "".join(t.text or "" for t in rows[0].findall(".//w:t", ns))
            if not first.startswith("Thuộc tính"):
                continue
            fields = set()
            for row in rows[1:]:
                cell = row.find("w:tc", ns)
                label = "".join(t.text or "" for t in cell.findall(".//w:t", ns))
                fields.add(re.split(r"[ (]", label)[0])
            field_sets.append(fields)
        for name, model in TABLE_MODELS.items():
            self.assertIn(set(model.model_fields), field_sets, name)

    def test_session_identifiers_are_distinct_and_use_existing_learner(self):
        learner = str(uuid4())
        data = self.new(learner_id=learner, thread_id="group-checkpoint")
        s = data["session"]
        self.assertEqual(s["learner_id"], learner)
        self.assertEqual(s["thread_id"], "group-checkpoint")
        self.assertNotEqual(s["id"], s["attempt_id"])
        self.assertNotIn("session_id", s)
        self.assertNotIn("q_id", s["current_question"])
        data = self.submit(data)
        a = data["answers"][0]
        self.assertEqual(a["attempt_id"], s["attempt_id"])
        self.assertEqual(a["response"], TEXT)
        self.assertNotEqual(a["id"], a["speaking_turn"]["id"])

    def test_full_session_normalizes_all_relationships_and_preserves_unicode(self):
        data = self.new()
        for _ in range(10):
            data = self.submit(data)
        payload = self.export(data)
        t = payload["tables"]
        self.assertEqual(len(t["SESSION"]), 1)
        self.assertEqual(len(t["ATTEMPT"]), 1)
        self.assertEqual(len(t["ANSWER"]), 10)
        self.assertEqual(len(t["SPEAKING_TURN"]), 10)
        self.assertEqual(len(t["ASKED_QUESTION"]), 10)
        self.assertEqual(t["ATTEMPT"][0]["text_or_transcript"], "\n\n".join([TEXT] * 10))
        # A typed session is practice: the mock exam only accepts recordings.
        self.assertEqual(t["SESSION"][0]["kind"], "practice")
        self.assertIsNone(t["ATTEMPT"][0]["audio_uri"])
        self.assertIsNone(t["ATTEMPT"][0]["raw_score"])
        self.assertTrue(all(t["ASKED_QUESTION"][-i]["refs_point_id"] for i in (1, 2, 3)))
        self.assertFalse(t["FINAL_SCORE"])
        self.assertEqual(t["ASSESSMENT"][0]["word_count"], len(TEXT.split()) * 10)
        self.assertEqual(payload, self.export(data))

    def test_evidence_offsets_are_attempt_relative_and_retrieval_links_differ_from_citations(self):
        data = self.submit(self.new(), "🙂 " + TEXT)
        data = self.submit(data)
        with self.store.connection() as db:
            state = self.store.read(db, data["session"]["id"])
            answers = self.store.answers(db, state["session_id"])
        source = answers[1]
        quote = "programming"
        start = source["transcript"].index(quote)
        corpus = [{"chunk_id": c, "test_part": "speaking", "criterion": c, "band": 6, "version": "fixture-v1", "source_url": None, "text": "Test fixture only"} for c in ("FC", "LR", "GRA")]
        corpus.append({**corpus[0], "chunk_id": "FC-extra", "band": 7})
        result = {"criteria": [{"criterion": c, "status": "assessed", "band": 6, "comment": "Test only", "descriptor_refs": [c],
                                "evidence": [{"answer_id": source["answer_id"], "turn_id": source["turn_id"], "transcript_ref": source["transcript_ref"], "transcript_version": 1, "quote": quote, "start_char": start, "end_char": start + len(quote), "t_start_s": None}]} for c in ("FC", "LR", "GRA")]
                              + [{"criterion": "PR", "status": "not_assessed", "band": None, "comment": "Text", "descriptor_refs": [], "evidence": []}],
                  "flags": [], "corrections": [{"answer_id": a["answer_id"], "upgraded_answer": "An upgraded answer.", "vocabulary": ["improve"]} for a in answers]}
        with patch("ielts_agent.agents.speaking.grading.capabilities", return_value={"grading_ready": True}), patch("ielts_agent.agents.speaking.grading.load_descriptors", return_value=corpus):
            grading = grade_session(state, answers, caller=lambda payload: deepcopy(result))
        exported = export_database(state, answers, grading)
        t = exported["tables"]
        for evidence in t["EVIDENCE_SPAN"]:
            self.assertEqual(evidence["start_char"], len(answers[0]["transcript"]) + 2 + start)
            self.assertEqual(t["ATTEMPT"][0]["text_or_transcript"][evidence["start_char"]:evidence["end_char"]], quote)
            self.assertTrue(evidence["verified"])
        self.assertEqual({r["grader_role"] for r in t["GRADING"]}, {"A", "B"})
        self.assertEqual(len(t["GRADING_CRITERION"]), 8)
        self.assertEqual(len(t["FINAL_SCORE"]), 4)  # FC/LR/GRA/overall; no fake PR
        self.assertEqual(len(t["GRADING_CHUNK"]), 8)
        self.assertEqual(len(t["CRITERION_REF"]), 6)
        self.assertTrue(all(r["source"] == "average" for r in t["FINAL_SCORE"]))
        bad = deepcopy(exported)
        bad["tables"]["EVIDENCE_SPAN"][0]["start_char"] = start
        with self.assertRaises(ValueError):
            validate_export(bad)

    def test_export_rejects_unknown_columns_and_orphan_keys(self):
        exported = self.export(self.submit(self.new()))
        for table, field, value in [("SESSION", "session_id", str(uuid4())), ("ANSWER", "attempt_id", str(uuid4()))]:
            bad = deepcopy(exported)
            bad["tables"][table][0][field] = value
            with self.assertRaises(ValueError):
                validate_export(bad)

    def test_audio_uri_is_real_and_all_recordings_require_consent(self):
        audio = audio_fixture("sample-01.m4a")
        for consent in (True, False):
            data = self.new("voice", consent)
            for n in range(2):
                state = data["session"]
                with patch("ielts_agent.agents.speaking.server.transcribe_groq", return_value=(TEXT, [])), patch.dict("os.environ", {"GROQ_API_KEY": "test-placeholder"}):
                    r = self.client.post(f"/api/exam/sessions/{state['id']}/voice", files={"audio": ("answer.m4a", audio)}, data={"question_id": state["current_question"]["question_id"], "request_id": f"voice-{n}", "version": state["version"]})
                self.assertEqual(r.status_code, 200, r.text)
                data = r.json()
            exported = self.export(data)
            attempt = exported["tables"]["ATTEMPT"][0]
            turns = exported["tables"]["SPEAKING_TURN"]
            if consent:
                recording = self.client.get(attempt["audio_uri"])
                self.assertEqual(recording.status_code, 200)
                with wave.open(BytesIO(recording.content)) as wav:
                    self.assertEqual(wav.getframerate(), 16000)
                    self.assertAlmostEqual(wav.getnframes() / 16000, sum(t["duration_s"] for t in turns), places=5)
                self.assertEqual(turns[0]["t_start_s"], 0)
                self.assertAlmostEqual(turns[1]["t_start_s"], turns[0]["duration_s"], places=5)
            else:
                self.assertIsNone(attempt["audio_uri"])
                self.assertTrue(all(t["t_start_s"] is None for t in turns))

    def test_legacy_checkpoints_export_stable_ids_without_rewriting_audio(self):
        data = self.submit(self.new())
        sid = data["session"]["id"]
        with self.store.connection() as db:
            state = self.store.read(db, sid)
            state.pop("attempt_id")
            state.pop("item_id")
            state.pop("kind")
            state.pop("thread_id")
            self.store.write(db, state)
        first = self.client.get(f"/api/exam/sessions/{sid}/export").json()
        second = self.client.get(f"/api/exam/sessions/{sid}/export").json()
        self.assertEqual(first, second)
        validate_export(first)
        self.assertEqual(first["tables"]["ANSWER"][0]["id"], data["answers"][0]["id"])

    def test_practice_exports_use_same_schema(self):
        answer = {"id": str(uuid4()), "part": 2, "question": {"id": "part2-skill", "text": "Describe a skill", "part": 2, "points": ["one", "two", "three"]},
                  "transcript": "I'm studying at Ngô Gia Tự High School", "audio_seconds": 4, "words": [], "quality": {"timing_valid": False}}
        payload = {"session_id": str(uuid4()), "created_at": "2026-10-16T00:00:00Z", "answers": [answer]}
        r = self.client.post("/api/speaking/export", json=payload)
        self.assertEqual(r.status_code, 200, r.text)
        t = r.json()["tables"]
        self.assertEqual(t["SESSION"][0]["kind"], "practice")
        self.assertEqual(t["ANSWER"][0]["response"], answer["transcript"])
        self.assertEqual(t["SPEAKING_TURN"][0]["part"], "part2")
        self.assertIsNone(t["ATTEMPT"][0]["audio_uri"])
        self.assertEqual(r.json(), self.client.post("/api/speaking/export", json=payload).json())

    def test_pending_teacher_does_not_export_final_scores_or_fake_reviews(self):
        data = self.submit(self.new(), "Yes.")
        with self.store.connection() as db:
            state = self.store.read(db, data["session"]["id"])
            answers = self.store.answers(db, state["session_id"])
        assessment = empty_assessment(state, "Need review")
        assessment.update(status="pending_teacher", grading_errors=["Unresolved grader evidence"])
        payload = export_database(state, answers, {"assessment": assessment, "graders": []})
        self.assertEqual(payload["tables"]["ASSESSMENT"][0]["status"], "pending_teacher")
        self.assertTrue(payload["tables"]["RECONCILIATION"][0]["escalated"])
        self.assertEqual(payload["tables"]["ASSESSMENT_FLAG"][0]["set_by"], "code")
        for table in ("FINAL_SCORE", "RECON_CRITERION", "TEACHER_REVIEW"):
            self.assertEqual(payload["tables"][table], [])

    def test_descriptor_corpus_uses_chunk_id_and_legacy_id_is_readable(self):
        path = Path(self.temp.name) / "descriptors.json"
        for key in ("id", "chunk_id"):
            path.write_text(json.dumps([{key: "speaking-fc-6", "test_part": "speaking", "criterion": "FC", "text": "Fixture", "version": "fixture"}]))
            with patch.dict("os.environ", {"SPEAKING_DESCRIPTORS_PATH": str(path)}):
                rows = load_descriptors()
            self.assertEqual(rows[0]["chunk_id"], "speaking-fc-6")
            self.assertNotIn("id", rows[0])


if __name__ == "__main__":
    unittest.main()
