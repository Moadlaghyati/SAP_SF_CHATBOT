# SAP SuccessFactors Absence Agent

This project is a local HR AI assistant MVP with a dedicated SAP SuccessFactors absence workflow. The assistant can understand absence-related natural-language questions, decide whether the SAP absence workflow should run, extract retrieval parameters, query SAP SuccessFactors OData APIs, and return formatted absence summaries.

The implementation is intentionally modular so more SAP SuccessFactors agents can be added later, such as employee profile, payroll, onboarding, and performance review agents.

## What It Can Answer

The assistant is designed to handle absence, leave, PTO, vacation, holiday, sick leave, and time-off questions.

Examples:

```text
How many absences did Walid Regragi have in 2026?
Show me Walid Regragi's absences in April 2026.
Did user 90000634 have vacation in April 2026?
Who was absent in March 2026?
Who was absent in avril 2026?
Are there any employees on vacation on 2026-05-07?
I want to see all absences in this company in 2026.
Show all leaves for this organization in April 2026.
```

Non-absence questions should not trigger SAP absence retrieval.

Examples that should not trigger the SAP absence agent:

```text
What is SAP SuccessFactors?
What can you do?
How much is 3+3?
Show payroll for Walid Regragi.
Who is Walid's manager?
```

## Architecture

The absence workflow is separated from the general assistant flow.

```text
backend/
  app/
    agents/
      sap/
        sap_absence_agent.py
        sap_success_factors_client.py
        sap_auth_service.py
        absence_intent.py
        absence_extraction.py
        absence_schemas.py
        absence_formatter.py
    orchestrator/
      service.py
```

Main responsibilities:

| Component | Responsibility |
|---|---|
| `absence_intent.py` | Detects whether a message is absence-related. |
| `absence_extraction.py` | Extracts employee name, userId, date range, month, year, and scope. |
| `sap_auth_service.py` | Fetches and caches OAuth2 SAML Bearer access tokens. |
| `sap_success_factors_client.py` | Builds OData URLs, sends authenticated SAP requests, follows pagination. |
| `absence_formatter.py` | Normalizes SAP dates and formats human-readable summaries. |
| `sap_absence_agent.py` | Coordinates intent, extraction, name resolution, SAP query, and response formatting. |
| `orchestrator/service.py` | Routes absence-related messages to the SAP Absence Agent only when appropriate. |

## Runtime Flow

```text
User message
  -> Main assistant/orchestrator
  -> Absence intent precheck
  -> If absence-related: SAP Absence Agent
  -> Parameter extraction
  -> Employee-specific or workforce/company-wide scope decision
  -> Optional name-to-userId resolution
  -> OAuth token fetch/cache
  -> SAP EmployeeTime OData query
  -> Pagination handling
  -> Result normalization
  -> Formatted response
```

The workflow does not run for every message. It runs only when the request clearly asks for absence, leave, PTO, vacation, holiday, sick leave, days off, or time-off records.

## Supported Query Scopes

### Employee-Specific

Triggered when the user provides an employee name or SAP `userId`.

```text
Show absences for Walid Regragi in 2026.
Get leave records for user 90000634 in April 2026.
```

If the user provides a name, the app resolves the name through the SAP `User` entity:

```text
GET /User?$filter=firstName eq 'Walid' and lastName eq 'Regragi'
```

If the name cannot be resolved to exactly one `userId`, the assistant asks for clarification.

### Workforce / Company-Wide

Triggered when the user asks about all employees, the company, organization, workforce, or who was absent.

```text
Who was absent in March 2026?
I want to see all absences in this company in 2026.
Which employees are on vacation on 2026-05-07?
```

These queries do not require an employee name or userId. They query the SAP population visible to the configured API user.

If the SAP API user is permission-scoped to a specific company, such as `FRMF - Morocco National Team (Test) (MM01)`, then company-wide queries will effectively be limited by that SAP permission scope. If the API user has broader permissions, the results may include broader data unless an explicit company filter is added.

## SAP OData Queries

Employee-specific absence query:

```http
GET {SAP_BASE_URL}/EmployeeTime?$format=json&$filter=userId eq '<USER_ID>' and startDate ge datetime'<START_DATE>T00:00:00' and endDate le datetime'<END_DATE>T23:59:59'
```

Workforce/company-wide absence query uses overlap logic:

```http
GET {SAP_BASE_URL}/EmployeeTime?$format=json&$filter=startDate le datetime'<END_DATE>T23:59:59' and endDate ge datetime'<START_DATE>T00:00:00'
```

Overlap logic is important because it includes absences that started before the requested day or range but still overlap it.

Example:

```text
Absence: 2026-05-01 to 2026-05-10
Question: Who is absent on 2026-05-07?
Result: included
```

## Authentication

The app uses SAP SuccessFactors OAuth2 SAML Bearer authentication.

Required environment variables:

```env
SAP_BASE_URL=https://api012.successfactors.eu/odata/v2
SAP_COMPANY_ID=<YOUR_COMPANY_ID>
SAP_OAUTH_TOKEN_URL=https://api012.successfactors.eu/oauth/token
SAP_AUTH_MODE=oauth
SAP_CLIENT_ID=<YOUR_CLIENT_ID>
SAP_SAML_ASSERTION=<YOUR_SAML_ASSERTION>
```

