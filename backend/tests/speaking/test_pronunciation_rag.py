from .fixtures_audio import audio_fixture
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, Mock
import wave

import numpy as np
from fastapi.testclient import TestClient

from ielts_agent.agents.speaking.pronunciation import assess_audio, recognize_file
from ielts_agent.agents.speaking.rag import RubricIndex
from ielts_agent.agents.speaking.server import app
from ielts_agent.agents.speaking.sessions import SessionStore


def azure_result():
    return {"NBest": [{"Display": "A different Azure transcript.", "PronunciationAssessment": {
        "AccuracyScore": 83, "FluencyScore": 75, "ProsodyScore": 71, "PronScore": 78},
        "Words": [{"Word": "school", "Offset": 1_000_000, "Duration": 2_000_000,
                   "PronunciationAssessment": {"AccuracyScore": 62, "ErrorType": "Mispronunciation"},
                   "Phonemes": [{"Phoneme": "s", "PronunciationAssessment": {"AccuracyScore": 60}}]}]}]}


class PronunciationTests(unittest.TestCase):
    def test_no_consent_never_calls_provider_even_if_configured(self):
        caller = Mock()
        with patch("ielts_agent.agents.speaking.pronunciation.capabilities", return_value={"configured": True}):
            result = assess_audio(np.ones(16000), recognize=caller)
        caller.assert_not_called()
        self.assertEqual(result["status"], "not_requested")

    def test_native_scores_and_word_evidence_no_ielts_conversion(self):
        def caller(path, seconds):
            with wave.open(str(path)) as audio:
                self.assertEqual((audio.getnchannels(), audio.getframerate(), audio.getsampwidth()), (1, 16000, 2))
                self.assertEqual(audio.getnframes(), 40 * 16000)
            self.assertEqual(seconds, 40)
            return [azure_result()]
        result = assess_audio(np.ones(40 * 16000) * .1, True, caller)
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["scores"]["accuracy"], 83)
        self.assertEqual(result["segments"][0]["words"][0]["start_s"], .1)
        self.assertIsNone(result["ielts_band"])

    def test_failed_and_empty_service_responses_do_not_invent_zero_scores(self):
        for caller, status in [(Mock(side_effect=RuntimeError("private provider error")), "unavailable"), (lambda *_: [], "no_speech")]:
            result = assess_audio(np.ones(16000), True, caller)
            self.assertEqual(result["status"], status)
            self.assertNotIn(0, result["scores"].values())
            self.assertNotIn("private", json.dumps(result))

    def test_sdk_uses_continuous_unscripted_with_prosody(self):
        import azure.cognitiveservices.speech as sdk
        recognizer = Mock()
        handlers = {}
        for name in ("recognized", "canceled", "session_stopped"):
            getattr(recognizer, name).connect.side_effect = lambda fn, name=name: handlers.update({name: fn})
        def start():
            event = Mock()
            event.result.reason = sdk.ResultReason.RecognizedSpeech
            event.result.json = json.dumps(azure_result())
            handlers["recognized"](event)
            handlers["session_stopped"](None)
        recognizer.start_continuous_recognition_async.return_value.get.side_effect = start
        with patch.dict("os.environ", {"AZURE_SPEECH_KEY": "placeholder", "AZURE_SPEECH_REGION": "eastus"}), \
             patch.object(sdk, "SpeechRecognizer", return_value=recognizer), patch.object(sdk.audio, "AudioConfig"), \
             patch.object(sdk, "SpeechConfig"), patch.object(sdk, "PronunciationAssessmentConfig") as config:
            result = recognize_file(Path("synthetic.wav"), 120)
        self.assertEqual(len(result), 1)
        self.assertEqual(config.call_args.kwargs["reference_text"], "")
        self.assertFalse(config.call_args.kwargs["enable_miscue"])
        config.return_value.enable_prosody_assessment.assert_called_once()
        recognizer.recognize_once_async.assert_not_called()
        recognizer.stop_continuous_recognition_async.assert_called_once()

    def test_both_endpoints_forward_opt_in_and_keep_groq_transcript(self):
        audio = audio_fixture("sample-01.m4a")
        original = "I'm studying at Ngô Gia Tự High School"
        report = assess_audio(np.ones(16000), True, lambda *_: [azure_result()])
        with TemporaryDirectory() as folder, TestClient(app) as client, \
             patch("ielts_agent.agents.speaking.exam_api.store", SessionStore(Path(folder) / "db.sqlite3")), \
             patch.dict("os.environ", {"GROQ_API_KEY": "placeholder"}), patch("ielts_agent.agents.speaking.server.Groq") as groq, \
             patch("ielts_agent.agents.speaking.server.assess_audio", return_value=report) as assess:
            groq.return_value.__enter__.return_value.audio.transcriptions.create.return_value = {"text": original, "words": []}
            response = client.post("/api/transcribe", files={"audio": ("a.m4a", audio)}, data={"question_id": "study-1", "pronunciation_consent": "true"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["transcript"], original)
            self.assertTrue(assess.call_args.kwargs["consent"])
            s = client.post("/api/exam/sessions", json={"mode": "voice"}).json()["session"]
            response = client.post(f"/api/exam/sessions/{s['id']}/voice", files={"audio": ("a.m4a", audio)}, data={
                "question_id": s["current_question"]["question_id"], "request_id": "one", "version": s["version"], "pronunciation_consent": "true"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["answers"][0]["response"], original)
            self.assertTrue(assess.call_args.kwargs["consent"])
            exported = client.get(f"/api/exam/sessions/{s['id']}/export").json()
            self.assertEqual(exported["extensions"]["pronunciation"][0]["scores"]["accuracy"], 83)
            self.assertEqual(exported["tables"]["FINAL_SCORE"], [])


class RagTests(unittest.TestCase):
    def setUp(self):
        self.corpus = [{"chunk_id": str(i), "test_part": "speaking", "criterion": criterion, "band": band,
                        "version": "test", "source_url": "https://example.org/rubric", "text": text}
                       for i, (criterion, band, text) in enumerate([
                           ("FC", 4, "frequent pauses repetition limited connectives"),
                           ("FC", 8, "fluent coherent topic development hesitation content"),
                           ("PR", 6, "stress rhythm intonation phonological intelligibility"),
                           ("GRA", 6, "complex structures grammar accuracy errors"),
                           ("LR", 6, "vocabulary meaning paraphrase word choice")])]
        self.index = RubricIndex(self.corpus)

    def test_metadata_isolation_and_reranking_scores(self):
        hits = self.index.search("frequent pauses repetition", criterion="FC")
        self.assertEqual(hits[0]["band"], 4)
        self.assertTrue(all(h["criterion"] == "FC" for h in hits))
        self.assertEqual(set(hits[0]["retrieval"]), {"bm25", "dense_lsa", "rrf", "rerank", "rank"})
        self.assertEqual(self.index.search("stress intonation", criterion="PR", band=6)[0]["chunk_id"], "2")

    def test_abstains_on_out_of_scope_and_unknown_terms(self):
        for query in ("What is the test fee?", "Writing coherence scoring", "Refund registration", "quantum zebras xyzzy"):
            self.assertEqual(self.index.search(query, criterion="FC"), [], query)

    def test_grading_keeps_entire_band_ladder(self):
        from ielts_agent.agents.speaking.rag import grading_context
        hits = grading_context(self.corpus, "FC", [{"transcript": "fluently talked about school"}])
        self.assertEqual({h["band"] for h in hits}, {4, 8})

    def test_empty_corpus_and_service_validation(self):
        self.assertEqual(RubricIndex([]).search("stress"), [])
        with TestClient(app) as client, patch("ielts_agent.agents.speaking.server.load_descriptors", return_value=self.corpus):
            self.assertEqual(client.post("/api/speaking/rubric/search", json={"query": "stress", "criterion": "PR"}).json()["chunks"][0]["criterion"], "PR")
            self.assertEqual(client.post("/api/speaking/rubric/search", json={"query": "stress", "criterion": "Writing"}).status_code, 422)

    def test_reject_score_citing_different_band(self):
        from ielts_agent.agents.speaking.assessment import validate_assessment
        from .test_exam import GradingTests
        fixture = GradingTests(); fixture.setUp()
        for row in fixture.corpus:
            row["band"] = 9
        errors = validate_assessment(fixture.valid, fixture.session, {a["answer_id"]: a for a in fixture.answers}, fixture.corpus)
        self.assertTrue(any("assigned band" in e for e in errors))

    def test_pdf_cell_mapping_and_merged_zero_band(self):
        from ielts_agent.agents.speaking.ingest_rubric import extract_pdf, FALLBACK_URL
        page = Mock()
        rows = [[str(b), f"FC {b}", f"LR {b}", f"GRA {b}", f"PR {b}"] for b in range(1, 10)]
        rows.append(["0", "Does not complete the test", None, None, None])
        page.extract_tables.return_value = [rows]
        pdf = Mock(); pdf.pages = [page]
        with TemporaryDirectory() as folder, patch("pdfplumber.open") as opened:
            path = Path(folder) / "synthetic.pdf"; path.write_bytes(b"synthetic PDF fixture")
            opened.return_value.__enter__.return_value = pdf
            corpus = extract_pdf(path, FALLBACK_URL)
            self.assertEqual(len(corpus), 40)
            self.assertEqual(next(d for d in corpus if d["criterion"] == "GRA" and d["band"] == 6)["text"], "GRA 6")
            self.assertEqual({d["text"] for d in corpus if d["band"] == 0}, {"Does not complete the test"})
            self.assertTrue(all(d["source_url"] == FALLBACK_URL and d["page"] == 1 for d in corpus))
            page.extract_tables.return_value = [rows[:-1]]
            with self.assertRaisesRegex(ValueError, "40 complete"):
                extract_pdf(path, FALLBACK_URL)


if __name__ == "__main__":
    unittest.main()
