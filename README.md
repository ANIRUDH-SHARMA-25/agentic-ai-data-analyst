# Agentic AI Data Analyst

A resume-focused AI/ML project that will let users upload CSV data, ask
natural-language questions, and receive computed analysis, charts, and
AI-generated explanations. **Phases 1-7 implement data processing, the HTTP API, one analytical agent, the Streamlit dashboard, bounded conversation memory, mocked evaluations, and local container/CI configuration.**

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
backend/conversations.py      bounded dataset-bound conversation manager
backend/config.py             validated API configuration
backend/schemas.py            typed response schemas
backend/upload_limits.py      bounded upload request handling
backend/data/                 CSV processing, DuckDB, sessions, restricted SQL
backend/agent/                lazy Gemini model config and one LangChain agent
frontend/                     Streamlit dashboard, HTTP client, chart rules
data/sample/                 small tracked synthetic dataset
evaluations/                 deterministic benchmark and network-free model
examples/                     runnable Phase 1 demonstration
tests/                        data layer, sessions, API, agent, and frontend tests
docker/                       separate images and local deployment guide
compose.yaml                  local-only backend/frontend services
.github/workflows/ci.yml       key-free Python verification on main pushes/PRs
requirements-*.txt            pinned runtime dependencies per service
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
files are not loaded automatically by Python. Set environment variables in PowerShell.
Docker Compose can read an optional .env for interpolation; see the container guide.

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
| `POST /analyze` | Analyze a selected dataset; optionally continue a conversation | 200 |
| `DELETE /conversation/{conversation_id}?dataset_id=UUID` | Clear conversation context for the selected dataset | 200 |

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
| 409 | Conversation is busy or belongs to a different dataset |
| 410 | Conversation is unknown, expired, or cleared |
| 503 | Dataset capacity reached or Gemini configuration/access unavailable |
| 429 | Gemini rate limit reached |
| 502 | Provider/model failed to produce a complete grounded answer |
| 504 | Gemini or SQL execution timed out |

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
The installed LangChain/LangSmith dependencies include the HTTPX support used
by Starlette TestClient. Tests block live Gemini generation
and disable hosted tracing; no real key, API calls, or billed tokens are used.

## Phase 3: one tool-using analyst

Each analysis request gets a fresh LangChain `create_agent` graph (LangGraph
underneath), one configured ChatGoogleGenerativeAI model (switched from OpenAI in Phase 7), and three closures bound to that
request's dataset snapshot. Phase 5 supplies compact backend-managed context;
there is no durable conversation storage or LangGraph checkpointer,
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
the question are sent to Gemini when a real analysis is requested.

A first SQL validation/execution error is returned as sanitized tool feedback,
allowing one correction. A second failure ends the request. Both attempts use
the same validator. SQL timeouts end immediately. The API refuses a successful
answer after unresolved SQL errors or without schema inspection. Provider
failures produce clear errors rather than fabricated fallback answers.

### Configure Gemini securely (free tier only)

