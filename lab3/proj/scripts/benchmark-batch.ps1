param(
  [string]$BaseUrl = 'http://localhost:8000',
  [int]$N = 10
)
$ErrorActionPreference = 'Stop'
$creds = Get-Credential -Message 'Enter the registered Orders API username and password'
$userName = $creds.UserName
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($creds.Password)
try { $pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
$body = 'username=' + [uri]::EscapeDataString($userName) + '&password=' + [uri]::EscapeDataString($pass)
$login = Invoke-RestMethod -Method POST -Uri "$BaseUrl/auth/login" -ContentType 'application/x-www-form-urlencoded' -Body $body
$pass = $null
$headers = @{Authorization = "Bearer $($login.access_token)"}
$orders = @()
for ($i = 0; $i -lt $N; $i++) {
  $orders += @{
    client_name = "Batch Benchmark $i"; gr_liv_area = (1600 + $i*60)
    total_bsmt_sf = 1000; garage_area = 400; year_built = 2005
    overall_qual = 7; ms_zoning = 'RL'
  }
}
$batchJson = ConvertTo-Json -InputObject $orders -Depth 5 -Compress
$sw = [Diagnostics.Stopwatch]::StartNew()
$result = Invoke-RestMethod -Method POST -Uri "$BaseUrl/orders/batch" -Headers $headers -ContentType 'application/json' -Body $batchJson
$sw.Stop()
$batchMs = $sw.Elapsed.TotalMilliseconds
Write-Host "One batch with $N items: $([math]::Round($batchMs, 2)) ms; results=$($result.results.Count)"
$sw.Restart()
$last = $null
foreach ($item in $orders) {
  $json = ConvertTo-Json -InputObject @($item) -Depth 5 -Compress
  $last = Invoke-RestMethod -Method POST -Uri "$BaseUrl/orders/batch" -Headers $headers -ContentType 'application/json' -Body $json
}
$sw.Stop()
$serialMs = $sw.Elapsed.TotalMilliseconds
Write-Host "$N separate one-item batch calls: $([math]::Round($serialMs, 2)) ms"
if ($batchMs -gt 0) { Write-Host "Ratio (separate/batch): $([math]::Round($serialMs/$batchMs, 2))x" }
Write-Host 'NOTE: samples are saved as orders in PostgreSQL. Timing includes request overhead and DB writes.'
