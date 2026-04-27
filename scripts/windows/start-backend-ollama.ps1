param(
    [string]$Model = "qwen2.5:7b",
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$backendPath = Join-Path $repoRoot "backend"
$venvPython = Join-Path $backendPath ".venv\Scripts\python.exe"

function Resolve-PythonExecutable {
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return "py"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return "python"
    }

    throw "Python was not found. Create backend\.venv first or install Python."
}

try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 5
} catch {
    throw "Ollama is not responding on http://127.0.0.1:11434. Start the Ollama app first."
}

$installedModels = @($tags.models | ForEach-Object { $_.name })
if ($installedModels -notcontains $Model) {
    throw "Model '$Model' is not installed locally. Run scripts/windows/install-ollama-model.ps1 -Model $Model"
}

$pythonExe = Resolve-PythonExecutable

Set-Location $backendPath
$env:LLM_BACKEND = "ollama"
$env:CONNECTOR_BACKEND = "mock"
$env:OLLAMA_MODEL = $Model

Write-Host "Starting backend with local model '$Model' on port $Port..." -ForegroundColor Cyan

if ($pythonExe -eq "py") {
    & py -m uvicorn app.main:app --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
}

& $pythonExe -m uvicorn app.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
