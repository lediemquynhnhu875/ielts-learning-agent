"""Generation contracts and provider failures without other UC-04 agents."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ielts_agent.agents.uc04 import generator as generator_module
from ielts_agent.agents.uc04.generator import ItemGenerationAgent
from ielts_agent.agents.uc04.models import ExerciseDraft, GenerateRequest
from ielts_agent.core.config import Settings
from ielts_agent.core.errors import InvalidAgentOutput, ProviderError
from ielts_agent.infrastructure.llm.client import JsonLLMClient


def generation_payload(skill="reading"):
    evidence = "Workers plant young trees along the river bank."
    count = 650 if skill == "reading" else 500
    text = evidence + " " + " ".join(["habitat"] * (count - len(evidence.split())))
    questions = []
    for index in range(10):
        kind = index % 3
        questions.append({
            "id": f"q{index + 1}",
            "kind": ["true_false_not_given", "multiple_choice", "sentence_completion"][kind],
            "prompt": ["Workers plant trees.", "What do workers plant?",
                       "Workers plant ____. Write NO MORE THAN TWO WORDS."][kind],
            "options": {"A": "Young trees", "B": "Flowers", "C": "Rice"} if kind == 1 else {},
            "word_limit": 2 if kind == 2 else None,
            "paragraph_id": None,
            "answer": ["TRUE", "A", "young trees"][kind],
            "evidence_span": evidence,
            "explanation": "The passage explicitly says that workers plant young trees.",
        })
    return {"title": "Coastal habitats", "text": text, "questions": questions}


@pytest.mark.parametrize("provider,token_key", [
    ("openai", "max_completion_tokens"), ("deepseek", "max_tokens"),
])
@pytest.mark.parametrize("skill", ["reading", "listening"])
def test_generation_parses_both_skills_and_provider_wires(provider, token_key, skill, harness_factory):
    payload = generation_payload(skill)
    harness = harness_factory(content=payload)
    runtime = JsonLLMClient(Settings(provider=provider, generator_model="configured-model"), client=harness.client)
    agent = ItemGenerationAgent(runtime)
    request = GenerateRequest(skill=skill, topic="Coastal habitats", target_band=6)

    result = agent.run(request, [])

    assert result.model_dump() == payload
    assert isinstance(result, ExerciseDraft)
    body = harness.requests[0]["body"]
    assert harness.requests[0]["url"].endswith("/chat/completions")
    assert body["model"] == "configured-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body[token_key] == 8192
    other_key = "max_tokens" if token_key == "max_completion_tokens" else "max_completion_tokens"
    assert other_key not in body
    assert json.loads(body["messages"][1]["content"])["request"] == request.model_dump()
    prompt = body["messages"][0]["content"]
    assert "600–900" in prompt and "400–700" in prompt and "8–13" in prompt
    assert "at least three distinct types" in prompt
    assert "Required JSON schema:" in prompt
    assert len(result.questions) == 10
    assert len({question.kind for question in result.questions}) == 3


def test_generation_feedback_is_stateless_and_metadata_identifies_packaged_skill(harness_factory):
    harness = harness_factory(content=generation_payload())
    agent = ItemGenerationAgent(JsonLLMClient(
        Settings(provider="deepseek", generator_model="custom-model"), client=harness.client,
    ))
    request = GenerateRequest(skill="reading", topic="Coastal habitats", target_band=6)
    feedback = [{"reason": "previous passage too short"}]
    agent.run(request, feedback)
    agent.run(request, [])

    first, second = [item["body"] for item in harness.requests]
    assert json.loads(first["messages"][1]["content"])["previous_validation_feedback"] == feedback
    assert json.loads(second["messages"][1]["content"])["previous_validation_feedback"] == []
    assert len(first["messages"]) == len(second["messages"]) == 2
    skill_path = Path(generator_module.__file__).parent / "skills/reading-item-generation/SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    assert agent.metadata == {
        "provider": "deepseek", "model": "custom-model",
        "prompt_version": "reading-item-generation.v1",
        "skill_hash": hashlib.sha256(skill.encode()).hexdigest(),
    }
    assert first["messages"][0]["content"].startswith(skill)


@pytest.mark.parametrize("content", [
    "not JSON", "", None, {},
    {"title": "A title", "text": "A passage", "questions": [{"id": "q1"}]},
    {"title": "A title", "text": "A passage", "questions": [], "unexpected": True},
])
def test_generation_rejects_invalid_json_and_output_schema(content, harness_factory):
    harness = harness_factory(content=content)
    agent = ItemGenerationAgent(JsonLLMClient(Settings(), client=harness.client))
    request = GenerateRequest(skill="reading", topic="Coastal habitats", target_band=6)
    with pytest.raises(InvalidAgentOutput, match="invalid ExerciseDraft JSON"):
        agent.run(request, [])


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls"])
def test_generation_rejects_incomplete_or_refused_response(finish, harness_factory):
    harness = harness_factory(content=generation_payload(), finish_reason=finish)
    agent = ItemGenerationAgent(JsonLLMClient(Settings(), client=harness.client))
    with pytest.raises(InvalidAgentOutput):
        agent.run(GenerateRequest(skill="reading", topic="Coastal habitats", target_band=6), [])


@pytest.mark.parametrize("status", [401, 429, 500])
def test_generation_sanitizes_provider_errors_without_retries(status, harness_factory, caplog):
    harness = harness_factory(status=status)
    agent = ItemGenerationAgent(JsonLLMClient(Settings(), client=harness.client))
    with pytest.raises(ProviderError) as raised:
        agent.run(GenerateRequest(skill="reading", topic="Coastal habitats", target_band=6), [])
    assert len(harness.requests) == 1
    for secret in ["RAW_UPSTREAM_SECRET", "offline-test-key"]:
        assert secret not in str(raised.value)
        assert secret not in caplog.text


def test_missing_key_fails_before_network_request():
    agent = ItemGenerationAgent(JsonLLMClient(Settings(openai_api_key="")))
    with pytest.raises(ProviderError, match="Missing OPENAI_API_KEY"):
        agent.run(GenerateRequest(skill="reading", topic="Coastal habitats", target_band=6), [])


@pytest.mark.parametrize("updates", [
    {"skill": "speaking"}, {"topic": "   "}, {"target_band": 6.2},
    {"target_band": 0}, {"target_band": 9.5},
    {"question_count": 7}, {"question_count": 14},
    {"completion_word_limit": 0}, {"completion_word_limit": 6},
    {"unexpected": True},
])
def test_input_schema_rejects_invalid_requests(updates):
    values = {"skill": "reading", "topic": "Coastal habitats", "target_band": 6, **updates}
    with pytest.raises(ValidationError):
        GenerateRequest(**values)


@pytest.mark.parametrize("provider,expected_url,key_field", [
    ("openai", "https://api.openai.com/v1", "openai_api_key"),
    ("deepseek", "https://api.deepseek.com", "deepseek_api_key"),
])
def test_provider_config_uses_environment_and_hides_credentials(provider, expected_url, key_field, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROVIDER", provider)
    monkeypatch.setenv("GENERATOR_MODEL", "chosen-model")
    monkeypatch.setenv(key_field.upper(), "CONFIG_TEST_SECRET")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "42")
    settings = Settings.from_env()
    assert settings.agent_config("generator") == (provider, "chosen-model", "CONFIG_TEST_SECRET", expected_url)
    assert settings.timeout_seconds == 42
    assert "CONFIG_TEST_SECRET" not in repr(settings)
    with pytest.raises(ValueError):
        Settings(provider="unsupported").agent_config("generator")
