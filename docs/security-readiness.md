# Security readiness review — Phase 8

Classification: **local-development-only, trusted single user, synthetic data**.
This is a focused source/configuration review and offline regression check,
not a penetration test, vulnerability certification or public-hosting approval.
Current model references reflect the later user-approved 3.6 migration; the
original Phase 8 audit did not change models.
The reviewed baseline is Phase 7 commit 75bdecd; Phase 8 changes are recorded in
[verification](phase8-verification.md). No model/provider switch, Gemini
request, billing change, package installation or deployment was performed.

## Safeguards and remaining risks

| Area | Implemented safeguard | Remaining risk / requirement |
| --- | --- | --- |
| SQL injection/constructs | Exact AST/function allowlists, one SELECT from dataset, canonical SQL and clamped LIMIT; no joins, subqueries, CTEs, DDL, file/network functions or extensions | Parser/engine bugs and costly allowed queries remain possible; do not broaden the allowlist as a workaround |
| DuckDB boundary | Fresh in-memory connection, external access/extension loading disabled, locked settings, one thread, memory setting, interrupt timer, row/value-byte caps, no spill | Embedded execution shares backend privileges and secrets; independent restricted worker/process boundary needed before hostile input/public hosting |
| Dataset/session isolation | Deep-copy snapshots, locked state, dataset-bound conversation leases and mismatch rejection | UUIDs are not authentication or ownership checks; anybody reaching the API with an ID can access/reset that session |
| Authentication/authorization | None; documented trusted local scope | Add identity, ownership checks on every session operation, and tenant-specific storage/access control before multi-user hosting |
| Uploads and request parsing | 5 MiB file cap, bounded multipart body, no path-based filenames, UTF-8/shape/column validation; 32 KiB analysis-body cap added | Parsing/inspection/Pandas memory amplification and concurrent uploads are not globally bounded; no explicit dataset row/column cap |
| Time/resource limits | Provider timeouts, model/tool/iteration caps, SQL interrupt and per-result bounds | No whole-run deadline/cancellation; frontend timeout does not cancel work; engine memory limit does not cap Python/Pandas or all engine allocations |
| Concurrency/rate limits | Reject overlapping turns/reset on the same conversation; dataset/session capacity limits | Different conversations can run concurrently; no global semaphore, per-user request/token quota or admission control |
| Multi-user/expiry | Single-process stores, lazy monotonic inactivity TTL, five bounded successful turns, shutdown clears state | No durable/shared sessions; lazy expiry is not a strict deletion schedule; UI clear does not immediately delete the backend dataset; restart loses state |
| Prompt injection | Treat CSV/schema/tool output/history as untrusted; tools close over selected frame; fresh evidence required | Prompt instructions are not a security guarantee; model can select misleading allowed SQL or produce unsupported claims; two synthetic live questions passed, not a general adversarial assessment |
| Output/rendering | Plain-text chat; table rendering; escaped Plotly labels; conservative chart/precision rules | Two synthetic live explanations passed; broader quality and real browser rendering remain unverified; frontend response limit is checked after buffering, so configured backend must be trusted |
| Secrets/errors/logging | Backend-only process key, optional Windows-user DPAPI local storage, ignore/build exclusions, disabled hosted tracing, safe API details and allowlisted provider diagnostics | Environment credentials are accessible to process/host admins; unexpected framework/library errors may reach local stderr; access logs include session URLs; public logging/redaction and secret rotation needed |
| Network/HTTPS | Python listeners and Compose host ports default to 127.0.0.1; no permissive CORS added | Localhost is not authentication; a user can override listener flags; no public HTTPS, proxy/host/origin policy or public abuse boundary |
| Dependencies/containers/CI | Pinned direct requirements, key-free tests/CI, least-privilege workflow, separate non-root images, read-only roots/tmpfs, capability/resource restrictions | Dependencies not certified vulnerability-free; no installed vulnerability scanner/image audit. Transitives, action version tags and image tags lack complete hash/digest pinning; actual builds/resource behavior unverified |
| Provider privacy/free tier | Fixed Gemini 3.6 Flash Developer API, Free-project attestation, no retries or fallback | Billing is human-confirmed, not programmatically audited. Questions/context/schema/statistics/results can contain sensitive values; use synthetic input only |

## Demonstrated defects fixed

1. Analysis JSON previously had no pre-parser body limit. A 40 KiB body was
   fully parsed and returned 422, including with absent/false Content-Length.
   The existing body middleware now rejects it with 413 before JSON/model work;
   malformed analysis Content-Length returns 400. Legitimate typed requests are
   covered by the retained API/agent/conversation suite.
2. st.write rendered question/answer strings as Markdown. Untrusted chat could
   declare remote images and links even without unsafe HTML enabled. Chat now
   uses st.text; the regression verifies the text is not in Markdown elements
   while its result table/chart still renders. This blocks that declaration
   path; no claim is made that a real browser exfiltration attack was performed.

Six new regression cases cover these changes and the analysis-specific frontend
413 message. Existing SQL allowlists, session semantics, model routing, retry
controls and encrypted credential workflow are preserved. Stale helper/API
comments were corrected without restructuring the application.

## Before public deployment

Public hosting requires a separately approved design: authenticated session
ownership; tenant isolation; independent SQL execution without provider secrets,
filesystem/network capabilities and with enforceable CPU/memory/deadline limits;
upload/concurrency/rate quotas; cancellation; HTTPS and network/origin policy;
secret storage/rotation; safe observability; expiry/deletion policy; vulnerability
and container review; tested recovery and multi-user behavior. Loopback defaults,
SQL validation and a Docker container alone do not satisfy these requirements.
See [prioritized acceptance checks](acceptance-checks.md).

## References checked

[DuckDB security guidance](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview)
discusses the need for execution isolation when handling untrusted SQL.
[Streamlit st.write](https://docs.streamlit.io/develop/api-reference/write-magic/st.write)
parses string input as Markdown;
[st.text](https://docs.streamlit.io/develop/api-reference/text/st.text) displays
strings without Markdown/HTML parsing. These references inform the local review;
source tests establish the specific application behavior described above.
