import json
from collections.abc import Iterator

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse


class FakeLLM:
    """Offline stand-in for a streaming LLM."""

    def stream(self, prompt: str) -> Iterator[str]:
        answer = (
            f"Simulated Kitchen Copilot response to: {prompt}. "
            "This response is delivered incrementally using SSE."
        )

        for word in answer.split():
            yield word + " "


def event_stream(prompt: str) -> Iterator[str]:
    llm = FakeLLM()

    # Simulate one tool execution before the answer.
    tool_step = {
        "tool": "get_stock_status",
        "status": "completed",
        "message": "Fake stock status retrieved successfully.",
    }

    yield (
        "event: tool_step\n"
        f"data: {json.dumps(tool_step)}\n\n"
    )

    # Stream the response token by token.
    for token in llm.stream(prompt):
        yield f"data: {json.dumps({'token': token})}\n\n"

    yield "data: [DONE]\n\n"


app = FastAPI(
    title="Kitchen Copilot Streaming Spike",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "healthy", "spike": "streaming"}


@app.get("/stream")
def stream_response(
    prompt: str = Query(min_length=1, max_length=1000),
):
    return StreamingResponse(
        event_stream(prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
