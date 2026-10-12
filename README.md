# Agentic AI Data Analyst

A resume-focused AI/ML project that will let users upload CSV data, ask
natural-language questions, and receive computed analysis, charts, and
AI-generated explanations. **Phases 1 and 2 implement the data layer and HTTP API.**

## Current capabilities

- Strict comma-delimited UTF-8 CSV loading (BOM accepted).
- Clear errors for empty/header-only datasets, invalid encoding, null bytes,
  duplicate/blank headers, broken quoting, and inconsistent field counts.
- Row/column counts, inferred Pandas types, missing values, descriptive
  statistics, and bounded JSON-compatible previews.
- Isolated in-memory DuckDB aggregation and filtering for internal Python use.
- FastAPI health, multipart CSV upload, and dataset inspection endpoints.
- UUID dataset sessions, configurable inactivity expiration and capacity.
- A 12-row synthetic retail sample and automated tests.

## Structure

```text
backend/main.py               FastAPI application and app factory
backend/config.py             validated API configuration
backend/schemas.py            typed response schemas
backend/upload_limits.py      bounded upload request handling
backend/data/                 CSV processing, DuckDB, dataset sessions
frontend/                     reserved for Streamlit
data/sample/                 small tracked synthetic dataset
evaluations/                 reserved for agent evaluation
examples/                     runnable Phase 1 demonstration
tests/                        data layer, sessions, and API tests
```

## Windows setup (PowerShell)

