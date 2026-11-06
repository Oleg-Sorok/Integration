param([Parameter(Mandatory=$true)][int]$Version)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
& docker compose -p proj run --rm trainer python -m app.registry promote "$Version"
if ($LASTEXITCODE -ne 0) { throw 'Alias change failed' }
& docker compose -p proj up -d --no-deps --force-recreate forecast-api
if ($LASTEXITCODE -ne 0) { throw 'Forecast restart failed' }
Write-Host 'Model promoted/rolled back; confirm with internal forecast health and new orders'
