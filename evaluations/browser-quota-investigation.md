# Browser acceptance quota failure: offline diagnosis and mapping fix

Date: 2026-10-15. No Gemini generation or metadata request, key loading,
billing/model change, retry, installation or deployment occurred during this
investigation. The historical live report and reviewed screenshot remain
unchanged in ignored `.tmp` files on D:.

## Historical evidence and its limits

The actual browser test used three generation attempts for Question 1. Upstream
Google statuses were 200, 200, then 429 RESOURCE_EXHAUSTED. Actual schema
inspection and SQL execution returned ordered Electronics 260, Home 150,
Stationery 120. The third request, which would have produced the final
explanation, failed. The run stopped, with no retries/fallback, Question 2 or
conversation-reset probe. It does not establish genuine result/chart rendering.

The user subsequently checked the Google AI Studio Rate Limit dashboard for
Gemini 3.6 Flash and reported:

| Dashboard dimension | User-observed value |
| --- | --- |
| RPM | 2 / 5 |
| TPM | 1.87K / 250K |
| RPD | 21 / 20, red |
| Banner | Rate-limit warning |

This confirms a historical daily quota overrun in the dashboard (21 against a
20-request daily limit). Together with the recorded Google 429, it strongly
supports daily quota exhaustion as the browser failure's cause. The retained
provider diagnostics alone identify quota/rate limitation, not its specific
quota dimension. The dashboard view shows peak usage over 28 days; those
figures do not establish current usage or remaining quota after a reset, nor
prove minute/token limits could never have contributed at another time. No
current quota/reset timestamp or available capacity was checked by API.
The observation is user-reported dashboard evidence, not an automated billing
or quota audit. No raw provider response or account screenshot is committed.

## Demonstrated mapping defect

The ordinary agent already maps Google quota failures to sanitized backend HTTP
429. Its standard FastAPI route preserves AnalysisError.status_code. The browser
evaluation wrapper, however, caught that exception and replaced its status with
422; then its response guard replaced any non-200 result with generic
backend_failure/422. The frontend's normal 422 mapping therefore displayed an
unsupported-question message. Google did not return 422.

The evaluation-only wrapper now preserves the agent's allowlisted provider
HTTP mapping (429/502/503/504), upstream diagnostic, and quota_or_rate_limit
category. The guard records backend_http_status and forwards a sanitized error
with that status, rather than replacing it with generic 422. Local SQL,
validation and budget failures still close the run as local evaluation failures;
they are not relabeled Google quota exhaustion. After quota failure the closed
gate continues returning a sanitized 429 without another provider dispatch.

The normal Streamlit application already handled a genuine backend 429 as
rate-limited, not unsupported, without replaying analysis. Its message now also
explicitly names possible free-tier quota exhaustion, advises waiting for quota
availability, and states that no automatic retry or paid fallback was used.
It deliberately does not assert that every 429 is a daily-limit failure or
promise an exact reset time. No raw backend/provider detail is displayed.

## Offline regression verification

Six new cases reproduced the deficiencies before the fix: browser quota on the
first generation and after correct SQL, normal backend-to-frontend quota on
those same turns, a sanitized client quota-message check, and actual Streamlit
AppTest rendering/rerun behavior. Sealed SDK MockTransport runs the real agent,
tools, SQL and HTTP path; it never contacts Google. Tests verify 429 rather than
422, the explicit quota message, preserved upstream RESOURCE_EXHAUSTED/category,
correct intermediate SQL evidence, closed-gate behavior, exact attempt counts,
no automatic retry and no private details/credential leakage. Existing provider
503 regression now checks preserved backend 502 on first failure rather than
incorrect 422; Google 503 remains a separate recorded upstream status. Existing SQL, memory, model and free-tier controls are retained.

Final offline verification: **524 tests passed, zero failed**; mocked benchmark
**28/28** (SQL 18/18, follow-ups 3/3, rejections 4/4); pip check passed.
No dependencies were changed. The full suite includes all six new quota cases. The existing
[two-question backend success](live-retail-verification.md) remains valid:
both questions passed in six separate real generation requests with correct
explanations, contextual Home/150 follow-up and Plotly generation. This later
browser quota failure neither invalidates that historical result nor completes
browser acceptance. The 28-case mocked benchmark is separate evidence.

## Next action: wait; no execution approval

Do not send another generation or metadata request now. After the next daily
quota reset, recheck the current dashboard view and available quota, confirm
Free tier/billing disabled afresh, and obtain separate explicit approval for a
bounded browser run. Retain the eight-total/four-per-question cap, 35-second
spacing, 60-second timeout, zero retries/fallbacks and stop-on-first-error policy.
The existing report continues to block accidental restart; do not overwrite it
or invent a new run authorization. No automatic monitoring or quota probe is set.
