"""Regression checks for original-language transcription (no live API calls)."""

from .fixtures_audio import audio_fixture
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from ielts_agent.agents.speaking.analysis import analyze, tokens
from ielts_agent.agents.speaking.server import app
from ielts_agent.agents.speaking.test_whisper import FILLER_PROMPT, groq_stt_model, transcription_prompt, transcribe_groq, transcribe_local


VI = "Tôi nghĩ học tiếng Anh rất hữu ích."
MIXED = "I like programming nhưng tôi chưa biết cách làm."


def setUpModule():
    # ielts_agent.agents.speaking.server loads .env on import, so a configured question
    # model would make the exam flow here call Groq for real.
    global _OFFLINE
    _OFFLINE = patch.dict(os.environ, {"SPEAKING_QUESTION_MODEL": "",
                                       "SPEAKING_GRADER_MODEL": "test-grader-model"})
    _OFFLINE.start()


def tearDownModule():
    _OFFLINE.stop()


class LanguageTests(unittest.TestCase):
    def test_groq_auto_detects_without_translation_or_language_override(self):
        with TemporaryDirectory() as folder:
            audio = Path(folder) / "audio.wav"
            audio.write_bytes(b"provider is mocked")
            for transcript in (VI, MIXED, "I enjoy learning English."):
                for keep_fillers in (False, True):
                    with self.subTest(transcript=transcript, keep_fillers=keep_fillers):
                        client = MagicMock()
                        words = [{"word": transcript, "start": 0.0, "end": 1.0}]
                        client.audio.transcriptions.create.return_value = {"text": transcript, "words": words}
                        result, returned_words = transcribe_groq(audio, keep_fillers, client)
                        kwargs = client.audio.transcriptions.create.call_args.kwargs
                        self.assertNotIn("language", kwargs)
                        client.audio.translations.create.assert_not_called()
                        self.assertEqual(kwargs["prompt"], FILLER_PROMPT if keep_fillers else None)
                        self.assertEqual(result, transcript)
                        self.assertEqual(returned_words, words)

    def test_local_explicitly_transcribes_and_detects_each_segment(self):
        for keep_fillers in (False, True):
            model = MagicMock()
            segments = [SimpleNamespace(text=text, words=[]) for text in ("I like programming", "nhưng tôi chưa biết cách làm.")]
            model.transcribe.return_value = (segments, None)
            result, _ = transcribe_local("mock.wav", keep_fillers, model)
            kwargs = model.transcribe.call_args.kwargs
            self.assertIsNone(kwargs["language"])
            self.assertEqual(kwargs["task"], "transcribe")
            self.assertTrue(kwargs["multilingual"])
            self.assertFalse(kwargs["vad_filter"])
            self.assertEqual(result, MIXED)

    def test_vietnamese_letters_are_not_removed_by_analysis(self):
        self.assertEqual(tokens("Tôi nghĩ, ừm, I don't know."), ["tôi", "nghĩ", "ừm", "i", "don't", "know"])
        result = analyze("Ừ à ơ", [], 3)
        self.assertNotIn("empty_transcript", [i["code"] for i in result["quality"]["issues"]])
        self.assertEqual(result["metrics"]["word_count"], 3)

    def test_practice_api_preserves_bilingual_provider_output(self):
        audio = audio_fixture("sample-01.m4a")
        with TestClient(app) as client, patch.dict("os.environ", {"GROQ_API_KEY": "test-placeholder"}), patch("ielts_agent.agents.speaking.server.Groq") as factory:
            provider = factory.return_value.__enter__.return_value
            provider.audio.transcriptions.create.return_value = {"text": MIXED, "words": []}
            response = client.post("/api/transcribe", files={"audio": ("answer.m4a", audio)}, data={"question_id": "study-1"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["transcript"], MIXED)
        self.assertEqual(response.json()["transcription_policy"], "original_language_context_v2")
        self.assertNotIn("language", provider.audio.transcriptions.create.call_args.kwargs)

    def test_exam_voice_preserves_vietnamese_and_flags_language_switch(self):
        from ielts_agent.agents.speaking.sessions import SessionStore
        audio = audio_fixture("sample-01.m4a")
        with TemporaryDirectory() as folder, patch("ielts_agent.agents.speaking.exam_api.store", SessionStore(Path(folder) / "exam.sqlite3")), TestClient(app) as client:
            data = client.post("/api/exam/sessions", json={"mode": "voice"}).json()["session"]
            with patch.dict("os.environ", {"GROQ_API_KEY": "test-placeholder"}), patch("ielts_agent.agents.speaking.server.Groq") as factory:
                provider = factory.return_value.__enter__.return_value
                provider.audio.transcriptions.create.return_value = {"text": VI, "words": []}
                response = client.post(f"/api/exam/sessions/{data['id']}/voice",
                                       files={"audio": ("answer.m4a", audio)},
                                       data={"question_id": data["current_question"]["question_id"], "request_id": "vi-answer", "version": data["version"]})
            self.assertEqual(response.status_code, 200, response.text)
            answer = response.json()["answers"][0]
            self.assertEqual(answer["response"], VI)
            self.assertIn("language_switch", answer["flags"])

    def test_name_hints_do_not_include_a_reference_answer(self):
        self.assertEqual(transcription_prompt(False, " Ngô Gia Tự "), "Ngô Gia Tự")
        self.assertEqual(transcription_prompt(True, "Ngô Gia Tự"), "Ngô Gia Tự; " + FILLER_PROMPT)
        self.assertIsNone(transcription_prompt(False))
        self.assertNotIn("tôi nghĩ", FILLER_PROMPT)
        self.assertNotIn("I think", FILLER_PROMPT)
        with patch.dict("os.environ", {"SPEAKING_STT_MODEL": ""}):
            self.assertEqual(groq_stt_model(), "whisper-large-v3")

    def test_configured_model_is_used_without_forcing_language(self):
        with TemporaryDirectory() as folder, patch.dict("os.environ", {"SPEAKING_STT_MODEL": "whisper-large-v3"}):
            audio = Path(folder) / "audio.wav"
            audio.write_bytes(b"mocked")
            client = MagicMock()
            original = "I'm studying at Ngô Gia Tự High School"
            client.audio.transcriptions.create.return_value = {"text": original, "words": []}
            transcript, _ = transcribe_groq(audio, False, client=client, vocabulary="Ngô Gia Tự")
            kwargs = client.audio.transcriptions.create.call_args.kwargs
            self.assertEqual(kwargs["model"], "whisper-large-v3")
            self.assertEqual(kwargs["prompt"], "Ngô Gia Tự")
            self.assertNotIn("language", kwargs)
            self.assertEqual(transcript, original)

    def test_vocabulary_reaches_both_voice_endpoints(self):
        from ielts_agent.agents.speaking.sessions import SessionStore
        audio = audio_fixture("sample-01.m4a")
        with TemporaryDirectory() as folder, patch("ielts_agent.agents.speaking.exam_api.store", SessionStore(Path(folder) / "exam.sqlite3")), TestClient(app) as client, patch.dict("os.environ", {"GROQ_API_KEY": "test-placeholder"}), patch("ielts_agent.agents.speaking.server.Groq") as factory:
            provider = factory.return_value.__enter__.return_value
            provider.audio.transcriptions.create.return_value = {"text": MIXED, "words": []}
            response = client.post("/api/transcribe", files={"audio": ("answer.m4a", audio)}, data={"question_id": "study-1", "vocabulary": "Ngô Gia Tự"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(provider.audio.transcriptions.create.call_args.kwargs["prompt"], "Ngô Gia Tự")
            self.assertEqual(response.json()["transcript"], MIXED)
            self.assertIn("vocabulary_needs_review", [i["code"] for i in response.json()["quality"]["issues"]])
            state = client.post("/api/exam/sessions", json={"mode": "voice"}).json()["session"]
            response = client.post(f"/api/exam/sessions/{state['id']}/voice", files={"audio": ("answer.m4a", audio)},
                                   data={"question_id": state["current_question"]["question_id"], "version": state["version"], "request_id": "hinted", "vocabulary": "Ngô Gia Tự"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(provider.audio.transcriptions.create.call_args.kwargs["prompt"], "Ngô Gia Tự")

    def test_vocabulary_length_is_validated(self):
        audio = audio_fixture("sample-01.m4a")
        with TestClient(app) as client:
            response = client.post("/api/transcribe", files={"audio": ("answer.m4a", audio)}, data={"question_id": "study-1", "vocabulary": "a" * 401})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
