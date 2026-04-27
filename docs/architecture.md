# Architecture

## System Overview

```mermaid
flowchart LR
    UI[React/Vite Frontend]
    API[FastAPI Agent Gateway]
    ORCH[Deterministic Orchestrator]
    LLM[Local LLM Adapter]
    TOOLS[Approved Internal Tools]
    MOCK[Mock SuccessFactors Connector]
    REAL[Real SuccessFactors Connector Scaffold]
    SAP[SAP SuccessFactors]
    DB[(SQLite Audit + Request History)]

    UI --> API
    API --> ORCH
    ORCH --> LLM
    ORCH --> TOOLS
    TOOLS --> MOCK
    TOOLS --> REAL
    MOCK --> SAP
    REAL --> SAP
    API --> DB
    ORCH --> DB
```

## Request Flow

```mermaid
sequenceDiagram
    participant User
    participant UI as Frontend
    participant API as Backend API
    participant Orch as Orchestrator
    participant LLM as Local LLM
    participant Tools as Tool Layer
    participant Conn as Connector
    participant DB as SQLite

    User->>UI: Ask HR question
    UI->>API: POST /api/chat
    API->>DB: Create request record
    API->>Orch: Forward request + demo user context
    Orch->>LLM: Extraction prompt
    LLM-->>Orch: Strict JSON only
    Orch->>Tools: resolve_employee(...)
    Orch->>Orch: Authorization check in backend code
    Orch->>Tools: count_absences(...) or list_absences(...)
    Tools->>Conn: Normalized connector call
    Conn-->>Tools: Normalized absence data
    Orch->>LLM: Final answer prompt with minimized result only
    LLM-->>Orch: Answer text
    Orch->>DB: Persist trace + audit
    API-->>UI: answer + trace + request_id
```

## Security Boundary Notes

- The model never receives SAP credentials.
- The model never selects arbitrary tools or raw SAP queries.
- Authorization happens after employee resolution and before absence retrieval.
- The answer-generation prompt receives only minimized normalized data.
- `RealSuccessFactorsConnector` is scaffolded with explicit TODO markers for production-grade OData filtering and normalization.
