# Agentic AI Data Analyst development instructions

## Scope
Phases 1 and 2 implement reusable CSV validation/inspection, in-memory DuckDB,
synthetic data, dataset sessions, the FastAPI backend, and automated tests.
Stop after Phase 2. Do not add agents, LLM integrations, /analyze, charts,
Streamlit, Docker, or deployment until requested.

## Architecture
- backend/data owns data functions and DatasetManager; keep them independent
  of UI/API code. backend/main.py exposes health, upload, and inspection only.
- backend/config.py validates environment settings; schemas.py owns Pydantic
  response models. Upload bodies and file bytes must both be bounded.
- Reuse the shared CSV parser for files and uploaded bytes; never persist uploads.
- Dataset sessions use UUIDs, UTC upload time, monotonic inactivity expiration,
  lazy cleanup, and a capacity limit. Store independent copies; do not expose
  mutable session state. This version is single-process; UUIDs are not auth.
- Keep temporary multipart spools under the D: repository's .tmp/uploads.
- frontend is reserved for Streamlit; evaluations for future agent evaluation.
- Planned stack: Python 3.11, Pandas, NumPy, DuckDB, LangChain/minimal LangGraph,
  one hosted LLM, FastAPI/Pydantic, Streamlit, Plotly, Pytest, Docker.
- Install only dependencies needed for the current phase. Do not add Spark,
  Airflow, TensorFlow, Redis, PostgreSQL, vector databases, background job
  services, or other infrastructure without explicit user authorization.
- Never expose raw SQL to users/LLMs. DuckDB's predefined internal operations
  are not a substitute for the future safe SQL execution layer.

## Conventions
Use straightforward functions/classes, type hints, clear errors, concise
comments, and meaningful HTTP codes. Preserve previous functionality/tests.
Never hardcode credentials. Keep .env, uploads/generated data, caches, and
virtual environments out of Git. Only the small synthetic sample is tracked.
Keep dependencies/artifacts on D:; reuse .venv, pip --no-cache-dir, and .tmp.
Run the full suite with D: basetemp, pip check, API import, and TestClient checks
before committing. Never claim a check passed without running it.
Use descriptive commits and push when the user authorizes it (authorized for
Phase 2 main commit/push). Stop at the phase boundary.
