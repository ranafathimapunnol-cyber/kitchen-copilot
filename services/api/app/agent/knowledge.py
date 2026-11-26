"""Approved kitchen procedures for the agent (source-grounded retrieval).

Only Markdown files in settings.AGENT_PROCEDURES_DIR are used; each file is
one approved procedure, its first heading the title. Nothing is invented:
with no folder or no match the agent says the procedure is unavailable from
the approved sources. No procedure documents have been approved yet, so
the folder is empty by default.
"""

import re
from pathlib import Path

from app.core.config import settings

WORD = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "is", "what", "how", "do", "we", "i", "my"}


def documents() -> list[dict]:
    folder = Path(settings.AGENT_PROCEDURES_DIR) if settings.AGENT_PROCEDURES_DIR else None
    if not folder or not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), path.stem)
        out.append({"source": path.name, "title": title, "text": text})
    return out


def search(topic: str, limit: int = 3) -> dict:
    docs = documents()
    terms = {w for w in WORD.findall(topic.lower()) if w not in STOP and len(w) > 2}
    hits = []
    for d in docs:
        paragraphs = [p.strip() for p in d["text"].split("\n\n") if p.strip()]
        best = max(((sum(p.lower().count(t) for t in terms), p) for p in paragraphs), default=(0, ""))
        if best[0]:
            hits.append({"source": d["source"], "title": d["title"], "excerpt": best[1][:600], "score": best[0]})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return {"documents_loaded": len(docs), "matches": hits[:limit]}
