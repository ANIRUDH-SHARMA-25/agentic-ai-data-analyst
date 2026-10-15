"""Retention and redaction are synthetic-only and bounded, including on failure."""
import json
import pytest
from evaluations.synthetic_diagnostics import bounded_explanation,console_summary,verified_synthetic_payload


def test_bounded_copy_and_secret_redaction():
    key="local-test-secret"
    copied=bounded_explanation("Home was second with 150. "+key+" "+("界"*6000),secrets=(key,))
    assert key not in copied["text"] and copied["redaction_applied"]
    assert copied["truncated"] and len(copied["text"])<=4096
    assert len(copied["text"].encode("utf-8"))<=8192
    assert copied["synthetic_dataset_only"]


def test_current_sample_fingerprint_passes_and_changed_input_fails(monkeypatch):
    assert b"revenue" in verified_synthetic_payload()
    monkeypatch.setattr("pathlib.Path.read_bytes",lambda _:b"private data")
    with pytest.raises(ValueError,match="fingerprint"):
        verified_synthetic_payload()


def test_console_summary_omits_generated_reply_and_excerpts():
    report={"model":"gemini-3.6-flash","generation_attempts":3,"success":False,"cases":[{
        "case_index":1,"generation_attempts":3,"passed":False,"failure_category":"answer_context_or_chart_check_failed",
        "final_explanation_local":{"text":"private reply"},"application_error":"private error",
        "validation_failures":[{"kind":"total","claim_excerpt":"private excerpt","observed":531,"expected":530}],
        "provider_attempts":[{"upstream_http_status":200}]}]}
    summary=console_summary(report)
    assert "private" not in json.dumps(summary)
    assert summary["cases"][0]["validation_failure_kinds"]==["total"]