Phase 7 uses the official `langchain-google-genai` integration and
`ChatGoogleGenerativeAI`, with **gemini-3.8-flash** only. The user approved this
model after Google's [2.5 Flash notice](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)
restricted 2.5 access to existing users. Google currently lists 3.8 Flash
standard input/output tokens as free and supports function calling. See
[pricing](https://ai.google.dev/gemini-api/docs/pricing) and
[model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash).

Create a key in [Google AI Studio](https://aistudio.google.com/api-keys) for a
project showing **Free**, with billing disabled and no linked billing account.
Do not enable billing, add payment details, upgrade, or purchase credits.
A model name or key alone cannot prove the project is free. This application
requires `GOOGLE_FREE_TIER_CONFIRMED=true`, a human attestation; it does not
verify the project's billing state through a Cloud API. Stop if free access
is unavailable. There is no alternate model/provider or OpenAI fallback.

Run locally in PowerShell (never paste the key into Codex):

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_gemini.ps1
```

The script asks you to type FREE after checking AI Studio, then accepts a
masked key. It saves only a Windows DPAPI-encrypted file in ignored `.tmp` on D:,
readable by your Windows account, and makes no API call. The execution-policy
option applies to this process only. Keep the encrypted file private too.
After setup, the following script starts localhost servers in hidden processes,
passes the decrypted key only to the backend, and prints their PIDs for stopping:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

Startup, upload, and inspection make no Gemini calls. Opening the dashboard
alone makes none. **Do not submit analysis until the requested separate approval
for live free-tier calls has been given.** The script prints a Stop-Process
command for just its server PIDs. Stop them after verification.

Manual environment configuration remains supported: GOOGLE_API_KEY,
GOOGLE_MODEL=gemini-3.8-flash, GOOGLE_FREE_TIER_CONFIRMED=true,
GOOGLE_TIMEOUT_SECONDS=30, and GOOGLE_MAX_OUTPUT_TOKENS=1200. Enter secrets
through a masked prompt, never literal command history. No .env loader is used
by Python. Imports/health work without credentials; analysis returns 503 until
key and free-project confirmation are present. Both inherited Vertex AI and
Enterprise routing flags are rejected before client construction. The official
Developer API endpoint is fixed; SDK backend selection is also checked.

Requests use low reasoning effort, text responses, no exposed thoughts, a
30-second timeout, the existing token/call/tool bounds, and **zero automatic
provider retries**. Google quotas are per project (not per key) and include
requests/minute, tokens/minute, and requests/day. Exact current limits depend
on the project/model; check [active limits in AI Studio](https://ai.google.dev/gemini-api/docs/rate-limits).
Daily quotas reset at midnight Pacific time. One question makes multiple model
requests; the normal agent permits at most eight. A 429 returns a clear quota
message; it never upgrades, switches models, or retries automatically.
Free-tier content may be used by Google to improve products: use only synthetic
data. Do not send sensitive datasets, questions, or conversation context.

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
  "conversation_id": "ed34b274-3e8d-4b29-9df3-1096d739cd56",
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

### Mocked and separately approved live verification

The complete suite and existing 28-case benchmark remain network-free. The
fixture removes provider keys, disables tracing, and blocks synchronous and
asynchronous ChatGoogleGenerativeAI generation. Provider errors, quota refusal,
free-tier confirmation, inherited paid routes, and Gemini text content blocks
have dedicated regressions. All previous SQL and memory safeguards remain.

For the small separately approved live evaluation, see
[evaluations/README.md](evaluations/README.md). Real results belong in a separate
ignored report with request counts; mocked results are never presented as
Gemini accuracy. Neither setup nor CI runs that live evaluation automatically.

References: [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents),
[Google integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai),
and [SQLGlot](https://sqlglot.com/sqlglot.html).

## Planned phases

Later authorized work may add real-model quality testing, security review, and
public deployment. Stop after Phase 7; public deployment is not authorized.

## Phase 4: Streamlit dashboard

Keep the backend running in its own PowerShell terminal. Open a second terminal:

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
$env:BACKEND_URL = 'http://127.0.0.1:8000'
$env:FRONTEND_REQUEST_TIMEOUT_SECONDS = '30'
$env:FRONTEND_ANALYSIS_TIMEOUT_SECONDS = '300'
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

Open [the dashboard](http://127.0.0.1:8501). Select a CSV and click **Load dataset**,
or use **Try the retail sample**. Upload/inspection works without an Gemini key.
Configure the key only in the backend terminal for real analysis; the frontend
never reads provider credentials. Both terminals use process environment settings,
not automatic .env loading. Stop either server with Ctrl+C.

The sidebar supports connection checking, refreshing inspection, and clearing
the selected dataset/history. The overview shows rows, columns, missing cells,
preview, types, and statistics. Chat responses show the explanation, result table,
and expandable executed SQL/tool names. Follow-ups use the latest five successful
turns for the selected dataset; the interface displays at most 10 questions.
New conversation clears backend context and displayed chat while retaining the
dataset. Changing datasets clears the old conversation and results before uploading; failed inspection can be
retried explicitly without duplicating the upload. Streamlit reruns alone perform
no HTTP requests. Session state retains metadata and bounded responses, not an
extra full DataFrame or raw CSV copy; Streamlit's uploader retains its input file
while selected. No uploads are permanently stored.

Charts use actual returned values and deterministic rules, with no extra model
call or generated Python. Exactly two distinct columns must contain one numeric
measure and unique string labels. Category comparisons become bars (at most 20
categories); ISO dates/months/timestamps become chronologically sorted lines
(at most 100 points). Missing numeric values remain line gaps; incomplete bar
rows are excluded with a notice and remain in the table. Ambiguous dimensions,
invalid/mixed dates, duplicate labels, single values, and precision-losing numbers
remain tables. No frontend aggregation changes values. Nullable integers retain precision;
very large integers and mixed-type columns are displayed as exact text.
Result tables show at most
200 rows and overview tables at most 100 columns. Charts are interactive.

HTTPX uses the existing health/upload/inspection/analyze endpoints with no
automatic retries. Connection/configuration, expiry, upload, unsupported question,
and provider errors appear as understandable messages. Request timeout can be
1-120 seconds and analysis timeout 1-600 (defaults 30/300). The agent can take up
to eight configured provider timeouts plus local work; increase the frontend
timeout when increasing backend limits. A frontend timeout does not cancel the
backend request: avoid resubmitting immediately. The client accepts at most 2 MiB
of response content after receiving it. UPLOAD_MAX_BYTES defaults to 5 MiB and
should match in both processes; frontend configuration permits up to 50 MiB.
Streamlit's server upload cap is also 5 MiB; override --server.maxUploadSize with
the desired whole-MiB cap if increasing the configured byte limit. Backend
validation remains authoritative.

The privacy notice states that real analysis sends the question, recent conversation context, and relevant
dataset-derived information to the configured LLM provider. This remains a
local, single-user portfolio application, with the Phase 3 security limitations.

Frontend tests cover mocked HTTP contracts/errors, faithful retail totals
(260/150/120), chart refusal/order/missing data, session transitions, and actual
Streamlit AppTest upload, overview, chat, charts, expiry, and configuration errors.
All tests forbid live Gemini generation. Run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp/pytest
.\.venv\Scripts\python.exe -m pip check
```

## Phase 5: basic conversational memory

POST /analyze still accepts the old dataset_id/question request. Omitting
conversation_id (or sending null) starts a fresh conversation; every successful
HTTP response additionally returns conversation_id. Send it with the same
dataset_id for subsequent questions:

```json
{
  "dataset_id": "VALID_DATASET_UUID",
  "conversation_id": "UUID_FROM_PREVIOUS_SUCCESSFUL_RESPONSE",
  "question": "Which category was second?"
}
```

The dataset_id remains authoritative. Conversations cannot select another
session or supply tool arguments. Invalid UUIDs return 422; unknown/expired
conversation IDs return 410; a different dataset or simultaneous request to
the same conversation returns 409. Expired datasets return 404. No model call
is made for a rejected ID, capacity check, or busy conversation.

ConversationManager retains at most 100 conversations, each with the latest
five completed successful turns. Each turn is capped at 4 KiB of UTF-8 JSON
(about 20 KiB of retained evidence per conversation, plus container overhead).
Evidence includes the prior question, executed SQL, at most 20 columns/five
result rows, original row count, tool names, and bounded verified statistics.
Oversized evidence is omitted with an evidence_truncated flag; if necessary
the question is shortened. No complete dataset, full tool-message transcript,
or unverified model prose is retained as historical numerical evidence.
Statistics are attached privately during analysis, not added to the public API.

Each request creates the same single LangChain agent with fresh request-local
tools. Historical JSON is passed as a HumanMessage explicitly marked untrusted,
followed by the current HumanMessage. It is not promoted to system instructions
or replayed as old tool calls. Context assists reference resolution; schema
inspection is still enforced on every turn. A follow-up must additionally call
get_statistics or execute_sql for fresh evidence. Unsupported or ambiguous
follow-ups can inspect statistics and ask for clarification; previous results
cannot replace current tools. The original SQL allowlist, one correction,
model/tool limits, timeouts, sanitized errors, and disabled hosted tracing remain.
Model explanations can still be wrong; review SQL and results.

Memory is single-process and temporary. Inactivity expiry defaults to the same
DATASET_TTL_SECONDS as datasets (30 minutes). Cleanup is lazy on conversation
operations and failed dataset lookups/new uploads. Reading conversation context
does not extend dataset TTL. Successful analyses refresh conversation inactivity;
failed/partial/rejected analyses do not append evidence or refresh it. Dataset
expiry invalidates associated conversations. An analysis finishing after its
dataset expires returns 404 and is not retained. Busy conversations are protected
from inactivity pruning while the request runs, but not from dataset expiry.
Overlapping requests/reset on the same conversation return 409 immediately;
independent conversations can run concurrently. A bounded slot is reserved for
new requests and released if analysis fails.

Backend shutdown/restart discards datasets and conversations. UUIDs are session
selectors, not authentication. Keep one worker and localhost binding. There is
no persistent database, cross-worker memory, cancellation protocol, or background
cleanup service. A client timeout does not cancel backend work and may leave a
success the client did not receive; no paid request is retried automatically.

In Streamlit, only the conversation ID is sent with the next question; the
frontend never sends its entire chat transcript. New conversation explicitly
clears backend memory and displayed history. Dataset switches do the same.
Expired conversations preserve displayed results for reference, disable new
questions, and prompt an explicit reset while keeping the active dataset.
A dataset mismatch discards the unusable ID so a new conversation can recover;
busy/reset failures preserve current state. Network failures leave history and
context IDs intact without repeating an analysis.

## Deterministic evaluation (MOCKED)

No API key or real provider calls are required for Phase 5 verification.
The benchmark uses a network-free scripted chat model, the actual LangChain
agent, real restricted DuckDB execution, and multi-turn FastAPI requests.
Expected numerical tables are computed independently with Pandas; explanations
are not used as expected answers. Ties have explicit deterministic sorting.

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m evaluations.benchmark
# Optional generated report stays ignored on D:
.\.venv\Scripts\python.exe -m evaluations.benchmark --output .tmp/phase5-evaluation.json
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp/pytest
.\.venv\Scripts\python.exe -m pip check
```

The 28 cases cover 18 numerical SQL tasks, three follow-ups, four rejected SQL
attempts (unknown column, DDL, file reader, join), two isolation/ID checks, and
one unsupported question. The three follow-ups use previous verified evidence
to choose the next rank/filter, then execute fresh SQL. The seed question is
setup, not an extra scored case. Reports include total task success, SQL
correctness, follow-up context correctness, rejection behavior, per-case outcomes,
and measured duration; the command exits nonzero if a case fails. Output is
labeled MOCKED / DETERMINISTIC, never Gemini model accuracy. Report files are
restricted to the repo's ignored .tmp or artifacts directories.

These checks demonstrate conversation/data isolation, API/message integration,
SQL execution and bounds, not real natural-language interpretation, robustness
against all prompt injections, or Gemini explanation accuracy. Scripted models
have predetermined actions; changing a scripted SQL query to a wrong computation
fails against the independent oracle. Real-model quality is unverified and is
reserved for a later authorized phase. Normal configured live analysis remains
available from earlier phases, but no live calls are part of Phase 5 work.

See evaluations/README.md for the case inventory and result interpretation.
Phase 6 added local containers/CI. Phase 7 adds secure Gemini setup and a
separate, approval-gated live evaluation; no public deployment is authorized.


## Phase 6: local Docker deployment and CI

See [the Docker guide](docker/README.md) for Windows/D: storage preparation,
configuration, startup, troubleshooting, key-free smoke checks, and stopping.
The direct Python instructions above remain supported. Stop those servers before
Compose uses the same ports. After Docker Desktop is installed and running in
Linux-container mode, and its large disk-image storage is confirmed on D:

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
docker version
docker compose version
docker compose config --quiet
docker compose build
docker compose up -d --wait
docker compose ps
Invoke-RestMethod 'http://127.0.0.1:8000/health'
# Open http://127.0.0.1:8501 in your browser.
# When finished:
docker compose stop
```

Both images use official Python 3.11 slim Bookworm, pinned direct dependencies,
and UID/GID 10001. The backend has one Uvicorn worker; the frontend communicates
through HTTP at http://backend:8000. Only localhost ports 8000 and 8501 are
published. Compose configures health checks, read-only roots, bounded writable
tmpfs, dropped capabilities, no privilege escalation, and CPU/memory/PID limits.
These runtime settings still need verification on an actual Docker engine.
No host directory, Docker socket, persistent upload volume, or provider key is
copied into either image. The frontend receives no provider key at runtime.
Direct pins and a named base-image tag simplify rebuilding, but transitive
dependencies and base images can change; these are not immutable image locks.

The single GitHub Actions workflow runs on main pushes and PRs to main using
Ubuntu and Python 3.11. It installs the combined development requirements,
checks dependencies/imports, runs all tests, and runs the mocked benchmark.
Normal runner pip caching is enabled; no API secret or deployment job is used.

Phase 6 local verification: **337 tests passed**, **28/28 mocked tasks passed**
(SQL 18/18, follow-up context 3/3, rejection behavior 4/4), pip check and key-free
imports passed. Compose passed the official specification's JSON Schema and
the CI YAML parsed. Docker/Compose were not found on PATH or standard install
paths, including the per-user path; WSL reported not installed. Docker Desktop
settings/data paths were absent, so no existing Docker storage location could
be confirmed. C: had about 18 GiB free, D: about 140 GiB. Nothing was installed,
relocated, or deleted. **Docker CLI validation, image builds, container startup,
health/upload/inspection, frontend connectivity, missing-key behavior, writable
path checks, logs/restarts, and container stopping were not run.**
Follow the manual guide when Docker is available. No real Gemini calls occurred.

This is local deployment preparation, not approval for public hosting. The
SQL executor remains embedded in the backend process. Docker restrictions
and SQL allowlists are defense in depth, not complete SQL isolation. UUIDs
are not authentication; sessions disappear on restart. Access control, rate
limiting, stronger execution isolation, and session handling need a later
security review before public exposure. Stop after Phase 7.


## Phase 7 verification status

Gemini 3.8 Flash replaces the former OpenAI provider; requirements, Compose,
CI, missing-key messages, privacy text, and provider tests are updated. The
SDK route/retry/timeout configuration is checked without generation. The
28-case benchmark remains MOCKED / DETERMINISTIC, not Gemini accuracy.
Official free-tier availability is documented; account-specific access/billing
requires the user's AI Studio check. Secure key setup and live approval completed. Two generation attempts were
made: the initial 30-second request timed out (504), and the approved 60-second
rerun was rejected by the provider (502). Both runs stopped at their first
request; no live task completed. A separate model-metadata lookup succeeded,
confirming key/model access, not generation success or free quota. The user
confirmed Free tier with billing disabled; billing was not queried by the app.
See [the live status](evaluations/phase7-live-status.md). No Docker/WSL installation or public deployment
is part of Phase 7.
