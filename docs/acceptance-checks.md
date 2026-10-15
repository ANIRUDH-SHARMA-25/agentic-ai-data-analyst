# Remaining acceptance checks

Phase 8 offline review/documentation is distinct from successful live model
verification or deployment readiness. None of these actions is automatically
authorized. Keep Gemini 3.6 Flash, Free tier and billing disabled.

## Isolated checks completed; end-to-end blockers remain

Two separately approved Gemini 3.6 Flash requests succeeded with upstream HTTP
200 and STOP: plain-text OK (one output token), and AUTO inspect_dataset({})
selection (ten output tokens). No tools or SQL were executed. The user then
approved migrating the application default/allowlist to gemini-3.6-flash.
These are not successful end-to-end agent or chart evaluations.

1. Obtain separate approval for a bounded synthetic retail agent evaluation.
   Verify genuine schema inspection, validated SQL, numerical results and thought
   signature/tool-response continuation. Confirm Free tier/billing disabled.
2. Verify grouped totals, contextual follow-ups and explanation grounding
   against independent Pandas expectations. Mocked 28/28 is not live evidence.
3. Review genuine Streamlit answers/tables/charts and session reset. Do not
   substitute scripted UI results for genuine model-result visualization.
4. When an authorized environment already has Docker, build both images and
   perform key-free container health/upload/inspection/restart/permission/resource
   smoke checks. Static configuration review is not runtime proof.

All new provider requests require explicit approval, a hard request cap, zero
retries and no fallback. See the proposed two-question bounded evaluation in
[the migration record](../evaluations/gemini-3.6-migration.md). Do not test 3.8,
change model again, enable billing or deploy without separate approval.

## Public-hosting blockers — separate scope

Before considering public hosting, address all requirements in
[security readiness](security-readiness.md): authentication and per-session
ownership, tenant handling, SQL isolation without provider credentials, workload
quotas/cancellation, HTTPS/network policy, lifecycle/deletion, secret management,
vulnerability/container review and multi-user recovery tests. No public deployment
is authorized by Phase 8, even if all live model checks eventually succeed.

## Optional improvements

A genuine key-free metadata screenshot, expanded synthetic datasets, broader
chart examples, accessibility polish and additional workflow benchmarks may help
presentation. They are not substitutes for live verification or security blockers.
Avoid new infrastructure until a demonstrated need and explicit scope justify it.
