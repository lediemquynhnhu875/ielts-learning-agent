from .fixtures_audio import audio_fixture
from io import BytesIO
import json
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import wave

from fastapi.testclient import TestClient

from ielts_agent.agents.speaking.analysis import analyze, disfluency_candidates
from ielts_agent.agents.speaking.server import SAMPLES, app, audio_info, safe_activity
from ielts_agent.agents.speaking.vad import activity_metrics, detect_activity


ROOT = Path(__file__).resolve().parents[3]
GROQ_RESULTS = json.loads((ROOT / "docs/speaking/stt-results/groq/results.json").read_text())["results"]
LOCAL_RESULTS = json.loads((ROOT / "docs/speaking/stt-results/local/results.json").read_text())["results"]


def recorded_result(results, sample, prompt=False):
    return next(r for r in results if r["sample"] == sample and r["keep_fillers"] == prompt)


class AnalysisTests(unittest.TestCase):
    def analyze_sample(self, sample, prompt=False):
        r = recorded_result(GROQ_RESULTS, sample, prompt)
        return analyze(r["transcript"], r["words"], r["audio_seconds"])

    def test_known_good_sample_has_timing_metrics(self):
        result = self.analyze_sample("sample-01")
        self.assertTrue(result["quality"]["timing_valid"])
        self.assertGreater(result["metrics"]["timing"]["words_per_minute"], 0)

    def test_groq_timestamp_beyond_audio_suppresses_timing(self):
        result = self.analyze_sample("sample-06", True)
        self.assertFalse(result["quality"]["timing_valid"])
        self.assertIsNone(result["metrics"]["timing"])
        issue = next(i for i in result["quality"]["issues"] if i["code"] == "timestamps_outside_audio")
        self.assertEqual(len(issue["word_indices"]), 8)

    def test_known_reversed_timestamps_suppress_timing(self):
        for sample in ["sample-03", "sample-07", "sample-08", "sample-10"]:
            with self.subTest(sample=sample):
                result = self.analyze_sample(sample)
                self.assertIsNone(result["metrics"]["timing"])
                self.assertIn("timestamps_reversed", [i["code"] for i in result["quality"]["issues"]])

    def test_repeated_local_fallback_is_flagged(self):
        r = recorded_result(LOCAL_RESULTS, "sample-05", True)
        result = analyze(r["transcript"], r["words"], r["audio_seconds"])
        self.assertIn("repeated_content", [i["code"] for i in result["quality"]["issues"]])
        self.assertIsNone(result["metrics"]["timing"])

    def test_ordinary_like_is_not_counted_as_filler(self):
        self.assertEqual(self.analyze_sample("sample-02")["metrics"]["filler_count"], 0)

    def test_invalid_timestamp_values_are_rejected(self):
        for value in [math.nan, math.inf, "1", None, True]:
            with self.subTest(value=value):
                result = analyze("Hello", [{"word": "Hello", "start": value, "end": 2}], 3)
                self.assertFalse(result["quality"]["timing_valid"])

    def test_mismatched_transcript_is_flagged(self):
        result = analyze("Hello there", [{"word": "Hello", "start": 0, "end": 1}], 2)
        self.assertIn("transcript_word_mismatch", [i["code"] for i in result["quality"]["issues"]])

    def test_zero_duration_words_disable_stt_timing(self):
        result = analyze("Hello there", [{"word": "Hello", "start": 0, "end": 0}, {"word": "there", "start": 1, "end": 2}], 3)
        self.assertIsNone(result["metrics"]["timing"])
        self.assertIn("zero_word_duration", [i["code"] for i in result["quality"]["issues"]])

    def test_long_word_warns_without_discarding_vad_pauses(self):
        activity = activity_metrics([{"start": 2, "end": 4}], 5)
        result = analyze("Hello", [{"word": "Hello", "start": 0, "end": 4}], 5, activity)
        self.assertTrue(result["quality"]["timing_valid"])
        self.assertEqual(result["quality"]["status"], "needs_review")
        self.assertEqual(result["metrics"]["audio_timing"]["words_per_minute"], 30)
        self.assertIn("word_overlaps_non_speech", [i["code"] for i in result["quality"]["issues"]])

    def test_phrases_and_restarts_are_candidates_not_scores(self):
        result = disfluency_candidates("I study at home, at home. Sorry, I mean at the library. I am more confident than I would, than when I started.")
        self.assertIn("at home", [p["text"] for p in result["repeated_phrases"]])
        self.assertIn("than", [p["marker"] for p in result["repair_candidates"]])
        self.assertIn("i mean", [p["marker"] for p in result["repair_candidates"]])
        self.assertEqual(disfluency_candidates("I solve problems step by step.")["repair_candidates"], [])

    def test_short_sentence_repetition_needs_review(self):
        result = analyze("Thank you. Thank you. Thank you.", [], 4)
        self.assertFalse(result["quality"]["text_checks_passed"])
        self.assertIn("repeated_short_sentences", [i["code"] for i in result["quality"]["issues"]])

    def test_bad_stt_still_allows_audio_pause_measurements(self):
        activity = activity_metrics([{"start": 1, "end": 2}, {"start": 3, "end": 4}], 5)
        result = analyze("Hello", [{"word": "Hello", "start": 0, "end": 8}], 5, activity)
        self.assertIsNone(result["metrics"]["timing"])
        self.assertEqual(result["metrics"]["audio_timing"]["internal_pause_count"], 1)
        self.assertIsNone(result["metrics"]["audio_timing"]["words_per_minute"])


