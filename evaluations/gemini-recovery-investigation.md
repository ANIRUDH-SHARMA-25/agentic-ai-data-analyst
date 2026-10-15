# Recovery diagnostic investigation — 2026-10-15

Historical record: model references and results below describe their original
run. The configured model is now 3.6; see [the migration record](gemini-3.6-migration.md).

No generation or metadata requests were made during this investigation. The
main agent, model, provider, free-tier safeguards and SQL layer are unchanged.
The ignored historical recovery report and temporary runner are preserved.

## Established evidence

The saved `.tmp/gemini-recovery-2026-10-15.json` records exactly one plain-text
request, upstream HTTP 200, reply_was_ok false and category unexpected_reply.
The temporary runner differs from the original only in its output path and
synthetic prompt (Reply with OK.). It used no tools, a 256-token output cap,
60-second timeout and no retries. The subprocess terminated after reporting.
No actual text, finish reason, content structure or token counts were retained.
Only that report and the runner exist among the local recovery artifacts.
The actual reply is therefore unavailable for safe inspection; do not invent
or reconstruct it. It is not possible to establish usable text generation.

HTTP 200 establishes an HTTP success on this attempt, not complete service
recovery, correct text generation, tool support or answer quality. The 503 did
not recur on this attempt. unexpected_reply was a local validation category,
not a Google error or SDK exception. model.invoke returned normally, but that
can also happen for empty candidates/content in the installed adapter.

## Validation and extraction findings

The old diagnostic stripped surrounding whitespace and required case-sensitive
text equal to OK. Thus OK followed by whitespace would pass; OK. or a differently
formatted answer could produce unexpected_reply even with visible text. An
empty result, a truncated response or an unsupported content structure shared
that same category. No saved field distinguishes them retrospectively.

The old extractor handles plain strings and the text dictionaries normally
emitted by the installed Gemini 3.x adapter correctly. Offline conversion of
real SDK response types confirms this. It does not prove that historical reply
was of either form. A demonstrated diagnostic-only gap is that valid list-of-
string content was discarded. The new extractor supports those blocks too,
ignores thought/reasoning blocks, and identifies unsupported content explicitly.

The improved diagnostic records only structural kind, visible-text presence/
character count, strict and relaxed OK-match booleans, allowlisted finish reason,
truncation flag, and integer output/reasoning token counts when available.
No text, thoughts, signatures, raw metadata, credentials or request bodies are
saved. The relaxed format check does not replace strict success validation.
Separate categories identify empty_text, output_truncated, unsupported_content,
expected_text_format_variation, unexpected_text and generation_not_completed.
A truncated result cannot pass merely because its visible text equals OK.
Provider HTTP success is recorded separately from the strict diagnostic result.

SDK-shaped offline fixtures reproduce normal text, formatted OK, empty STOP,
and empty/thought-only MAX_TOKENS cases, and confirm finish/token metadata
propagation. MAX_TOKENS plus no visible text would be consistent with truncation;
the previous 256-token budget and LOW thinking make this a hypothesis worth
checking, not an established diagnosis. No model configuration was changed.

## Next proposed live test — NOT approved or executed

One new plain-text request using the same model, encrypted key, exact synthetic
prompt Reply with OK., 256 output tokens, 60-second timeout, LOW thinking and
zero retries. No tools, SQL, metadata lookup, model switch or fallback. Use the
improved diagnostic and a fresh ignored output filename; preserve prior reports.
Capture only the safe characteristics above and actual upstream HTTP status.
Stop after one attempt; do not automatically increase tokens or run agent tests.
This keeps request settings unchanged while repairing the missing evidence.
If it confirms truncation, propose a separately approved token-budget test;
if it confirms usable text/OK, seek separate approval for a minimal tool test.
Human confirmation of Free tier and billing disabled remains required. No
additional live request is authorized by this offline investigation.

Reference: installed langchain-google-genai 4.4.2 response conversion and
[LangChain integration documentation](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai).

Offline verification: full suite 401 passed, 0 failed (previous 383 preserved
plus 18 response-classification regressions); mocked benchmark 28/28, SQL 18/18,
follow-ups 3/3, SQL rejections 4/4. No provider requests were made.
