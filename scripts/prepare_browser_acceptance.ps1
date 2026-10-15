# Preparation artifact only: -Execute and fresh human approval are required.
param([switch]$Execute, [switch]$FreeTierConfirmed)
$ErrorActionPreference = 'Stop'
if (!$Execute -or !$FreeTierConfirmed) {
    throw 'Not started. Separate execution approval and current Free-tier/billing-disabled confirmation are required.'
}
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
$reportPath = Join-Path $projectRoot '.tmp/browser-acceptance-live.json'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Existing D: environment is required.' }
if (Test-Path -LiteralPath $reportPath) { throw 'An existing report prohibits repeating/restarting this run.' }
if (!(Test-Path -LiteralPath '.tmp/gemini-key.dpapi')) { throw 'Existing encrypted key is required.' }
foreach ($portNumber in @(8002,8502)) {
    if (Get-NetTCPConnection -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $portNumber is occupied; do not reuse an unguarded server."
    }
}
$names = @('GOOGLE_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','GOOGLE_FREE_TIER_CONFIRMED','GOOGLE_MODEL','GOOGLE_GENAI_USE_VERTEXAI','GOOGLE_GENAI_USE_ENTERPRISE','BACKEND_URL','TEMP','TMP','LANGSMITH_TRACING','LANGCHAIN_TRACING_V2','LANGSMITH_API_KEY','LANGCHAIN_API_KEY','FRONTEND_ANALYSIS_TIMEOUT_SECONDS')
$previousValues = @{}
foreach ($name in $names) { $previousValues[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
$backendProcess = $null
try {
    $env:TEMP = Join-Path $projectRoot '.tmp'
    $env:TMP = $env:TEMP
    $env:LANGSMITH_TRACING = 'false'
    $env:LANGCHAIN_TRACING_V2 = 'false'
    foreach ($name in @('GEMINI_API_KEY','OPENAI_API_KEY','LANGSMITH_API_KEY','LANGCHAIN_API_KEY')) {
        [Environment]::SetEnvironmentVariable($name,$null,'Process')
    }
    $browserSecureKey = ConvertTo-SecureString ((Get-Content -LiteralPath '.tmp/gemini-key.dpapi' -Raw).Trim())
    $env:GOOGLE_API_KEY = [System.Net.NetworkCredential]::new('', $browserSecureKey).Password
    $env:GOOGLE_FREE_TIER_CONFIRMED = 'true'
    $env:GOOGLE_MODEL = 'gemini-3.6-flash'
    $env:GOOGLE_GENAI_USE_VERTEXAI = 'false'
    $env:GOOGLE_GENAI_USE_ENTERPRISE = 'false'
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','evaluations.browser_acceptance','--execute-approved-free-tier') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput '.tmp/browser-backend.stdout.log' -RedirectStandardError '.tmp/browser-backend.stderr.log' -PassThru
    # Only the guarded backend inherits the key. Never load it in Streamlit.
    [Environment]::SetEnvironmentVariable('GOOGLE_API_KEY',$null,'Process')
    [Environment]::SetEnvironmentVariable('GOOGLE_FREE_TIER_CONFIRMED',$null,'Process')
    $env:BACKEND_URL = 'http://127.0.0.1:8002'
    # Four 60-second generations plus spacing can exceed the ordinary 300s UI timeout.
    $env:FRONTEND_ANALYSIS_TIMEOUT_SECONDS = '600'
    $frontendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','streamlit','run','frontend/app.py','--server.address','127.0.0.1','--server.port','8502','--server.headless','true','--browser.gatherUsageStats','false') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput '.tmp/browser-frontend.stdout.log' -RedirectStandardError '.tmp/browser-frontend.stderr.log' -PassThru
    Write-Host "Guarded backend launcher: $($backendProcess.Id); frontend launcher: $($frontendProcess.Id)"
    Write-Host 'Open http://127.0.0.1:8502 only. The ordinary 8501 backend has no browser-test budget.'
    Write-Host 'Startup does not generate. Submit only the two approved questions after human execution approval.'
} catch {
    # No raw exception or environment dump; the existing key is never rewritten.
    Write-Host 'Browser acceptance startup failed; no automatic restart is permitted.'
    throw 'Inspect the sanitized local logs. Do not submit questions or rerun without review.'
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$previousValues[$name],'Process') }
    if ($browserSecureKey) { $browserSecureKey.Dispose() }
}
