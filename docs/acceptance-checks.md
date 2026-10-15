# Acceptance status and remaining checks

The application remains local-development-only. No action listed here grants
permission for additional provider requests, Docker installation or deployment.
Keep Gemini 3.6 Flash, Free tier and billing disabled.

## Completed bounded live acceptance

On 2026-10-15, both synthetic retail questions passed in six real Gemini
requests, three per question, all upstream HTTP 200. Actual inspect_dataset and
execute_sql execution returned descending category totals Electronics 260,
Home 150, Stationery 120. Both final explanations passed validation. The
follow-up retained the same dataset-bound conversation ID and prior result,
computed fresh evidence, and correctly identified Home as second with revenue
150. Plotly bar chart generation succeeded. No retries or fallback were used.
See the [bounded live record](../evaluations/live-retail-verification.md).
This is two live questions, separate from the 28-case mocked benchmark; broad
real-model accuracy and production readiness are not established.

## Remaining local acceptance checks

1. Review genuine Streamlit answers/tables/charts in a real browser, including
   reruns and session reset. Mocked AppTest and live API/chart evidence are
   distinct from a completed browser acceptance session. Any additional Gemini
   request needs fresh explicit approval, a request cap and Free-tier confirmation.
2. In a separately approved environment already equipped with Docker, build both
   images and perform key-free health/upload/inspection/restart/permission/resource
   smoke checks. Static configuration review is not runtime proof. Do not install
   Docker/WSL as part of the current finalization.
3. Broader synthetic datasets/question coverage and robustness measurements may
   be useful later, but are optional future work requiring separate live approval.

## Public-hosting requirements: separate scope

Before public hosting, address [security readiness](security-readiness.md):
authentication and session ownership, tenant handling, independent SQL isolation
without provider credentials, quotas/cancellation, HTTPS/network policy,
lifecycle/deletion, secret management, vulnerability/container review and
multi-user recovery tests. UUIDs, validated SQL and a container alone do not
satisfy these requirements. No public deployment is authorized.
