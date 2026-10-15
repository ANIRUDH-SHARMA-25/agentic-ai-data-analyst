"""Explicitly approved, one-request plain-text diagnostic; never used by CI live."""
import argparse
import json
import logging
import warnings
from dataclasses import replace
from pathlib import Path

from langchain_core.messages import HumanMessage
from langsmith import tracing_context

from backend.agent.analyst import create_gemini_model
from backend.agent.config import AgentSettings
from backend.agent.diagnostics import provider_diagnostic

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".tmp/gemini-plain-diagnostic.json"


FINISH_REASONS = frozenset({"STOP", "MAX_TOKENS", "SAFETY", "RECITATION",
                            "OTHER", "MALFORMED_FUNCTION_CALL", "BLOCKLIST",
                            "PROHIBITED_CONTENT", "SPII"})


def summarize_reply(reply):
    """Keep response characteristics, never text, thoughts or raw metadata."""
    content = reply.content
    pieces = []
    unsupported = False
    if isinstance(content, str):
        pieces.append(content)
        structure = "string"
    elif isinstance(content, list):
        structure = "list"
        for block in content:
            if isinstance(block, str):
                pieces.append(block)
            elif isinstance(block, dict) and (block.get("thought") or block.get("type") in {"thinking", "reasoning"}):
                continue
            elif isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                pieces.append(block["text"])
            else:
                unsupported = True
    else:
        structure, unsupported = "unsupported", True
    text = "".join(pieces).strip()
    metadata = getattr(reply, "response_metadata", None) or {}
    candidate = metadata.get("finish_reason") if isinstance(metadata, dict) else None
    finish = candidate if type(candidate) is str and candidate in FINISH_REASONS else None
    exact = text == "OK"
    # Formatting tolerance is diagnostic only, never replaces the strict check.
    relaxed = text.strip('`*" ' + chr(39)).casefold().rstrip('.!') == "ok"
    if finish == "MAX_TOKENS":
        category = "output_truncated"
    elif finish in FINISH_REASONS - {"STOP", "MAX_TOKENS"}:
        category = "generation_not_completed"
    elif unsupported:
        category = "unsupported_content"
    elif not text:
        category = "empty_text"
    elif exact:
        category = "success"
    elif relaxed:
        category = "expected_text_format_variation"
    else:
        category = "unexpected_text"
    usage = getattr(reply, "usage_metadata", None) or {}
    def count(value):
        return value if type(value) is int and 0 <= value <= 1_000_000 else None
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("output_token_details", {})
    details = details if isinstance(details, dict) else {}
    return {"category": category, "content_structure": structure,
            "has_visible_text": bool(text), "visible_text_characters": len(text),
            "unsupported_content_present": unsupported, "finish_reason": finish,
            "output_truncated": finish == "MAX_TOKENS", "reply_was_ok": exact,
            "reply_matches_ok_relaxed": relaxed,
            "output_tokens": count(usage.get("output_tokens")),
            "reasoning_tokens": count(details.get("reasoning"))}


def run_plain(*, approved=False, output=OUTPUT, model_factory=create_gemini_model):
    if not approved:
        raise ValueError("Separate human approval for exactly one request is required.")
    if output.exists():
        raise ValueError("Diagnostic report already exists; no additional request permitted.")
    settings = replace(AgentSettings.from_environment(), model_timeout_seconds=60,
                       max_output_tokens=256, max_model_calls=1)
    model = model_factory(settings)
    messages = [HumanMessage(content='Reply with OK.')]
    request = model._prepare_request(messages)
    config = request["config"]
    if (config.tools or config.tool_config or config.system_instruction
            or config.http_options.timeout != 60000
            or config.http_options.retry_options.attempts != 0
            or config.max_output_tokens != 256
            or request["model"] != "gemini-3.6-flash"):
        raise ValueError("Request limits or plain-text constraints failed; no request sent.")
    report = {"model": settings.model, "kind": "plain_text_no_tools",
              "generation_attempts": 0, "maximum_output_tokens": 256,
              "timeout_seconds": 60, "retries": 0,
              "free_tier": "human-confirmed; billing disabled",
              "success": False, "reply_was_ok": False,
              "category": "not_started", "upstream_http_status": None,
              "upstream_status": None}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    def before_request(http_request):
        if (report["generation_attempts"] != 0 or http_request.method != "POST"
                or http_request.url.host != "generativelanguage.googleapis.com"
                or http_request.url.path != "/v1beta/models/gemini-3.6-flash:generateContent"):
            raise RuntimeError("Additional or unexpected HTTP request blocked.")
        report["generation_attempts"] = 1
        report["category"] = "in_progress"
        save()
    def after_response(response):
        report["upstream_http_status"] = response.status_code
    client = model.client._api_client._httpx_client
    # This process has exactly one model client. Replace hooks to prevent logging
    # request/response data; the first hook refuses any second HTTP request.
    client.event_hooks = {"request": [before_request], "response": [after_response]}
    save()
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with warnings.catch_warnings(), tracing_context(enabled=False):
            warnings.simplefilter("ignore")
            reply = model.invoke(messages)
        report.update(summarize_reply(reply))
        report["provider_request_succeeded"] = report["upstream_http_status"] == 200
        report["success"] = report["category"] == "success" and report["provider_request_succeeded"]
    except Exception as exc:
        diagnostic = provider_diagnostic(exc)
        if diagnostic["upstream_http_status"] is None:
            diagnostic["upstream_http_status"] = report["upstream_http_status"]
        report.update(diagnostic)
    finally:
        logging.disable(previous_logging)
        save()
        model.client.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-single-plain-free-request", action="store_true")
    args = parser.parse_args()
    try:
        report = run_plain(approved=args.approve_single_plain_free_request)
    except Exception:
        print("Diagnostic did not complete; no exception details logged.")
        raise SystemExit(1)
    print(json.dumps(report))
    raise SystemExit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