Do not commit real credentials, SAML assertions, access tokens, or Authorization headers.

For local development, put real values in:

```text
backend/.env
```

This file is ignored by Git.

## Local Development

### Backend

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The frontend proxy expects the backend on port `8001`.

### Frontend

```powershell
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173
```

### Ollama

The project can use a local Ollama model.

Expected default:

```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
```

Check installed models:

```powershell
ollama list
```

Start Ollama if needed:

```powershell
ollama serve
```

## Workflow Visibility

Every request includes trace/debug workflow steps.

In the UI, expand:

```text
Trace & Debug -> Workflow Steps
```

Typical employee-specific success flow:

```text
received
request_context
absence_intent_precheck
sap_absence_agent
sap_absence_intent
sap_parameter_extraction
sap_user_resolution
sap_absence_query
sap_response_formatting
```

Typical workforce/company-wide success flow:

```text
received
request_context
absence_intent_precheck
sap_absence_agent
sap_absence_intent
sap_parameter_extraction
sap_absence_query
sap_response_formatting
```

These steps make it clear whether a request stopped at routing, extraction, name resolution, SAP authorization, SAP query, pagination, or formatting.

## Response Format

Employee-specific example:

```text
Found 5 absence records for user 90000634 from 2026-01-01 to 2026-12-31:
1. MA_Work - 2026-01-12 to 2026-01-12 - APPROVED
2. MA_Work - 2026-01-13 to 2026-01-13 - APPROVED
3. MA_Work - 2026-01-15 to 2026-01-15 - APPROVED
4. MA_Work - 2026-01-16 to 2026-01-16 - APPROVED
5. MAR_VACATION - 2026-04-13 to 2026-04-14 - APPROVED
```

Workforce/company-wide example:

```text
Found 3 employee absence records on 2026-05-07:
1. User 90000634 - MAR_VACATION - 2026-05-06 to 2026-05-08 - APPROVED
2. User 90000689 - Sick Leave - 2026-05-07 to 2026-05-07 - APPROVED
3. User 90000543 - PTO - 2026-05-01 to 2026-05-10 - PENDING
```

SAP `/Date(...) /` values are normalized to ISO dates.

## Pagination

SAP SuccessFactors OData responses may return only the first page of results, often capped around 1000 records.

The client follows SAP `__next` pagination links automatically and merges results.

A safety limit is applied to avoid runaway pagination:

```text
max_pages = 100
```

## Security Notes

The implementation avoids logging:

- access tokens
- SAML assertions
- Authorization headers
- raw credential values

Trace output uses presence flags such as:

```json
{
  "user_id_present": true
}
```

instead of exposing sensitive values unnecessarily in workflow steps.

Be careful with broad workforce/company-wide questions because they can return many employee records. SAP permission roles should restrict the API user to the intended target population.

## Test Questions

### Employee-Specific

```text
How many absences did Walid Regragi have in 2026?
Show me Walid Regragi's absences in April 2026.
Did Walid Regragi take vacation in April 2026?
Get leave records for user 90000634 from 2026-04-01 to 2026-04-30.
Show sick leave for Walid Regragi in March 2026.
```

### Workforce / Company-Wide

```text
Who was absent in March 2026?
Who was absent in avril 2026?
Are there any employees absent on 2026-05-07?
Which employees are on vacation on 2026-05-07?
I want to see all absences in this company in 2026.
Show all leaves for this organization in April 2026.
```

### Messy Natural Language

```text
how much leaves do Walid Regragi had in this year 2026?
how much leaves do Walid Regragi had in this mounth 04/2026?
did Walid take any days off in april?
who's off today?
anyone on vacation tomorrow?
```

### Clarification / Edge Cases

```text
Show me absences.
Did he take vacation in April?
Show absences for John.
Who was absent?
Show absences for user 99999999 in 2026.
```

### Non-Absence

```text
What is SAP SuccessFactors?
What can you do?
How much is 3+3?
Show payroll for Walid Regragi.
Who is Walid's manager?
```

## Running Tests

Backend:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest --basetemp .pytest_tmp_run
```

Frontend:

```powershell
cd frontend
npm.cmd test -- --run
```

## Troubleshooting

### The assistant says the employee is not found

Check whether:

- `CONNECTOR_BACKEND=successfactors`
- the SAP `User` lookup can find the employee
- the name is spelled as SAP stores it
- the API user has permission to read `User`

### The assistant asks for an employee when asking a broad question

Use workforce wording:

```text
Who was absent in April 2026?
Show all absences in this company in 2026.
Which employees are on leave on 2026-05-07?
```

### The assistant returns only 1000 records

The client supports SAP `__next` pagination. If it still stops early, check:

- SAP response includes `d.__next`
- the API user can access subsequent pages
- the safety page limit was not reached

### Health says connector is mock

The backend is not running against SAP.

Set:

```env
CONNECTOR_BACKEND=successfactors
```

Then restart the backend.

### Health says Ollama unavailable

Start Ollama:

```powershell
ollama serve
```

Then restart the backend or refresh health.

## Future Extensions

The SAP agent folder is designed for more agents:

```text
SapRouterAgent
  - SapAbsenceAgent
  - SapEmployeeProfileAgent
  - SapPayrollAgent
  - SapOnboardingAgent
  - SapPerformanceReviewAgent
```

The current implementation focuses only on absence retrieval.

