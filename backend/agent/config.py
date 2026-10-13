"""LLM configuration is loaded on demand so an API key is optional at startup."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSettings:
    api_key: str = field(default="", repr=False)
    model: str = "gemini-3.8-flash"
    model_timeout_seconds: int = 30
    max_output_tokens: int = 1200
    max_model_calls: int = 8
    max_tool_calls: int = 6
    free_tier_confirmed: bool = False

    def __post_init__(self) -> None:
        if self.model != "gemini-3.8-flash":
            raise ValueError("GOOGLE_MODEL must be gemini-3.8-flash; no model fallback is permitted.")
        if type(self.free_tier_confirmed) is not bool:
            raise ValueError("free_tier_confirmed must be a boolean.")
        bounds = {"model_timeout_seconds": 60, "max_output_tokens": 4000,
                  "max_model_calls": 12, "max_tool_calls": 10}
        for name, maximum in bounds.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}.")

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        confirmation = os.environ.get("GOOGLE_FREE_TIER_CONFIRMED", "false").lower()
        if confirmation not in {"true", "false"}:
            raise ValueError("GOOGLE_FREE_TIER_CONFIRMED must be true or false.")
        return cls(
            free_tier_confirmed=confirmation == "true",
            api_key=os.environ.get("GOOGLE_API_KEY", "").strip(),
            model=os.environ.get("GOOGLE_MODEL", "gemini-3.8-flash"),
            model_timeout_seconds=int(os.environ.get("GOOGLE_TIMEOUT_SECONDS", 30)),
            max_output_tokens=int(os.environ.get("GOOGLE_MAX_OUTPUT_TOKENS", 1200)),
        )
