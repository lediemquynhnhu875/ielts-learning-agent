"""Environment-only provider credentials and local service configuration."""

from dataclasses import dataclass, field
import os

from dotenv import load_dotenv


def _token_budget(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(raw)


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false)")


@dataclass
class Settings:
    provider: str = "openai"
    generator_model: str | None = None
    solver_provider: str | None = None
    solver_model: str | None = None
    openai_api_key: str = field(default="", repr=False)
    deepseek_api_key: str = field(default="", repr=False)
    database_url: str = field(default="postgresql://ielts:ielts_dev_password@localhost:55432/ielts", repr=False)
    api_token: str = field(default="", repr=False)
    timeout_seconds: float = 120
    # Hạn mức token mỗi lời gọi. Model "suy nghĩ" (ví dụ DeepSeek) cần cao hơn, ví dụ 32768 / 16384.
    generator_max_tokens: int = 8192
    solver_max_tokens: int = 6144
    database_auto_migrate: bool = True
    azure_speech_key: str = field(default="", repr=False)
    azure_speech_region: str = ""
    listening_voices: tuple[str, ...] = ("en-GB-SoniaNeural", "en-GB-RyanNeural")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        return cls(
            provider=os.getenv("PROVIDER", "openai"),
            generator_model=os.getenv("GENERATOR_MODEL") or None,
            solver_provider=os.getenv("SOLVER_PROVIDER") or None,
            solver_model=os.getenv("SOLVER_MODEL") or None,
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            database_url=os.getenv("DATABASE_URL", cls.__dataclass_fields__["database_url"].default),
            api_token=os.getenv("API_TOKEN", ""),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
            generator_max_tokens=_token_budget("GENERATOR_MAX_TOKENS", cls.generator_max_tokens),
            solver_max_tokens=_token_budget("SOLVER_MAX_TOKENS", cls.solver_max_tokens),
            database_auto_migrate=_boolean("DATABASE_AUTO_MIGRATE", cls.database_auto_migrate),
            azure_speech_key=os.getenv("AZURE_SPEECH_KEY", "").strip(),
            azure_speech_region=os.getenv("AZURE_SPEECH_REGION", "").strip(),
            listening_voices=tuple(v.strip() for v in os.getenv("LISTENING_VOICES", "").split(",") if v.strip()) or cls.listening_voices,
        )

    def agent_config(self, role: str = "generator") -> tuple[str, str, str, str]:
        if role not in {"generator", "solver"}:
            raise ValueError("LLM role must be generator or solver")
        provider = self.provider if role != "solver" else self.solver_provider or self.provider
        if provider not in {"openai", "deepseek"}:
            raise ValueError("PROVIDER and SOLVER_PROVIDER must be openai or deepseek")
        default = "gpt-4.1-mini" if provider == "openai" else "deepseek-flash"
        model = (self.solver_model if role == "solver" else self.generator_model) or default
        key = self.openai_api_key if provider == "openai" else self.deepseek_api_key
        base_url = "https://api.openai.com/v1" if provider == "openai" else "https://api.deepseek.com"
        return provider, model, key, base_url
