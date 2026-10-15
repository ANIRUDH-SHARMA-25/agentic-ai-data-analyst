# Gemini 3.6 Flash: bounded live retail verification

Date: 2026-10-15. The user separately approved the run and freshly confirmed
Google AI Studio Free tier with billing disabled. Billing state is a human
attestation, not an API audit. This record summarizes existing local evidence;
finalization made no new Gemini generation or metadata requests.

## Verified scope and outcome

Exactly two synthetic retail questions passed in one dataset-bound conversation.
Six actual Gemini generation requests succeeded (three per question), all with
upstream Google HTTP 200. Every request start was at least 35 seconds after the
previous start. Limits were eight attempts total, four per question, 60 seconds
per request, 1200 output tokens, LOW thinking, zero retries, no model switching
and no paid fallback. Both backend analysis responses returned HTTP 200.

| Case | Verified result |
| --- | --- |
| Group category revenue descending | Electronics 260, Home 150, Stationery 120 in that order; final explanation passed |
| Contextual second-category follow-up | Final explanation identified Home as second with revenue 150; passed |

Each turn actually executed inspect_dataset followed by execute_sql. The second
turn received the prior grouped result through the application conversation
store, retained the same conversation ID, and computed fresh SQL evidence.
Both turns recomputed the complete correctly ordered category table. That valid
alternative SQL shape passed separately from the final-answer and continuity
checks. Both final explanations passed the deterministic numerical claim checks
and were reviewed locally; neither contained a rejected numerical claim.

Both SQL executions used the validated query:

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

Plotly bar chart generation succeeded for both result tables, and the first
chart was saved as a standalone local HTML artifact. No provider, tool, SQL,
numerical, explanation, context or budget failure occurred. The approved run
stopped after the two questions; no additional API or metadata requests followed.

## Evidence handling and interpretation

The report `.tmp/gemini36-conversation-final-2026-10-15.json` and chart remain
ignored local files on D:. Bounded synthetic final explanations (206 and 253
characters, neither truncated) are retained only in that local report. Generated
replies, credentials, prompts, session IDs, provider bodies and charts are not
copied into Git. The summary above describes the observed outcome, not a saved
model transcript. The earlier standalone single-question run also passed in
three requests; its attempts are not included in this run's six-request count.

The separate 28-case benchmark uses scripted model actions with independent
Pandas expectations and makes no provider requests. Its 28/28 result is workflow
regression evidence, not 28 real Gemini cases. This two-question live success
establishes only the demonstrated synthetic workflow, not broad accuracy,
reliability under load, security certification or future provider availability.
The deterministic English explanation checker is conservative and not a general
semantic truth judge; see the [offline investigation](final-explanation-investigation.md).
Historical provider/evaluator failures remain documented in
[two-question history](two-question-status.md) and [Phase 7 history](phase7-live-status.md).

## Remaining acceptance work

- Real Streamlit browser testing of genuine answers, tables, charts and session
  reset; API TestClient and Plotly generation do not establish browser behavior.
- Docker image builds and runtime/resource/permission/restart smoke checks in a
  separately authorized environment; Docker was not installed for this work.
- Public hosting requires the authentication, tenant ownership, independent SQL
  isolation, quotas, cancellation, HTTPS, secrets, lifecycle and recovery work
  described in [security readiness](../docs/security-readiness.md).

No further live test or public deployment is authorized by this record.
