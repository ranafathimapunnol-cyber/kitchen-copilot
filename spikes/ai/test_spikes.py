import json

import pytest  # type: ignore

from spikes.ai.retrieval import (
    DIMENSIONS,
    HashEmbeddingProvider,
    add_document,
    get_engine,
    initialize_schema,
    search_procedures,
)
from spikes.ai.streaming import event_stream
from spikes.ai.tool_calling import (
    ToolCall,
    UserContext,
    build_registry,
    run_tool_call,
)


# --------------------------------------------------
# Tool calling tests
# --------------------------------------------------

def test_tool_call_returns_campus_scoped_stock():
    user = UserContext(
        user_id="test-user",
        campus_id="KC-DEMO-NORTH",
        role="STORE_KEEPER",
    )

    result = run_tool_call("Show rice stock", user)

    assert result["tool"] == "get_stock_status"
    assert result["result"]["campus_id"] == "KC-DEMO-NORTH"
    assert result["result"]["quantity"] == 125


def test_tool_call_rejects_unauthorized_role():
    registry = build_registry()

    user = UserContext(
        user_id="test-user",
        campus_id="KC-DEMO-NORTH",
        role="ACCOUNTS",
    )

    with pytest.raises(PermissionError):
        registry.execute(
            ToolCall("get_stock_status", {"item_name": "Rice"}),
            user,
        )


def test_tool_call_rejects_unregistered_tool():
    registry = build_registry()

    user = UserContext(
        user_id="test-user",
        campus_id="KC-DEMO-NORTH",
        role="ADMIN",
    )

    with pytest.raises(PermissionError):
        registry.execute(
            ToolCall("delete_all_stock", {}),
            user,
        )


def test_tool_call_rejects_cross_campus_result():
    registry = build_registry()

    def wrong_campus_handler(context, arguments):
        return {
            "campus_id": "KC-DEMO-SOUTH",
            "quantity": 80,
        }

    registry.register(
        "wrong_campus_test",
        ("STORE_KEEPER",),
        wrong_campus_handler,
    )

    user = UserContext(
        user_id="test-user",
        campus_id="KC-DEMO-NORTH",
        role="STORE_KEEPER",
    )

    with pytest.raises(PermissionError):
        registry.execute(
            ToolCall("wrong_campus_test", {}),
            user,
        )


def test_tool_call_returns_south_campus_stock():
    user = UserContext(
        user_id="test-user",
        campus_id="KC-DEMO-SOUTH",
        role="STORE_KEEPER",
    )

    result = run_tool_call("Show rice stock", user)

    assert result["result"]["campus_id"] == "KC-DEMO-SOUTH"
    assert result["result"]["quantity"] == 80


def test_tool_call_handles_missing_item():
    registry = build_registry()

    user = UserContext(
        user_id="test-user",
        campus_id="KC-DEMO-NORTH",
        role="STORE_KEEPER",
    )

    result = registry.execute(
        ToolCall("get_stock_status", {"item_name": "Sugar"}),
        user,
    )

    assert result["campus_id"] == "KC-DEMO-NORTH"
    assert result["message"] == "No matching stock record found."


# --------------------------------------------------
# Retrieval tests
# --------------------------------------------------

def test_embedding_is_deterministic():
    provider = HashEmbeddingProvider()

    first = provider.embed("Rice storage procedure")
    second = provider.embed("Rice storage procedure")

    assert first == second
    assert len(first) == DIMENSIONS


def test_embedding_is_normalized():
    vector = HashEmbeddingProvider().embed("Rice storage procedure")

    magnitude = sum(value * value for value in vector) ** 0.5

    assert magnitude == pytest.approx(1.0)


def test_pgvector_retrieval_respects_campus():
    engine = get_engine()
    test_campus = "KC-TEST-RETRIEVAL"

    documents = [
        (
            "rice-storage",
            "Rice storage procedure",
            "Store rice in a clean, dry and ventilated area.",
            "DEMO-SOP-001",
        ),
        (
            "vegetable-cleaning",
            "Vegetable cleaning procedure",
            "Wash vegetables with clean potable water.",
            "DEMO-SOP-002",
        ),
    ]

    try:
        initialize_schema(engine)

        from sqlalchemy import text  # type: ignore

        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM ai_spike.procedure_documents "
                    "WHERE campus_id = :campus_id"
                ),
                {"campus_id": test_campus},
            )

        for document in documents:
            add_document(engine, test_campus, *document)

        north_results = search_procedures(
            engine,
            test_campus,
            "How should rice be stored?",
        )

        south_results = search_procedures(
            engine,
            "KC-TEST-OTHER-CAMPUS",
            "How should rice be stored?",
        )

        assert len(north_results) > 0
        assert all(
            result["source_ref"].startswith("DEMO-SOP-")
            for result in north_results
        )
        assert south_results == []

    finally:
        from sqlalchemy import text  # type: ignore

        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM ai_spike.procedure_documents "
                    "WHERE campus_id = :campus_id"
                ),
                {"campus_id": test_campus},
            )
        engine.dispose()


# --------------------------------------------------
# Streaming tests
# --------------------------------------------------

def test_streaming_produces_sse_events():
    events = list(event_stream("How should rice be stored?"))

    assert len(events) > 1

    # The first event reports the fake tool execution.
    assert events[0].startswith("event: tool_step\n")
    assert '"tool": "get_stock_status"' in events[0]
    assert '"status": "completed"' in events[0]

    # The remaining events stream response tokens.
    token_events = [
        event for event in events
        if event.startswith("data: {")
    ]

    assert token_events
    assert all(
        json.loads(event[6:]).get("token")
        for event in token_events
    )
    assert events[-1] == "data: [DONE]\n\n"


def test_streaming_includes_prompt():
    events = list(event_stream("Check rice storage"))

    combined = "".join(
        json.loads(event[6:])["token"]
        for event in events
        if event.startswith("data: {")
    )

    assert "Check rice storage" in combined