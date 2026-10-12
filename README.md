# Agentic AI Data Analyst

A resume-focused AI/ML project that will let users upload CSV data, ask
natural-language questions, and receive computed analysis, charts, and
AI-generated explanations. **Phase 1 implements the foundation and data layer.**

## Current capabilities
- Strict comma-delimited UTF-8 CSV loading (BOM accepted), default 10 MiB limit.
- Clear errors for empty/header-only datasets, unreadable files, invalid
  encoding, null bytes, duplicate/blank headers, broken quoting, and records
  with too many or too few fields.
- Row/column counts, inferred Pandas types, per-column missing values,
  descriptive statistics, and a bounded JSON-compatible preview.
- Isolated in-memory DuckDB sessions with predefined aggregation and filtering.
- A 12-row synthetic retail dataset and automated tests.

## Structure
```text
backend/data/       reusable CSV processing and DuckDB analytics
frontend/           reserved for Streamlit
data/sample/       small tracked synthetic dataset
evaluations/       reserved for agent evaluation
examples/           runnable Phase 1 demonstration
tests/              Pytest suite
```

## Windows setup (PowerShell)
Work in `D:\GPT work\CODEX\agentic-ai-data-analyst` using Python 3.11.
```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
python -m venv .venv
New-Item -ItemType Directory -Path .tmp -Force | Out-Null
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
$env:PIP_NO_CACHE_DIR = '1'
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
.\.venv\Scripts\python.exe -m pytest --basetemp '.tmp\pytest'
.\.venv\Scripts\python.exe -m examples.inspect_retail
```
Activation is optional; invoking the environment's Python directly avoids
PowerShell execution-policy changes. No API key or .env file is needed.
Dependencies are pinned to the versions verified for Phase 1.

## Reusable data layer
```python
from backend.data.csv_processing import load_csv, inspect_dataset
from backend.data.duckdb_store import DuckDBDataset

frame = load_csv('data/sample/retail_sales.csv')
summary = inspect_dataset(frame, preview_rows=5)
with DuckDBDataset(frame) as dataset:
    totals = dataset.aggregate('revenue', 'sum', group_by='category')
    large_sales = dataset.filter_rows('quantity', 5, operator='>=')
```
The demo produces category revenues of Electronics **260**, Home **150**,
and Stationery **120**, totaling **530** across **41** items sold.
`DatasetError` and `AnalyticsError` are ValueError subclasses for later API
error mapping. Summaries use null for missing/nonfinite values and are JSON
serializable. Infinite numeric values are excluded from descriptive statistics;
missing-value counts reflect the original data. Pandas infers numeric/text types; dates remain strings and its
standard missing-value tokens (such as empty cells and NA) are recognized.
A CSV must include a header; one-column files are supported. No domain-specific
retail schema is enforced on arbitrary datasets. Blank physical lines are
ignored; records containing missing cells are retained.

## DuckDB boundaries
Each context owns a private DataFrame snapshot and an in-memory connection,
closed on exit. No persistent database or external service is used.
Aggregation supports sum, avg, min, max, and count; count excludes missing
cells. Other aggregations require numeric columns. Filtering accepts a known
column, an allowlisted comparison, and a bound parameter; None maps to
IS NULL / IS NOT NULL. Results are limited to 1,000 rows with unspecified
ordering. No public method accepts SQL. This is a Phase 1 internal helper,
not the future security layer for arbitrary user/LLM-generated SQL.

## Planned phases
The finalized stack adds LangChain/minimal LangGraph, one hosted LLM provider
(to be selected), FastAPI/Pydantic, Streamlit, Plotly, and Docker when needed.
Future work includes natural-language SQL, single-agent tools, automatic
charts, grounded explanations, follow-up questions, dedicated safe SQL
execution, agent evaluation, and deployment. None is implemented in Phase 1.
