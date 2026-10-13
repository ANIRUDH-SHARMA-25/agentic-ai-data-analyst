# Honest local demo and portfolio guide

## A five-minute demo with no provider access

1. Start the two key-free Python services using the root README. Do not use the
   encrypted-key startup helper. Bind both listeners to 127.0.0.1. All provider
   generation and metadata requests remain on hold.
2. Open Streamlit and choose **Try the retail sample**, or upload
   data/sample/retail_sales.csv with **Load dataset**. Preview the 12 rows and
   6 columns, column types, zero missing values and descriptive statistics.
   Refresh overview to demonstrate the HTTP inspection path. Health checks,
   upload and inspection make no Gemini calls. Do not submit a live question.
3. Run the deterministic benchmark and point out its MOCKED / DETERMINISTIC
   label. It executes the actual agent/tools/API/SQL path with scripted model
   choices; independent Pandas calculations verify tables. Verified totals are
   revenue 530, Electronics 260, Home 150, Stationery 120; these are numerical
   test evidence, not a Gemini-produced result.
4. Demonstrate mocked Streamlit widget/chart integration with the tests below.
   They execute the real UI, render a category bar chart and an ordered time
   series from explicitly injected results, and inspect Plotly chart values.
   AppTest verifies widget state; it is not a screenshot of a live Gemini run.
5. Explain the intended live flow using the architecture guide. State that the
   single approved plain-text Gemini request returned Google 503 UNAVAILABLE,
   and that genuine model answers, SQL choice, follow-ups and live charts still
   require separately approved verification. Docker runtime remains untested.

```powershell
.\.venv\Scripts\python.exe -m examples.inspect_retail
.\.venv\Scripts\python.exe -m evaluations.benchmark --output .tmp/demo-benchmark.json
.\.venv\Scripts\python.exe -m pytest -q tests/test_frontend.py -k 'app_empty_upload_analysis_rerun_and_clear or app_line_rendering' --basetemp=.tmp/pytest-demo
```

The example uses predefined trusted-Python DuckDB operations and makes no model
call. The chart tests are mocked, explicitly labeled evidence. There is no new
demo service or fabricated screenshot. If capturing a screenshot later, use the
key-free running application with real sample metadata, omit credentials/session
IDs, and label the capture “local dataset inspection; no Gemini analysis”.
Stop local servers after the demo. UI clear resets context/display, while backend
datasets remain until lazy expiry or shutdown; explain that limitation if asked.

## Suggested interview points

- Keep language interpretation separate from computation: the agent chooses
  tools, SQL is validated, and charts come from returned values.
- Explain why 28/28 scripted cases validate workflow correctness rather than
  model accuracy; describe independent numerical oracles and rejection cases.
- Explain dataset-bound conversation memory and fresh evidence on follow-ups.
- Discuss the two audit fixes and why embedded DuckDB/UUIDs are not enough for
  public multi-user operation.
- Describe upstream 503 separately from the backend's translated 502.

## Resume bullet suggestions

Use only wording consistent with your own contribution and demonstrated scope:

- Developed a local CSV analytics application with Streamlit, FastAPI and a
  single LangChain/LangGraph agent integrating Gemini and restricted DuckDB SQL.
- Implemented dataset-bound conversational context, SQL validation/resource
  controls, sanitized provider diagnostics and deterministic Plotly charts.
- Verified 28/28 scripted benchmark cases with independent Pandas expectations
  and an automated suite covering API, SQL rejection, sessions and UI behavior.
- Completed a focused security review, fixing oversized analysis-body parsing
  and untrusted Markdown rendering; documented public-hosting prerequisites.

Do not claim production deployment, real Gemini accuracy, successful live
natural-language answers, independent security certification or sole authorship
unless you have separate evidence for those claims. See phase8-verification.md
for the final automated test count; Gemini availability remains an open blocker.
