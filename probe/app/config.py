import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    # Any OpenAI-compatible endpoint that supports tool calling.
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_timeout_seconds: float = _float("PROBE_LLM_TIMEOUT_SECONDS", 300)
    # Where the probe sends its requests, and where a browser can open the JIT trace.
    jit_base_url: str = os.getenv("JIT_BASE_URL", "http://127.0.0.1:8766")
    jit_public_url: str = os.getenv("JIT_PUBLIC_URL", "http://127.0.0.1:8766")
    jit_timeout_seconds: float = _float("PROBE_JIT_TIMEOUT_SECONDS", 300)
    max_steps: int = int(os.getenv("PROBE_MAX_STEPS", "8"))
    # Models the web app offers, weakest first, so runs can be compared across a capability ladder.
    # The default model (llm_model) is always offered.
    extra_models: str = os.getenv("PROBE_MODELS", "")

    @property
    def models(self) -> list[str]:
        listed = [m.strip() for m in self.extra_models.split(",") if m.strip()]
        return listed + [self.llm_model] if self.llm_model and self.llm_model not in listed else listed


settings = Settings()
