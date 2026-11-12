"""UC-04 item-generation agent and its required versioned skill."""

import hashlib
from pathlib import Path

from ...infrastructure.llm.client import JsonLLMClient
from .models import ExerciseDraft, GenerateRequest


PROMPT_VERSION = "reading-item-generation.v1"


class ItemGenerationAgent:
    def __init__(self, client: JsonLLMClient):
        self.client = client
        self._skill = (
            Path(__file__).parent / "skills" / "reading-item-generation" / "SKILL.md"
        ).read_text(encoding="utf-8")

    @property
    def metadata(self) -> dict:
        return {
            "provider": self.client.provider,
            "model": self.client.model,
            "prompt_version": PROMPT_VERSION,
            "skill_hash": hashlib.sha256(self._skill.encode()).hexdigest(),
        }

    def run(self, request: GenerateRequest, feedback: list[dict]) -> ExerciseDraft:
        return self.client.complete(
            self._skill,
            {"request": request.model_dump(), "previous_validation_feedback": feedback},
            ExerciseDraft,
            self.client.settings.generator_max_tokens,
        )
