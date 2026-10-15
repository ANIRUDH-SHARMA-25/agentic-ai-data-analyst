# Controlled Gemini 3.6 Flash migration — 2026-10-15

The user explicitly approved replacing the application default and exact model
allowlist with gemini-3.6-flash. This supersedes the historical 3.8-only setting.
No provider generation or metadata requests were made during this migration.
The encrypted key stays on D: in ignored .tmp; it was not read for this work.
No dependencies, billing settings, Docker installation or deployment were added.

## Verified isolated evidence (before migration)

| Separately approved test | Actual outcome |
| --- | --- |
| Plain text, Reply with OK., 256 tokens, MINIMAL | One request; upstream 200; exact OK; two visible characters; STOP; one output token |
| Three existing declarations, AUTO selection, 512 tokens, MINIMAL | One request; upstream 200; exactly inspect_dataset({}); no invalid calls; STOP; ten output tokens |

Neither test executed a tool or SQL or continued the conversation. Safe local
reports are .tmp/gemini-3.6-isolated-2026-10-15.json and
.tmp/gemini-3.6-function-2026-10-15.json; they remain ignored. Reasoning-token
counts were unavailable, not assumed zero. These are narrow provider checks,
not proof of genuine end-to-end agent SQL, follow-ups, explanations or charts.
Historical 3.8 failures and the ambiguous HTTP 200 are preserved separately;
they are not relabeled as 3.6 outcomes.

## Changes and preserved boundaries

Updated backend defaults/allowlist, .env.example, Compose, encrypted-key local
launcher, plain diagnostic endpoint assertions, tests and current documentation.
Tests now explicitly reject 3.8, 3.7 and other model/provider identifiers.
Previously reviewed response-classification diagnostic improvements and their
18 offline regression cases are included, preserving the old local reports.

The main model constructor reads the new approved model from AgentSettings;
its compatible parameters remain unchanged: LOW thinking, include_thoughts
false, TEXT output, temperature/top_p/top_k omitted, 30-second default timeout,
1200 default output tokens, 8 model calls, 6 tools, zero retries. LOW is supported
by 3.6; MINIMAL was used only in the isolated tests. LOW agent behavior is not
yet live-verified. Settings retain their validation and maximum bounds.

One LangChain/LangGraph agent and its inspect_dataset/get_statistics/execute_sql
tools are preserved. No SQL AST/function allowlist, execution/resource boundary,
dataset isolation, memory, frontend, benchmark or CI workflow was rewritten.
Developer API routing remains fixed; inherited Vertex/Enterprise routes are
rejected. Free-project/billing-disabled human confirmation is required before
client construction. There is no paid route, retry or model/provider fallback.
An obsolete shell GOOGLE_MODEL override must be removed or set to 3.6; stale
3.8 values fail closed instead of silently falling back. Python does not load
.env automatically; a privately managed Compose .env must also use the new model.
No private .env values or key material are included in this record.

## Official Google compatibility basis

- [Model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash): text output, function calling and supported output limits.
- [Thinking levels](https://ai.google.dev/gemini-api/docs/thinking): 3.6 supports MINIMAL/LOW/MEDIUM/HIGH.
- [Sampling guidance](https://ai.google.dev/gemini-api/docs/troubleshooting): omit custom sampling parameters for Gemini 3.6+.
- [Standard free-tier pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash): free input/output, including thinking, subject to account quota/capacity; use synthetic data due to free-tier data-sharing terms.

Installed versions remain google-genai 2.30.1, langchain-google-genai 4.4.2,
langchain 1.4.4 and langchain-core 1.6.10. Offline tests use scripted models or
sealed HTTP MockTransport, including actual SDK serialization and signature
replay. A constructor/serialization test is not an account-level API check.

## Proposed next live evaluation — NOT approved or executed

Use only the tracked synthetic retail CSV with the migrated single agent and
a fresh conversation, subject to new explicit human approval:

1. Ask for total revenue by category, ordered descending. Independently expect
   Electronics 260, Home 150, Stationery 120; build a deterministic bar chart
   from those genuine returned rows if the request succeeds.
2. Ask how much revenue the second category generated. Independently expect
   Home 150, with the same conversation UUID and fresh schema/SQL evidence.

Expected normal sequence per question: one generation chooses inspect_dataset,
one chooses execute_sql, and one returns the explanation. That is normally
six generation requests across two questions, but model behavior can vary.
Hard cap: eight total generation attempts, at most four per question and three
tool calls per question. At most one validated SQL correction remains allowed.
Count every attempted generation, including failures; no automatic HTTP retry.
Space generation starts at least 35 seconds apart, use a 60-second per-request
timeout and 1200 output tokens with LOW thinking, and stop on the first provider,
validation, numerical, context or budget failure. No metadata requests, fallback,
extra cases or later automatic continuation. Billing must remain disabled.

This is a proposal for a two-case subset; the existing four-case live runner is
reference material, not authorization to run four cases. A separately approved
run must enforce the two-question subset and eight-attempt budget. Subsequent
Streamlit browser review of genuine results remains separate from this API test.
The normal six-call count is an expectation, not a promise of exact behavior.


## Offline migration verification

- Full suite: 403 passed, 0 failed. Previous 383 tests preserved, 18 diagnostic
  classification regressions included, and two model-rejection cases added.
- Mocked deterministic benchmark: 28/28, SQL 18/18, follow-ups 3/3, rejections 4/4.
- pip check passed; key-free FastAPI/Streamlit imports and new default passed.
- Real SDK MockTransport integration exercised the migrated endpoint, three
  declarations, signature replay, no retries and safe provider error mappings.
- Dependencies, main model constructor/agent graph, SQL layer, sessions, memory,
  frontend code and CI workflow unchanged. No provider request during migration.
- Static model/Compose/launcher consistency, Markdown links, whitespace and
  credential/artifact exclusions checked before commit; runtime Docker untested.

The commit hash and push-triggered CI result are supplied at handoff. Live
end-to-end acceptance remains pending even after CI success.
