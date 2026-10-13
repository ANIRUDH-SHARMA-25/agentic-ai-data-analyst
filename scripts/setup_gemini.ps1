$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
Write-Host 'Check Google AI Studio: this project must show Free, with billing disabled.'
Write-Host 'Do not link billing, enter payment details, purchase credits, or upgrade.'
$confirmation = Read-Host 'Type FREE only after checking those settings'
if ($confirmation -cne 'FREE') { throw 'Free-tier confirmation is required; nothing was saved.' }
$localKey = Read-Host 'Enter your Gemini key locally (masked; never paste it into chat)' -AsSecureString
if ($localKey.Length -eq 0) { throw 'An empty key was not saved.' }
New-Item -ItemType Directory -Path '.tmp' -Force | Out-Null
# Windows DPAPI encrypts for the current Windows user; no plaintext key file.
$localKey | ConvertFrom-SecureString | Set-Content -LiteralPath '.tmp/gemini-key.dpapi' -Encoding ASCII
Set-Content -LiteralPath '.tmp/gemini-free-tier.confirmed' -Value 'FREE' -Encoding ASCII
Write-Host 'Encrypted local key saved on D:. No API request was made.'
Write-Host 'Tell Codex setup is ready; do not share the key. Live tests still need separate approval.'
