import json
from collections.abc import Iterator

from fastapi import FastAPI, Query  # type: ignore
from fastapi.responses import StreamingResponse  # pyright: ignore[reportMissingImports]


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

    for token in llm.stream(prompt):
        yield f"data: {json.dumps({'token': token})}\n\n"

    yield "data: [DONE]\n\n"


app = FastAPI(
    title="Kitchen Copilot Streaming Spike",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "healthy", "spike": "streaming"}


@app.get("/stream")
def stream_response(prompt: str = Query(min_length=1, max_length=1000)):
    return StreamingResponse(
        event_stream(prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
