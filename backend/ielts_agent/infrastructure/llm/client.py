"""Domain-independent JSON transport for OpenAI-compatible providers."""

import json
from typing import Literal, TypeVar

from openai import APIError, OpenAI
from pydantic import BaseModel, ValidationError

from ...core.config import Settings
from ...core.errors import InvalidAgentOutput, ProviderError


T = TypeVar("T", bound=BaseModel)


class JsonLLMClient:
    """Make stateless JSON calls; domain agents own prompts and contracts."""

    def __init__(
        self,
        settings: Settings,
        role: Literal["generator", "solver"] = "generator",
        client=None,
    ):
        if role not in {"generator", "solver"}:
            raise ValueError("LLM role must be generator or solver")
        self.settings = settings
        self.role = role
        self.provider, self.model, self._key, self._base_url = settings.agent_config(role)
        self._client = client
        self._closed = False

    def complete(self, system: str, payload: dict, contract: type[T], budget: int) -> T:
        if self._closed:
            raise ProviderError("LLM client is closed")
        if self._client is None:
            if not self._key:
                raise ProviderError(f"Missing {self.provider.upper()}_API_KEY for {self.role}")
            self._client = OpenAI(
                api_key=self._key,
                base_url=self._base_url,
                timeout=self.settings.timeout_seconds,
                max_retries=0,
            )
        token_arg = {"max_completion_tokens": budget} if self.provider == "openai" else {"max_tokens": budget}
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system + "\nRequired JSON schema:\n" + json.dumps(contract.model_json_schema())},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                **token_arg,
            )
        except APIError as exc:
            raise ProviderError(f"{self.role} provider request failed ({type(exc).__name__})") from exc
        if not response.choices or response.choices[0].finish_reason != "stop":
            raise InvalidAgentOutput(f"{self.role} response incomplete or refused")
        try:
            return contract.model_validate_json(response.choices[0].message.content or "")
        except ValidationError as exc:
            # Raw upstream bodies may contain unsafe content or credentials.
            raise InvalidAgentOutput(f"{self.role} returned invalid {contract.__name__} JSON") from exc

    def close(self) -> None:
        if not self._closed and self._client is not None:
            self._client.close()
        self._closed = True
