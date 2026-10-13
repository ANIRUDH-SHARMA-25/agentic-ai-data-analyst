# MOCKED / DETERMINISTIC evaluation

From the repo root in PowerShell:

```powershell
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m evaluations.benchmark
.\.venv\Scripts\python.exe -m evaluations.benchmark --output .tmp/phase5-evaluation.json
```

The command requires no provider key and makes no external model calls. No hosted
tracing or paid evaluation service is used. Its scripted model is explicitly
injected into the existing single-agent workflow. Synthetic input is the tracked
retail CSV plus a three-row missing-value DataFrame created in memory.

| Group | Cases | Independent expectation |
| --- | ---: | --- |
| Numerical SQL | 18 | Pandas calculations, never scripted model prose |
| Follow-up context | 3 | Pandas category ranking and filtered quantity total |
| SQL rejection | 4 | 422 after two attempts with the same SQL validator |
| Isolation/IDs | 2 | Dataset mismatch 409; unknown conversation 410 |
| Unsupported question | 1 | Schema inspection, no SQL/table, explicit unsupported explanation |

Numerical cases include total revenue/quantity, row count, mean/min/max revenue,
category/product totals, highest/lowest category, category/date/quantity filters,
distinct products/categories, missing count, nonmissing average, and COALESCE sum.
The verified category totals are Electronics 260, Home 150, Stationery 120.
Product ties are sorted explicitly by name. Oracle functions receive the source
DataFrame and do not receive generated answers or SQL output. Integer comparison
is exact; floating results use 1e-9 tolerance with null/shape/type checks.

Follow-ups ask for second and third categories, then quantity sold by the last
category. Scripted SQL uses the actual retained previous result to select its
threshold/category. Every follow-up still performs fresh schema inspection and
SQL execution through FastAPI. The seed turn is unscored setup. Safety cases cover
an unknown column, DROP, read_csv, and a join. Original broader SQL safety tests
also remain in the full test suite.

Reports contain total success rate, SQL execution correctness, follow-up context
correctness, rejection behavior, per-case pass/fail, and elapsed seconds. Generated
JSON belongs only in ignored .tmp/artifacts; it is not committed. Case results are
deterministic, while UUIDs and elapsed times naturally differ. A failure gives a
nonzero exit status. No model prose is scored as numerical evidence.

This benchmark verifies deterministic workflow behavior and regression safety.
It does **not** measure Gemini accuracy or prove live follow-up interpretation.
Scripted actions are known in advance. Pytest additionally runs the benchmark
twice and deliberately changes a query to confirm the independent oracle catches
wrong computation. Phase 7 prepares a separately approved real Gemini evaluation below; the
mocked benchmark continues to make no provider calls.


## Separate real Gemini evaluation (approval required)

Use only the tracked synthetic retail CSV. Before running, check AI Studio
shows Free with billing disabled, enter the key locally with
scripts/setup_gemini.ps1, and obtain explicit approval for live free-tier calls.
Official pricing is not proof of account-specific free access. Never upgrade
billing, switch models, or use OpenAI if access/quota fails.

The live check covers four questions: total revenue (530), highest category
(Electronics, 260), descending category totals (260/150/120), and a contextual
follow-up about the second category (Home, 150). Expected tables come from
independent Pandas operations. Every analysis must inspect schema and execute
validated SQL; shared conversational context must retain the same ID.
The run stops on the first error, wrong table, exhausted budget, or quota.
No automatic provider retries are permitted. It allows at most 16 generation
attempts across four questions (four per question, including final explanation).
Do not run the 28-case mocked benchmark against a live model.

Record results separately in `.tmp/gemini-live-evaluation.json`, marked REAL
GEMINI, with attempt counts, case indices, comparison outcomes, tool/row
summaries, chart decisions, and allowlisted provider diagnostics. Do not save
prompts, full responses, or raw exceptions in diagnostic reports.
Explanation grounding and rendering deserve human review; correct numerical
tables alone do not prove explanation quality. Key setup and explicit approval were completed. The initial and approved
second run failed on their first generation request (504 timeout, then 502
provider error; upstream status was not retained). A subsequent separately
approved plain-text diagnostic without tools returned actual Google HTTP
503 UNAVAILABLE. It stopped after exactly one attempt with no retries. No live
numerical task completed. All further generation and metadata requests are
on hold until fresh explicit approval. Gemini 3.8 Flash remains configured;
Gemini 3.7 Flash is only a conditional future research candidate, with no
verified free-tier eligibility or approved switch. See
[the recorded live status](phase7-live-status.md).

In the dashboard inspect each successful answer, its SQL/table, and the category
Plotly bar chart; compare its labels/values to 260/150/120. Confirm the follow-up
uses the same conversation. Clear/re-upload after server restart. Free-tier
content may be used by Google for product improvement, so synthetic data only.

The following evaluation command is reference material only; the current hold
prohibits running it. After fresh explicit approval for a bounded evaluation,
run in a local PowerShell window:

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
$secureKey = ConvertTo-SecureString ((Get-Content '.tmp/gemini-key.dpapi' -Raw).Trim())
try {
    $env:GOOGLE_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
    $env:GOOGLE_FREE_TIER_CONFIRMED = 'true'
    $env:GOOGLE_MODEL = 'gemini-3.8-flash'
    $env:GOOGLE_GENAI_USE_VERTEXAI = 'false'
    $env:GOOGLE_GENAI_USE_ENTERPRISE = 'false'
    .\.venv\Scripts\python.exe -m evaluations.live_gemini --approve-live-free-tier --max-calls 16
} finally {
    Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:GOOGLE_FREE_TIER_CONFIRMED -ErrorAction SilentlyContinue
}
```

The flag records operator approval; it does not prove billing status or replace
the human approval step. The runner uses FastAPI TestClient with the real agent
and Gemini provider, validates actual SQL/tool evidence, and saves a standalone
Plotly category-chart HTML on D:. Browser review is still required. Attempt
counts include failed generation attempts, not just successful responses.
