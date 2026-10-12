"""LLM configuration is loaded on demand so an API key is optional at startup."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSettings:
    api_key: str = field(default="", repr=False)
    model: str = "gpt-4.1-mini"
    model_timeout_seconds: int = 30
    max_output_tokens: int = 1200
    max_model_calls: int = 8
    max_tool_calls: int = 6

    def __post_init__(self) -> None:
        if not self.model.strip() or len(self.model) > 100:
            raise ValueError("OPENAI_MODEL must be a non-empty model name.")
        bounds = {"model_timeout_seconds": 60, "max_output_tokens": 4000,
                  "max_model_calls": 12, "max_tool_calls": 10}
        for name, maximum in bounds.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}.")

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            model_timeout_seconds=int(os.environ.get("OPENAI_TIMEOUT_SECONDS", 30)),
            max_output_tokens=int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", 1200)),
        )
