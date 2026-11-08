# Kitchen Copilot — Architecture

```mermaid
flowchart TD
    U[Campus Users] --> WEB[Next.js]
    WEB --> API[FastAPI Core API]
    API --> DB[(PostgreSQL)]
    API --> V[(pgvector)]
    API --> M[(MongoDB)]
    API --> R[(Redis)]
    R --> C[Celery Workers]
    API --> L[LLM Provider]
    C --> L
    API --> A[Flask Actions Service]
    A --> DB
```

Next.js provides the interface. FastAPI handles authentication, permissions, campus isolation, business APIs and AI orchestration. PostgreSQL is authoritative for transactions. pgvector supports procedure retrieval. Redis/Celery handle background tasks. Flask Actions validates approved operations. The frontend never calls the LLM directly.
