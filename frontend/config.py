"""Frontend-only configuration; no LLM credentials are read here."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class FrontendSettings:
    backend_url: str = "http://127.0.0.1:8000"
    request_timeout_seconds: int = 30
    analysis_timeout_seconds: int = 300
    max_upload_bytes: int = 5 * 1024 * 1024

    def __post_init__(self) -> None:
        url = urlsplit(self.backend_url)
        _ = url.port  # Reject malformed ports before making requests.
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                or url.password or url.query or url.fragment):
            raise ValueError("Backend URL must be HTTP(S), without credentials, query, or fragment.")
        for name, maximum in (("request_timeout_seconds", 120), ("analysis_timeout_seconds", 600),
                              ("max_upload_bytes", 50 * 1024 * 1024)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}.")

    @classmethod
    def from_environment(cls) -> "FrontendSettings":
        return cls(
            backend_url=os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/"),
            request_timeout_seconds=int(os.environ.get("FRONTEND_REQUEST_TIMEOUT_SECONDS", 30)),
            analysis_timeout_seconds=int(os.environ.get("FRONTEND_ANALYSIS_TIMEOUT_SECONDS", 300)),
            max_upload_bytes=int(os.environ.get("UPLOAD_MAX_BYTES", 5 * 1024 * 1024)),
        )
