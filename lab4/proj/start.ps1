<##
Practice 4 one-command Windows launcher.
First run provisions secrets+CSV+dependencies, MLflow DB, executes trainer (if @prod
is absent) and launches all live services. Later runs do NOT retrain.
No database volume is removed and no existing db_password is overwritten.
#>
param([string]$ProjectName='proj', [switch]$ForceTrain)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$root=(Get-Location).Path
$integrationDir=Split-Path (Split-Path $root -Parent) -Parent
$oldProjects=@('house-price-lab3-ready','house-price-lab-task3','house-price-lab-task2')
function Fail([string]$msg) { throw "LAB4: $msg" }
function Is-NonemptyFile([string]$path) {
  (Test-Path -LiteralPath $path -PathType Leaf) -and ((Get-Item -LiteralPath $path).Length -gt 0)
}
function Replace-EmptyPlaceholder([string]$path) {
  if (Test-Path -LiteralPath $path -PathType Container) {
    if ((Get-ChildItem -LiteralPath $path -Force | Measure-Object).Count -ne 0) {
      Fail "Expected a file, but found a non-empty directory: $path"
    }
    Remove-Item -LiteralPath $path -Force
    Write-Host "Removed empty Docker bind placeholder directory: $path"
  }
}
function Find-Previous([string]$relative) {
  foreach ($name in $oldProjects) {
    $candidate=Join-Path (Join-Path (Join-Path $integrationDir $name) 'proj') $relative
    if (Is-NonemptyFile $candidate) { return $candidate }
  }
  return $null
}
function Random-Secret([string]$target, [int]$n) {
  $bytes=New-Object byte[] $n
  $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  [IO.File]::WriteAllText($target,[Convert]::ToBase64String($bytes),(New-Object Text.UTF8Encoding($false)))
  Write-Host "Generated secret file: $(Split-Path $target -Leaf) (hidden)"
}
function Ensure-Secret([string]$name, [bool]$allowNew, [int]$size) {
  $path=Join-Path $root ("secrets\"+$name)
  Replace-EmptyPlaceholder $path
  if (Is-NonemptyFile $path) { Write-Host "Using existing ${name}"; return }
  if (Test-Path -LiteralPath $path) { Fail "Empty $name file; restore a backup" }
  $old=Find-Previous ("secrets\"+$name)
  if ($null -ne $old) { Copy-Item -LiteralPath $old -Destination $path; Write-Host "Copied $name from previous lab"; return }
  if (-not $allowNew) { Fail "Existing proj_pgdata volume: original $name must be copied from previous project" }
  Random-Secret $path $size
}
function Dc([string[]]$arguments) {
  & docker compose -p $ProjectName @arguments
  if ($LASTEXITCODE -ne 0) { Fail ("docker compose " + ($arguments -join ' ') + " failed") }
}
Write-Host '=== LAB 4: MLflow + registry + Redis/RQ start ==='
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Install/start Docker Desktop' }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker Engine is unavailable; open Docker Desktop' }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail 'Install uv (pip install uv) for resolving the shared uv.lock' }
New-Item -ItemType Directory -Force -Path 'secrets','training_service\data' | Out-Null
if (-not (Test-Path '.env' -PathType Leaf)) { Copy-Item '.env.example' '.env' }
if (Select-String -Path '.env' -Pattern '^\s*(POSTGRES_PASSWORD|MODEL_VERSION)\s*=' -Quiet) {
  Fail 'Remove POSTGRES_PASSWORD and MODEL_VERSION from .env; use Docker secret and MODEL_ALIAS'
}
& docker volume inspect "${ProjectName}_pgdata" *> $null
$hasPgVolume = ($LASTEXITCODE -eq 0)
Ensure-Secret 'db_password' (-not $hasPgVolume) 24
Ensure-Secret 'jwt_secret_key' $true 48
$dataset=Join-Path $root 'training_service\data\ames_train.csv'
Replace-EmptyPlaceholder $dataset
if (-not (Is-NonemptyFile $dataset)) {
  $old=Find-Previous 'forecast-service\data\ames_train.csv'
  if ($null -ne $old) { Copy-Item -LiteralPath $old -Destination $dataset; Write-Host 'Copied Ames CSV from previous lab' }
  else {
    Fail 'Copy Ames train.csv into training_service\data\ames_train.csv (from your Lab 3 forecast-service\data)'
  }
}
$header=Get-Content -LiteralPath $dataset -TotalCount 1
foreach ($field in @('SalePrice','GrLivArea','TotalBsmtSF','GarageArea','YearBuilt','OverallQual','MSZoning')) {
  if (-not (($header -split ',') -contains $field)) { Fail "Dataset lacks required column ${field}" }
}
Write-Host 'Dataset validated'
Write-Host 'Resolving shared uv.lock for the pinned project dependencies...'
& uv lock --python 3.12
if ($LASTEXITCODE -ne 0) { Fail 'uv lock failed; internet access is required for first dependency resolve' }
Dc -arguments @('config','--quiet')
# The old Practice 3 project may have a forecast-api with an embedded Ridge image.
# Prevent it from serving stale model while MLflow is being bootstrapped.
# Docker Compose writes progress to stderr. In Windows PowerShell 5.1,
# redirecting native stderr while ErrorActionPreference=Stop can raise NativeCommandError.
$previousErrorAction = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  & docker compose -p $ProjectName stop forecast-api 2>$null | Out-Null
  $stopExitCode = $LASTEXITCODE
} finally {
  $ErrorActionPreference = $previousErrorAction
}
if ($stopExitCode -ne 0) { Fail 'Unable to stop the previous forecast-api container' }
Write-Host 'Starting PostgreSQL, MLflow, Redis, Orders API and a separate worker...'
Dc -arguments @('up','-d','--build','postgres','mlflow-db-init','mlflow','redis','orders-api','orders-worker')
# Check alias without exporting secrets or requiring trainer to have been built.
# A missing @prod alias is expected on first run: it triggers training.
# Silence stderr without turning the expected nonzero exit into a fatal PS error.
$previousErrorAction = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $aliasOut = & docker compose -p $ProjectName exec -T mlflow python /opt/alias_check.py 2>$null
  $aliasReady = ($LASTEXITCODE -eq 0)
} finally {
  $ErrorActionPreference = $previousErrorAction
}
if (-not $aliasReady -or $ForceTrain) {
  Write-Host 'Training/registering two versions: Ridge baseline + XGBoost (20 Optuna trials)...'
  Dc -arguments @('run','--rm','--build','trainer')
} else { Write-Host "Using existing registry alias house-price@prod -> version $aliasOut" }
Write-Host 'Starting Registry-backed Forecast API...'
Dc -arguments @('up','-d','--build','--force-recreate','forecast-api')
Dc -arguments @('ps','-a')
Write-Host 'Lab 4 startup requested. Verify: curl.exe http://localhost:8000/health'
Write-Host 'Swagger: http://localhost:8000/docs | MLflow UI: http://localhost:5000'
