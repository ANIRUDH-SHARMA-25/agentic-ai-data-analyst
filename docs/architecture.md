# Architecture and interview guide

## Data and request flow

Streamlit sends HTTP requests to FastAPI. Upload bytes are bounded before
multipart parsing, validated as UTF-8 CSV, parsed by Pandas and stored as an
independent DataFrame copy in DatasetManager. A UUID identifies the snapshot.
Inspection returns counts, preview and descriptive statistics without Gemini.

For analysis, FastAPI retrieves a copy and acquires a dataset-bound conversation
lease. DataAnalysisAgent creates a fresh LangGraph-backed LangChain agent and
three closures over that copy: inspect_dataset, get_statistics and execute_sql.
The Gemini Developer API receives the question, selected schema, optional
historical context, and tool results as the run progresses. It does not receive
a filesystem capability or a user-selectable dataset ID inside tools.

A schema inspection must precede other tools. SQLGlot parses and canonicalizes
one allowed SELECT; DuckDB registers only the snapshot as dataset. Results pass
row, type, byte and timeout checks. Successful API responses contain prose,
validated SQL, columns, rows, tool names and a conversation UUID. Five compact
successful turns are retained; failed requests do not add evidence. Statistics
evidence is kept privately for context, not exposed as an extra API field.

The frontend validates the response, shows text/table/SQL and uses deterministic
Plotly rules. An unambiguous label plus numeric measure can form a bar chart;
ordered unique date labels can form a line chart. No model-produced plotting
code is executed; ambiguous/oversized/precision-losing charts are refused.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| backend/main.py, schemas.py, config.py | API, typed validation and local settings |
| backend/upload_limits.py | Upload and analysis body caps before parsing |
| backend/data/csv_processing.py | CSV validation and Pandas inspection |
| backend/data/dataset_manager.py | Locked snapshot store, capacity and lazy TTL |
| backend/conversations.py | Dataset binding, concurrent-turn exclusion and bounded evidence |
| backend/agent/config.py, analyst.py | Fixed Gemini route/config and one agent workflow |
| backend/agent/diagnostics.py | Allowlisted upstream error classification |
| backend/data/safe_sql.py | Fail-closed SQL subset and bounded embedded execution |
| backend/data/duckdb_store.py | Original trusted-Python predefined analytics helper; not the agent executor |
| frontend/api_client.py, session.py | HTTP response checks and UI session transitions |
| frontend/app.py, charts.py | Native widgets, plain-text chat and deterministic charts |
| evaluations/benchmark.py, fake_model.py | Scripted actions and independent numerical oracles |
| evaluations/*gemini*.py | Separately approval-gated live harnesses; not run in CI |
| tests/, .github/workflows/ci.yml | Offline regression coverage and key-free verification |
| docker/, compose.yaml | Local container configuration, runtime unverified |

## Why a single agent

The task has one selected dataset and three narrowly scoped tools. One graph
keeps evidence, tool limits, errors and conversation handling understandable.
Additional agents, RAG, vector storage or distributed services would increase
complexity without solving a demonstrated need. The model handles language and
tool choice; application code owns authorization boundaries, SQL checks and
visualization rules. No authentication boundary is currently implemented.

## A concise interview explanation

“I built a local CSV analysis workflow with a Streamlit UI and FastAPI backend.
The agent is designed to inspect the dataset before computing results through a
restricted SQL tool. SQL results, not model prose, are the numerical evidence.
I tested the workflow with scripted actions and independent Pandas expectations.
The 28-case benchmark is mocked; the real Gemini integration still needs live
verification because the approved plain-text diagnostic returned upstream 503.
The application remains local-only because UUIDs are not authorization and
embedded DuckDB is not independently sandboxed.”

Do not describe a model request timeout as a whole-run deadline or a dataset
UUID as a user account. Client timeouts do not cancel backend work, and multiple
processes would have separate in-memory session stores.
