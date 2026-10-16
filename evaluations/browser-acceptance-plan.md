# Prepared Gemini browser acceptance plan: NOT authorized for execution

> Later result (2026-10-16): a separately approved guarded real-browser run
> passed both questions in six successful Gemini requests and verified visible
> explanations, SQL/tables, Plotly charts, context and New conversation reset.
> See [the browser record](streamlit-browser-verification.md). Historical failures
> and proposals below remain preserved; no further API request is authorized.

> Historical plan: execution was separately approved and stopped on Question 1's
> third request with Google HTTP 429 RESOURCE_EXHAUSTED. The user later observed
> historical RPD 21/20 in AI Studio. See the [quota investigation](browser-quota-investigation.md).
> Its mapping is fixed offline; current quota after reset is unverified. No new
> requests are authorized and the existing report must not be overwritten.

Prepared offline on 2026-10-15. The user's approval covers preparation only.
No key was loaded/decrypted, no question was submitted in a browser, no Gemini
generation/metadata request was sent, and the prepared services were not started.
Existing key-free smoke-test services on 8000/8501 are separate from this plan.
No browser permissions, billing, model, application, Docker or dependencies changed.

## Exact scope and expected results

Use the existing retail sample only. In the actual Streamlit interface submit,
once each and in this order:

1. "List total revenue grouped by category, ordered highest to lowest."
2. "How much revenue did the second category in that list generate?"

Expected descending table: Electronics 260, Home 150, Stationery 120. The second
answer must explicitly identify Home as second with revenue 150. Correct
single-row Home/150, scalar 150 or complete correctly ordered grouped SQL output
is acceptable; the final explanation must still be correct and independently
validated. Actual inspect_dataset and execute_sql execution, fresh SQL evidence,
same conversation ID and correct retained prior grouped result are required.
Check genuine visible explanations, SQL/tool details, result rows and Plotly bars
in Streamlit. Mocked runner coverage does not stand in for this UI work.

After both cases pass, choose New conversation. Verify both displayed turns,
result tables and charts disappear while the dataset overview remains. The
backend DELETE must succeed and its report must record reset_verified=true.
The real conversation store deletes that context. Do not submit a third question
as a reset probe: the completed harness blocks every further analysis request.

## Enforced budget and isolation

`evaluations/browser_acceptance.py` is an evaluation-only wrapper around the
unchanged real FastAPI app, single agent and dataset-bound conversation store.
It uses the corrected existing table/explanation checks and wire-level budget.

- Hard maximum eight actual generation attempts total, at most four per case;
  normally three per question/six total. Failed attempts count too.
- At least 35 seconds between request starts across both questions, 60-second
  per-request timeout, 1200 output tokens, existing LOW thinking.
- Gemini 3.6 Flash Developer API endpoint only; zero SDK retries, no fallback,
  model switching or metadata requests.
- One backend process/worker, serialized analysis. Duplicate, overlapping,
  out-of-order, extra-question, changed-dataset or wrong-conversation submissions
  are blocked before another dispatch and latch the run closed on failure.
- Reruns/refresh/inspection do not reset the backend counters. New conversation
  does not reopen the gate. Failure or completion closes analysis permanently.
- A report is exclusively reserved at startup; reusing its path refuses startup.
  A process crash/restart is not permission to use a fresh report. No automatic
  restart/reload, supervisor, second worker or alternate live backend is permitted.
- Only the fingerprint-checked tracked synthetic sample may reach generation.
  A different upload can be inspected key-free, but cannot trigger generation.

The request cap protects against ordinary UI reruns and repeated submissions,
not deliberate removal of the harness or launching another credentialed server.
An already dispatched request cannot be recalled if a concurrent UI failure is
noticed; the gate prevents subsequent dispatches. Visual defects still require
the operator to stop before submitting the next approved question.

## Prepared execution sequence: requires new explicit approval

1. Obtain explicit approval for this exact two-question/eight-attempt browser
   run and fresh confirmation that AI Studio currently shows Free with billing
   disabled. The application cannot independently audit billing state.
