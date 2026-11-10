
# Week 1 — Technical Spike Results

**Project:** Kitchen Copilot
**Evaluation date:** 10 November 2026
**Scope:** Week 1 technical prototypes
**Status:** Three prototype experiments implemented and evaluated

## 1. AI Tool-Calling Spike

### Objective

Validate whether an LLM can select an available Python function, provide its arguments, and use the function result to generate a natural-language response.

### Implementation

- Implemented a Python tool registry.
- Implemented FakeLLM for deterministic testing without external API access.
- Integrated the Google Gemini API using the `google-genai` SDK.
- Configured Gemini function calling for `get_stock_status`.
- Implemented Python-side tool execution.
- Added role-based authorization.
- Added campus-scoped user context.
- Added cross-campus result protection.
- Used synthetic stock records for demonstration.

### Gemini configuration

| Setting | Value |
|---|---|
| Provider | Google Gemini |
| SDK | google-genai |
| Model | gemini-3.1-flash-lite |
| Function | get_stock_status |
| API key | Environment variable |

### Verified experiment

**User prompt:**

> How much rice stock is available in my campus?

**Gemini function selection:**

`get_stock_status`

**Arguments:**

```json
{
  "item_name": "rice"
}
```

**Python tool result:**

```json
{
  "campus_id": "KC-DEMO-NORTH",
  "item_name": "Rice",
  "quantity": 125,
  "unit": "kg"
}
```

**Final Gemini response:**

> There are 125 kg of rice currently available at your campus.

### Result

**Passed.** The real Gemini API successfully selected the Python function, received its result, and generated a natural-language response.

The experiment verified the following execution sequence:

1. User submits a question.
2. Gemini requests a registered function.
3. Backend validates the function and user permissions.
4. Python executes the function.
5. Backend returns the function result to Gemini.
6. Gemini generates the final answer.

### Security checks

- Unauthorized roles are rejected.
- Unregistered tools are rejected.
- Cross-campus results are rejected.
- Tool execution remains under Python backend control.

### Limitations

- Stock data is synthetic and not connected to the production inventory database.
- The experiment validates read-only tool execution only.
- It does not establish production AI-agent functionality.
- Human approval workflows for future write operations remain separate requirements.

## 2. PostgreSQL Vector Retrieval Spike

### Objective

Validate PostgreSQL pgvector storage and campus-scoped similarity retrieval for kitchen procedure documents.

### Implementation

- Created an isolated `ai_spike` schema.
- Stored synthetic procedure documents.
- Implemented a 64-dimensional deterministic hash-embedding provider.
- Implemented vector similarity search.
- Implemented campus-scoped retrieval.

### Retrieval benchmark

| Metric | Result |
|---|---:|
| Test questions | 10 |
| Expected documents retrieved in top 3 | 10 |
| Hit@3 | 100% |
| Week 1 target | At least 70% |
| Result | Passed |

All 10 synthetic benchmark questions retrieved their expected document within the top three results.

### Limitations

- The benchmark uses a small synthetic document collection.
- The hash-embedding provider is deterministic and is not a production semantic embedding model.
- The 100% result must not be interpreted as production retrieval accuracy.
- Real campus SOPs and a production embedding model require separate evaluation.

## 3. Streaming Spike

### Objective

Validate backend token streaming from FastAPI to a client using Server-Sent Events.

### Implementation

- Implemented a standalone FastAPI streaming endpoint.
- Used Server-Sent Events (SSE).
- Streamed FakeLLM output token by token.
- Emitted a simulated `get_stock_status` tool-step event.
- Verified the completion marker `[DONE]`.
- Integrated the stream into the Next.js `/streaming` page.
- Verified tool-event display, incremental tokens, and completion status in the browser.

### Result

**Passed.** FastAPI SSE delivery and Next.js browser integration were both verified using FakeLLM.

### Limitations

- The experiment uses FakeLLM.
- The tool-step event is simulated; it does not access production inventory.
- Real Gemini streaming has not been validated.

## 4. Automated Test Results

The AI spike test suite covers tool calling, authorization, campus isolation, embeddings, retrieval, and streaming.

Latest verified command:

    docker compose exec -T api pytest -q /app/spikes/ai/test_spikes.py

Latest verified result:

**11 passed in 1.50s**

The automated test suite uses FakeLLM and does not make live Gemini API requests.

Real Gemini function calling was separately verified using the configured API credentials and model.

## 5. Week 1 Technical Spike Summary

| Spike | Implementation | Evaluation |
|---|---|---|
| Tool calling | FakeLLM and Gemini function calling | Passed |
| Vector retrieval | pgvector and deterministic hash embeddings | Passed at prototype level |
| Streaming | FastAPI SSE, simulated tool event, and Next.js frontend | Passed at prototype level; browser integration verified |

### Overall conclusion

The three Week 1 AI technical spikes have been implemented and evaluated at prototype level.

The tool-calling experiment successfully demonstrated real Gemini function selection, Python-side execution, campus-scoped data access, and natural-language response generation.

The retrieval benchmark achieved **10/10 (100%) Hit@3**, exceeding the Week 1 target of 7/10.

The automated AI spike test suite currently reports **11 passed**.

These results demonstrate technical feasibility for the Week 1 prototypes only. They do not establish production readiness or completion of the full AI-agent functionality.

The production AI agent remains disabled (`AGENT_ENABLED=false`). Production semantic embeddings, real Gemini streaming, and production AI-agent integration remain separate work items. The verified frontend streaming page is a FakeLLM demonstration, not a production AI chat workflow.
