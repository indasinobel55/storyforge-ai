param(
    [switch]$SkipFrontend,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not $SkipTests) {
    Write-Host "Running backend tests..." -ForegroundColor Cyan
    python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed" }
}

if (-not $SkipFrontend) {
    Write-Host "Building frontend..." -ForegroundColor Cyan
    Push-Location -LiteralPath (Join-Path $root "frontend")
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    }
    finally {
        Pop-Location
    }
}

Write-Host "All checks passed." -ForegroundColor Green
