# Two-question Gemini 3.6 evaluation: live evidence and offline fix

> Current status (2026-10-15): a later separately approved Gemini 3.6 Flash
> two-question run passed in six real generation requests, with tool/SQL execution,
> both explanations, contextual Home/150 follow-up and Plotly generation verified.
> See [the final live record](live-retail-verification.md). Earlier failures,
> proposals and test counts below are historical. No new API calls are authorized.


Date: 2026-10-15. No provider generation or metadata requests were made while
investigating or fixing this evaluator. Main agent behavior, Gemini parameters,
SQL security, session/memory implementation and free-tier safeguards are unchanged.

## Actual historical live run

The ignored `.tmp/gemini36-two-question-2026-10-15.json` is preserved unchanged.
Five actual generation attempts occurred, all upstream HTTP 200, spaced 35
seconds apart, with no retries or model/provider fallback.

| Question | Actual verified outcome |
| --- | --- |
| 1: grouped revenue, highest to lowest | Passed live in three generation requests. inspect_dataset and execute_sql ran. SQL returned Electronics 260, Home 150, Stationery 120 in descending order. Final explanation checks passed; Plotly bar chart generated. |
| 2: revenue of the second category | Two generation requests. Correct prior context was supplied; fresh inspect_dataset and execute_sql ran. SQL recomputed the same correct ordered category table. The evaluator stopped with local 422 before another generation could produce a final response. Home/150 final-answer correctness and final-response conversation-ID continuity were not verified. |

Do not relabel Question 2 as a model memory failure, an incorrect generated
answer, or a live pass. Its intermediate SQL evidence was correct; the final
answer was never generated. Browser review in Streamlit remains a separate
acceptance step; the generated Plotly artifact is not proof of browser review.

## Exact failure mechanism

strict_sql called matches immediately after a successful SQL execution. For
index 1, matches accepted only [[Home,150]] or [[150]]. The full table equaled
expected[0], not expected[1], so fail raised AnalysisError with status 422 and
category incorrect_numerical_result. That bypassed the remaining model step.
Google did not return 422; it returned 200 for both Question 2 generations.

## Offline correction

- Accept the exact Home/150 row, scalar 150, or the exact complete ordered
  category table as valid follow-up evidence. Numeric values, labels and row
  order must match independent Pandas expectations; merely containing Home/150
  is insufficient. Partial/duplicate/wrongly ordered tables still fail.
- Validate final answers independently. They must associate Home with 150 and
  identify Home as second (including supported forms such as second-highest,
  2nd or rank #2). A full table or a bare mention of Home/150 is not enough.
- Assess prior context and conversation ID separately from numerical and answer
  checks; any continuity failure prevents the case passing.
- Require actual inspect_dataset/execute_sql execution and a matching recorded
  SQL result, SQL text, columns and rows before marking evidence verified.
- Record separate numerical_evidence_valid, sql_execution_verified,
  final_answer_verified and conversation_continuity_verified fields. Cases
  start unverified; partial SQL success never upgrades missing final responses.

An additional flaw was found in the old explanation checker: independent
name/number substring membership could accept swapped category amounts or a
wrong rank. It also parsed -150 as 150. The new evaluator checks category-to-
amount associations, signed numeric claims and rank-to-category associations.
It permits other correct category values in a full-table follow-up explanation.
These deterministic checks cover specified English sentence/list/table forms;
they are conservative regression oracles, not a general natural-language truth
judge. Unsupported/ambiguous paraphrases can fail and require offline review.
No separate model judge or extra provider request is used.

The runner now accepts a fresh --output filename under ignored .tmp, rejects
existing reports, and gives each chart its report-specific name so an approved
future run need not overwrite the historical chart. The original four-question
runner is not imported or invoked; the two-question list stays fixed.

## Offline regression coverage

Sealed SDK MockTransport tests exercise single-row, scalar and full-table
follow-ups through the real agent/tools/SQL/API path, with correct answers and
with intentionally incorrect ordering, amounts and explanations. Unit tests
cover rank/amount association, negative values, duplicates/partial tables,
missing SQL traces, mismatched SQL and conversation IDs, missing prior context,
and table-only explanations. Existing budget, 35-second spacing, provider/tool/
SQL failure, truncation, approval and no-repeat checks remain intact.

## Earlier fresh-run proposal (subsequently approved and executed)

Repeat exactly the same two questions and synthetic retail CSV using a fresh
conversation and report `.tmp/gemini36-two-question-followup-fixed-2026-10-15.json`.
Normally six generation requests are needed: inspect selection, SQL selection,
then final answer per question. Enforce eight actual attempts total and four
per question, at least 35 seconds between starts, 60-second request timeouts,
1200 output tokens, existing LOW thinking, zero retries, and no paid/model
fallback. Confirm the project is Free with billing disabled before any call.
Stop at the first provider, tool, SQL validation/execution, wrong numerical or
ordering result, final-answer, context or budget failure. No correction/retry
on SQL failure in this evaluation. No extra questions or metadata calls.

The following was the earlier proposal, not current authorization. Use the secure local credential
loading process and the two-question runner with --approve-two-question-free-tier
and --output .tmp/gemini36-two-question-followup-fixed-2026-10-15.json.
The approval flag does not replace human authorization. The earlier run's unused
budget is not continuing approval. No requests are authorized by this document.


## Verification results for this offline correction

- Focused two-question suite: 48 passed (the original 9 safeguarded-runner cases
  plus 39 additional parameterized integration/oracle cases).
- Complete suite: 451 passed, 0 failed.
- Mocked benchmark: 28/28; SQL 18/18, follow-ups 3/3, rejections 4/4.
- pip check: no broken requirements; no dependencies installed or changed.
- Main agent, SQL allowlists/security, session/memory code and Gemini model
  parameters unchanged. Historical live JSON and chart preserved; no provider
  generation/metadata requests made during this investigation.


## Subsequent live run and final-explanation investigation

The separately approved fresh run was executed and retained at ignored
`.tmp/gemini36-two-question-followup-fixed-2026-10-15.json`. Question 1 used
three generation attempts, all upstream Google HTTP 200, with start gaps
38.781 and 48.954 seconds. Schema inspection and SQL execution returned the
correct ordered Electronics/260, Home/150, Stationery/120 table, and a Plotly
chart was generated. The local final-explanation checker reported
`numerical_claims_supported=false`; the case did not pass. Question 2 was not
attempted. This was an evaluator rejection after backend HTTP 200, not a Google
provider error.

The 203-character historical final explanation was not retained. The exact
failing statement cannot be reconstructed conclusively. Demonstrated offline
checker defects are possible explanations, not proof of what that answer said.
The earlier run's Question 1 pass and Question 2 intermediate-only evidence
remain historical facts; the subsequent run does not verify the follow-up.

See [the focused offline explanation investigation](final-explanation-investigation.md)
for typed claim validation, adversarial regressions, diagnostic privacy bounds,
current verification results and the smaller proposed next test. No provider
requests were made during this offline investigation. All live requests remain
on hold pending fresh explicit approval.
