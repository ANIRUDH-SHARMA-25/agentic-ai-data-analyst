# Remaining acceptance checks

Phase 8 offline review/documentation is distinct from successful live model
verification or deployment readiness. None of these actions is automatically
authorized. Keep Gemini 3.8 Flash, Free tier and billing disabled.

## Live-verification blockers, in order

1. Obtain new explicit approval for one bounded real plain-text generation.
   Confirm Free tier/billing disabled and capture only safe provider diagnostics.
   Last observed result: upstream Google 503 UNAVAILABLE; its persistence is not
   known. Stop on failure; no automatic retries or model switch.
2. After plain-text success, separately approve a minimal real function-calling
   test. Verify declarations and thought-signature replay with genuine responses.
3. Separately approve the bounded synthetic retail evaluation. Verify actual
   SQL totals/category ordering, contextual follow-ups and explanation grounding
   against independent expectations. Mocked 28/28 is not acceptance evidence here.
4. Review genuine end-to-end Streamlit answers/tables/charts. Verify labels,
   values, precision, exclusions and session reset without fabricating outputs.
5. When an authorized environment already has Docker, build both images and
   perform the documented key-free container health/upload/inspection/restart/
   permission/resource smoke checks. Static config review is not runtime proof.

Gemini 3.7 Flash can be investigated via official public documentation only if
3.8 remains unavailable. Existence/free-tier eligibility and account access are
not verified. Switching or sending requests needs separate explicit approval.

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