2. Review `scripts/prepare_browser_acceptance.ps1`. Only after that approval,
   run it with -Execute -FreeTierConfirmed. Its defaults refuse startup. It
   requires unused ports 8002/8502 and the existing encrypted D: key; it never
   rewrites the key or calls setup/enables billing.
3. The launcher decrypts the key locally for the guarded backend process only,
   removes provider credentials before starting Streamlit, then restores the
   launcher's prior environment and disposes the SecureString. The frontend
   has no key. Hosted tracing and telemetry are disabled; logs remain ignored.
4. Verify backend health and fresh report counters (zero attempts), then open
   http://127.0.0.1:8502 in the actual browser. Both services bind 127.0.0.1 only.
   Do not use the ordinary smoke-test page at 8501 for live analysis: it has no
   shared browser-test budget. Backend access logging is disabled.
5. Load Try the retail sample. No file-picker permission change is needed.
   Verify overview 12 rows/6 columns/zero missing. Submit Question 1 once.
   Wait for completion; review the report, final explanation, table, SQL/tools,
   and Plotly bar labels/values. Stop on any provider/application/SQL/numerical/
   explanation/context/chart problem; do not correct or resubmit.
6. Only if Question 1 passes and the UI is sound, submit Question 2 once in the
   same conversation. Review the genuine Home/150 answer, SQL evidence, chart,
   retained prior context and unchanged conversation ID. Stop on any failure.
7. If both pass, use New conversation and verify clearing/reset as above. Record
   final wire counts/statuses, UI observations and reset evidence. No additional
   analysis request, metadata call or automatic evaluation follows.
8. Capture only synthetic result areas, excluding terminals, key setup, browser
   account/profile UI and session identifiers. Inspect captures before sharing.
   Stop only the two test-owned service process trees after reviewing results;
   include Windows venv child interpreters, not unrelated local services.

## Diagnostics and remaining acceptance risks

Fresh report: `.tmp/browser-acceptance-live.json` on D:. Generated SQL/table/tool
facts and allowlisted provider statuses are local. Final explanations are
redacted, limited to 4096 characters/8192 UTF-8 bytes, with bounded claim-failure
excerpts. Reports are atomically replaced; no raw provider body/exception,
credential, prompt or conversation ID is logged by the harness. Report/screenshots
and launcher logs remain ignored local files, never Git artifacts. No generated
reply is printed to the console. Browser screenshots require manual visual review
because automatic credential redaction of pixels is not guaranteed.

The direct file-picker limitation remains documented; the retail-sample button
already exercises upload/inspection. Browser display and nonempty reset remain
unverified until this specifically approved execution. The prior six-request
API evaluation and 28-case MOCKED benchmark are separate evidence. A pass here
would verify this narrow synthetic UI flow, not broad Gemini accuracy or public
hosting readiness. Docker runtime and public-hosting security work remain outside
scope. Provider availability/quota cannot be proven offline; stop on first error.

## Offline preparation checks

- Sealed SDK MockTransport exercises the actual agent/tools/SQL/API path for both
  questions, preserves the conversation ID, validates full-table follow-up shape,
  and confirms the real reset endpoint invalidates the old conversation.
- Regressions cover no-approval startup, lazy/no-call health and inspection,
  failed provider/tool/SQL/explanation, duplicate/out-of-order/wrong-context/
  changed-dataset/extra submissions, non-synthetic input, overlapping requests,
  exhausted wire budget, no repeat/restart, timing and diagnostic redaction.
- Existing wire-budget tests also exercise four-per-question/eight-total limits;
  existing frontend tests cover displayed history clearing and mocked charts.
- Focused suite: 126 passed. Final complete suite after atomic report-write
  refinement: 518 passed, zero failed. Mocked benchmark: 28/28 (SQL 18/18,
  follow-ups 3/3, SQL rejections 4/4). pip check passed.
- Prepared PowerShell launcher syntax parsed without executing it or reading the
  encrypted key. No new dependencies or application changes are needed.

STOP: obtain separate explicit execution approval before running this plan.
