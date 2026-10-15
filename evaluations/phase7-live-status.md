# Phase 7 real Gemini status

Historical record: model references and results below describe their original
run. The configured model is now 3.6; see [the migration record](gemini-3.6-migration.md).

Model: gemini-3.8-flash (user-approved replacement for restricted 2.5 Flash).
Date: 2026-10-14, Asia/Calcutta.

Google's official pricing lists standard input/output tokens on the Free tier;
its model page supports function calling. The user confirmed their AI Studio
project is Free with billing disabled. Historical live approvals are exhausted;
all further provider requests are paused pending fresh explicit approval.
No billing, payment method, paid upgrade, OpenAI fallback, or public deployment
was enabled. Account billing is human-confirmed, not programmatically audited.

| Check | Actual result |
| --- | --- |
| Secure local setup | Masked entry, Windows-user DPAPI file in ignored D: .tmp |
| Backend and Streamlit | Started locally; both health endpoints returned 200 |
| Initial live evaluation | 1 generation attempt, Backend HTTP 504 timeout at 30 seconds; upstream status not retained |
| Explicitly approved rerun | 1 generation attempt, Backend HTTP 502 with 60-second timeout; upstream status not retained |
| Metadata lookup | 1 read-only request; key accessed gemini-3.8-flash, including generateContent support |
| Approved plain-text diagnostic | 1 generation attempt without tools; actual upstream Google HTTP 503, UNAVAILABLE; no retries |
| Total generation attempts | 3 across separate approvals; all stopped after their first failure |
| Live numerical tasks completed | 0/4; no successful answer/tool/SQL result |
| Real follow-up/explanation/chart checks | Not completed; no results invented |
| Automated verification | 377 passed; original 360 preserved plus 17 offline diagnostic tests |
| Mocked benchmark | 28/28; SQL 18/18, follow-ups 3/3, SQL rejections 4/4 |

The four planned questions are total revenue, highest category, grouped category
revenues, and a contextual second-category follow-up. Expected values remain
530, Electronics 260, category totals 260/150/120, and Home 150. Those values
passed mocked/independent Pandas checks, not real-model checks.

The two actual failed runs are saved separately in ignored
.tmp/gemini-live-evaluation-first.json and
.tmp/gemini-live-evaluation-second.json. Model access is recorded separately in
.tmp/gemini-model-access.json. These files contain sanitized outcomes, not keys,
provider raw exceptions, or private dataset information. No real chart artifact
was produced. The live runner reports failed cases without fabricating answers.

The original timeout and backend 502 do not establish their upstream causes.
The later tool-free diagnostic establishes Google HTTP 503 UNAVAILABLE for
that request, categorized as service_unavailable. It does not retroactively
prove the earlier failures had the same cause or establish how long the
service condition will persist. Metadata access does not prove successful
generation or available free quota. Wait before another live test; make no
generation or metadata requests without fresh explicit approval. Do not enable
billing or switch to a paid option to resolve this. Free-tier content may be used by Google to improve products; use synthetic
data only. Phase 7 integration is implemented; successful real-model testing
remains blocked. Docker runtime verification from Phase 6 also remains pending.

Sources: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing),
[model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
[active rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).


## Offline investigation follow-up (2026-10-14)

Backend HTTP 502 is a local translation, not evidence that Google returned 502.
The second report retained only the public error text. The upstream HTTP code,
symbolic status, and original exception were not saved. See
[offline investigation](phase7-offline-investigation.md) for findings and the
approval-gated proposal. No additional generation or metadata requests were made.
The original 360 tests are preserved; 12 offline diagnostic/SDK tests were added
(372 passing). The mocked benchmark remains 28/28.


## Confirmed plain-text diagnosis and hold

The user approved exactly one plain-text generation request, with no tool
declarations, a synthetic reply-OK instruction, the unchanged Gemini 3.8 Flash
model, at most 256 output tokens, a 60-second timeout, and zero retries.
The ignored `.tmp/gemini-plain-diagnostic.json` records one attempted generation,
`success=false`, upstream HTTP `503`, upstream status `UNAVAILABLE`, and category
`service_unavailable`. This is Google's HTTP status observed directly from the
SDK HTTP response, not FastAPI's translated status. No reply content, raw
exception, key, request body, or prompt was saved in the diagnostic report.
The run stopped after the failure; no tool-calling follow-up was attempted.

Current instruction: wait before another live test. No further generation or
metadata requests are authorized. Gemini 3.8 Flash remains the configured model.
If its unavailability persists, Gemini 3.7 Flash may be investigated later as a
possible free-tier alternative using official public documentation first. Its
existence, free-tier availability, account access, and compatible parameters are
not verified here. Do not alter the model allowlist/configuration or send any
provider request without the user's explicit approval. No automatic monitoring,
billing changes, paid fallback, Docker installation, Phase 8, or public deployment.

Entirely offline work can cover regression tests, mocked benchmark runs,
request-format/diagnostic review, and documentation. Those checks cannot prove
provider recovery, account-specific model access or quotas, live answer quality,
or successful real-model numerical/tool/follow-up/chart evaluation. Docker
runtime verification also remains pending; no Docker installation is authorized.


Offline verification after recording the diagnosis: 377 tests passed; the
mocked benchmark passed 28/28 (SQL 18/18, follow-ups 3/3, SQL rejections 4/4).
Only documentation changed during this update; existing code, tests, ignored
historical reports, SQL safety controls and free-tier safeguards were preserved.
No provider requests were made during the update.


## Final offline commit verification

Before committing the completed Phase 7 offline changes, the full suite was
rerun: 377 passed. The network-free benchmark again passed 28/28 (SQL 18/18,
follow-ups 3/3, SQL rejections 4/4). Dependency checks and key-free backend/
Streamlit imports passed. Git diff whitespace checks passed.

The reviewed tracked and proposed files contain no detected API credential
patterns, temporary diagnostic reports, encrypted key files, logs, or generated
artifacts. No reviewed file exceeds 1 MiB. The encrypted local key, historical
live reports, plain-text diagnostic report, and generated benchmark report stay
under ignored `.tmp/`; only sanitized findings are included in documentation.
This verification made no Gemini generation or metadata requests. Model,
free-tier guards, SQL safeguards and live-request hold remain unchanged.
