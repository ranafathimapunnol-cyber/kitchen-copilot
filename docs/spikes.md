# Week 1 — Technical Spike Results

**Project:** Kitchen Copilot
**Date:** 09 November 2026
**Status:** Completed for Week 1 prototype evaluation

## 1. AI Tool-Calling Spike

- Implemented a prototype tool registry.
- Used FakeLLM to simulate tool selection without an external LLM API.
- Added a synthetic stock-summary tool.
- Added role-based access checks for tool execution.
- Added campus-scoped user context.
- Verified that unauthorized roles are rejected.

**Limitation:** This is a prototype. It does not provide production AI decision-making or unrestricted action execution.

## 2. PostgreSQL Vector Retrieval Spike

- Used PostgreSQL with the pgvector extension.
- Created an isolated `ai_spike` schema for synthetic procedure documents.
- Implemented a 64-dimensional deterministic hash-embedding provider.
- Implemented campus-scoped similarity search.

### Retrieval benchmark

| Metric | Result |
|---|---:|
| Test questions | 10 |
| Expected documents retrieved in top 3 | 10 |
| Hit@3 | 100% |
| Week 1 target | At least 70% |
| Result | Passed |

All 10 synthetic benchmark questions retrieved their expected document within the top three results.

**Limitations:**
- The benchmark uses a small synthetic document collection.
- The hash-embedding provider is a deterministic prototype, not a production semantic embedding model.
- The 100% result must not be interpreted as production retrieval accuracy.
- Real campus SOPs and a production embedding model require separate evaluation.

## 3. Streaming Spike

- Implemented a standalone FastAPI streaming endpoint.
- Used Server-Sent Events (SSE) to stream FakeLLM output token by token.
- Verified the completion marker `[DONE]`.

**Limitation:** The spike verifies the backend streaming prototype. Full frontend integration and real LLM streaming are not established by this test.

## 4. Week 1 Conclusion

The tool-calling, vector retrieval, and streaming prototypes have been implemented and evaluated at prototype level.

The retrieval benchmark achieved **10/10 (100%) Hit@3**, exceeding the Week 1 target of 7/10.

These results demonstrate technical feasibility for the Week 1 prototypes only. They do not establish production readiness or complete AI-agent functionality.