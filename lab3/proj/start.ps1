<##
Lab 3 one-command launcher (Windows PowerShell 5.1+).
It bootstraps NON-SECRET config, reuses Lab 2 secrets and Ames dataset when present,
then starts the whole Compose stack. It never resets PostgreSQL data.
#>
param(
    [string]$ProjectName = 'proj',
    [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$root = (Get-Location).Path
$integrationDir = Split-Path (Split-Path $root -Parent) -Parent
$oldProj = Join-Path (Join-Path $integrationDir 'house-price-lab-task2') 'proj'

function Stop-With([string]$message) { throw "LAB3 SETUP: $message" }
function Existing-File([string]$path) {
    return ((Test-Path -LiteralPath $path -PathType Leaf) -and ((Get-Item -LiteralPath $path).Length -gt 0))
}
function Ensure-Not-Directory([string]$path) {
    if (Test-Path -LiteralPath $path -PathType Container) {
        $first = Get-ChildItem -LiteralPath $path -Force | Select-Object -First 1
        if ($null -ne $first) { Stop-With "Expected a file, found non-empty directory: $path" }
        Remove-Item -LiteralPath $path -Force
        Write-Host "Removed empty placeholder directory: $path"
    }
}
function New-RandomSecret([string]$dest, [int]$bytesCount) {
    $bytes = New-Object byte[] $bytesCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $value = [Convert]::ToBase64String($bytes)
    [System.IO.File]::WriteAllText($dest, $value, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Generated missing secret file: $(Split-Path $dest -Leaf) (value not displayed)"
}
function Ensure-Secret([string]$name, [int]$size, [bool]$canGenerate) {
    $dest = Join-Path $root ("secrets\" + $name)
    Ensure-Not-Directory $dest
    if (Existing-File $dest) { Write-Host "Using existing $name"; return }
    if (Test-Path -LiteralPath $dest) { Stop-With "Secret $name exists but is empty. Restore a valid backup; it will not be overwritten." }
    $old = Join-Path $oldProj ("secrets\" + $name)
    if (Existing-File $old) {
        Copy-Item -LiteralPath $old -Destination $dest
        Write-Host "Copied $name from the working Lab 2 project"
        return
    }
    if (-not $canGenerate) { Stop-With "Cannot safely create a new $name with an existing PostgreSQL volume. Copy the original from Lab 2 into secrets\$name." }
    New-RandomSecret $dest $size
}

Write-Host '=== Lab 3: one-command setup + Compose startup ==='
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Stop-With 'Docker not found. Install/start Docker Desktop.' }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Stop-With 'Docker Engine is not running. Open Docker Desktop.' }
if (-not (Test-Path -LiteralPath '.env' -PathType Leaf)) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env with non-sensitive defaults'
}
$legacyPassword = Select-String -Path '.env' -Pattern '^POSTGRES_PASSWORD\s*=' -ErrorAction SilentlyContinue
if ($legacyPassword) { Stop-With 'Remove POSTGRES_PASSWORD from .env; Docker Secrets is the only supported password source.' }

# Compose project name proj is intentionally preserved to reuse the Lab 2 pgdata volume.
$existingVolume = "${ProjectName}_pgdata"
& docker volume inspect $existingVolume *> $null
$hasVolume = $LASTEXITCODE -eq 0
New-Item -ItemType Directory -Force -Path 'secrets', 'forecast-service\data' | Out-Null
Ensure-Secret 'db_password' 24 (-not $hasVolume)
Ensure-Secret 'jwt_secret_key' 48 $true

$data = Join-Path $root 'forecast-service\data\ames_train.csv'
Ensure-Not-Directory $data
if (-not (Existing-File $data)) {
    $oldData = Join-Path $oldProj 'forecast-service\data\ames_train.csv'
    if (Existing-File $oldData) {
        Copy-Item -LiteralPath $oldData -Destination $data
        Write-Host 'Copied Ames Housing training CSV from Lab 2'
    } else {
        # Public MIT-licensed Kaggle Ames Housing mirror. No credentials needed.
        $url = 'https://raw.githubusercontent.com/manavkapadnis/House-prices-Advanced-regression-techniques/master/train.csv'
        Write-Host 'Dataset missing in Lab 2; downloading public Ames Housing train.csv...'
        $tmp = $data + '.download'
        try {
            Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing -ErrorAction Stop
            Move-Item -LiteralPath $tmp -Destination $data -Force
        } catch {
            if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
            Stop-With "Could not obtain dataset. Copy Lab 2 forecast-service\data\ames_train.csv to this project. Original error: $($_.Exception.Message)"
        }
    }
}
$csvHeader = Get-Content -LiteralPath $data -TotalCount 1
foreach ($field in @('SalePrice', 'GrLivArea', 'TotalBsmtSF', 'GarageArea', 'YearBuilt', 'OverallQual', 'MSZoning')) {
    if (-not (($csvHeader -split ',') -contains $field)) { Stop-With "Dataset lacks required column ${field}: $data" }
}
Write-Host 'Ames Housing CSV: present and required columns found'

if (-not (Existing-File (Join-Path $root 'uv.lock'))) {
    $oldLock = Join-Path $oldProj 'uv.lock'
    if (Existing-File $oldLock) {
        Copy-Item -LiteralPath $oldLock -Destination 'uv.lock'
        Write-Host 'Copied uv.lock from Lab 2 (same pyproject.toml)'
    } else {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Stop-With 'uv.lock is missing. Install uv or copy uv.lock from Lab 2.' }
        Write-Host 'Generating lockfile with uv lock...'
        & uv lock
        if ($LASTEXITCODE -ne 0) { Stop-With 'uv lock failed; internet access may be required once.' }
    }
}

& docker compose -p $ProjectName config --quiet
if ($LASTEXITCODE -ne 0) { Stop-With 'Docker Compose config is invalid.' }
$args = @('compose', '-p', $ProjectName, 'up', '-d')
if (-not $NoBuild) { $args += '--build' }
Write-Host ('Running: docker ' + ($args -join ' '))
& docker @args
if ($LASTEXITCODE -ne 0) { Stop-With 'Docker Compose failed; inspect its output.' }
Write-Host '=== Containers ==='
& docker compose -p $ProjectName ps -a
Write-Host 'Checking Orders API /health...'
$ok = $false
for ($n = 0; $n -lt 20; $n++) {
    try {
        $h = Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 2 -ErrorAction Stop
        if ($h.status -eq 'ok') { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $ok) {
    Write-Host 'Orders API has not become available; recent logs:'
    & docker compose -p $ProjectName logs --tail=35 orders-api
    Stop-With 'Orders API /health is not responding. Check DB secret and logs above.'
}
Write-Host 'SUCCESS: Orders API responds; Swagger: http://localhost:8000/docs'
Write-Host 'Forecast API is intentionally internal (not published at localhost:8001).'

