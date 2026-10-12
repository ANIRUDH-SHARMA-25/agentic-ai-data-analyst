# Streamlit frontend

Run from the repository root with `.venv\Scripts\python.exe -m streamlit run frontend/app.py`.
See the root README for two-terminal PowerShell setup, configuration, privacy,
chart rules, timeouts, and limits.

- app.py: native dashboard and rendering
- api_client.py: HTTPX boundary and user-readable errors
- config.py: bounded frontend configuration
- charts.py: deterministic Plotly recommendations
- session.py: upload/session/history transitions

The frontend imports no backend state or agent code. Questions are independent,
and no paid request is retried automatically.
