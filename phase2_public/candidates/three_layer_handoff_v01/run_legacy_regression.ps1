param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$DependencyDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$legacyPackage = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../scope_dependency_v41'))
$overlayPath = (Resolve-Path -LiteralPath $DependencyDirectory).Path
$previous = @{}
$settings = @{ PYTHONPATH=$overlayPath; PYTHONIOENCODING='utf-8'; PYTHONDONTWRITEBYTECODE='1'; HF_HUB_OFFLINE='1'; TRANSFORMERS_OFFLINE='1' }
foreach ($key in $settings.Keys) { $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process') }
try {
    foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process') }
    & $Python (Join-Path $legacyPackage 'src/run_offline_regression_suite.py') --package $legacyPackage --output $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw "Frozen regression failed; preserve the output and inspect the error." }
} finally {
    foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
