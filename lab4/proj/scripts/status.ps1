Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
docker compose -p proj ps -a
Write-Host '=== Orders API ==='
curl.exe http://localhost:8000/health
Write-Host '=== MLflow ==='
curl.exe -I http://localhost:5000/
Write-Host '=== Forecast internal health ==='
docker compose -p proj exec -T forecast-api python -m app.check
Write-Host '=== Registry versions ==='
docker compose -p proj run --rm trainer python -m app.registry list
