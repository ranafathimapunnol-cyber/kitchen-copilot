
# Kitchen Copilot — AI Spikes

Week 1 isolated AI experiments for validating the technical feasibility of AI integration.

These experiments are separate from production application workflows. They use synthetic demonstration data and do not modify actual kitchen inventory.

## 1. AI Tool Calling

File: `tool_calling.py`

Demonstrates how an LLM can select a registered Python function, how the backend validates the request, executes the function, and returns the result to the LLM.

### Implementation

- Implemented a tool registry for registering and executing Python tools.
- Implemented `FakeLLM` for deterministic testing without network access.
- Integrated the Google Gemini API using the `google-genai` Python SDK.
- Configured Gemini function declarations for `get_stock_status`.
- Implemented the function-calling conversation flow:
  1. User sends a question.
  2. Gemini selects a function and provides its arguments.
  3. Python validates the requested tool and user permissions.
  4. Python executes the registered function.
  5. The result is returned to Gemini.
  6. Gemini generates a natural-language response.
- Added role-based authorization.
- Added campus-scoped user context and cross-campus result protection.
- Used synthetic stock records for demonstration.

### Gemini configuration

- SDK: `google-genai`
- Model: `gemini-3.1-flash-lite`
- API key: Loaded from `GEMINI_API_KEY` environment variable.
- Model configuration: `GEMINI_MODEL`

The API key must remain in the environment configuration and must never be committed to Git.

### Verified Gemini experiment

Prompt:

> How much rice stock is available in my campus?

Gemini selected:

`get_stock_status`

Arguments:

```json
{
  "item_name": "rice"
}
```

Python returned:

```json
{
  "campus_id": "KC-DEMO-NORTH",
  "item_name": "Rice",
  "quantity": 125,
  "unit": "kg"
}
```

Gemini generated:

> There are 125 kg of rice currently available at your campus.

**Result: Successful.** Real Gemini function calling, Python tool execution, and final response generation were verified.

### Run FakeLLM (offline)

From the project root:

    docker compose exec -T api python -m spikes.ai.tool_calling

### Run real Gemini function calling

From the project root:

    docker compose exec -T api python - <<'PY'
    from spikes.ai.tool_calling import UserContext, run_gemini_tool_call

    user = UserContext(
        user_id="demo-user-1",
        campus_id="KC-DEMO-NORTH",
        role="STORE_KEEPER",
    )

    result = run_gemini_tool_call(
        "How much rice stock is available in my campus?",
        user,
    )

    print(result)
    PY

Requires `GEMINI_API_KEY` and `GEMINI_MODEL` in the API container environment.

## 2. PostgreSQL Vector Retrieval

File: `retrieval.py`

Demonstrates PostgreSQL pgvector storage, vector similarity search, and campus-scoped procedure retrieval using synthetic documents.

### Implementation

- Created an isolated `ai_spike` PostgreSQL schema.
- Implemented procedure document storage.
- Implemented a deterministic 64-dimensional hash-embedding provider.
- Implemented vector similarity search.
- Added campus-scoped retrieval.

### Limitation

Uses deterministic feature-hashing embeddings. Production semantic retrieval using a real embedding model has not been validated.

## 3. Streaming Responses

File: `streaming.py`

Demonstrates FastAPI Server-Sent Events (SSE) and token-by-token streaming using FakeLLM.

### Run

From the project root:

    docker compose --profile ai up -d

The streaming service is available on port 8010 when the AI profile is configured and running.

Example request:

    curl -N "http://127.0.0.1:8010/stream?prompt=How%20should%20rice%20be%20stored"

Stop the service using the corresponding Docker Compose command.

### Limitation

The backend streaming prototype uses FakeLLM. Real Gemini streaming and complete frontend integration have not yet been validated.

## 4. Automated Tests

File: `test_spikes.py`

The test suite verifies:

- FakeLLM tool calling.
- Campus-scoped stock access.
- Unauthorized role rejection.
- Unregistered tool rejection.
- Cross-campus result rejection.
- Missing stock item handling.
- Deterministic embeddings.
- Embedding normalization.
- Campus-scoped pgvector retrieval.
- SSE event generation.
- Streaming prompt inclusion.

Run from the project root:

    docker compose exec -T api pytest -q /app/spikes/ai/test_spikes.py

Latest verified result:

**11 passed**

The automated tests use FakeLLM and do not require a live Gemini API request.

The real Gemini function-calling experiment was separately executed successfully.

## 5. Safety and Limitations

- Tool execution is controlled by the Python backend, not directly by the LLM.
- Role authorization is checked before executing a registered tool.
- Campus isolation is checked against the authenticated user context.
- Stock data in this experiment is synthetic.
- The tool is read-only and does not modify inventory.
- Retrieval uses prototype hash embeddings, not a production semantic embedding model.
- Streaming uses FakeLLM, not a live model.
- These experiments are isolated from production application workflows.
- The production AI agent remains disabled by default (`AGENT_ENABLED=false`).

## 6. Week 1 Status

| Experiment | Status |
|---|---|
| FakeLLM tool calling | Implemented and tested |
| Gemini function calling | Implemented and successfully verified |
| Tool authorization | Tested |
| Campus isolation | Tested |
| pgvector retrieval | Implemented and tested |
| Retrieval benchmark | 10/10 Hit@3 |
| SSE streaming prototype | Implemented and tested |
| Automated spike tests | 11 passed |
| Production semantic embeddings | Pending |
| Real Gemini streaming | Pending |
| Production AI agent integration | Pending |

These results establish technical feasibility for the Week 1 prototypes. They do not establish production readiness or completion of the full AI-agent functionality.
