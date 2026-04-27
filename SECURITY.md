# Security Notes for the Local MVP

## Why Data Stays Local

- The application only supports `LLM_BACKEND=ollama` or `LLM_BACKEND=mock`.
- The Ollama adapter rejects non-local hosts such as external URLs.
- No external AI API client is included in the codebase.
- The UI surfaces `Model inference: local` and `External AI calls: none` from backend metadata.

## Security Controls Included in the MVP

- SAP credentials are read from environment variables only.
- The model never receives SAP credentials.
- The model never selects arbitrary tools or raw SAP queries.
- Authorization is enforced in backend code before absence retrieval.
- Only minimized normalized data is passed to final answer generation.
- Request traces and audit records are persisted for review.
- Connector access is abstracted behind an allowlisted internal tool layer.

## What This MVP Does Not Fully Protect Yet

- It is not hardened for multi-tenant or internet-facing deployment.
- Demo user switching is intentionally simple and not real authentication.
- SQLite is used for local demo persistence, not production-grade auditing.
- The real SuccessFactors connector is scaffolded only and not yet fully implemented.
- Logging and redaction are basic and should be expanded before production use.

## Planned Production Hardening

- Replace demo user switching with real SSO and session management.
- Move secrets to a managed secret store and rotate them regularly.
- Add structured audit logging to a centralized secure sink.
- Add row-level authorization backed by real org hierarchy and policy data.
- Add rate limiting, CSRF protections where relevant, and stronger input abuse controls.
- Add production monitoring, alerting, and connector retry/circuit breaker behavior.
- Add end-to-end integration tests against a real SuccessFactors sandbox.
