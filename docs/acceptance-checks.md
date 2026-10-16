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

## Completed actual browser acceptance (2026-10-16)

Both retail questions passed through actual Brave/Streamlit in six real Gemini
3.6 Flash requests, all HTTP 200. Genuine explanations, executed SQL/tool panels,
correct tables, Plotly charts and same-conversation Home/150 follow-up rendered
and passed checks. New conversation cleared both displayed turns/results and
reset backend context while preserving the dataset; generation count stayed 6.
The tested local synthetic workflow is verified. See the
[browser acceptance record](../evaluations/streamlit-browser-verification.md).
This separate browser run does not expand the 28 mocked cases into real-model
accuracy evidence or establish production readiness.

## Remaining local acceptance checks

1. Manually verify direct file-picker CSV upload. Automation was blocked by
   extension permissions, which were not changed. The sample-button path used
   real CSV upload/inspection and passed.
2. In a separately approved environment with Docker already available, build
   both images and run key-free health/upload/inspection/restart/permission/
   resource smoke checks. Static configuration review is not runtime proof;
   Docker/WSL installation is outside current scope.
3. Broader dataset/question and robustness measurements are optional future
   work. Any new Gemini request needs fresh explicit approval, a request cap,
   Free-tier/billing-disabled confirmation, zero retries and no fallback.

## Public-hosting requirements: separate scope

Before public hosting, address [security readiness](security-readiness.md):
authentication and session ownership, tenant handling, independent SQL isolation
without provider credentials, quotas/cancellation, HTTPS/network policy,
lifecycle/deletion, secret management, vulnerability/container review and
multi-user recovery tests. UUIDs, validated SQL and a container alone do not
satisfy these requirements. No public deployment is authorized.


Historical browser status (2026-10-15): correct schema/SQL was followed by
Google 429 RESOURCE_EXHAUSTED on the third generation; final rendering/reset
were not completed in that run. User-reported historical RPD 21/20 supports daily
quota exhaustion; its 28-day peak view did not prove current availability.
The 422 mapping defect was fixed offline before the separately approved
October 16 browser success. See the
[quota investigation](../evaluations/browser-quota-investigation.md).
