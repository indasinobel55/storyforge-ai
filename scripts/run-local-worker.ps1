param(
    [string]$ApiUrl = "http://localhost:8000",
    [string]$Token = $env:LOCAL_EXECUTION_TOKEN,
    [switch]$Drain,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not $Token) {
    throw "Set LOCAL_EXECUTION_TOKEN or pass -Token. Create a token in Settings -> Execution."
}

$env:STUDIO_API_URL = $ApiUrl
$env:LOCAL_EXECUTION_TOKEN = $Token

$arguments = @("-m", "local_agent", "--api-url", $ApiUrl)
if ($Once) { $arguments += "--once" }
elseif ($Drain) { $arguments += "--drain" }

Write-Host "Starting local worker against $ApiUrl (EXECUTION_MODE must be local)." -ForegroundColor Cyan
python @arguments
