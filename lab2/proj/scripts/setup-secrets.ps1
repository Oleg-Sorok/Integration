# Run inside proj. Uses cryptographic RNG; only creates missing secrets.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path 'secrets' | Out-Null
foreach ($item in @(@('db_password', 24), @('jwt_secret_key', 48))) {
    $target = Join-Path 'secrets' $item[0]
    if (Test-Path $target) {
        Write-Host "Secret already exists: $target (not overwritten)"
        continue
    }
    $buffer = New-Object byte[] ([int]$item[1])
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    $value = [Convert]::ToBase64String($buffer)
    [System.IO.File]::WriteAllText((Join-Path (Get-Location).Path $target), $value, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Created $target"
}
Write-Host 'On Linux/WSL also enforce chmod 600. On Windows, restrict ACLs to your user.'
