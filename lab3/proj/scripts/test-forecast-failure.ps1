# This experiment modifies the running stack only temporarily and always restarts Forecast API.
param([string]$ProjectName = 'proj')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host 'Stopping Forecast API for controlled failure experiment...'
& docker compose -p $ProjectName stop forecast-api
if ($LASTEXITCODE -ne 0) { throw 'Could not stop forecast-api' }
try {
    & docker compose -p $ProjectName ps -a
    Write-Host 'Now perform authenticated POST /orders in Swagger (expect 202/pending), then GET by id (expect failed/null).'
    Write-Host 'Save screenshots before returning here. Press Enter only after completing the Swagger checks.'
    [void](Read-Host)
} finally {
    & docker compose -p $ProjectName start forecast-api
    & docker compose -p $ProjectName ps -a
    Write-Host 'Forecast API restart requested.'
}
