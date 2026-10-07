"""Deterministic lexical retriever; embeddings/vector DB are deliberately deferred."""
from __future__ import annotations

import re
from .models import RetrievedDocument, ThreatDocument
from .store import KnowledgeStore

_TOKEN = re.compile(r"[a-z0-9_.:-]+", re.I)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if len(t) > 1}


class Retriever:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def search(self, query: str, *, top_k: int = 3) -> tuple[RetrievedDocument, ...]:
        if not isinstance(query, str) or not query.strip():
            return ()
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        q = _tokens(query)
        if not q:
            return ()
        scored: list[RetrievedDocument] = []
        for doc in self.store.all():
            fields = {
                "title": _tokens(doc.title),
                "content": _tokens(doc.content),
                "tags": set(doc.tags),
                "mitre": set(doc.mitre_techniques),
                "cve": set(doc.cve_ids),
            }
            matched = q & set().union(*fields.values())
            if not matched:
                continue
            # Title/tags/verified identifiers carry more weight than body text.
            score = (
                3.0 * len(q & fields["title"])
                + 2.0 * len(q & fields["tags"])
                + 2.0 * len(q & fields["mitre"])
                + 2.0 * len(q & fields["cve"])
                + 1.0 * len(q & fields["content"])
            ) / max(1, len(q))
            scored.append(RetrievedDocument(document=doc, score=score, matched_terms=tuple(sorted(matched))))
        scored.sort(key=lambda x: (-x.score, x.document.document_id))
        return tuple(scored[:top_k])
