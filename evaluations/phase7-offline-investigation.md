# Phase 7 offline Gemini investigation

Historical record: model references and results below describe their original
run. The configured model is now 3.6; see [the migration record](gemini-3.6-migration.md).

Date: 2026-10-14. Model remains gemini-3.8-flash. No live generation or metadata
requests were made during this investigation. No billing, fallback, deployment,
or model/provider changes were made. Historical ignored reports are preserved.

## Findings

The first and second ignored reports each record one generation attempt. Their
HTTP statuses (504 and 502) are the backend's statuses, not saved Google statuses.
The first public message establishes the timeout handling path, but cannot
separate a local deadline from an upstream deadline. The second public message
identifies the generic Google SDK/LangChain provider exception branch. It does
not establish that Google returned HTTP 502 or that quota was exhausted.

Under the historical installed exception mapping, ordinary upstream 429 maps to
backend 429, 401/403/404 to backend 503, and 408/504 to backend 504. Thus ordinary
quota/authentication/model-not-found failures are less consistent with the second
report than an upstream 400/500/503, or a wrapped error without a recoverable code.
Account prerequisites can also cause a 400; this is not proof of invalid syntax.
The original code/status is missing, so none of these possibilities is proven.
The saved model metadata supports name/access visibility and generateContent
capability, but does not establish usable generation access or available quota.
Known backend log files contain no retained traceback/upstream status evidence.

A concrete compatibility concern was found: the factory sent temperature=1.0.
Google now advises removing temperature/top_p/top_k for Gemini 3.6+; currently
these are ignored with deprecation headers, with future 400 rejection documented.
The installed LangChain 4.4.2 fixed-sampling allowlist contains 3.6 Flash and 3.5
Flash Lite, but omits 3.8 Flash. The application now explicitly sets temperature
None, causing omission on the wire. This removes a documented compatibility
risk; it does NOT prove that this parameter caused the historical failure.

The remaining configured values agree with model/API documentation: thinking LOW
(3.8 supports low/medium/high, not minimal), TEXT output, one candidate, output
cap 1200 (below the model limit), Developer API v1beta generateContent endpoint,
and three function declarations. The adapter's reasoning_effort alias maps to
thinking_level. SDK versions are langchain-google-genai 4.4.2 and google-genai
2.30.1, with no broken dependencies found. No SDK incompatibility was reproduced.

Tool-call thought signatures must be retained across turns. The actual agent and
adapter preserve signatures in a mocked round trip. Both historical failures
occurred on the first generation attempt, before any tool response existed;
a missing signature in a later tool-response turn cannot explain those failures.
Offline serialization cannot prove server-side acceptance or account permissions.

## Diagnostic changes and verification

AnalysisError now carries an internal provider_diagnostic with only category,
upstream_http_status (integer or null), and upstream_status (allowlisted symbol
or null). A bounded, cycle-safe cause walk handles nested wrappers. Exception
messages, details, URLs, headers, keys, request bodies, prompts, and response
content are never copied into these diagnostic fields. A local timeout has a
null upstream status, not an invented Google 504. The public HTTP error contract
is unchanged. The live evaluation harness records these safe fields internally,
uses case indices instead of saved prompts, and omits full successful responses.
No real provider error was captured during this offline work.

Twelve new tests use fake credentials and an explicitly sealed httpx.MockTransport.
They exercise actual agent declarations, real SDK wire serialization, thought
signature/tool-response replay, 400 INVALID_ARGUMENT and FAILED_PRECONDITION,
401/403/404/429/500/503/504 mappings, no HTTP retries, redaction, nested causes,
cycles, and timeout origin. Existing CI network guards remain intact.

- Complete suite: 372 passed (original 360 preserved).
- Mocked benchmark: 28/28; SQL 18/18, follow-ups 3/3, rejections 4/4.
- Dependency check: no broken requirements.
- SQL controls, memory controls, iteration limits and billing guards unchanged.

## Historical tool-enabled proposal, superseded and NOT executed

This historical proposal was superseded by the user's plain-text request below.
It has no active approval. The original proposal was one non-streaming request to
the same gemini-3.8-flash Developer API model, using the application's three tool
declarations, a short synthetic schema/question, LOW thinking, TEXT output,
256 output tokens, and a 60-second timeout. No metadata requests, retries,
automatic agent continuation, tool execution, model switch, or paid route.
Keep the project Free with billing disabled. Record only the three safe error
fields, or a success flag if Google accepts the request; do not record response
content. Stop after that single attempt, whatever its result.

A failure with code/status would distinguish request/precondition, quota,
access, and service categories. Some 400 errors may still require a second
separately approved isolation test, because raw error text is deliberately not
retained. A success would show current acceptance, not prove the cause of the
historical failure or complete the four-question real-model evaluation.

## Official sources checked

- [Gemini 3.8 Flash capabilities and thinking levels](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
- [GenerateContent endpoint, tools and generation config](https://ai.google.dev/api/generate-content)
- [Google troubleshooting and sampling deprecation](https://ai.google.dev/gemini-api/docs/troubleshooting)
- [Function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Thinking](https://ai.google.dev/gemini-api/docs/thinking)
- [Thought signatures](https://ai.google.dev/gemini-api/docs/thought-signatures)
- [LangChain Google integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai)

Google's newer error-code/function-calling guides include Interactions API
examples; their wire payloads are not substituted for this application's
GenerateContent payload. The SDK tests and GenerateContent reference check the
endpoint actually used here. The investigation does not migrate API surfaces.


## Subsequent approved plain-text diagnostic

After the offline investigation, the user approved exactly one request without
any tools: the same gemini-3.8-flash model, a synthetic instruction to reply OK,
256 output tokens, at most 60 seconds, and no retries/fallback. Five additional
offline tests validated the runner against a sealed mock HTTP transport before
the live call, including approval gating, no-tools payload, actual upstream
status capture, sanitized reports, and prevention of a repeated run.

The single live request failed with directly observed Google HTTP 503 and
allowlisted status UNAVAILABLE, category service_unavailable. The sanitized
ignored report is `.tmp/gemini-plain-diagnostic.json`. No tool tests followed.
This establishes the current provider failure category; it does not recover
the lost upstream error from the earlier backend 502. A 503 is not a recorded
429 quota restriction, 400 invalid parameter, or 401/403 authentication/access
error. Persistence and exact service-side cause remain unknown.

All live generation and metadata requests are now on hold until fresh explicit
approval. The project remains human-confirmed Free with billing disabled.
Gemini 3.7 Flash is only a conditional future research candidate if 3.8 remains
unavailable, not an approved or verified replacement. No model/configuration
change, fallback, billing, Docker installation, Phase 8, or public deployment.
Remaining test/review/documentation work can run entirely offline; live model
availability and four-question correctness cannot be established by mocks.

Documentation follow-up verification: complete suite 377 passed (original 360
plus 17 offline tests); mocked benchmark 28/28. No provider requests or code/test
changes during the documentation follow-up.
