"""Hạn mức token của generator và solver cấu hình được qua biến môi trường.

Model "suy nghĩ" như DeepSeek dùng hết hạn mức mặc định (8192 / 6144) trước khi trả JSON,
nên mọi lần sinh đều lỗi `generation_exhausted`. Mặc định giữ nguyên để không đổi hành vi cũ.
"""

import pytest

from ielts_agent.agents.uc04.generator import ItemGenerationAgent
from ielts_agent.agents.uc04.models import GenerateRequest
from ielts_agent.agents.uc04.solver import BlindSolverAgent
from ielts_agent.core.config import Settings
from ielts_agent.infrastructure.llm.client import JsonLLMClient

from .test_generation import generation_payload
from .test_solver import solver_draft, solver_output


def test_default_budgets_are_unchanged():
    settings = Settings()
    assert settings.generator_max_tokens == 8192
    assert settings.solver_max_tokens == 6144


def test_budgets_read_from_environment(monkeypatch):
    monkeypatch.setenv("GENERATOR_MAX_TOKENS", "32768")
    monkeypatch.setenv("SOLVER_MAX_TOKENS", "16384")
    settings = Settings.from_env()
    assert settings.generator_max_tokens == 32768
    assert settings.solver_max_tokens == 16384


def test_empty_environment_value_keeps_default(monkeypatch):
    monkeypatch.setenv("GENERATOR_MAX_TOKENS", "")
    monkeypatch.setenv("SOLVER_MAX_TOKENS", "")
    settings = Settings.from_env()
    assert (settings.generator_max_tokens, settings.solver_max_tokens) == (8192, 6144)


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_invalid_budget_is_rejected(monkeypatch, value):
    monkeypatch.setenv("GENERATOR_MAX_TOKENS", value)
    with pytest.raises(ValueError, match="GENERATOR_MAX_TOKENS"):
        Settings.from_env()


def test_generator_sends_configured_budget(harness_factory):
    harness = harness_factory(content=generation_payload("reading"))
    settings = Settings(provider="deepseek", generator_max_tokens=32768)
    agent = ItemGenerationAgent(JsonLLMClient(settings, client=harness.client))
    agent.run(GenerateRequest(skill="reading", topic="Coastal habitats", target_band=6), [])
    assert harness.requests[0]["body"]["max_tokens"] == 32768


def test_solver_sends_configured_budget(harness_factory):
    draft = solver_draft()
    harness = harness_factory(content=solver_output(draft).model_dump())
    settings = Settings(provider="deepseek", solver_max_tokens=16384)
    agent = BlindSolverAgent(JsonLLMClient(settings, "solver", client=harness.client))
    agent.run(draft)
    assert harness.requests[0]["body"]["max_tokens"] == 16384
