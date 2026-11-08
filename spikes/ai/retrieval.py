import argparse
import hashlib
import math
import re

from sqlalchemy import create_engine, text

DIMENSIONS = 64


class HashEmbeddingProvider:
    """Offline baseline embedding provider."""

    def embed(self, content: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", content.lower())
        vector = [0.0] * DIMENSIONS

        for token in tokens:
            digest = hashlib.blake2b(
                token.encode(),
                digest_size=8,
            ).digest()

            number = int.from_bytes(digest, "big")
            index = number % DIMENSIONS
            sign = 1.0 if (number >> 8) % 2 == 0 else -1.0
            vector[index] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))

        if magnitude:
            vector = [value / magnitude for value in vector]

        return vector


def vector_literal(vector):
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def get_engine():
    from app.core.config import settings
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def initialize_schema(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ai_spike"))

        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS ai_spike.procedure_documents (
                    campus_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    embedding vector({DIMENSIONS}) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (campus_id, document_id)
                )
                """
            )
        )


def add_document(engine, campus_id, document_id, title, content, source_ref):
    embedding = HashEmbeddingProvider().embed(title + " " + content)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO ai_spike.procedure_documents
                    (campus_id, document_id, title, content,
                     source_ref, embedding)
                VALUES
                    (:campus_id, :document_id, :title, :content,
                     :source_ref, CAST(:embedding AS vector))
                ON CONFLICT (campus_id, document_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    source_ref = EXCLUDED.source_ref,
                    embedding = EXCLUDED.embedding
                """
            ),
            {
                "campus_id": campus_id,
                "document_id": document_id,
                "title": title,
                "content": content,
                "source_ref": source_ref,
                "embedding": vector_literal(embedding),
            },
        )


def search_procedures(engine, campus_id, question, limit=3):
    if not campus_id.strip():
        raise ValueError("Campus ID is required.")

    embedding = HashEmbeddingProvider().embed(question)

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT document_id, title, content, source_ref,
                       embedding <=> CAST(:embedding AS vector) AS distance
                FROM ai_spike.procedure_documents
                WHERE campus_id = :campus_id
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                """
            ),
            {
                "embedding": vector_literal(embedding),
                "campus_id": campus_id,
                "limit": limit,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def run_demo(campus_id):
    engine = get_engine()

    try:
        initialize_schema(engine)

        documents = [
            (
                "rice-storage",
                "Rice storage procedure",
                "Store rice in a clean, dry and ventilated area. "
                "Keep bags away from moisture and inspect regularly.",
                "DEMO-SOP-001",
            ),
            (
                "vegetable-cleaning",
                "Vegetable cleaning procedure",
                "Wash vegetables with clean potable water before "
                "preparation. Use clean equipment.",
                "DEMO-SOP-002",
            ),
            (
                "stock-rotation",
                "Stock rotation procedure",
                "Use first-in first-out. Check expiry dates and "
                "use older stock first.",
                "DEMO-SOP-003",
            ),
        ]

        for document in documents:
            add_document(engine, campus_id, *document)

        results = search_procedures(
            engine,
            campus_id,
            "How should rice be stored safely?",
        )

        print(f"\nResults for campus: {campus_id}")

        for result in results:
            print(f"\nTitle: {result['title']}")
            print(f"Source: {result['source_ref']}")
            print(f"Content: {result['content']}")
            print(f"Distance: {result['distance']:.4f}")

    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campus", default="KC-DEMO-NORTH")
    args = parser.parse_args()

    run_demo(args.campus)
