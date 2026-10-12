# Agentic AI Data Analyst

A resume-focused AI/ML project that will let users upload CSV data, ask
natural-language questions, and receive computed analysis, charts, and
AI-generated explanations. **Phases 1-3 implement the data layer, HTTP API, and agentic SQL analysis.**

## Current capabilities

- Strict comma-delimited UTF-8 CSV loading (BOM accepted).
- Clear errors for empty/header-only datasets, invalid encoding, null bytes,
  duplicate/blank headers, broken quoting, and inconsistent field counts.
- Row/column counts, inferred Pandas types, missing values, descriptive
  statistics, and bounded JSON-compatible previews.
- Isolated in-memory DuckDB aggregation and filtering for internal Python use.
- FastAPI health, CSV upload, dataset inspection, and natural-language analysis.
- One tool-using LangChain/LangGraph agent with a dedicated restricted SQL layer.
- UUID dataset sessions, configurable inactivity expiration and capacity.
- A 12-row synthetic retail sample and automated tests.

## Structure

```text
backend/main.py               FastAPI application and app factory
backend/config.py             validated API configuration
backend/schemas.py            typed response schemas
backend/upload_limits.py      bounded upload request handling
backend/data/                 CSV processing, DuckDB, sessions, restricted SQL
backend/agent/                lazy OpenAI model config and one LangChain agent
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
Health, upload, inspection, and all tests need no API key; live analysis does. `.env.example` documents optional configuration; `.env`
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
| `POST /analyze` | Analyze a selected dataset with the agent | 200 |

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
| 422 | Invalid request or unsupported/rejected analysis |
| 404 | Dataset is unknown or expired |
| 503 | Dataset capacity reached or OpenAI configuration/access unavailable |
| 429 | OpenAI rate limit reached |
| 502 | Provider/model failed to produce a complete grounded answer |
| 504 | OpenAI or SQL execution timed out |

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

Agent tools obtain only the selected DataFrame snapshot. POST /analyze accepts
a question, never raw SQL or a tool-selected dataset ID. The original
DuckDBDataset helper remains for trusted internal Python use; generated SQL
always goes through the separate safe_sql validator/executor.

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

The suite preserves the 101 Phase 1/2 tests and adds fake-model agent, SQL
security/resource, and analyze endpoint tests. The earlier phase-boundary test
now checks the authorized /analyze endpoint rather than its previous absence. TestClient
checks the retail sample through upload/inspection, malformed and oversized
uploads (including missing/inaccurate Content-Length), unknown/expired sessions,
isolation, capacity, JSON serialization, and temporary-file cleanup.
The OpenAI integration also installs HTTPX2 transitively, resolving the earlier
Starlette TestClient HTTPX deprecation warning. Tests block live OpenAI generation
and disable hosted tracing; no real key, API calls, or billed tokens are used.

## Phase 3: one tool-using analyst

Each analysis request gets a fresh LangChain `create_agent` graph (LangGraph
underneath), one configured ChatOpenAI model, and three closures bound to that
request's dataset snapshot. There is no persisted conversation/checkpointer,
multi-agent graph, web access, shell tool, filesystem tool, or Python execution.
The system prompt requires schema inspection and actual evidence, tells the
model to explain unsupported questions, and treats dataset contents as untrusted.

| Tool | Inputs | Evidence returned |
| --- | --- | --- |
| inspect_dataset | None | Columns, types, row/column counts |
| get_statistics | None | Existing missing-value counts and descriptive statistics |
| execute_sql | query string | Validated SQL, bounded columns/rows and row count |

Tools cannot change dataset IDs. Schema inspection is enforced before statistics
or SQL. Tool names and arguments are checked before dispatch, with one tool per
model turn. Defaults allow at most 8 model calls and 6 tool calls. Model requests
have a 30-second timeout, 1,200 output-token cap, and zero automatic retries.
The maximum provider wait across a run is therefore up to eight such timeouts,
plus local processing; there is no additional whole-request cancellation timer.
Hosted LangSmith tracing is disabled, including when inherited environment
settings enable it. Dataset-derived schema, selected statistics/results, and
the question are sent to OpenAI when a real analysis is requested.

A first SQL validation/execution error is returned as sanitized tool feedback,
allowing one correction. A second failure ends the request. Both attempts use
the same validator. SQL timeouts end immediately. The API refuses a successful
answer after unresolved SQL errors or without schema inspection. Provider
failures produce clear errors rather than fabricated fallback answers.

### Configure OpenAI

The application imports, starts, and serves deterministic endpoints/tests without
a key. A real /analyze call without OPENAI_API_KEY returns HTTP 503.
Set the key privately in the server terminal, not in tracked files:

```powershell
$secureKey = Read-Host 'OpenAI API key' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
$env:OPENAI_MODEL = 'gpt-4.1-mini'
$env:OPENAI_TIMEOUT_SECONDS = '30'
$env:OPENAI_MAX_OUTPUT_TOKENS = '1200'
$env:TIKTOKEN_CACHE_DIR = Join-Path $PWD '.cache/tiktoken'
```

OPENAI_MODEL is configurable; the requested gpt-4.1-mini is the initial default.
Timeout can be 1-60 seconds and output tokens 1-4,000. Configuration is read
when analysis starts. Invalid settings return a sanitized 503. No .env loader
is used. The provider URL is fixed to the official OpenAI API; provider endpoint
overrides are not supported in this phase. Account/model access, billing, and
rate limits must be configured separately by the user.

### Analyze a previously uploaded dataset

After uploading with the earlier command, use its returned UUID:

```powershell
$body = @{
  dataset_id = $datasetId
  question = 'Which category generated the highest total revenue?'
} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/analyze' -Method Post -ContentType 'application/json' -Body $body
```

Questions must contain meaningful text, be at most 2,000 characters, and exclude
unsupported controls. Extra request fields are rejected. A verified fake-model
example executes this SQL and explains its actual result:

```json
{
  "answer": "Electronics generated the highest total revenue: 260.",
  "sql": "SELECT category, SUM(revenue) AS total FROM dataset GROUP BY category ORDER BY total DESC LIMIT 1",
  "columns": ["category", "total"],
  "rows": [["Electronics", 260.0]],
  "row_count": 1,
  "tools_used": ["inspect_dataset", "execute_sql"]
}
```

The returned SQL is the canonical query actually executed, including its row
cap. Tables contain at most 200 rows by default, 128 KiB of serialized values,
and JSON nulls for missing/nonfinite values. Native SQL integer results preserve
large integer precision; exact Decimal values are serialized as strings rather
than rounded floats. Timestamps are ISO strings. If multiple queries succeed, the
response table/SQL describe the latest successful query; tools_used records
the execution names only, not private prompts or provider traces. Statistics-only
or unsupported-question explanations have sql=null and an empty table.

### SQL validation and execution controls

SQLGlot parses the DuckDB dialect. Validation permits one SELECT from the
unqualified dataset table with optional alias. Referenced columns must exist;
projection aliases are allowed in GROUP BY, HAVING, and ORDER BY. The validator
checks exact AST node classes and rejects unknown expressions by default.

Supported operations: projections (including *), DISTINCT, arithmetic,
comparisons, AND/OR/NOT, IS NULL, BETWEEN, literal IN, LIKE/ILIKE, WHERE,
GROUP BY, HAVING, ORDER BY, and positive integer LIMIT. Safe functions are
SUM, AVG, MIN, MAX, COUNT, ABS, ROUND, LOWER, UPPER, LENGTH, and COALESCE.
Unknown tables/columns/functions, qualified catalogs/schemas, joins, subqueries,
CTEs, unions, window functions, casts, table/star modifiers, OFFSET, DDL/DML,
PRAGMA, SET, ATTACH, COPY, extension loading, file readers, and table functions
are rejected. This intentionally small subset may reject otherwise useful SQL.
SQL is capped at 8,000 characters and 256 AST nodes. Comments are removed from
canonical SQL; trailing comment-only parser nodes have no executable meaning.
LIMIT is clamped/inserted as a parsed integer AST node, never interpolated user
text. There are no application-supplied string SQL values; existing internal
filtering continues to use bound parameters.

Each execution creates a fresh in-memory DuckDB connection and registers only
the selected frame. External access, unsigned extensions, automatic extension
installation, and automatic extension loading are disabled. The temporary
spill directory is empty, removing DuckDB's automatic temporary-directory access
exemption; connection configuration is locked. Defaults are one
DuckDB thread, a 128 MB engine memory limit, zero temporary spill space, a
5-second interrupt timer, a 200-row cap, and a 128 KiB result-value cap. SQLLimits
allows bounded developer overrides. Connections/timers are cleaned on failure
and success. Engine memory limits do not cover every Pandas/Python allocation.
Dataset schema/statistics supplied to the model are limited to 32 KiB each.

**Security limitation:** embedded DuckDB runs with the host process's privileges.
AST validation and connection settings are defense in depth, not a complete
sandbox. Timer interruption and memory settings are practical limits, not strict
OS-enforced isolation. Keep this phase local-only using 127.0.0.1 and one worker.
Before public untrusted execution, use a separately restricted execution process
or container, authentication, and broader resource/security controls. No public
deployment is implemented. UUIDs still do not authenticate users.

Model-written explanations can still misunderstand questions or misstate facts;
review the SQL and computed table. Deterministic tests verify actual SQL output
against known retail totals and Pandas, rather than treating model prose as proof.
Prompt-injection instructions in dataset contents are ignored by policy, but a
prompt is not a complete defense against malicious content. Tool/SQL boundaries
remain enforced independently of the model.

### Testing without an API key; optional approved live test

Run the existing full-suite command. Fake tool-calling models exercise the real
create_agent graph and real restricted DuckDB execution. Tests cover all verified
retail totals (260, 150, 120, total 530), tool selection, evidence, retries,
model/tool limits, SQL bypass attempts, interruption, provider error mapping,
dataset isolation, and upload-to-analysis JSON responses. The autouse fixture
blocks ChatOpenAI generation before any network call and removes API keys from
test configuration. No live API smoke test is part of automated verification.

A live test can incur OpenAI charges. After explicit user approval for a live
smoke test, configure the process key, start the localhost server, upload the
sample, and run the analyze command above once. Review the returned SQL/table
against known totals; do not rely only on prose. This live test has not been
performed for Phase 3. Stop the server and remove the process key when done:

```powershell
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
```

References: [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents),
[OpenAI GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
and [SQLGlot](https://sqlglot.com/sqlglot.html).

## Planned phases

Later phases may add Plotly charts, Streamlit, conversational follow-ups,
agent evaluation, Docker, and deployment. Stop after Phase 3; none of those
components is implemented here.
