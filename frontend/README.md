# Streamlit frontend

Run from the repository root with `.venv\Scripts\python.exe -m streamlit run frontend/app.py`.
See the root README for two-terminal PowerShell setup, configuration, privacy,
chart rules, timeouts, and limits.

- app.py: native dashboard and rendering
- api_client.py: HTTPX boundary and user-readable errors
- config.py: bounded frontend configuration
- charts.py: deterministic Plotly recommendations
- session.py: upload/session/history transitions

The frontend imports no backend state or agent code. It sends the current
conversation ID with follow-ups; the backend retains up to five compact
successful turns. Displayed history stays bounded to 10 questions. New
conversation clears backend context/history while retaining the dataset.
Dataset switches clear both the old conversation and displayed results.
Expired conversations require an explicit reset, and no paid request is
retried automatically. No API key is needed for AppTest/mocked verification.

Phase 8 renders questions and answers as plain text to prevent untrusted
Markdown image/link declarations. SQL tables and deterministic charts are
preserved. See ../docs/demo-portfolio.md for a key-free local demo.
