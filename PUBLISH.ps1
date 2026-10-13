# Run on a computer with working GitHub access and GitHub CLI authentication.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& gh auth status
if ($LASTEXITCODE -ne 0) { throw 'Run gh auth login on your own computer, then rerun this script.' }
& py scripts/check_secrets.py
if ($LASTEXITCODE -ne 0) { throw 'Publication scan failed.' }
$owner = & gh api user --jq .login
if ($LASTEXITCODE -ne 0) { throw 'Could not identify the authenticated GitHub account.' }
$repository = "$owner/esp32-display-app"
& gh repo create $repository --private --source . --remote origin
if ($LASTEXITCODE -ne 0) { throw 'Repository creation failed; do not push to an existing repository without checking it.' }
& git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Main branch push failed.' }
& git push -u origin development
if ($LASTEXITCODE -ne 0) { throw 'Development branch push failed.' }
& gh repo edit $repository --default-branch main
if ($LASTEXITCODE -ne 0) { throw 'Could not set default branch.' }
Write-Output 'Private repository created. Use development for ongoing work.'
