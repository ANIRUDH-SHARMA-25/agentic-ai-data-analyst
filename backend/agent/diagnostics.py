"""Strictly allowlisted provider diagnostics; never serialize exception text/details."""

import httpx
from google.genai.errors import APIError
from langchain_core.exceptions import (
    ModelTimeoutError, ModelRateLimitError, ModelAuthenticationError,
    ModelPermissionDeniedError, ModelNotFoundError,
)

STATUSES = frozenset({
    "INVALID_ARGUMENT", "FAILED_PRECONDITION", "UNAUTHENTICATED",
    "PERMISSION_DENIED", "NOT_FOUND", "RESOURCE_EXHAUSTED", "INTERNAL",
    "UNAVAILABLE", "DEADLINE_EXCEEDED", "UNKNOWN", "OUT_OF_RANGE",
    "CANCELLED", "UNIMPLEMENTED",
})
CATEGORIES = {400: "invalid_request_or_precondition", 401: "authentication",
              402: "payment_required", 403: "access_denied", 404: "model_or_resource_not_found",
              408: "timeout", 429: "quota_or_rate_limit", 500: "service_error",
              502: "service_error", 503: "service_unavailable", 504: "timeout"}


def provider_diagnostic(error: BaseException) -> dict:
    """Read only typed SDK codes and allowlisted statuses through bounded causes.

    No message parsing, response body copying, URLs, headers, exception repr,
    prompt content, or request data. A client timeout has no upstream HTTP code.
    """
    code = status = None
    category = "unknown"
    seen = set()
    current = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, APIError):
            candidate = current.code
            if code is None and type(candidate) is int and 100 <= candidate <= 599:
                code = candidate
            candidate_status = current.status
            if type(candidate_status) is str and candidate_status in STATUSES:
                status = candidate_status
        if isinstance(current, (ModelTimeoutError, httpx.TimeoutException, TimeoutError)):
            category = "timeout"
        elif isinstance(current, ModelRateLimitError):
            category = "quota_or_rate_limit"
        elif isinstance(current, ModelAuthenticationError):
            category = "authentication"
        elif isinstance(current, ModelPermissionDeniedError):
            category = "access_denied"
        elif isinstance(current, ModelNotFoundError):
            category = "model_or_resource_not_found"
        elif isinstance(current, httpx.TransportError):
            category = "connection"
        current = current.__cause__
    if code is not None:
        category = CATEGORIES.get(code, "unknown_http_error")
    if code == 400 and status == "FAILED_PRECONDITION":
        category = "failed_precondition"
    return {"category": category, "upstream_http_status": code, "upstream_status": status}
