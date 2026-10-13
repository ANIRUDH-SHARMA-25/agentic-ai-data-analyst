from pathlib import Path

import pytest

from backend.data.csv_processing import load_csv


@pytest.fixture
def retail_frame():
    sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "retail_sales.csv"
    return load_csv(sample)


@pytest.fixture(autouse=True)
def forbid_live_gemini(monkeypatch):
    """Accidental real provider invocations fail before any network request."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    for name in ("GOOGLE_API_KEY", "GOOGLE_MODEL", "GOOGLE_TIMEOUT_SECONDS", "GOOGLE_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    for name in ("GEMINI_API_KEY", "GOOGLE_FREE_TIER_CONFIRMED", "OPENAI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE", "GOOGLE_CLOUD_PROJECT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    def forbidden(*args, **kwargs):
        raise AssertionError("Live Gemini calls are forbidden in automated tests.")

    async def async_forbidden(*args, **kwargs):
        raise AssertionError("Live Gemini calls are forbidden in automated tests.")

    monkeypatch.setattr(ChatGoogleGenerativeAI, "_generate", forbidden)
    monkeypatch.setattr(ChatGoogleGenerativeAI, "_agenerate", async_forbidden)
