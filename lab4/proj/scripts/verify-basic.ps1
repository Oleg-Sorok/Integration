param([string]$BaseUrl = 'http://localhost:8000')
$ErrorActionPreference = 'Stop'
function Require($ok, $message) { if (-not $ok) { throw "FAILED: $message" }; Write-Host "PASS: $message" }
function Check-Unauthorized($url) {
  try {
    $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
    throw 'Expected HTTP 401 but request succeeded'
  } catch {
    $resp = $_.Exception.Response
    if ($null -eq $resp -or [int]$resp.StatusCode -ne 401) { throw }
  }
}
Write-Host '=== Lab 4 acceptance smoke tests (does not stop any service) ==='
$health = Invoke-RestMethod "$BaseUrl/health"
Require ($health.status -eq 'ok') 'Orders API /health'
Check-Unauthorized "$BaseUrl/orders"
Require $true 'GET /orders without token returns 401'

$cred = Get-Credential -Message 'Enter existing Lab 2 username and password. (Register via Swagger first if needed.)'
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password)
try { $pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
$loginBody = 'username=' + [uri]::EscapeDataString($cred.UserName) + '&password=' + [uri]::EscapeDataString($pass)
$tokenResult = Invoke-RestMethod -Uri "$BaseUrl/auth/login" -Method POST -ContentType 'application/x-www-form-urlencoded' -Body $loginBody
$pass = $null
Require ($tokenResult.token_type -eq 'bearer') 'OAuth2 login returns Bearer token'
$headers = @{Authorization = "Bearer $($tokenResult.access_token)"}
$me = Invoke-RestMethod -Uri "$BaseUrl/auth/me" -Headers $headers
Require ($me.username -eq $cred.UserName) 'GET /auth/me returns current user'

$property = @{
  client_name='Lab4 Smoke Test'; gr_liv_area=1800; total_bsmt_sf=1000
  garage_area=500; year_built=2005; overall_qual=7; ms_zoning='RL'
}
$create = Invoke-WebRequest -Uri "$BaseUrl/orders" -Method POST -Headers $headers -ContentType 'application/json' -Body (ConvertTo-Json -InputObject $property -Compress) -UseBasicParsing
$first = $create.Content | ConvertFrom-Json
Require ($create.StatusCode -eq 202 -and $first.status -eq 'pending' -and $null -eq $first.predicted_price -and $create.Headers['Location']) 'POST /orders -> 202, pending, Location header'
$id = [int]$first.id
Write-Host "Created test order id=$id"

$after = $null
for ($i=0; $i -lt 40; $i++) {
  $after = Invoke-RestMethod -Uri "$BaseUrl/orders/$id" -Headers $headers
  if ($after.status -ne 'pending') { break }
  Start-Sleep -Milliseconds 1000
}
Require ($after.status -eq 'priced' -and $null -ne $after.predicted_price -and $after.model_version) 'GET /orders/{id}: pending -> priced, registered model_version persisted'
$beforePrice = [double]$after.predicted_price

$patchName = Invoke-RestMethod -Uri "$BaseUrl/orders/$id" -Method PATCH -Headers $headers -ContentType 'application/json' -Body '{"client_name":"Lab4 Rename Only"}'
Require ($patchName.status -eq 'priced' -and [double]$patchName.predicted_price -eq $beforePrice -and $patchName.model_version -eq $after.model_version) 'PATCH client_name keeps forecast and model version'
$patchFeatures = Invoke-RestMethod -Uri "$BaseUrl/orders/$id" -Method PATCH -Headers $headers -ContentType 'application/json' -Body '{"overall_qual":9}'
Require ($patchFeatures.status -eq 'pending' -and $null -eq $patchFeatures.predicted_price -and $null -eq $patchFeatures.model_version) 'PATCH features -> pending, clears price and model version'
for ($i=0; $i -lt 40; $i++) {
  $after = Invoke-RestMethod -Uri "$BaseUrl/orders/$id" -Headers $headers
  if ($after.status -ne 'pending') { break }
  Start-Sleep -Milliseconds 1000
}
Require ($after.status -eq 'priced' -and $null -ne $after.predicted_price -and $after.model_version) 'PATCH queue worker updates model version'

$batch = @($property,$property,$property)
$resp = Invoke-RestMethod -Uri "$BaseUrl/orders/batch" -Method POST -Headers $headers -ContentType 'application/json' -Body (ConvertTo-Json -InputObject $batch -Depth 6 -Compress)
Require ($resp.total -eq 3 -and $resp.results.Count -eq 3 -and ($resp.results | Where-Object { $_.model_version -and $_.status -eq 'priced' }).Count -eq 3) 'POST /orders/batch handles all 3, each with model_version'

$retry = Invoke-WebRequest -Uri "$BaseUrl/orders/$id/retry" -Method POST -Headers $headers -UseBasicParsing
$retried = $retry.Content | ConvertFrom-Json
Require ($retried.id -eq $id -and $retry.StatusCode -eq 200) 'Retry priced order: no duplicate and unchanged (200)'
Write-Host 'Done. Still verify MLflow UI, nested trials, artifacts, rollback, alias fail-fast and image isolation separately.'
