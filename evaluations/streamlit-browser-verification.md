# Verified local Streamlit workflow: 2026-10-16

The separately approved, guarded real-browser acceptance test passed both
synthetic retail questions through the actual Streamlit interface in Brave.
The user freshly confirmed AI Studio Free tier with billing not configured,
and reported that the 1 Day view no longer showed the historical daily-limit
warning or recent Gemini 3.6 usage. This was human confirmation, not an API
billing/quota audit. This document summarizes existing evidence; its preparation
made no Gemini generation or metadata requests.

## Verified real-browser result

Exactly **six actual Gemini 3.6 Flash generation requests succeeded**, three
per question, all with upstream Google HTTP 200. Both backend analysis responses
were HTTP 200. The test had a hard maximum of eight attempts total/four per
question, at least 35 seconds between starts, 60-second provider timeouts,
1200 output tokens, existing LOW thinking, zero retries and no fallback.
Observed start gaps were 35, 35, 68.078, 35 and 35 seconds.

| Browser step | Observed outcome |
| --- | --- |
| Retail sample | Loaded through the real UI: 12 rows, 6 columns, zero missing cells |
| Grouped revenue question | Correct descending Electronics 260, Home 150, Stationery 120; passed |
| Contextual second-category question | Genuine final explanation identified Home as second, revenue 150; passed |
| Actual tools | inspect_dataset and execute_sql executed freshly on each turn |
| Memory | Same dataset-bound conversation ID; actual prior grouped result supplied to the follow-up |
| Explanation grounding | Both final explanations passed independent claim validation and were reviewed in Streamlit |
| Result rendering | Both actual SQL result tables and Plotly category bar charts rendered in the browser |
| SQL/tool detail panels | Expanded and visually checked against actual executed SQL and tool names |
| New conversation | Both displayed turns, result tables/charts and SQL areas cleared; dataset overview remained |
| Backend reset | Real reset endpoint succeeded; local report reset_verified=true; generation count stayed 6 |
| Errors | No provider, SQL, validation, application or browser-console error/warning observed |

Both turns executed the same validated query and recomputed fresh evidence:

```sql
SELECT category, SUM(revenue) AS total_revenue
FROM dataset
GROUP BY category
ORDER BY total_revenue DESC
LIMIT 200
```

| Category | Total revenue |
| --- | ---: |
| Electronics | 260 |
| Home | 150 |
| Stationery | 120 |

The follow-up returned the complete correctly ordered table, an accepted
alternative SQL shape. Its final explanation independently identified Home/150;
the table alone did not satisfy the answer or continuity requirements. Answers
rendered as plain text under the existing untrusted-output safeguard; any
Markdown markers remained literal text. Separate tables/charts displayed the
actual computed values. No third question or generation was used to probe reset.

## Scope of evidence

| Verification | Scope | Provider requests |
| --- | --- | ---: |
| 28-case mocked benchmark | Scripted agent actions, independent Pandas oracles, SQL/context/rejection/isolation regressions | 0 |
| 2026-10-15 backend live evaluation | Two retail questions through FastAPI TestClient, real Gemini tools/SQL/explanations/context and Plotly generation | 6 |
| 2026-10-16 browser acceptance | Two retail questions through actual Brave/Streamlit, real explanations/tables/charts/SQL and New conversation reset | 6 |

These are distinct runs and methodologies. The browser run is six requests,
not the mocked benchmark and not a broad model-accuracy or reliability study.
The tested local synthetic Streamlit workflow is verified. General model
accuracy, arbitrary datasets/questions, future provider availability, production
readiness, public deployment and security certification are not established.
The earlier October 15 quota failure and its offline mapping fix remain in the
[historical quota investigation](browser-quota-investigation.md); they are not
reclassified as a successful browser run.

## Privacy and local operation

Only the guarded backend received the existing encrypted key via its process
environment. Backend/frontend listeners were 127.0.0.1 only; no billing, model,
browser-permission or dependency change occurred. Both test-owned service
process trees were stopped after evidence capture; no later generation or
metadata requests were sent. The completed request gate stayed closed.

The bounded final explanations, diagnostic JSON, generated result screenshots
and private outcome notes remain ignored locally on D:. The dated report is
`.tmp/browser-acceptance-2026-10-16.json`; it did not overwrite the failed run.
Reviewed screenshots contain synthetic results/app controls only, with no
credential, account UI, session ID or raw provider body. No retained model reply,
prompt, private report, screenshot or generated chart is committed. This tracked
record contains a sanitized factual summary rather than a model transcript.

## Remaining limitations

- Direct file-picker CSV upload has not been manually verified. Browser
  automation was blocked by extension file-access permission; permissions were
  not changed. The retail sample exercised the actual upload/inspection path.
- Docker image builds and runtime/resource/restart/permission smoke checks are
  untested. Docker/WSL installation was not performed or authorized.
- Public hosting requires authentication/session ownership, tenant isolation,
  independent SQL execution without provider secrets, quotas/cancellation,
  HTTPS/network policy, secret/lifecycle controls, vulnerability review and
  multi-user recovery work in [security readiness](../docs/security-readiness.md).

Any further provider request or deployment requires separate explicit approval.
