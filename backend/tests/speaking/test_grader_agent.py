"""Offline behavioral tests for the examiner's scoped tool loop."""

from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from ielts_agent.agents.speaking.grader_agent import ExaminerLoop, MAX_STEPS
from ielts_agent.agents.speaking.grading import GRADER_SCHEMA, grade_session, send, call_grader


TEXT = "I learned programming with my friends because we wanted to build useful things."
CORPUS = [{"chunk_id": f"{c}-{b}", "criterion": c, "band": b,
           "test_part": "speaking", "version": "test", "text": f"{c} descriptor band {b}"}
          for c in ("FC", "LR", "GRA", "PR") for b in range(10)]
ANSWERS = [{"answer_id": str(i), "turn_id": f"t{i}", "transcript_ref": f"ref{i}",
            "transcript": TEXT, "analysis": {}, "flags": [], "duration_s": None,
            "question": {"part": "part1", "text": "What did you learn?"}} for i in range(2)]


def tool(name, criteria=None, ids=None):
    return {"name": name, "arguments": {"criteria": criteria or [], "answer_ids": ids or []}}


def tools(*calls):
    return {"action": "tools", "tool_calls": list(calls), "assessment": None}


def final(bad_quote=False):
    return {"action": "final", "tool_calls": [], "assessment": {
        "criteria": [{"criterion": c, "status": "assessed", "band": 6,
                      "comment": "Supported by the supplied evidence.", "descriptor_refs": [f"{c}-6"],
                      "evidence": [{"answer_id": "0", "quote": "invented quote" if bad_quote else "I learned programming"}]}
                     for c in ("FC", "LR", "GRA")] + [
                         {"criterion": "PR", "status": "not_assessed", "band": None,
                          "comment": "No calibrated pronunciation score.", "descriptor_refs": [], "evidence": []}],
        "flags": [], "corrections": [{"answer_id": str(i), "upgraded_answer": "I learned to program with friends.",
                                       "vocabulary": ["program"]} for i in range(2)],
    }}


def scripted(request):
    if not request["answers"]:
        return tools(tool("get_transcript_evidence", ids=[a["answer_id"] for a in request["answer_catalog"]]),
                     tool("retrieve_descriptors", criteria=["FC", "LR", "GRA"]))
    return final()


