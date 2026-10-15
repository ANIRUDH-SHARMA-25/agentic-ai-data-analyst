# Local Docker deployment (Phase 6)

The application is for local, single-user use. Container execution has not been
verified on this machine: Docker/Compose were not found and WSL is not installed.
The steps below are future manual acceptance references, not reported results
or authorization to install Docker/WSL. Phase 8 performs static review only;
public deployment and provider requests remain prohibited.

## Prepare Windows storage before a first build

The repository, virtual environment, and generated reports live on D:. Docker's
image layers, build cache, and Linux disk image are managed separately from the
repository. Placing source on D: does not place those large files on D:. At the
Phase 6 check, C: had about 18 GiB free and D: about 140 GiB; no Docker settings
or existing data directory were found. No Docker installation or migration was
performed. Windows and Docker may still use small configuration files on C:.

1. Follow the official [Windows installation guide](https://docs.docker.com/desktop/setup/install/windows-install/)
   to install Docker Desktop and its WSL 2 prerequisites yourself. Review its
   system requirements and use Linux containers. Keep the installer on D:.
2. Before building this project, check Docker Desktop **Settings > Resources >
   Advanced** for its disk-image location. If your version offers the setting,
   choose a D: directory such as `D:\DockerData`, apply, and verify the displayed
   location after Docker restarts. The official [WSL guide](https://docs.docker.com/desktop/features/wsl/)
   describes this setting and the default C: data directory.
3. For a fresh installation, the official installer also documents
   `--wsl-default-data-root=<path>` to choose the WSL disk location and
   `--installation-dir=<path>` for an all-users application install. These are
   installer options, not commands to move an existing installation. Use the
   options supported by your selected installation mode/version.
4. For existing data, back it up using Docker's
   [backup guide](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/)
   before a supported migration. If the location setting is unavailable, follow
   the current official procedure for your backend/version before proceeding.
   Do not drag/move VHD files, edit settings JSON, unregister WSL distributions,
   or delete images/volumes to make space. Confirm D: storage before building.

Open a new PowerShell window after installing. `docker version` must show both
Client and Server, and `docker compose version` must succeed. A Client-only
result means the engine is not reachable; start Docker Desktop and wait.

## Configure and start

Stop any direct Python servers with Ctrl+C first: both modes use ports 8000/8501.
Run from the repository root:

```powershell
Set-Location 'D:\GPT work\CODEX\agentic-ai-data-analyst'
New-Item -ItemType Directory -Path .tmp -Force | Out-Null
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
docker version
docker compose version
docker compose config --quiet
docker compose build
docker compose up -d --wait
docker compose ps
```

Stop if any command fails. Building downloads Python images and dependencies
and requires internet access; it does not call Gemini. `--wait` waits for both
services' health checks. Backend startup needs no key. Open
[the dashboard](http://127.0.0.1:8501) and
[API docs](http://127.0.0.1:8000/docs).

Compose interpolates optional shell variables or a root `.env`. Defaults need
no `.env`. Python itself does not auto-load it. An optional blank template can
be copied with `Copy-Item .env.example .env` only if `.env` does not already
exist. It is ignored by Git and Docker. Keep real keys out of tracked files.
Compose explicitly selects each service's environment; it does not forward
the whole .env to containers. Never use `env_file: .env` for the frontend.

| Setting | Default / location |
| --- | --- |
| Host backend port | 127.0.0.1:8000 |
| Host dashboard port | 127.0.0.1:8501 |
| Container backend URL | http://backend:8000 (fixed frontend value) |
| UPLOAD_MAX_BYTES | 5242880; shared frontend/backend |
| STREAMLIT_SERVER_MAX_UPLOAD_SIZE | 5; frontend server cap in whole MiB |
| DATASET_TTL_SECONDS / MAX_ACTIVE_DATASETS | 1800 / 20; backend |
| GOOGLE_API_KEY | empty; backend runtime only |
| GOOGLE_FREE_TIER_CONFIRMED | false; set true only after checking Free project/billing disabled |
| GOOGLE_MODEL | gemini-3.6-flash; backend |
| GOOGLE_TIMEOUT_SECONDS / GOOGLE_MAX_OUTPUT_TOKENS | 30 / 1200; backend |
| FRONTEND_REQUEST_TIMEOUT_SECONDS / FRONTEND_ANALYSIS_TIMEOUT_SECONDS | 30 / 300 |

The Dockerfiles set container listeners to 0.0.0.0; Compose publishes only
127.0.0.1 on Windows. Do not replace those host bindings with all interfaces.
Inside the frontend, localhost refers to the frontend itself, so its API URL
must be the Compose service name `backend`, not localhost or a Windows path.
The existing HTTPX client is used without importing backend objects.

## Key-free manual smoke checks

Use a blank/unset key for these checks. If a key is configured, do not perform
the analyze check; stop and use a separate key-free configuration. Do not print
expanded Compose configuration, container environments, or secrets in logs.

```powershell
# Verify absence without printing a value; abort on nonzero exit.
docker compose exec -T backend python -c "import os,sys; sys.exit(2 if os.environ.get('GOOGLE_API_KEY') else 0)"
if ($LASTEXITCODE -ne 0) { throw 'Backend key is configured: stop the key-free smoke test.' }
docker compose exec -T frontend python -c "import os; assert not os.environ.get('GOOGLE_API_KEY'); print('Frontend has no API key')"
Invoke-RestMethod 'http://127.0.0.1:8000/health'
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8501/_stcore/health'
# Verify the real frontend client reaches the backend over service DNS.
docker compose exec -T frontend python -c "from frontend.config import FrontendSettings; from frontend.api_client import APIClient; print(APIClient(FrontendSettings.from_environment()).health())"
# Upload via the containerized HTTP API, then inspect that exact dataset.
$uploadText = curl.exe --fail --silent --show-error -X POST 'http://127.0.0.1:8000/upload' -F 'file=@data/sample/retail_sales.csv'
if ($LASTEXITCODE -ne 0) { throw 'Upload failed.' }
$upload = $uploadText | ConvertFrom-Json
if ($upload.row_count -ne 12 -or $upload.column_count -ne 6) { throw 'Unexpected sample shape.' }
$datasetId = $upload.dataset_id
$inspection = Invoke-RestMethod "http://127.0.0.1:8000/dataset/$datasetId"
if ($inspection.row_count -ne 12 -or $inspection.column_count -ne 6) { throw 'Inspection failed.' }
$inspection
# Missing-key response must be HTTP 503 with a clear configuration message.
$body = @{ dataset_id = $datasetId; question = 'What is total revenue?' } | ConvertTo-Json -Compress
$body | Set-Content -Encoding ASCII '.tmp/missing-key-request.json'
curl.exe --silent --show-error -w '\nHTTP %{http_code}\n' -H 'Content-Type: application/json' --data-binary '@.tmp/missing-key-request.json' 'http://127.0.0.1:8000/analyze'
```

The missing-key guard precedes model generation; no provider call is needed.
In the browser click **Check connection**, then **Try the retail sample**.
Verify rows, columns, preview, types, missing values, and statistics; no real
analysis should be submitted. Source sample totals are revenue 530, quantity 41,
and category revenues Electronics 260, Home 150, Stationery 120. The network-free
benchmark verifies these computed values through the real agent/SQL execution
path using a fake model; a health response alone does not verify analytics.
Run tests and the benchmark with the existing D: Python environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp/pytest
.\.venv\Scripts\python.exe -m evaluations.benchmark --output .tmp/phase6-evaluation.json
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from backend.main import app; import streamlit; print(app.version)"
```

Check actual temporary permissions, non-root execution, logs and restart counts:

```powershell
docker compose exec -T backend python -c "import os,tempfile,pathlib; assert os.getuid()==10001; f=tempfile.TemporaryFile(dir='/app/.tmp/uploads'); f.close(); assert not os.access('/app/backend/main.py',os.W_OK); print('Backend writable scratch and read-only code checked')"
docker compose exec -T frontend python -c "import os,tempfile; assert os.getuid()==10001; f=tempfile.TemporaryFile(dir='/tmp'); f.close(); assert not os.access('/app/frontend/app.py',os.W_OK); print('Frontend writable scratch and read-only code checked')"
docker compose logs --tail 80 backend frontend
$containerIds = @(docker compose ps -q)
foreach ($containerId in $containerIds) {
    docker inspect --format 'user={{.Config.User}} read_only={{.HostConfig.ReadonlyRootfs}} memory={{.HostConfig.Memory}} cpu={{.HostConfig.NanoCpus}} pids={{.HostConfig.PidsLimit}} restarts={{.RestartCount}} health={{.State.Health.Status}}' $containerId
}
docker compose restart backend frontend
docker compose up -d --wait
docker compose ps
# The old dataset ID should now return HTTP 404; re-upload to continue.
curl.exe --silent --show-error -w '\nHTTP %{http_code}\n' "http://127.0.0.1:8000/dataset/$datasetId"
docker compose stop
docker compose ps -a
```

Record health/exit states and any startup errors. Containers should remain
healthy with no unexpected restarts. `restart: no` deliberately avoids masking
crashes. Stopping affects this Compose project only; no prune, volume removal,
or image deletion is needed. `docker compose up -d --wait` starts them again.
Backend restarts discard all datasets and conversations; frontend history can
be stale, so clear the selected dataset/reload after a restart.

## Troubleshooting and optional future credentials

- Docker is missing: install it yourself via the official Windows guide; no
  application changes can substitute for an engine. A daemon error means Docker
  Desktop is not ready or the selected context points elsewhere.
- Port already allocated: stop the earlier local Python servers or the specific
  application using port 8000/8501; do not stop unrelated containers blindly.
- Backend unavailable: inspect `docker compose ps` and service logs. Backend
  must be healthy; invalid numeric environment configuration prevents startup.
  Keep the frontend URL `http://backend:8000`. A host browser cannot resolve
  `backend`; use the published localhost URLs there.
- Permission/read-only errors: collect the failing path from local startup logs
  and check the UID/tmpfs configuration. Do not resolve this by running as root
  or removing all filesystem restrictions. These paths need runtime validation.
- OOM/large data: a container memory limit may terminate the process and lose
  sessions. Use small CSVs and lower session capacity for available RAM.
- Restarted/expired session: upload again; an old UUID is not persistent storage.

After secure key setup and explicit approval for free-tier live tests, a key may be supplied as `GOOGLE_API_KEY` in the
backend process environment, or a private ignored `.env` for Compose
interpolation, then recreate the backend with
`docker compose up -d --no-deps --force-recreate backend`. Do not put keys in
Dockerfiles, build arguments, URLs, command history containing literal values,
GitHub workflow secrets for this key-free CI, or frontend settings. Set GOOGLE_FREE_TIER_CONFIRMED=true only after checking AI Studio shows Free
and billing is disabled. The model is restricted to gemini-3.6-flash, with no
Vertex AI, Enterprise route, paid fallback, or retries. Runtime
environment credentials are visible to administrators who can inspect containers;
they are not a secret vault. Do not share expanded config/inspect environment
output. No key onboarding or live analysis was performed in Phase 6.

## Container boundaries and remaining work

The backend installs only backend requirements and copies backend code. The
frontend installs only frontend requirements and copies frontend code, the
Streamlit config, and the synthetic CSV. The build context is an allowlist;
Git history, virtual environments, caches, reports, private datasets and keys
are excluded. Neither image contains tests or unnecessary development files.
Both use non-root UID/GID 10001, one CPU and 128 PIDs per service. Backend memory
is 1 GiB, frontend 768 MiB. Read-only roots have bounded noexec/nosuid/nodev
tmpfs: backend uploads/cache 64 MiB plus /tmp 16 MiB; frontend /tmp 64 MiB.
No host filesystem mounts or Docker socket are used. Tmpfs uses memory and may
be swapped by the host/VM; it is not a promise of zero disk activity.

The existing SQL validation, external-access prohibition, execution/result
limits, bounded conversation memory, and no-retry behavior are unchanged.
DuckDB executes inside the backend process and shares its boundary, including
its runtime credentials. These controls are defense in depth, not a complete
independent SQL sandbox. There is no public authentication, rate limiting,
shared session store, or durable storage. Before any public deployment, a later
security review must address untrusted execution isolation, access control,
rate limits, and session handling. This phase provides local deployment
preparation only; no cloud deployment or new infrastructure is authorized.


Phase 7 updates only provider configuration: GOOGLE_* replaces OPENAI_*, with
Gemini 3.6 Flash now explicitly approved after isolated diagnostics. Keep keys out of frontend containers.
Free-tier content may be used by Google to improve products; use synthetic data.
The Windows setup script encrypts a local key for direct Python startup; Compose
does not read that encrypted file. For Compose supply the optional key securely
in its shell environment, then clear it when finished. Docker runtime remains
unverified here and this phase does not install Docker or WSL.
