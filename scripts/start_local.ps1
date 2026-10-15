$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Create the D: Python environment first.' }
if (!(Test-Path -LiteralPath '.tmp/gemini-key.dpapi')) { throw 'Run scripts/setup_gemini.ps1 locally first.' }
if ((Get-Content -LiteralPath '.tmp/gemini-free-tier.confirmed' -Raw).Trim() -cne 'FREE') { throw 'Free project confirmation is missing.' }
foreach ($portNumber in @(8000,8501)) {
    if (Get-NetTCPConnection -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $portNumber is already in use. Stop the specific earlier server before continuing."
    }
}
$names = @('GOOGLE_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','GOOGLE_FREE_TIER_CONFIRMED','GOOGLE_MODEL','GOOGLE_GENAI_USE_VERTEXAI','GOOGLE_GENAI_USE_ENTERPRISE','BACKEND_URL','TEMP','TMP','LANGSMITH_TRACING','LANGCHAIN_TRACING_V2')
$previousValues = @{}
foreach ($variableName in $names) { $previousValues[$variableName] = [Environment]::GetEnvironmentVariable($variableName,'Process') }
$backendProcess = $null
$frontendProcess = $null
try {
    $env:TEMP = Join-Path $projectRoot '.tmp'; $env:TMP = $env:TEMP
    $env:LANGSMITH_TRACING = 'false'; $env:LANGCHAIN_TRACING_V2 = 'false'
    [Environment]::SetEnvironmentVariable('GEMINI_API_KEY',$null,'Process')
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY',$null,'Process')
    $encryptedKey = Get-Content -LiteralPath '.tmp/gemini-key.dpapi' -Raw
    $secureKey = ConvertTo-SecureString -String $encryptedKey.Trim()
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try { $env:GOOGLE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
    $env:GOOGLE_FREE_TIER_CONFIRMED = 'true'
    $env:GOOGLE_MODEL = 'gemini-3.6-flash'; $env:GOOGLE_GENAI_USE_VERTEXAI = 'false'; $env:GOOGLE_GENAI_USE_ENTERPRISE = 'false'
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000','--workers','1') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput '.tmp/backend.stdout.log' -RedirectStandardError '.tmp/backend.stderr.log' -PassThru
    # Clear all provider credentials before the frontend inherits its environment.
    [Environment]::SetEnvironmentVariable('GOOGLE_API_KEY',$null,'Process')
    [Environment]::SetEnvironmentVariable('GOOGLE_FREE_TIER_CONFIRMED',$null,'Process')
    $env:BACKEND_URL = 'http://127.0.0.1:8000'
    $frontendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','streamlit','run','frontend/app.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput '.tmp/frontend.stdout.log' -RedirectStandardError '.tmp/frontend.stderr.log' -PassThru
    # Windows venv launchers can spawn a child interpreter; include that child
    # when printing the stop command so the listening servers are stopped too.
    Start-Sleep -Seconds 2
    $rootPids = @($backendProcess.Id,$frontendProcess.Id)
    $childPids = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -in $rootPids -and $_.Name -eq 'python.exe' } | Select-Object -ExpandProperty ProcessId)
    $stopPids = @($childPids + $rootPids | Select-Object -Unique)
    Write-Host "Backend launcher PID: $($backendProcess.Id); frontend launcher PID: $($frontendProcess.Id)"
    Write-Host 'Open http://127.0.0.1:8501. Startup makes no Gemini calls.'
    Write-Host 'Do not submit analysis until live-call approval is given.'
    Write-Host "Stop these servers: Stop-Process -Id $($stopPids -join ',')"
} catch {
    if ($backendProcess -and !$frontendProcess) { Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue }
    throw
} finally {
    foreach ($variableName in $names) { [Environment]::SetEnvironmentVariable($variableName,$previousValues[$variableName],'Process') }
}
