from pathlib import Path

import pytest

from backend.data.csv_processing import load_csv


@pytest.fixture
def retail_frame():
    sample = Path(__file__).resolve().parents[1] / "data" / "sample" / "retail_sales.csv"
    return load_csv(sample)


@pytest.fixture(autouse=True)
def forbid_live_openai(monkeypatch):
    """Accidental real provider invocations fail before any network request."""
    from langchain_openai import ChatOpenAI

    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TIMEOUT_SECONDS", "OPENAI_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    def forbidden(*args, **kwargs):
        raise AssertionError("Live OpenAI calls are forbidden in automated tests.")

    async def async_forbidden(*args, **kwargs):
        raise AssertionError("Live OpenAI calls are forbidden in automated tests.")

    monkeypatch.setattr(ChatOpenAI, "_generate", forbidden)
    monkeypatch.setattr(ChatOpenAI, "_agenerate", async_forbidden)
