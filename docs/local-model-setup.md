# Local Model Setup

This MVP already supports a fully local LLM path through Ollama. Use this guide to install a local model and switch the backend from `mock` to a real local runtime.

## Recommended Starting Model

For this HR assistant MVP, start with:

- `qwen2.5:7b`

Why this is a good default for the demo:

- good general instruction-following
- good JSON and structured-output behavior
- multilingual support
- moderate size for a local Windows laptop or desktop

If your machine is smaller, try:

- `qwen2.5:3b`

If your machine is stronger and you want better quality, try:

- `qwen2.5:14b`

## 1. Install Ollama on Windows

Official options:

- GUI installer: https://ollama.com/download/windows
- PowerShell installer:

```powershell
irm https://ollama.com/install.ps1 | iex
```

After installation, Ollama runs locally and serves its API on `http://localhost:11434`.

## 2. Pull a Local Model

Simplest path:

```powershell
Set-Location 'C:\Users\HP\Desktop\sap sf IA chat'
.\scripts\windows\install-ollama-model.ps1 -Model qwen2.5:7b
```

Equivalent direct Ollama command:

```powershell
ollama pull qwen2.5:7b
```

## 3. Confirm the Model Is Installed

CLI:

```powershell
ollama ls
```

API:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:11434/api/tags'
```

## 4. Switch This App to the Local Model

Set these values in `backend/.env` or your terminal session:

```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
CONNECTOR_BACKEND=mock
```

## 5. Start the Backend with Ollama

Helper script:

```powershell
Set-Location 'C:\Users\HP\Desktop\sap sf IA chat'
.\scripts\windows\start-backend-ollama.ps1 -Model qwen2.5:7b -Port 8001
```

Manual command:

```powershell
Set-Location 'C:\Users\HP\Desktop\sap sf IA chat\backend'
$env:LLM_BACKEND='ollama'
$env:CONNECTOR_BACKEND='mock'
$env:OLLAMA_MODEL='qwen2.5:7b'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## 6. Verify in the App

Once the backend is up:

- `GET /api/health` should show `llm_backend: ollama`
- `GET /api/health` should show `llm_model: qwen2.5:7b`
- the UI trace panel should display the configured local model
- the `Current Access` panel should show an installed-model selector when Ollama is active

## 7. Switch Models from the UI

When the backend is running with `LLM_BACKEND=ollama`, the frontend can now:

- list installed local Ollama models
- show the active model in health/trace
- switch the active model for future requests

This uses backend-controlled demo endpoints and does not change the approved tool boundary.

## Notes

- If Ollama is reachable but the model is missing, the backend now returns a clearer error telling you to run `ollama pull <model>`.
- If you need to store models somewhere other than your home directory, set the user environment variable `OLLAMA_MODELS` before starting Ollama.
- Keep `CONNECTOR_BACKEND=mock` until your SuccessFactors tenant access is available.
- If `ollama` is not recognized in a fresh PowerShell session, reopen the terminal after installation. The local API can still be reachable even before PATH refreshes.
