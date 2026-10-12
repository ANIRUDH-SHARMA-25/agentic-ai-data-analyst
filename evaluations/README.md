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
It does **not** measure OpenAI accuracy or prove live follow-up interpretation.
Scripted actions are known in advance. Pytest additionally runs the benchmark
twice and deliberately changes a query to confirm the independent oracle catches
wrong computation. Real-model testing remains deferred beyond Phase 5.