class ExaminerAgentTests(unittest.TestCase):
    def test_final_stage_accepts_the_original_assessment_schema_after_tools(self):
        def caller(request):
            if request.get("_agent_final"):
                return final()["assessment"]
            return scripted(request)
        result = self.grade(caller)
        self.assertEqual(result["assessment"]["overall_band"], 6)
        self.assertTrue(all(g["valid"] for g in result["graders"]))

    def test_conservative_token_estimate_does_not_reject_a_provider_accepted_request(self):
        accepted = {"action": "tools", "tool_calls": [], "assessment": None}
        response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5000, completion_tokens=100),
                                   choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(accepted)))])
        raw = SimpleNamespace(headers={}, parse=lambda: response)
        with patch.dict(os.environ, {"SPEAKING_GRADER_MODEL": "qwen/test"}), \
             patch.dict("ielts_agent.agents.speaking.grading._BUDGETS", {"qwen/test": {"limit": 8000}}), \
             patch("ielts_agent.agents.speaking.grading.completion_budget", return_value=1200), \
             patch("ielts_agent.agents.speaking.grading.pace") as pace, \
             patch("ielts_agent.agents.speaking.grading.remember_budget"), \
             patch("ielts_agent.agents.speaking.grading.send", return_value=raw) as transport:
            result = call_grader({"_agent_step": True, "padding": "x" * 30000})
        self.assertEqual(result, accepted)
        transport.assert_called_once()
        self.assertEqual(pace.call_args.args[1], 8000)

    def grade(self, caller=None):
        with patch.dict(os.environ, {"SPEAKING_GRADER_MODEL": "test-grader", "SPEAKING_GRADER_MODEL_B": "test-grader-b"}), \
             patch("ielts_agent.agents.speaking.grading.capabilities", return_value={"grading_ready": True}), \
             patch("ielts_agent.agents.speaking.grading.load_descriptors", return_value=CORPUS):
            return grade_session({"session_id": "s", "mode": "text", "turns": []},
                                 deepcopy(ANSWERS), agent_caller=caller)

    def test_default_production_path_uses_two_independent_tool_loops(self):
        requests = []
        def caller(request):
            requests.append(deepcopy(request))
            return scripted(request)
        with patch("ielts_agent.agents.speaking.grading.call_grader", side_effect=caller):
            result = self.grade()
        self.assertEqual(result["assessment"]["overall_band"], 6)
        self.assertEqual([r["grader_role"] for r in requests], ["A", "A", "B", "B"])
        for request in (requests[0], requests[2]):
            self.assertEqual(request["answers"], [])
            self.assertEqual(request["descriptor_context"], {})
            self.assertNotIn("assessment", request)
            self.assertNotIn("graders", request)
        for grader in result["graders"]:
            trace = grader["attempts"][0]["agent_trace"]
            self.assertEqual(sum(e["event"] == "tool" for e in trace), 2)
            self.assertTrue(any(e["event"] == "skill" for e in trace))
            self.assertNotIn(TEXT, json.dumps(trace))
            self.assertEqual(len(grader["retrieved_chunk_ids"]), 30)

    def test_foreign_answer_is_denied_and_model_can_recover(self):
        observations = []
        def caller(request):
            if request["step"] == 1:
                return tools(tool("get_transcript_evidence", ids=["another-learner-answer"]))
            observations.extend(request["tool_observations"])
            return scripted(request)
        result = self.grade(caller)
        self.assertEqual(result["assessment"]["overall_band"], 6)
        self.assertTrue(any(o.get("ok") is False for o in observations))

    def test_premature_final_cannot_skip_tools_and_is_bounded(self):
        calls = []
        def caller(request):
            calls.append(request)
            return final()
        result = self.grade(caller)
        self.assertIsNone(result["assessment"]["overall_band"])
        self.assertEqual(result["assessment"]["status"], "pending_teacher")
        self.assertEqual(len(calls), MAX_STEPS * 3 * 2)
        self.assertTrue(all(not g["valid"] for g in result["graders"]))

    def test_repeated_tools_stop_without_fabricating_scores(self):
        calls = []
        def caller(request):
            calls.append(request)
            return tools(tool("retrieve_descriptors", criteria=["FC"]))
        result = self.grade(caller)
        self.assertEqual(len(calls), MAX_STEPS * 3 * 2)
        self.assertIsNone(result["assessment"]["overall_band"])

    def test_final_evidence_validator_still_repairs_invalid_quotes(self):
        requests = []
        def caller(request):
            requests.append(deepcopy(request))
            if request["answers"]:
                return final(bad_quote=not bool(request["validation_errors"]))
            return scripted(request)
        result = self.grade(caller)
        self.assertEqual(result["assessment"]["overall_band"], 6)
        self.assertEqual([len(g["attempts"]) for g in result["graders"]], [2, 2])
        self.assertTrue(any(r["validation_errors"] for r in requests))

    def test_provider_outage_is_retryable_and_logged_without_provider_body(self):
        def caller(request):
            raise RuntimeError("sensitive provider body")
        result = self.grade(caller)
        self.assertTrue(result["retryable"])
        self.assertIsNone(result["assessment"]["overall_band"])
        trace = result["graders"][0]["attempts"][0]["agent_trace"]
        self.assertEqual(trace[-1]["status"], "failed")
        self.assertNotIn("sensitive provider body", json.dumps(result))

    def test_only_scoped_read_tools_and_exact_argument_contract_are_allowed(self):
        loop = ExaminerLoop([], {"FC": []}, [])
        for call in (tool("memory_write"), tool("retrieve_descriptors", criteria=["PR"]),
                     {"name": "get_transcript_evidence", "arguments": {"criteria": [], "answer_ids": [], "learner_id": "foreign"}}):
            with self.assertRaises(ValueError):
                loop.tool(call)

    def test_unread_descriptor_cannot_be_smuggled_into_final_assessment(self):
        def caller(request):
            if request["answers"]:
                result = final()
                result["assessment"]["criteria"][0]["descriptor_refs"] = ["PR-6"]
                return result
            return scripted(request)
        result = self.grade(caller)
        self.assertIsNone(result["assessment"]["overall_band"])
        self.assertTrue(all(not g["valid"] for g in result["graders"]))

    def test_live_transport_requests_action_envelope_and_skill(self):
        with patch("ielts_agent.agents.speaking.grading.Groq") as groq:
            send("test", json.dumps({"_agent_step": True}), 3000, None)
            kwargs = groq.return_value.__enter__.return_value.chat.completions.with_raw_response.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"]["json_schema"]["name"], "speaking_examiner_action")
        self.assertIn("speaking-assessment", kwargs["messages"][0]["content"])
        self.assertIn("get_transcript_evidence", kwargs["messages"][0]["content"])
        # The existing direct-result seam still uses the original response schema.
        with patch("ielts_agent.agents.speaking.grading.Groq") as groq:
            send("test", json.dumps({"grader_role": "A"}), 3000, None)
            kwargs = groq.return_value.__enter__.return_value.chat.completions.with_raw_response.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"]["json_schema"], GRADER_SCHEMA)
        with patch("ielts_agent.agents.speaking.grading.Groq") as groq:
            send("test", json.dumps({"_agent_step": True, "_agent_final": True}), 3000, None)
            kwargs = groq.return_value.__enter__.return_value.chat.completions.with_raw_response.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"]["json_schema"], GRADER_SCHEMA)


if __name__ == "__main__":
    unittest.main()
