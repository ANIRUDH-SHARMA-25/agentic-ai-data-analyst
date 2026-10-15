# Offline final-explanation investigation

> Current status (2026-10-15): a later separately approved Gemini 3.6 Flash
> two-question run passed in six real generation requests, with tool/SQL execution,
> both explanations, contextual Home/150 follow-up and Plotly generation verified.
> See [the final live record](live-retail-verification.md). Earlier failures,
> proposals and test counts below are historical. No new API calls are authorized.


Date: 2026-10-15. No generation or metadata API requests were made. No credential
was decrypted, no dependency installed, and no model, agent, SQL, memory,
frontend or billing setting changed. This work is confined to evaluation code,
tests and documentation.

## What the historical failure establishes

The latest ignored live report records Question 1 correct schema/SQL evidence,
Electronics 260, Home 150, Stationery 120 ordered descending, and a generated
Plotly bar chart. Three provider attempts returned HTTP 200. The backend returned
200; the local evaluator rejected numerical_claims_supported and did not start
Question 2. The 203-character answer was not retained. Its exact failed claim
cannot be reconstructed conclusively. Synthetic regressions demonstrate checker
bugs but do not establish which, if any, occurred in the historical answer.

## Demonstrated problems and targeted corrections

The old checker used a global number whitelist and category proximity. It could
reject direction headings such as highest to lowest, ordinary numbered lists,
amount-before-category wording and valid derived percentages. It could also
accept a wrong total or category count when the number happened to be another
known result. Correct SQL alone still never passes explanation validation.

The synthetic-only evaluator now separately checks:

| Claim | Independent expectation |
| --- | --- |
| Category revenue | Electronics 260; Home 150; Stationery 120, with correct association |
| Combined revenue | 530, including totals stated across named categories |
| Category count | 3, including number words and category-count wording |
| Category ranking | Electronics first, Home second, Stationery third; integer ranks only |
| Revenue share | category revenue / 530 * 100; decimal half-up rounding to displayed precision |

Correct shares include Electronics 49.06%, Home 28.30%, Stationery 22.64%
(or approximately 23%). Trailing zeros do not alter precision; comparisons use
Decimal and support at most 12 effective fractional digits. Whole-category share
100% and an explicit denominator 530 are also checked independently. Reversed
revenue wording, spelled supported amounts and numbered lists are covered.

Wrong totals/counts, swapped labels, negative signs/negative wording/Unicode
minus, accounting-style negative amounts, fractional/wrong ranks, scaled million
claims, unsupported profit/units/growth claims and incorrect percentages fail.
An extra false claim fails even when all three correct revenues appear elsewhere.
Unknown numerical expressions fail closed: this remains a deterministic English
oracle, not a general semantic judge. Some valid unrecognized phrasing may still
need offline review. No model-based judge or extra provider request was added.

Final-answer facts, second-category identification, exact SQL evidence and
conversation continuity remain separate requirements. A full correct table is
valid SQL evidence for the follow-up but cannot substitute for a final answer
identifying Home as second with revenue 150. Existing schema execution, SQL
trace, row ordering, numeric values and conversation ID checks remain intact.

## Local diagnostics and privacy

Validation failures now include a bounded normalized claim excerpt (160
characters), claim kind, observed value, expected value and associated category
where known, capped at 20 failure records. For example, the hand-written
synthetic regression total revenue 531 reports kind total, observed 531,
expected 530. This is not the missing historical reply.

The runner verifies the SHA-256 fingerprint of the tracked synthetic retail CSV
before loading a model. It reads/uploads that same payload. A changed dataset
blocks diagnostic capture. Reports must resolve below the D: repository `.tmp`
directory and existing reports cannot be overwritten. Final explanations are
redacted using the configured credential and credential-pattern rules, limited
to 4096 characters and 8192 UTF-8 bytes, with truncation/redaction metadata.
The full in-memory answer is validated; a truncated retained copy is not passed
instead. Failure excerpts are redacted too. The console exposes only counts,
statuses, failure categories and claim kinds, never replies/excerpts. Provider
errors retain the existing sanitized diagnostic handling; no raw SDK exception,
request body or prompt is newly logged. `.tmp` remains ignored; no generated
reply, credential, diagnostic JSON or HTML chart is tracked.

## Offline verification

- Complete automated suite: 505 passed, zero failed.
- Focused explanation regression cases: 49, including positive and adversarial claims.
- Real SDK MockTransport runner cases cover success/failure, local explanation
  retention, one-question-only scope, no retries, request budgets and timing.
- Mocked benchmark: 28/28, SQL 18/18, follow-ups 3/3, rejection behavior 4/4.
- pip check: no broken requirements. No dependencies added or updated.
- Original historical live reports preserved. No live requests during this work.

## Smallest useful next live test: pending explicit approval

Run only the first fixed grouped-category question on the fingerprint-checked
synthetic CSV using `--first-question-only` and a fresh ignored report, for example
`.tmp/gemini36-explanation-q1-review.json`. The mocked test proves this mode
never submits the second question. It has a hard global maximum of four actual
generation attempts (also four per question); normally three are needed for
inspect selection, SQL selection and the final explanation.

Use existing encrypted credentials, Gemini 3.6 Flash only, LOW thinking, 1200
output tokens, 60-second timeout, at least 35 seconds between starts, zero
retries/fallbacks, and a freshly confirmed Free project with billing disabled.
Stop on the first provider, tool, SQL, numerical, explanation, context or budget
failure. Save the bounded local final explanation for offline review and verify
its SQL/table/chart. Do not run the follow-up, metadata calls or any additional
question. Success verifies only Question 1; a full live contextual follow-up
still requires separate approval. The approval CLI flag is not human approval.
No live run is authorized or executed by this document.
