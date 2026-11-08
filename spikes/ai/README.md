# Kitchen Copilot — AI Spikes

Week 1 isolated AI experiments.

## 1. Tool Calling

File: tool_calling.py

Demonstrates role authorization, registered tool execution, campus-scoped stock access, and cross-campus protection using FakeLLM.

Run from project root:

    cd services/api
    PYTHONPATH=../.. .venv/bin/python -m spikes.ai.tool_calling

## 2. pgvector Procedure Retrieval

File: retrieval.py

Demonstrates PostgreSQL pgvector storage, vector similarity search, and campus-scoped procedure retrieval using synthetic documents.

Run from project root:

    cd services/api
    PYTHONPATH=../.. .venv/bin/python -m spikes.ai.retrieval

Limitation: Uses deterministic feature-hashing embeddings. Production semantic retrieval has not been validated.

## 3. Streaming Responses

File: streaming.py

Demonstrates FastAPI Server-Sent Events (SSE) and token-by-token streaming using FakeLLM.

Run from project root:

    cd services/api
    PYTHONPATH=../.. .venv/bin/uvicorn spikes.ai.streaming:app --host 127.0.0.1 --port 8010

In another terminal:

    curl -N "http://127.0.0.1:8010/stream?prompt=How%20should%20rice%20be%20stored"

Stop the server with Ctrl+C.

## 4. Tests

Run from project root:

    cd services/api
    PYTHONPATH=../.. .venv/bin/python -m pytest ../../spikes/ai/test_spikes.py -q

Latest verified result: 9 passed.

## 5. Limitations

- Tool calling uses FakeLLM, not a live LLM provider.
- Retrieval uses feature hashing, not a production embedding model.
- Streaming uses FakeLLM, not a live model.
- Only synthetic demonstration data is used.
- These experiments are isolated from production application workflows.

## 6. Week 1 Status

- Tool calling prototype: implemented and tested.
- pgvector retrieval prototype: implemented and tested.
- SSE streaming prototype: implemented and tested.
- Automated tests: 9 passed.
- Production LLM integration: pending.
- Production semantic embeddings: pending.
