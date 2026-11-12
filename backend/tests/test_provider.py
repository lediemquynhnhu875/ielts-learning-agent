"""OpenAI/DeepSeek wire-contract tests with a network-free HTTP transport."""

import json

import pytest

from ielts_agent.core.config import Settings
from ielts_agent.agents.uc04.models import ExerciseDraft
from ielts_agent.bootstrap import build_uc04_agents
from ielts_agent.core.errors import InvalidAgentOutput, ProviderError


def one_question_draft():
    return ExerciseDraft(title="A reserve", text="Workers plant young trees.", questions=[{
        "id": "q1", "kind": "sentence_completion", "prompt": "Workers plant ____.",
        "word_limit": 2, "answer": "ANSWER_KEY_SECRET", "evidence_span": "EVIDENCE_SECRET",
        "explanation": "EXPLANATION_SECRET",
    }])


@pytest.mark.parametrize("provider,token_key", [("openai", "max_completion_tokens"), ("deepseek", "max_tokens")])
def test_both_provider_wires_request_json_and_correct_token_parameter(provider, token_key, harness_factory):
    harness = harness_factory(content={"allowed": True, "reason": "Suitable educational topic"})
    agents = build_uc04_agents(Settings(provider=provider), generator_client=harness.client)
    assert agents.safety.run("Can Gio mangroves").allowed
    sent = harness.requests[0]
    assert sent["url"].endswith("/chat/completions")
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert sent["body"][token_key] > 0
    other_key = "max_tokens" if token_key == "max_completion_tokens" else "max_completion_tokens"
    assert other_key not in sent["body"]
    assert sent["body"]["messages"][0]["role"] == "system"
    assert json.loads(sent["body"]["messages"][1]["content"]) == {"content": "Can Gio mangroves"}


def test_solver_wire_never_receives_generator_key_evidence_or_explanation(harness_factory):
    generator = harness_factory(content={"allowed": True, "reason": "Safe"})
    solver = harness_factory(content={"answers": [{"id": "q1", "answer": "young trees", "evidence_span": "Workers plant young trees.", "reason": "The workers plant these."}]})
    settings = Settings(provider="deepseek", solver_provider="openai", solver_model="independent-model")
    agents = build_uc04_agents(settings, generator_client=generator.client, solver_client=solver.client)
    draft = one_question_draft()
    result = agents.solver.run(draft)
    assert result.answers[0].answer == "young trees"
    assert not generator.requests
    body = solver.requests[0]["body"]
    assert body["model"] == "independent-model"
    assert len(body["messages"]) == 2
    payload = json.loads(body["messages"][1]["content"])
    assert set(payload) == {"text", "questions"}
    assert payload["text"] == draft.text
    assert set(payload["questions"][0]) == {"id", "kind", "prompt", "options", "word_limit", "paragraph_id"}
    wire = json.dumps(payload)
    assert "ANSWER_KEY_SECRET" not in wire
    assert "EVIDENCE_SECRET" not in wire
    assert "EXPLANATION_SECRET" not in wire


@pytest.mark.parametrize("content", ["not JSON", "", None, {"allowed": "false", "reason": "unsafe"}, {"allowed": True, "reason": "safe", "unexpected": "field"}])
def test_malformed_safety_output_fails_closed(content, harness_factory):
    harness = harness_factory(content=content)
    agents = build_uc04_agents(Settings(), generator_client=harness.client)
    with pytest.raises(InvalidAgentOutput):
        agents.safety.run("Metro systems")


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls"])
def test_non_final_or_refused_output_is_never_parsed_as_success(finish, harness_factory):
    harness = harness_factory(content={"allowed": True, "reason": "safe"}, finish_reason=finish)
    agents = build_uc04_agents(Settings(), generator_client=harness.client)
    with pytest.raises(InvalidAgentOutput):
        agents.safety.run("Metro systems")


@pytest.mark.parametrize("status", [401, 429, 500])
def test_upstream_http_failure_is_sanitized_and_not_silently_retried(status, harness_factory):
    harness = harness_factory(status=status)
    agents = build_uc04_agents(Settings(), generator_client=harness.client)
    with pytest.raises(ProviderError) as raised:
        agents.safety.run("Metro systems")
    assert "RAW_UPSTREAM_SECRET" not in str(raised.value)
    assert "offline-test-key" not in str(raised.value)
    assert len(harness.requests) == 1


def test_missing_key_fails_before_any_network_request():
    agents = build_uc04_agents(Settings(openai_api_key=""))
    with pytest.raises(ProviderError, match="Missing OPENAI_API_KEY"):
        agents.safety.run("Metro systems")


def test_provider_configuration_uses_official_endpoints_and_separate_roles():
    settings = Settings(provider="deepseek", solver_provider="openai", openai_api_key="OPENAI_SECRET", deepseek_api_key="DEEPSEEK_SECRET")
    assert settings.agent_config("generator") == ("deepseek", "deepseek-flash", "DEEPSEEK_SECRET", "https://api.deepseek.com")
    assert settings.agent_config("solver") == ("openai", "gpt-4.1-mini", "OPENAI_SECRET", "https://api.openai.com/v1")
    assert "OPENAI_SECRET" not in repr(settings)
    assert "DEEPSEEK_SECRET" not in repr(settings)
    with pytest.raises(ValueError):
        Settings(provider="unsupported").agent_config("generator")