Use Python 3.11 and the existing D: virtual environment. Create it only if absent.

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
if (!(Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
New-Item -ItemType Directory -Path .tmp -Force | Out-Null
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
$env:PIP_NO_CACHE_DIR = '1'
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
```

Activation is optional; invoking the environment's Python directly avoids
PowerShell execution-policy changes. Dependencies are pinned to tested versions.
No API key is needed. `.env.example` documents optional configuration; `.env`
files are not loaded automatically. Set environment variables in PowerShell.

## Start the backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open [Swagger UI](http://127.0.0.1:8000/docs) to try file uploads and inspect the
response schemas. [OpenAPI JSON](http://127.0.0.1:8000/openapi.json) describes the
API. Stop the server with Ctrl+C. Restarting it discards every dataset session.
The application lifespan directs multipart temporary spooling to `.tmp/uploads`
inside the repository and removes temporary upload files when requests finish.

| Endpoint | Purpose | Success |
| --- | --- | --- |
| `GET /health` | Return `{"status":"ok"}` | 200 |
| `POST /upload` | Multipart field `file` containing a CSV | 201 |
| `GET /dataset/{dataset_id}` | Inspect a previously uploaded dataset | 200 |

Upload returns `dataset_id`, `row_count`, `column_count`, `columns`, `dtypes`,
and up to five preview rows. Inspection additionally returns `missing_values`
and per-column `statistics`. UUID path parameters and multipart File parameters
validate requests; Pydantic models validate responses and document the schemas.
Dates loaded from CSV remain strings. DataFrame timestamps are serialized to
ISO strings; NumPy/Pandas scalars become JSON values. Missing and infinite
numeric values become null in previews. Infinite values are excluded from
statistics; missing-value counts reflect the original data.

### Upload the retail sample

In another PowerShell terminal:

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
curl.exe -X POST 'http://127.0.0.1:8000/upload' -F 'file=@data/sample/retail_sales.csv'
# Copy dataset_id from the response into this variable:
$datasetId = 'REPLACE_WITH_RETURNED_UUID'
Invoke-RestMethod "http://127.0.0.1:8000/dataset/$datasetId"
```

The retail upload reports 12 rows and 6 columns. The sample contains 530 in
revenue across 41 items. A smaller CSV (`product,revenue` with `a,10` and `b,20`)
produces this illustrative upload response; each request generates a new UUID:

```json
{
  "dataset_id": "ed34b274-3e8d-4b29-9df3-1096d739cd56",
  "row_count": 2,
  "column_count": 2,
  "columns": ["product", "revenue"],
  "dtypes": {"product": "str", "revenue": "int64"},
  "preview": [{"product": "a", "revenue": 10}, {"product": "b", "revenue": 20}]
}
```

### Errors and limits

Errors consistently use `{"detail":"Human-readable message"}`.

| Status | Meaning |
| --- | --- |
| 400 | Invalid filename, CSV content, multipart syntax, or Content-Length |
| 413 | File or multipart request exceeds its size limit |
| 415 | Filename does not have a `.csv` extension |
| 422 | Missing upload field or invalid UUID parameter |
| 404 | Dataset is unknown or expired |
| 503 | All active dataset slots are occupied |

The actual CSV bytes are validated; client MIME types are not trusted as proof
of CSV format. Single-column CSVs are valid, so plain text with a header and
consistent rows can also be a valid CSV. A file must include a header. Blank
physical lines are ignored; records with missing cells are retained.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `UPLOAD_MAX_BYTES` | 5242880 (5 MiB) | Maximum CSV byte size |
| `DATASET_TTL_SECONDS` | 1800 | Inactivity time before expiration |
| `MAX_ACTIVE_DATASETS` | 20 | Maximum active sessions per process |

All three must be positive integers; invalid configuration fails early. Example:

```powershell
$env:UPLOAD_MAX_BYTES = '5242880'
$env:DATASET_TTL_SECONDS = '1800'
$env:MAX_ACTIVE_DATASETS = '20'
```

Upload bodies are bounded before multipart parsing even without an accurate
Content-Length. Total multipart body size permits only an additional 64 KiB
for boundaries and headers; the CSV itself must fit the configured file limit.
No uploaded CSV is permanently stored. Small uploads stay in memory; larger
multipart files may spool temporarily on D: and are closed/deleted afterward.
Pandas memory use may exceed CSV byte size, so configure capacity to suit RAM.

## Dataset sessions and future tools

`DatasetManager.add(frame)` validates and stores an independent snapshot under
a UUID. `get(UUID(dataset_id))` returns a copy and refreshes only that dataset's
inactivity deadline. `uploaded_at(UUID(dataset_id))` returns its UTC upload
time without refreshing inactivity. Store/get operations lazily remove expired
entries. A lock makes capacity checks and session access safe across request
threads. App shutdown clears sessions. There is no scheduler or persistent DB.

This backend is intended for **one process/worker**. Multiple workers would
have separate session dictionaries. Dataset IDs select data and are **not user
authentication**: anyone holding an ID can retrieve that dataset in this local
version. The default command binds to localhost. Authentication and shared
storage require a later design before multi-user deployment.

Future agent tools can obtain a selected DataFrame from this manager and use
the existing data functions or `DuckDBDataset`. No HTTP endpoint accepts SQL,
and no `/analyze` or placeholder AI endpoint exists.

## Reusable Phase 1 data layer

```python
from backend.data.csv_processing import load_csv, inspect_dataset
from backend.data.duckdb_store import DuckDBDataset

frame = load_csv('data/sample/retail_sales.csv')
summary = inspect_dataset(frame, preview_rows=5)
with DuckDBDataset(frame) as dataset:
    totals = dataset.aggregate('revenue', 'sum', group_by='category')
    large_sales = dataset.filter_rows('quantity', 5, operator='>=')
```

Local `load_csv` keeps its original 10 MiB default; HTTP uploads default to
5 MiB. Both it and `load_csv_bytes` use the same parser. Pandas infers numeric
and text types and recognizes standard missing-value tokens such as empty
cells and NA. No domain-specific retail schema is enforced.
`DatasetError` and `AnalyticsError` are ValueError subclasses.

DuckDB contexts own a private DataFrame snapshot and in-memory connection,
closed on exit. Aggregation supports sum, avg, min, max, and count; count excludes
missing cells, and other aggregations require numeric columns. Filtering uses
known columns, allowlisted comparisons, and bound parameters. None maps to
IS NULL / IS NOT NULL. Results are capped at 1,000 rows with unspecified order.
No public method accepts raw SQL. This internal helper is not the future safe
execution layer for arbitrary user/LLM SQL.

## Tests and verification

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp '.tmp\pytest'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from backend.main import app; print(app.title)"
.\.venv\Scripts\python.exe -m examples.inspect_retail
```

The suite includes all 56 Phase 1 tests plus API and session tests. TestClient
checks the retail sample through upload/inspection, malformed and oversized
uploads (including missing/inaccurate Content-Length), unknown/expired sessions,
isolation, capacity, JSON serialization, and temporary-file cleanup.
The installed Starlette TestClient emits an upstream HTTPX deprecation warning;
HTTPX currently works and the tests pass. No warning is suppressed.

## Planned phases

Later phases add LangChain/minimal LangGraph, one hosted LLM provider (to be
selected), controlled natural-language SQL, automatic Plotly charts, grounded
explanations, conversational follow-ups, Streamlit, agent evaluation, and Docker
with deployment. Stop after Phase 2; none of those components is implemented yet.
