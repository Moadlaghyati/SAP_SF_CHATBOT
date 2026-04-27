param(
    [string]$Model = "qwen2.5:7b"
)

$ErrorActionPreference = "Stop"

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host ""
    Write-Host "Ollama is not installed or not on PATH." -ForegroundColor Red
    Write-Host "Install it from https://ollama.com/download/windows" -ForegroundColor Yellow
    Write-Host "or run: irm https://ollama.com/install.ps1 | iex" -ForegroundColor Yellow
    exit 1
}

Write-Host "Pulling local model '$Model'..." -ForegroundColor Cyan
ollama pull $Model
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Installed models:" -ForegroundColor Green
ollama ls
