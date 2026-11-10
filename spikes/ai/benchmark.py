from sqlalchemy import text

from spikes.ai.retrieval import (
    get_engine,
    initialize_schema,
    add_document,
    search_procedures,
)

CAMPUS = "KC-WEEK1-BENCHMARK"

DOCUMENTS = [
    ("rice", "Rice grain storage", "Keep rice dry in ventilated storage and protect grain bags from moisture.", "SOP-001"),
    ("lentils", "Lentil pest protection", "Store lentils in airtight containers to prevent insects and pests.", "SOP-002"),
    ("vegetables", "Vegetable washing", "Wash vegetables using clean potable water before food preparation.", "SOP-003"),
    ("rotation", "Stock rotation", "Use first in first out FIFO and check expiry dates before issuing stock.", "SOP-004"),
    ("dairy", "Dairy refrigeration", "Keep milk and dairy products refrigerated at safe cold temperatures.", "SOP-005"),
    ("hands", "Hand washing", "Wash hands with soap and clean water before handling food.", "SOP-006"),
    ("knives", "Knife sanitation", "Clean and sanitize knives and cutting boards after food preparation.", "SOP-007"),
    ("oil", "Cooking oil storage", "Keep cooking oil sealed in a cool dark place away from sunlight.", "SOP-008"),
    ("waste", "Waste segregation", "Separate biodegradable kitchen waste from plastic and other dry waste.", "SOP-009"),
    ("meat", "Frozen meat storage", "Keep frozen meat in a freezer and maintain the required freezing temperature.", "SOP-010"),
]

QUESTIONS = [
    ("rice", "How can rice grain be protected from moisture during dry storage?"),
    ("lentils", "How should lentils be protected from insects and pests?"),
    ("vegetables", "What water should be used to wash vegetables before preparation?"),
    ("rotation", "Explain FIFO stock rotation and expiry date checking."),
    ("dairy", "How should milk and dairy products be kept cold?"),
    ("hands", "What should kitchen staff use to wash hands before food handling?"),
    ("knives", "How should knives and cutting boards be cleaned after preparation?"),
    ("oil", "Where should sealed cooking oil be stored away from sunlight?"),
    ("waste", "How should biodegradable and plastic kitchen waste be separated?"),
    ("meat", "Where should frozen meat be kept and at what condition?"),
]


def main():
    engine = get_engine()
    hits = 0

    try:
        initialize_schema(engine)

        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM ai_spike.procedure_documents WHERE campus_id = :campus"),
                {"campus": CAMPUS},
            )

        for document in DOCUMENTS:
            add_document(engine, CAMPUS, *document)

        print("Kitchen Copilot retrieval benchmark")
        print("Metric: Hit@3\n")

        for number, (expected, question) in enumerate(QUESTIONS, 1):
            results = search_procedures(engine, CAMPUS, question, limit=3)
            found = any(item["document_id"] == expected for item in results)
            hits += int(found)
            status = "HIT" if found else "MISS"
            print(f"{number:02}. {status} | Expected: {expected}")

        score = hits / len(QUESTIONS) * 100
        print(f"\nHit@3: {hits}/10 ({score:.0f}%)")

    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM ai_spike.procedure_documents WHERE campus_id = :campus"),
                {"campus": CAMPUS},
            )
        engine.dispose()


if __name__ == "__main__":
    main()
