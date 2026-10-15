"""Local-only, bounded diagnostics restricted to the pinned synthetic retail CSV."""
import hashlib
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SAMPLE_SHA256="0f6caaddff745a56e1ad77d43b7c0ace879e611948d42cbc74f91aae4a2fd58a"
MAX_ANSWER_CHARACTERS=4096
MAX_ANSWER_BYTES=8192


def verified_synthetic_payload():
    payload=(ROOT/"data/sample/retail_sales.csv").read_bytes()
    if hashlib.sha256(payload.replace(b"\r\n",b"\n")).hexdigest()!=SAMPLE_SHA256:
        raise ValueError("The synthetic CSV fingerprint changed; diagnostic capture is prohibited.")
    return payload


def redact(text, secrets=()):
    for secret in secrets:
        if secret:
            text=text.replace(secret,"[REDACTED]")
    text=re.sub(r"AIza[0-9A-Za-z_-]{30,}|(?:gh[pousr]_[A-Za-z0-9]{20,})|sk-(?:proj-)?[A-Za-z0-9_-]{20,}","[REDACTED]",text)
    text=re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*)([^\s,;]+)",r"\1[REDACTED]",text)
    return text


def bounded_explanation(text, secrets=()):
    safe=redact(text,secrets)
    bounded=safe[:MAX_ANSWER_CHARACTERS].encode("utf-8")[:MAX_ANSWER_BYTES].decode("utf-8",errors="ignore")
    return {"synthetic_dataset_only":True,"text":bounded,"truncated":bounded!=safe,
            "original_characters":len(text),"retained_characters":len(bounded),
            "redaction_applied":safe!=text}


def console_summary(report):
    """No generated explanation, excerpts, prompts, SQL or raw errors on stdout."""
    return {"model":report["model"],"generation_attempts":report["generation_attempts"],
            "success":report["success"],"cases":[{
                "case_index":c["case_index"],"generation_attempts":c["generation_attempts"],
                "passed":c["passed"],"failure_category":c.get("failure_category"),
                "validation_failure_kinds":[f["kind"] for f in c.get("validation_failures",[])],
                "upstream_http_statuses":[a["upstream_http_status"] for a in c["provider_attempts"]],
            } for c in report["cases"]]}
