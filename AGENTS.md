# Agentic AI Data Analyst development instructions

## Scope
Phase 1 implements the reusable data layer only: CSV validation/loading,
inspection, synthetic sample data, in-memory DuckDB analytics, and tests.
Stop after Phase 1. Do not add an agent, LLM integration, UI, API endpoints,
Docker, or deployment until requested.

## Architecture
- backend/data owns reusable data functions; keep it independent of UI/API code.
- frontend is reserved for Streamlit; evaluations for future agent evaluation.
- Planned stack: Python 3.11, Pandas, NumPy, DuckDB, LangChain with minimal
  LangGraph, one hosted LLM, FastAPI/Pydantic, Streamlit, Plotly, Pytest, Docker.
- Install only dependencies needed by the current phase.
- Do not add Spark, Airflow, TensorFlow, Redis, PostgreSQL, vector databases,
  or other infrastructure without explicit user authorization.
- DuckDB sessions are isolated and in memory. Predefined operations are not
  a substitute for the future safe SQL execution layer. Never expose raw SQL
  to users or LLMs in Phase 1.

## Conventions
Use straightforward functions/classes, type hints, clear errors, and concise
comments. Preserve existing files and avoid unnecessary abstractions.
Never hardcode credentials. Keep .env, uploaded/generated data, caches, and
virtual environments out of Git. Only the small synthetic sample is tracked.
Keep dependencies and artifacts on D:; use .venv, pip --no-cache-dir, and
.tmp for temporary files. Run tests with a D: basetemp before committing.
Do not claim a successful check without running it. Use descriptive commits;
push only when the user has authorized it (authorized for initial Phase 1).
