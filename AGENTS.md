# Agentic AI Data Analyst development instructions

## Scope
Phases 1-8 are authorized: CSV processing, internal DuckDB helpers, dataset
sessions, FastAPI, one LangChain create_agent workflow using LangGraph and
langchain-google-genai, the Gemini Developer API, restricted SQL, and deterministic tests.
Use gemini-3.8-flash only, as approved by the user after Google restricted 2.5
Flash to existing users. No model/provider fallback. Phase 4 adds native Streamlit and deterministic
Plotly charts over the existing HTTP API. Phase 5 adds bounded dataset-bound
conversation memory and deterministic mocked evaluations. Phase 6 adds local
Docker Compose, basic CI, and deployment documentation. Phase 7 switches providers and permits a small live evaluation only after
free-project confirmation, secure local key entry, and separate human approval.
Phase 8 authorizes a focused security audit, targeted regression fixes,
repository/documentation polish and portfolio material only. Stop after Phase 8.
Do not add public/cloud deployment, RAG/vector databases,
multiple agents, or background infrastructure until explicitly requested.

## Architecture and safety
- backend/data owns CSV processing, DatasetManager, and safe_sql. Keep it
  independent of API/LLM code. Preserve the original DuckDBDataset helper/tests.
- backend/agent owns lazy model configuration and the single analytical agent.
  Use current LangChain create_agent, not a custom multi-agent graph.
- FastAPI exposes health, upload, dataset inspection, and POST /analyze.
  Pydantic schemas type requests/responses. Reuse existing dataset functions.
- Bind all agent tools to the request's DataFrame snapshot. Tools accept no
  dataset IDs. Expose only inspect_dataset, get_statistics, execute_sql.
- Treat dataset contents/questions/tool evidence as untrusted data. Explain
  actual tool results; never invent computed values or substitute fake answers.
- Validate every SQL attempt with SQLGlot's DuckDB parser and a fail-closed
  expression/function allowlist. Only one SELECT from dataset; no joins,
  subqueries, CTEs, DDL/DML, file functions, extensions, or arbitrary functions.
- Use fresh in-memory connections with external access and automatic/unsigned
  extensions disabled. Enforce row, result byte, memory, thread, and time limits.
  Validation/settings are defense in depth, not a complete sandbox. Keep the
  API local-only. Public untrusted execution needs a separate restricted process
  or container plus authentication and a broader security design in a later phase.
- Cap model calls and tool calls, select one tool per turn, allow only one SQL
  correction, and never bypass validation. Disable hosted tracing for analysis.
- Read keys from the process environment. Do not log them, prompts, raw provider
  exceptions, or tracebacks in API responses. Start/import without an API key.
- Never make billable/live API calls in tests. The test fixture blocks ChatGoogleGenerativeAI
  generation. No live smoke test without explicit human approval.
- Dataset sessions remain single-process with independent copies, lazy TTL,
  UUID IDs, UTC upload time, and capacity limits. UUIDs do not authenticate users.

## Development conventions
Use simple functions/classes, type hints, concise comments, and useful errors.
Preserve prior functionality/tests; update phase-boundary assertions when the
user explicitly authorizes an endpoint. Install only phase-relevant packages.
Do not introduce Spark, TensorFlow, Airflow, Redis, PostgreSQL, or new services.
Keep .venv, temporary spools, generated artifacts, uploads, and caches on D:;
use pip --no-cache-dir. Never track secrets or generated files. Only the small
synthetic sample is tracked. Run the entire suite with D: basetemp, pip check,
key-free API import, SQL rejection cases, and mocked upload-to-analysis checks
before committing. Report actual checks and remaining limitations.
Use descriptive commits; the user authorized Phase 8 commit/push to main.
Stop at the phase boundary.

## Frontend
Use HTTPX only; never import backend session or agent objects into Streamlit.
No plotting code from an LLM, eval/exec, or extra model calls. Chart actual values
conservatively, bound histories and displays, and never retry paid requests silently.
Keep compact successful context in backend memory; reset frontend conversation IDs
and displayed history when datasets change or the user starts a new conversation. Keep secrets
in the backend process environment and mock HTTP/model calls in frontend tests.

## Phase 5 verification
No real OpenAI calls, API-key requirement, or billable services in this phase.
Keep one agent and existing SQL limits. Previous context is untrusted historical
data, never fresh evidence. Bound conversations, reject dataset mismatches and
concurrent writes, and save only completed successful turns. Evaluate with fake
models against independent numerical expectations, label reports MOCKED, and
run the full suite and deterministic benchmark before committing.

## Phase 6 deployment
Use two official Python 3.11 slim images, non-root users, exactly one backend
worker, HTTP between services, and host ports bound to 127.0.0.1. Keep keys
out of build context/images/frontend; accept an optional backend key only at
runtime. Restrict temporary writable paths and resources. Container settings
are defense in depth, not an independent SQL sandbox. Do not install/migrate
Docker, change Docker Desktop settings, delete user resources, expose publicly,
or call live OpenAI. Verify Python/tests/evaluation and available Docker checks;
report blocked Docker runtime checks accurately. Keep generated reports on D:.

## Phase 7 zero-cost requirements
Use Gemini Developer API explicitly (vertexai=False), GOOGLE_API_KEY only in
the backend, and GOOGLE_MODEL=gemini-3.8-flash. Before model construction require
GOOGLE_FREE_TIER_CONFIRMED=true, a human confirmation that the project is Free
with billing disabled; this is not an API billing verification. Never enable
billing, register payment methods, buy credits, use paid APIs, add OpenAI
fallback, or switch models on quota exhaustion. No automatic provider retries.
Use only synthetic data: Google may use free-tier content to improve products.
Automated tests and the mocked benchmark never call a provider. Keep actual
live results separate and count requests; no live call before explicit approval.
Keep all key entry local and masked, with secrets absent from logs/Git/frontend.
Do not install Docker/WSL, publicly deploy, or add unrelated features.


## Phase 8 security review and portfolio readiness
Preserve application behavior, SQL allowlists, model/provider selection and
free-tier safeguards. Make no Gemini generation or metadata requests. Do not
install Docker/WSL or new software for the audit, enable billing, or deploy
publicly. Only targeted fixes for demonstrated defects are in scope; document
major architectural gaps. Use local-development-only classification. Distinguish
mocked benchmark success from real-model accuracy. Document the observed Google
503 UNAVAILABLE and unverified Docker runtime honestly. Demo upload/inspection
and mocked charts without a provider key; never label scripted output Gemini.
Run full offline tests, benchmark, dependencies/imports and available static
container checks; verify secret/artifact exclusions, then commit/push to main
and check CI. Stop after Phase 8; no subsequent live test is authorized.
