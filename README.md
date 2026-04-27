# HR AI Assistant Local MVP

Local demo MVP for an HR AI assistant that queries SAP SuccessFactors through a connector boundary while keeping all model inference local.

## What This MVP Demonstrates

- Natural-language HR questions about absences
- Deterministic orchestration with a strict tool allowlist
- Local-only LLM integration through a pluggable adapter
- Backend-enforced authorization for employee, manager, and hr_admin demo roles
- Traceable request history and audit logging in SQLite
- Mock SuccessFactors mode that runs end-to-end before real SAP credentials are available

## Architecture Overview

- Frontend: `React + Vite + TypeScript`
- Backend: `FastAPI + Pydantic + SQLAlchemy`
- Persistence: `SQLite`
- Local model runtime target: `Ollama`
- Connector boundary: `MockSuccessFactorsConnector` and `RealSuccessFactorsConnector`

Detailed diagrams live in [docs/architecture.md](docs/architecture.md).
Local model setup steps live in [docs/local-model-setup.md](docs/local-model-setup.md).

## Repository Layout

```text
/frontend
/backend
  /app
    /api
    /audit
    /auth
    /config
    /connectors
    /llm
    /orchestrator
    /repositories
    /schemas
    /services
    /tests
    /tools
/docker
/docs
```

## Environment Variables

Copy [.env.example](.env.example) and use the values you need for backend and frontend local runs.

Core variables:

- `CONNECTOR_BACKEND=mock|successfactors`
- `LLM_BACKEND=ollama|mock`
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=qwen2.5:7b`
- `DATABASE_URL=sqlite:///./hr_ai_assistant.db`
- `DEMO_REFERENCE_DATE=2026-04-22`

SAP scaffold variables:

- `SAP_BASE_URL`
- `SAP_COMPANY_ID`
- `SAP_OAUTH_TOKEN_URL`
- `SAP_AUTH_MODE=basic|oauth`
- `SAP_USERNAME`
- `SAP_PASSWORD`
- `SAP_CLIENT_ID`
- `SAP_CLIENT_SECRET`
- `SAP_SAML_ASSERTION`

SAP SuccessFactors absence workflow variables:

```env
SAP_BASE_URL=https://api012.successfactors.eu/odata/v2
SAP_COMPANY_ID=iconunternD
SAP_OAUTH_TOKEN_URL=https://api012.successfactors.eu/oauth/token
SAP_CLIENT_ID=<PUT_CLIENT_ID_IN_ENV>
SAP_SAML_ASSERTION=<PUT_SAML_ASSERTION_IN_ENV>
```

Do not commit real OAuth client IDs, SAML assertions, access tokens, Authorization headers, or employee-sensitive data.

## Run Locally on Windows

### 1. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
uvicorn app.main:app --reload
```

If PowerShell script execution blocks activation, use:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### 2. Frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

### 3. Open the Demo

- Frontend: `http://127.0.0.1:5173`
- Backend API: `http://127.0.0.1:8000`
- FastAPI docs: `http://127.0.0.1:8000/docs`

## Mock Mode

Mock mode is the default fastest path to a full demo.

Set:

```env
CONNECTOR_BACKEND=mock
LLM_BACKEND=mock
```

That gives you:

- local deterministic mock LLM extraction and answer generation
- seeded demo employees and absence records
- authorization, audit, request history, trace view, and UI flow end-to-end

For a real local-model path, switch to:

```env
CONNECTOR_BACKEND=mock
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5:7b
```

Then:

1. install Ollama on Windows
2. pull a model locally
3. start the backend against Ollama

Quickest Windows path:

```powershell
Set-Location 'C:\Users\HP\Desktop\sap sf IA chat'
.\scripts\windows\install-ollama-model.ps1 -Model qwen2.5:7b
.\scripts\windows\start-backend-ollama.ps1 -Model qwen2.5:7b -Port 8001
```

The full step-by-step guide is in [docs/local-model-setup.md](docs/local-model-setup.md).

When the backend is running with `LLM_BACKEND=ollama`, the UI also exposes a local model selector so you can switch among installed Ollama models without editing env files between runs.

## Real SAP Later

`backend/app/connectors/real_successfactors.py` is scaffolded for the real SuccessFactors integration.

What is already in place:

- environment-based credential loading
- connector contract parity with the mock connector
- explicit TODO markers for OData filtering, narrow selects, and normalization
- hard failure when configuration is incomplete

What remains:

- tenant-specific authentication flow
- real OData request implementation
- response normalization from SAP payloads into internal models
- integration tests against a real or sandbox SuccessFactors tenant

## Demo Walkthrough

1. Launch in mock mode.
2. Keep the default user as `Meryem Ait Said` to demo manager access.
3. Run these prompts in order:
   `How many absences did Sara Bennani have between 2026-01-01 and 2026-03-31?`
   `How many sick leaves did Sara Bennani have in Q1 2026?`
   `How many absences did my direct report Ahmed have last month?`
   `Show the absence breakdown by type for Yasmine in February 2026.`
4. Switch to `Nadia El Fassi` to demonstrate ambiguity with `Yasmine`.
5. Switch back to `Meryem Ait Said` and ask about `Karim Ouali` to show forbidden access.
6. Ask a payroll question to show the unsupported fallback.

## API Summary

- `POST /api/chat`
- `GET /api/requests`
- `GET /api/requests/{id}`
- `GET /api/audit`
- `GET /api/health`
- `GET /api/demo/users`
- `POST /api/demo/switch-user`

`POST /api/chat` accepts:

```json
{
  "message": "How many absences did Sara Bennani have between 2026-01-01 and 2026-03-31?"
}
```

with acting user supplied via `X-Demo-User-Id`.

## Tests

Backend tests target:

- parsed-question schema validation
- employee resolution and auth filtering
- absence counting logic
- unsupported intent fallback
- ambiguous employee handling
- forbidden access handling
- connector contract consistency
- API happy path

Run them with:

```powershell
cd backend
pytest
```

Frontend smoke test:

```powershell
cd frontend
npm.cmd test
```

## What Is Mocked vs Real

Mocked now:

- SuccessFactors data retrieval
- local LLM behavior when `LLM_BACKEND=mock`
- demo user identities and access scopes

Real now:

- FastAPI backend and orchestration flow
- request history and audit persistence
- role-based authorization enforcement
- trace/debug metadata and UI visibility
- Ollama adapter contract and local-only guardrails

Scaffolded but not complete:

- real SuccessFactors API calls
- production-grade authentication, monitoring, and secrets management

## Notes About This Machine

This repository was built with Windows-native execution in mind. Docker files are included, but Docker was not available on PATH in the current environment during implementation, so native local startup is the primary documented path.