class VadTests(unittest.TestCase):
    def test_internal_pauses_exclude_leading_and_trailing_audio(self):
        result = activity_metrics([{"start": 2, "end": 3.5}, {"start": 4, "end": 5}, {"start": 5.2, "end": 7}], 10)
        self.assertEqual(result["internal_pause_count"], 1)
        self.assertEqual(result["pause_seconds"], 0.5)
        self.assertEqual(result["leading_non_speech_seconds"], 2)
        self.assertEqual(result["trailing_non_speech_seconds"], 3)
        self.assertEqual(result["speech_window_seconds"], 5)
        self.assertEqual(result["voiced_seconds"], 4.3)

    def test_empty_vad_has_no_rate_or_window(self):
        result = activity_metrics([], 5)
        self.assertEqual(result["status"], "no_speech")
        self.assertIsNone(result["speech_window_seconds"])
        self.assertIsNone(result["words_per_minute"])

    def test_vad_failure_is_explicit_not_a_fabricated_zero(self):
        with patch("ielts_agent.agents.speaking.server.detect_activity", side_effect=RuntimeError("model unavailable")):
            result = safe_activity([])
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("internal_pause_count", result)

    def test_actual_user_audio_vad_regression(self):
        _, samples = audio_info(audio_fixture("part2-skill-test-01.webm"))
        result = detect_activity(samples)
        self.assertEqual(result["internal_pause_count"], 13)
        self.assertAlmostEqual(result["pause_seconds"], 11.168, places=3)
        self.assertAlmostEqual(result["speech_start_seconds"], 2.816, places=3)
        answer = json.loads((ROOT / "docs/speaking/stt-results/user-tests/part2-skill-test-01.json").read_text())["answers"][0]
        checked = analyze(answer["transcript"], answer["words"], answer["audio_seconds"], result)
        self.assertEqual(checked["metrics"]["audio_timing"]["words_per_minute"], 138.7)
        self.assertEqual(checked["metrics"]["timing"]["pause_count"], 7)
        self.assertEqual(checked["quality"]["status"], "needs_review")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.audio = audio_fixture("sample-01.m4a")

    def upload(self, filename="answer.m4a", content=None, question="study-1"):
        return self.client.post("/api/transcribe", files={"audio": (filename, self.audio if content is None else content)},
                                data={"question_id": question, "keep_fillers": "false"})

    def test_question_bank_and_sample_playback(self):
        if not (SAMPLES / "sample-01.m4a").exists():
            self.skipTest("thiếu bản thu mẫu; đặt SPEAKING_SAMPLES_DIR tới thư mục chứa chúng")
        topics = self.client.get("/api/questions").json()["topics"]
        self.assertEqual(sum(len(t["questions"]) for t in topics), 15)
        self.assertEqual(self.client.get("/api/samples/sample-01/audio").content, self.audio)
        self.assertEqual(self.client.get("/api/samples/not-a-sample/audio").status_code, 404)

    def test_saved_sample_is_revalidated_without_api(self):
        response = self.client.get("/api/samples/sample-06?keep_fillers=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "benchmark")
        self.assertIsNone(response.json()["metrics"]["timing"])

    def test_live_pipeline_with_stubbed_provider(self):
        r = recorded_result(GROQ_RESULTS, "sample-01")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}), patch("ielts_agent.agents.speaking.server.transcribe_groq", return_value=(r["transcript"], r["words"])) as provider:
            response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["source"], "live")
        self.assertEqual(response.json()["question"]["id"], "study-1")
        self.assertTrue(response.json()["quality"]["timing_valid"])
        self.assertEqual(response.json()["schema_version"], "1.2")
        self.assertEqual(response.json()["metrics"]["audio_timing"]["status"], "ok")
        provider.assert_called_once()

    def test_missing_key_returns_actionable_error(self):
        with patch.dict(os.environ, {}, clear=True), patch("ielts_agent.agents.speaking.server.load_dotenv"):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertIn("GROQ_API_KEY", response.json()["detail"])

    def test_bad_uploads_are_rejected(self):
        self.assertEqual(self.upload("answer.txt").status_code, 415)
        self.assertEqual(self.upload(content=b"").status_code, 422)
        self.assertEqual(self.upload(content=b"not real audio").status_code, 422)
        self.assertEqual(self.upload(question="nonexistent").status_code, 422)

    def test_silent_audio_does_not_call_provider(self):
        content = BytesIO()
        with wave.open(content, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(16000)
            recording.writeframes(bytes(32000))
        with patch("ielts_agent.agents.speaking.server.transcribe_groq") as provider:
            response = self.upload("silence.wav", content.getvalue())
        self.assertEqual(response.status_code, 422)
        provider.assert_not_called()

    def test_cue_cards_have_complete_original_prompts(self):
        result = self.client.get("/api/cue-cards").json()
        self.assertEqual(result["preparation_seconds"], 60)
        self.assertEqual(result["speaking_seconds"], 120)
        self.assertEqual(len(result["cards"]), 6)
        self.assertEqual(len({c["id"] for c in result["cards"]}), 6)
        self.assertTrue(all(c["part"] == 2 and len(c["points"]) == 3 and c["explain"] for c in result["cards"]))

    def test_part2_preserves_cue_card_and_preparation_in_response(self):
        r = recorded_result(GROQ_RESULTS, "sample-01")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}), patch("ielts_agent.agents.speaking.server.transcribe_groq", return_value=(r["transcript"], r["words"])):
            response = self.client.post("/api/transcribe", files={"audio": ("answer.m4a", self.audio)},
                data={"question_id": "part2-skill", "preparation_seconds": "45.5", "notes": "practice every day"})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["part"], 2)
        self.assertEqual(len(data["question"]["points"]), 3)
        self.assertEqual(data["speaking_limit_seconds"], 120)
        self.assertEqual(data["preparation"]["seconds"], 45.5)
        self.assertEqual(data["preparation"]["notes"], "practice every day")

    def test_part2_rejects_audio_longer_than_two_minutes(self):
        content = BytesIO()
        with wave.open(content, "wb") as recording:
            recording.setnchannels(1); recording.setsampwidth(2); recording.setframerate(16000)
            recording.writeframes(bytes(16000 * 2 * 122))
        with patch("ielts_agent.agents.speaking.server.transcribe_groq") as provider:
            response = self.upload("long.wav", content.getvalue(), question="part2-skill")
        self.assertEqual(response.status_code, 413)
        self.assertIn("120", response.json()["detail"])
        provider.assert_not_called()

    def test_part2_rejects_invalid_preparation_metadata(self):
        for seconds in ["-1", "61"]:
            response = self.client.post("/api/transcribe", files={"audio": ("answer.m4a", self.audio)},
                data={"question_id": "part2-skill", "preparation_seconds": seconds})
            self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/transcribe", files={"audio": ("answer.m4a", self.audio)},
            data={"question_id": "part2-skill", "notes": "x" * 2001})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
