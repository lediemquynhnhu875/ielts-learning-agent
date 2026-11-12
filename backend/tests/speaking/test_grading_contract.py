"""Grader payload, code-resolved evidence, rate limits, teacher review, planning.

All provider behaviour is stubbed: no Groq call is made.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ielts_agent.agents.speaking.assessment import (drop_unusable_grammar_evidence, grammar_evidence_blocked,
                                 quote_timestamp, resolve_evidence,
                                 validate_assessment)
from ielts_agent.agents.speaking.grading import (MIN_COMPLETION_TOKENS, RATE_LIMIT_MESSAGE, RateLimited, answer_view,
                              capabilities, descriptor_view, grade_session, retry_delay,
                              seconds_from_header, stated_budget)
from ielts_agent.agents.speaking.planning import weakness_profile
from ielts_agent.agents.speaking.server import app
from ielts_agent.agents.speaking.sessions import SessionStore


ANSWER_TEXT = "I learned programming at university because it helps me solve difficult problems with my friends."


def setUpModule():
    global _OFFLINE
    _OFFLINE = patch.dict(os.environ, {"SPEAKING_QUESTION_MODEL": "",
                                       "SPEAKING_GRADER_MODEL": "test-grader-model"})
    _OFFLINE.start()


def tearDownModule():
    _OFFLINE.stop()


def descriptor(criterion, band):
    return {"chunk_id": f"{criterion.lower()}-{band}", "criterion": criterion, "band": band,
            "test_part": "speaking", "version": "test-version", "text": f"{criterion} band {band} descriptor text",
            "source_url": "https://example.invalid/rubric.pdf", "page": 3,
            "source_sha256": "a" * 64, "publisher": "IELTS Partners", "rights": "Copyright retained"}


CORPUS = [descriptor(c, band) for c in ("FC", "LR", "GRA", "PR") for band in range(10)]


class PayloadTests(unittest.TestCase):
    def test_descriptor_view_sends_rubric_text_without_provenance(self):
        view = descriptor_view(descriptor("FC", 6))
        self.assertEqual(set(view), {"chunk_id", "criterion", "band", "text"})

    def test_answer_view_drops_timestamps_vad_and_pronunciation_detail(self):
        answer = {
            "answer_id": "a1", "turn_id": "t1", "transcript_ref": "ref", "transcript": ANSWER_TEXT,
            "flags": ["too_short"], "duration_s": 12.5, "stt_confidence": None,
            "question": {"part": "part2", "text": "Describe a skill.", "points": ["what it is"]},
            "analysis": {
                "words": [{"word": "I", "start": 0.1, "end": 0.3}] * 400,
                "quality": {"status": "needs_review", "timing_valid": True,
                            "issues": [{"code": "long_word_duration", "severity": "warning", "word_indices": [1, 2, 3]}]},
                "metrics": {"word_count": 15, "filler_count": 2, "adjacent_repetitions": ["the"],
                            "timing": {"words_per_minute": 110.2, "pause_count": 3, "pause_seconds": 4.1,
                                       "longest_pause_seconds": 1.9, "pauses": [{"after": "the", "at": 1.0, "length": 1.9}]},
                            "audio_timing": {"status": "ok", "words_per_minute": 104.0,
                                             "speech_segments": [{"start": 0, "end": 12}] * 50},
                            "disfluency_candidates": {"repeated_phrases": [{"text": "I mean"}],
                                                      "repair_candidates": [{"type": "explicit_marker"}, {"type": "restarted_connector"}]}},
                "pronunciation": {"status": "assessed", "segments": [{"words": [{"phonemes": [1, 2, 3]}] * 80}]},
            },
        }
        view = answer_view(answer)
        serialized = json.dumps(view, ensure_ascii=False)
        self.assertIn(ANSWER_TEXT, serialized)
        for leaked in ("phonemes", "speech_segments", "word_indices", "pauses", '"words"'):
            self.assertNotIn(leaked, serialized, leaked)
        self.assertEqual(view["measurements"]["words_per_minute"], 110.2)
        self.assertEqual(view["measurements"]["vad_words_per_minute"], 104.0)
        self.assertEqual(view["measurements"]["repair_candidate_count"], 2)
        self.assertEqual(view["quality"]["issue_codes"], ["long_word_duration"])
        self.assertEqual(view["cue_card_points"], ["what it is"])
        # A full voice answer must stay small enough for a per-minute token limit.
        self.assertLess(len(serialized), 2000)

    def test_answer_view_tolerates_an_answer_without_a_question(self):
        view = answer_view({"answer_id": "a1", "transcript": ANSWER_TEXT, "flags": [], "analysis": {}})
        self.assertIsNone(view["part"])
        self.assertEqual(view["transcript"], ANSWER_TEXT)


class EvidenceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.text = {"mode": "text"}
        self.voice = {"mode": "voice"}
        self.answers = {"a1": {
            "answer_id": "a1", "turn_id": "t1", "transcript_ref": "answer:a1:v1", "transcript": ANSWER_TEXT,
            "duration_s": 9.0, "flags": [],
            "analysis": {"quality": {"timing_valid": True},
                         "words": [{"word": word, "start": index * 0.5, "end": index * 0.5 + 0.4}
                                   for index, word in enumerate(ANSWER_TEXT.split())]}}}

    def result(self, quote, criterion="FC"):
        return {"criteria": [{"criterion": criterion, "status": "assessed", "band": 6, "comment": "c",
                              "descriptor_refs": [criterion.lower() + "-6"],
                              "evidence": [{"answer_id": "a1", "quote": quote}]}]}

    def test_offsets_turn_and_reference_are_filled_by_code(self):
        result = self.result("solve difficult problems")
        self.assertEqual(resolve_evidence(result, self.text, self.answers), [])
        span = result["criteria"][0]["evidence"][0]
        self.assertEqual(ANSWER_TEXT[span["start_char"]:span["end_char"]], "solve difficult problems")
        self.assertEqual(span["turn_id"], "t1")
        self.assertEqual(span["transcript_ref"], "answer:a1:v1")
        self.assertEqual(span["transcript_version"], 1)
        self.assertIsNone(span["t_start_s"])

    def test_a_quote_that_is_not_verbatim_is_reported_not_adjusted(self):
        result = self.result("solve  difficult   problems")
        errors = resolve_evidence(result, self.text, self.answers)
        self.assertTrue(any("verbatim" in error for error in errors), errors)
        self.assertNotIn("start_char", result["criteria"][0]["evidence"][0])

    def test_unknown_answer_and_wordless_quote_are_refused(self):
        result = self.result("solve difficult problems")
        result["criteria"][0]["evidence"][0]["answer_id"] = "missing"
        self.assertTrue(resolve_evidence(result, self.text, self.answers))
        result = self.result("...")
        self.assertTrue(resolve_evidence(result, self.text, self.answers))

    def test_voice_timestamps_come_from_the_word_opening_the_quote(self):
        result = self.result("difficult problems")
        self.assertEqual(resolve_evidence(result, self.voice, self.answers), [])
        span = result["criteria"][0]["evidence"][0]
        index = ANSWER_TEXT.split().index("difficult")
        self.assertEqual(span["t_start_s"], round(index * 0.5, 3))
        self.assertLessEqual(span["t_start_s"], self.answers["a1"]["duration_s"])

    def test_no_timestamp_is_invented_when_timing_is_invalid(self):
        self.answers["a1"]["analysis"]["quality"]["timing_valid"] = False
        self.assertIsNone(quote_timestamp(self.answers["a1"], 10))
        result = self.result("difficult problems")
        resolve_evidence(result, self.voice, self.answers)
        self.assertIsNone(result["criteria"][0]["evidence"][0]["t_start_s"])

    def test_resolved_evidence_then_passes_the_independent_validator(self):
        result = {"criteria": [{"criterion": c, "status": "assessed", "band": 6, "comment": "c",
                                "descriptor_refs": [f"{c.lower()}-6"],
                                "evidence": [{"answer_id": "a1", "quote": "solve difficult problems"}]}
                               for c in ("FC", "LR", "GRA")]
                  + [{"criterion": "PR", "status": "not_assessed", "band": None, "comment": "text",
                      "descriptor_refs": [], "evidence": []}],
                  "flags": [],
                  "corrections": [{"answer_id": "a1", "upgraded_answer": "Better.", "vocabulary": ["word"]}] * 2}
        session = {"mode": "text", "turns": []}
        self.assertEqual(resolve_evidence(result, session, self.answers), [])
        errors = validate_assessment(result, session, self.answers, CORPUS)
        self.assertEqual(errors, ["Corrections must reference two distinct answers"])


class GrammarEvidenceTests(unittest.TestCase):
    """Timing warnings must not block GRA: they leave the words themselves intact."""

    def answer(self, **quality):
        return {"answer_id": "a1", "turn_id": "t1", "transcript_ref": "ref", "transcript": ANSWER_TEXT,
                "flags": [], "duration_s": 9.0, "analysis": {"quality": quality, "words": []}}

    def test_timing_warnings_alone_keep_an_answer_usable_for_grammar(self):
        timing_only = self.answer(status="needs_review", timing_valid=False, text_checks_passed=True,
                                  issues=[{"code": "timestamps_reversed", "severity": "error", "word_indices": []}])
        self.assertFalse(grammar_evidence_blocked(timing_only))
        self.assertTrue(answer_view(timing_only)["usable_for_grammar_evidence"])

    def test_a_failed_transcript_check_blocks_grammar_evidence(self):
        broken = self.answer(status="needs_review", timing_valid=False, text_checks_passed=False,
                             issues=[{"code": "transcript_word_mismatch", "severity": "error", "word_indices": []}])
        self.assertTrue(grammar_evidence_blocked(broken))
        self.assertFalse(answer_view(broken)["usable_for_grammar_evidence"])
        answers = {"a1": broken}
        result = {"criteria": [{"criterion": c, "status": "assessed", "band": 6, "comment": "c",
                                "descriptor_refs": [f"{c.lower()}-6"],
                                "evidence": [{"answer_id": "a1", "quote": "difficult problems"}]}
                               for c in ("FC", "LR", "GRA")]
                  + [{"criterion": "PR", "status": "not_assessed", "band": None, "comment": "t",
                      "descriptor_refs": [], "evidence": []}],
                  "flags": [],
                  "corrections": [{"answer_id": "a1", "upgraded_answer": "Better.", "vocabulary": ["w"]}] * 2}
        session = {"mode": "text", "turns": []}
        resolve_evidence(result, session, answers)
        errors = validate_assessment(result, session, answers, CORPUS)
        self.assertTrue(any(error.startswith("GRA: transcript text failed") for error in errors), errors)
        # Only GRA is refused; the same quote still supports FC and LR.
        self.assertFalse([error for error in errors if error.startswith(("FC:", "LR:"))])

    def test_one_unusable_quote_is_dropped_instead_of_failing_the_attempt(self):
        """A re-grade costs a full extra provider call, which the free token
        budget cannot spare, so a GRA row keeps its usable quotes."""
        good = self.answer(status="ok", timing_valid=True, text_checks_passed=True, issues=[])
        broken = {**self.answer(status="needs_review", timing_valid=False, text_checks_passed=False, issues=[]),
                  "answer_id": "a2", "turn_id": "t2", "transcript_ref": "ref2"}
        answers = {"a1": good, "a2": broken}
        result = {"criteria": [{"criterion": "GRA", "status": "assessed", "band": 6, "comment": "c",
                                "descriptor_refs": ["gra-6"],
                                "evidence": [{"answer_id": "a1", "quote": "difficult problems"},
                                             {"answer_id": "a2", "quote": "difficult problems"}]}]}
        dropped = drop_unusable_grammar_evidence(result, answers)
        self.assertEqual(len(dropped), 1)
        self.assertEqual([e["answer_id"] for e in result["criteria"][0]["evidence"]], ["a1"])

    def test_a_row_with_nothing_citable_is_left_for_the_validator_to_refuse(self):
        broken = self.answer(status="needs_review", timing_valid=False, text_checks_passed=False, issues=[])
        result = {"criteria": [{"criterion": "GRA", "status": "assessed", "band": 6, "comment": "c",
                                "descriptor_refs": ["gra-6"],
                                "evidence": [{"answer_id": "a1", "quote": "difficult problems"}]}]}
        self.assertEqual(drop_unusable_grammar_evidence(result, {"a1": broken}), [])
        self.assertEqual(len(result["criteria"][0]["evidence"]), 1)

    def test_low_confidence_is_still_refused_for_grammar(self):
        flagged = self.answer(status="ok", timing_valid=True, text_checks_passed=True, issues=[])
        flagged["flags"] = ["low_stt_confidence"]
        self.assertFalse(answer_view(flagged)["usable_for_grammar_evidence"])


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.session = {"session_id": "s", "mode": "text", "turns": []}
        self.answers = [{"answer_id": str(i), "turn_id": f"t{i}", "transcript_ref": f"ref{i}",
                         "transcript": ANSWER_TEXT, "transcript_version": 1, "analysis": {},
                         "flags": [], "duration_s": None,
                         "question": {"part": "part1", "text": "Q?"}} for i in range(2)]

    def grade(self, caller):
        with patch("ielts_agent.agents.speaking.grading.capabilities", return_value={"grading_ready": True}), \
             patch("ielts_agent.agents.speaking.grading.load_descriptors", return_value=CORPUS):
            return grade_session(self.session, self.answers, caller)

    def test_header_and_message_wait_hints_are_parsed(self):
        self.assertAlmostEqual(seconds_from_header("690ms"), 0.69)
        self.assertAlmostEqual(seconds_from_header("1m26.4s"), 86.4)
        self.assertIsNone(seconds_from_header(None))
        self.assertAlmostEqual(retry_delay(RuntimeError("Please try again in 19.2s")), 20.2, places=3)
        self.assertEqual(retry_delay(RuntimeError("no hint at all")), 30.0)

    def test_an_oversized_request_is_told_apart_from_a_spent_budget(self):
        spent = RuntimeError("(TPM): Limit 8000, Used 2698, Requested 5582. Please try again in 2.1s.")
        oversized = RuntimeError("Limit 8000, Requested 13375, please reduce your message size")
        self.assertEqual(stated_budget(spent), (8000, 5582))
        self.assertEqual(stated_budget(oversized), (8000, 13375))
        # Only the oversized request is unfixable by waiting.
        self.assertLessEqual(stated_budget(spent)[1], stated_budget(spent)[0])
        self.assertGreater(stated_budget(oversized)[1], stated_budget(oversized)[0])
        self.assertEqual(stated_budget(RuntimeError("no numbers")), (None, None))
        self.assertGreaterEqual(MIN_COMPLETION_TOKENS, 3000)

    def test_a_token_limit_keeps_the_run_retryable_and_scores_absent(self):
        def limited(payload):
            raise RateLimited(fatal=True)

        result = self.grade(limited)
        self.assertTrue(result["retryable"])
        self.assertEqual(result["assessment"]["status"], "provisional")
        self.assertIn(RATE_LIMIT_MESSAGE, result["assessment"]["grading_errors"])
        self.assertIsNone(result["assessment"]["overall_band"])
        for row in result["assessment"]["criteria"]:
            self.assertIsNone(row["band"])

    def test_a_daily_limit_is_reported_as_itself_and_never_waited_out(self):
        """A per-day refusal cannot be fixed by sleeping inside the request, and
        telling the learner to retry 'in a minute' would be wrong."""
        from ielts_agent.agents.speaking.grading import daily_limit

        per_day = RuntimeError("Rate limit reached for model `openai/gpt-oss-120b` in organization `org_x` "
                               "service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198369, "
                               "Requested 5949. Please try again in 31m5.3s.")
        per_minute = RuntimeError("Rate limit reached for model `openai/gpt-oss-120b` on tokens per minute "
                                  "(TPM): Limit 8000, Used 7000, Requested 5949. Please try again in 9.5s.")
        self.assertEqual(daily_limit(per_day), "31m5.3s")
        self.assertIsNone(daily_limit(per_minute))

        message = RateLimited(message="Hết hạn mức ngày cho openai/gpt-oss-120b").message

        def limited(payload):
            raise RateLimited(message=message)

        with patch("ielts_agent.agents.speaking.grading.time.sleep") as sleep:
            result = self.grade(limited)
        self.assertFalse(sleep.called, "a per-day limit must not burn the wait budget")
        self.assertTrue(result["retryable"])
        self.assertEqual(result["assessment"]["grading_errors"], [message])
        self.assertEqual(result["assessment"]["criteria"][0]["comment"], message)

    def test_graders_can_run_on_two_models_for_two_token_budgets(self):
        from ielts_agent.agents.speaking.grading import grader_model

        with patch.dict(os.environ, {"SPEAKING_GRADER_MODEL": "model-a", "SPEAKING_GRADER_MODEL_B": ""}):
            self.assertEqual([grader_model("A"), grader_model("B")], ["model-a", "model-a"])
        with patch.dict(os.environ, {"SPEAKING_GRADER_MODEL": "model-a", "SPEAKING_GRADER_MODEL_B": "model-b"}):
            self.assertEqual([grader_model("A"), grader_model("B")], ["model-a", "model-b"])
            self.assertEqual(capabilities()["grader_model_b"], "model-b")

    def test_each_model_keeps_its_own_token_budget(self):
        from ielts_agent.agents.speaking.grading import _BUDGETS, available_tokens, remember_budget

        _BUDGETS.clear()
        remember_budget("model-a", {"x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "100"})
        self.assertLess(available_tokens("model-a"), 8000)
        # A second model starts with its own, unknown budget rather than inheriting one.
        self.assertIsNone(available_tokens("model-b"))
        _BUDGETS.clear()

    def test_a_schema_violation_is_regraded_instead_of_ending_the_run(self):
        """json_validate_failed means the model mis-generated, not that Groq is
        down, so it must consume a re-grade rather than abandon the session."""
        import httpx
        from groq import BadRequestError
        from ielts_agent.agents.speaking.grading import call_grader

        body = {"error": {"message": "Failed to generate JSON.", "code": "json_validate_failed"}}
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com"), json=body)
        failure = BadRequestError("Failed to generate JSON.", response=response, body=body)
        with patch.dict(os.environ, {"SPEAKING_GRADER_MODEL": "m", "GROQ_API_KEY": "k"}), \
             patch("ielts_agent.agents.speaking.grading.send", side_effect=failure):
            with self.assertRaises(ValueError):
                call_grader({"grader_role": "A"})

    def test_the_reserve_shrinks_to_what_a_model_actually_needs(self):
        """Groq charges prompt + max_completion_tokens per minute, so a model that
        answers in ~1200 tokens must not keep reserving the 4000-token default."""
        from ielts_agent.agents.speaking.grading import _BUDGETS, _OBSERVED, completion_budget

        _BUDGETS.clear(); _OBSERVED.clear()
        _BUDGETS["m"] = {"limit": 8000, "remaining": 8000, "at": 0.0}
        first = completion_budget("m", 5800)
        self.assertGreaterEqual(first, MIN_COMPLETION_TOKENS)
        _OBSERVED["m"] = 1200
        second = completion_budget("m", 5800)
        self.assertLess(second, first)
        self.assertGreaterEqual(second, 1200, "the reserve must still fit a full answer")
        self.assertLess(5800 + second, 8000, "prompt plus reserve has to fit the per-minute limit")
        _BUDGETS.clear(); _OBSERVED.clear()

    def test_the_whole_run_shares_one_wait_budget(self):
        """Pacing and 429 waits draw on the same budget, so a single grading run
        cannot stall for minutes by spending the full budget per grader."""
        from ielts_agent.agents.speaking.grading import RATE_LIMIT_WAIT_BUDGET, _WAITED, hold, wait_budget

        _WAITED["seconds"] = 0.0
        with patch("ielts_agent.agents.speaking.grading.time.sleep") as sleep:
            self.assertEqual(hold(10), 10)
            self.assertEqual(hold(RATE_LIMIT_WAIT_BUDGET), RATE_LIMIT_WAIT_BUDGET - 10)
            self.assertEqual(wait_budget(), 0)
            self.assertEqual(hold(5), 0)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(_WAITED["seconds"], RATE_LIMIT_WAIT_BUDGET)

    def test_waiting_out_a_limit_does_not_consume_a_regrade_attempt(self):
        calls = []
        valid = {"criteria": [{"criterion": c, "status": "assessed", "band": 6, "comment": "c",
                               "descriptor_refs": [f"{c.lower()}-6"],
                               "evidence": [{"answer_id": "0", "quote": "difficult problems"}]}
                              for c in ("FC", "LR", "GRA")]
                 + [{"criterion": "PR", "status": "not_assessed", "band": None, "comment": "t",
                     "descriptor_refs": [], "evidence": []}],
                 "flags": [],
                 "corrections": [{"answer_id": str(i), "upgraded_answer": "Better.", "vocabulary": ["w"]} for i in range(2)]}

        def caller(payload):
            calls.append(payload["grader_role"])
            if len(calls) == 1:
                raise RateLimited(0.5)
            return deepcopy(valid)

        with patch("ielts_agent.agents.speaking.grading.time.sleep") as sleep:
            result = self.grade(caller)
        self.assertTrue(sleep.called)
        self.assertGreater(result["rag"]["rate_limit_wait_seconds"], 0)
        self.assertEqual(result["assessment"]["status"], "provisional")
        self.assertEqual(result["assessment"]["overall_band"], 6)
        self.assertEqual([g["attempts"][-1]["attempt"] for g in result["graders"]], [1, 1])

    def test_a_retryable_failure_is_not_cached_so_grading_can_be_rerun(self):
        with TemporaryDirectory() as folder:
            store = SessionStore(Path(folder) / "exam.sqlite3")
            with patch("ielts_agent.agents.speaking.exam_api.store", store):
                client = TestClient(app)
                data = client.post("/api/exam/sessions", json={"mode": "text", "kind": "practice"}).json()
                while data["session"]["status"] != "finished":
                    session = data["session"]
                    data = client.post(f"/api/exam/sessions/{session['id']}/text", json={
                        "question_id": session["current_question"]["question_id"],
                        "version": session["version"], "request_id": str(session["version"]),
                        "text": ANSWER_TEXT}).json()
                session_id = data["session"]["id"]
                failing = {"assessment": {**data["session"]["assessment"], "status": "provisional"},
                           "graders": [{"id": "g1", "grader_role": "A", "valid": False, "attempts": []}],
                           "retryable": True, "descriptor_chunks": [], "rag": {}}
                with patch("ielts_agent.agents.speaking.exam_api.grade_session", return_value=failing):
                    client.post(f"/api/exam/sessions/{session_id}/assessment")
                with store.connection() as db:
                    self.assertIsNone(db.execute("SELECT content FROM grading WHERE session_id=?",
                                                 (session_id,)).fetchone())


class TeacherReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SessionStore(Path(self.temp.name) / "exam.sqlite3")
        patcher = patch("ielts_agent.agents.speaking.exam_api.store", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.session_id = self.finished_session()

    def finished_session(self):
        data = self.client.post("/api/exam/sessions", json={"mode": "text", "kind": "practice"}).json()
        while data["session"]["status"] != "finished":
            session = data["session"]
            data = self.client.post(f"/api/exam/sessions/{session['id']}/text", json={
                "question_id": session["current_question"]["question_id"], "version": session["version"],
                "request_id": str(session["version"]), "text": ANSWER_TEXT}).json()
        return data["session"]["id"]

    def disagreeing_grading(self, bands_a, bands_b):
        """A cached run where both graders are valid but their bands differ.

        Shaped like grade_session's disagreement path: evidence, rewrites and
        per-grader bands survive, every released band is withheld.
        """
        with self.store.connection() as db:
            state = self.store.read(db, self.session_id)
            answers = self.store.answers(db, self.session_id)
        quote = "difficult problems"
        start_char = ANSWER_TEXT.index(quote)
        span = {"answer_id": answers[0]["answer_id"], "turn_id": answers[0]["turn_id"],
                "transcript_ref": answers[0]["transcript_ref"], "transcript_version": 1,
                "quote": quote, "start_char": start_char, "end_char": start_char + len(quote),
                "t_start_s": None}
        corrections = [{"answer_id": a["answer_id"], "upgraded_answer": "Better.", "vocabulary": ["word"]}
                       for a in answers[:2]]

        def criteria_for(bands):
            return [{"criterion": c, "status": "assessed", "band": bands[c], "comment": f"{c} comment",
                     "descriptor_refs": [f"{c.lower()}-{int(bands[c])}"], "evidence": [dict(span)]}
                    for c in ("FC", "LR", "GRA")] + [
                {"criterion": "PR", "status": "not_assessed", "band": None, "comment": "text",
                 "descriptor_refs": [], "evidence": []}]

        def grader(role, bands):
            return {"id": f"grading-{role}", "run_id": state["assessment"]["run_id"], "grader_role": role,
                    "model": "stub-grader", "prompt_version": "test", "trace_id": None, "valid": True,
                    "retrieved_chunk_ids": ["fc-6"], "retrieval_context": {}, "attempts": [],
                    "result": {"criteria": criteria_for(bands), "flags": [], "corrections": corrections}}

        criteria = [{**row, "band": None,
                     "evidence": [] if row["criterion"] == "PR" else [dict(span), dict(span)],
                     "grader_bands": {"A": bands_a.get(row["criterion"]), "B": bands_b.get(row["criterion"])}}
                    for row in state["assessment"]["criteria"]]
        assessment = {**state["assessment"], "status": "pending_teacher", "corrections": corrections,
                      "criteria": criteria,
                      "grading_errors": ["UC03: grader disagreement ≥1.0; teacher reconciliation required"]}
        grading = {"assessment": assessment, "graders": [grader("A", bands_a), grader("B", bands_b)],
                   "retryable": False, "descriptor_chunks": CORPUS, "rag": {}}
        with self.store.connection() as db:
            db.execute("INSERT INTO grading VALUES (?,?)", (self.session_id, json.dumps(grading, ensure_ascii=False)))
            state["assessment"] = assessment
            self.store.write(db, state)
        return grading

    def review(self, **body):
        return self.client.post(f"/api/exam/sessions/{self.session_id}/teacher-review",
                                json={"teacher_id": "11111111-1111-1111-1111-111111111111", **body})

    def test_review_requires_an_existing_grading_run(self):
        self.assertEqual(self.review(action="approve").status_code, 409)

    def test_approve_releases_the_mean_of_the_two_graders(self):
        self.disagreeing_grading({"FC": 5, "LR": 6, "GRA": 6}, {"FC": 6, "LR": 6, "GRA": 6})
        response = self.review(action="approve", note="Nghe lại audio, đồng \xfd khoảng 5–6.")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["assessment"]["status"], "final")
        self.assertEqual(body["teacher_review"]["bands"], {"FC": 5.5, "LR": 6.0, "GRA": 6.0})
        self.assertAlmostEqual(body["assessment"]["overall_band"], 5.83, places=2)
        self.assertEqual(body["teacher_review"]["decisions"]["FC"]["chosen"], "middle")
        self.assertIsNone(body["teacher_review"]["decisions"]["PR"]["final_band"])

    def test_edit_overrides_the_pair_and_a_bad_band_is_refused(self):
        self.disagreeing_grading({"FC": 5, "LR": 6, "GRA": 6}, {"FC": 7, "LR": 6, "GRA": 6})
        self.assertEqual(self.review(action="edit", bands={"FC": 12}).status_code, 422)
        response = self.review(action="edit", bands={"FC": 6, "LR": 5.5, "GRA": 6})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["teacher_review"]["bands"], {"FC": 6.0, "LR": 5.5, "GRA": 6.0})
        self.assertEqual(self.review(action="approve").status_code, 409)

    def test_reject_withholds_every_score(self):
        self.disagreeing_grading({"FC": 4, "LR": 6, "GRA": 6}, {"FC": 7, "LR": 6, "GRA": 6})
        body = self.review(action="reject", note="Audio kh\xf4ng nghe được.").json()
        self.assertEqual(body["assessment"]["status"], "pending_teacher")
        self.assertIsNone(body["assessment"]["overall_band"])
        export = self.client.get(f"/api/exam/sessions/{self.session_id}/export").json()
        self.assertEqual(export["tables"]["FINAL_SCORE"], [])
        self.assertEqual(len(export["tables"]["TEACHER_REVIEW"]), 1)

    def test_approved_review_exports_teacher_rows_and_final_scores(self):
        self.disagreeing_grading({"FC": 5, "LR": 6, "GRA": 6}, {"FC": 6, "LR": 6, "GRA": 6})
        self.review(action="approve", note="Đ\xe3 đối chiếu dẫn chứng.")
        export = self.client.get(f"/api/exam/sessions/{self.session_id}/export").json()
        tables = export["tables"]
        self.assertEqual(len(tables["TEACHER_REVIEW"]), 1)
        self.assertEqual(tables["TEACHER_REVIEW"][0]["action"], "approve")
        self.assertEqual(len(tables["RECONCILIATION"]), 1)
        self.assertTrue(tables["RECONCILIATION"][0]["escalated"])
        self.assertEqual({row["criterion"] for row in tables["RECON_CRITERION"]}, {"FC", "LR", "GRA", "PR"})
        scores = {row["criterion"]: row for row in tables["FINAL_SCORE"]}
        self.assertEqual(set(scores), {"FC", "LR", "GRA", "overall"})
        for row in scores.values():
            self.assertEqual(row["source"], "teacher")
            self.assertEqual(row["status"], "final")
            self.assertEqual(row["version"], 2)
            self.assertEqual(row["review_id"], tables["TEACHER_REVIEW"][0]["id"])
        self.assertNotIn("PR", scores)

    def test_weakness_profile_waits_for_the_teacher_then_ranks_criteria(self):
        self.disagreeing_grading({"FC": 4, "LR": 6, "GRA": 5}, {"FC": 5, "LR": 6, "GRA": 5})
        pending = self.client.get(f"/api/exam/sessions/{self.session_id}/weakness-profile").json()
        self.assertEqual(pending["status"], "pending_teacher")
        self.assertEqual(pending["criteria"], [])
        self.assertIsNone(pending["write_target"])
        self.review(action="approve")
        profile = self.client.get(f"/api/exam/sessions/{self.session_id}/weakness-profile").json()
        self.assertEqual(profile["status"], "ready")
        self.assertEqual([row["criterion"] for row in profile["criteria"]], ["FC", "GRA", "LR"])
        self.assertEqual(profile["weakest_criteria"], ["FC"])
        self.assertEqual(profile["criteria"][0]["rank"], 1)
        target = profile["criteria"][0]["next_band_descriptor"]
        self.assertEqual(target["band"], 5)
        self.assertEqual(target["chunk_id"], "fc-5")
        self.assertEqual(target["version"], "test-version")
        self.assertEqual(profile["not_assessed"], ["PR"])
        self.assertEqual(len(profile["corrections"]), 2)
        self.assertTrue(profile["criteria"][0]["evidence"][0]["quote"])


class PlanningTests(unittest.TestCase):
    def test_profile_is_unavailable_before_grading_and_names_the_reason(self):
        state = {"session_id": "11111111-1111-1111-1111-111111111111",
                 "learner_id": "22222222-2222-2222-2222-222222222222",
                 "mode": "text", "thread_id": "thread", "assessment": None}
        profile = weakness_profile(state, [])
        self.assertEqual(profile["status"], "unavailable")
        self.assertEqual(profile["reason"], "Phi\xean chưa được chấm.")
        self.assertIsNone(profile["write_target"])

    def test_recurring_flags_are_counted_per_turn(self):
        state = {"session_id": "11111111-1111-1111-1111-111111111111",
                 "learner_id": "22222222-2222-2222-2222-222222222222",
                 "mode": "voice", "thread_id": "thread", "assessment": None}
        answers = [{"answer_id": "a1", "flags": ["too_short", "language_switch"]},
                   {"answer_id": "a2", "flags": ["too_short"]}]
        profile = weakness_profile(state, answers)
        counted = {row["flag"]: row for row in profile["recurring_flags"]}
        self.assertEqual(counted["too_short"]["turn_count"], 2)
        self.assertEqual(counted["too_short"]["turn_numbers"], [1, 2])
        self.assertEqual(counted["language_switch"]["turn_count"], 1)


if __name__ == "__main__":
    unittest.main()
