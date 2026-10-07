"""In-memory knowledge store for the Phase 11 prototype."""
from __future__ import annotations

from .models import ThreatDocument


class KnowledgeStore:
    def __init__(self) -> None:
        self._docs: dict[str, ThreatDocument] = {}

    def add(self, document: ThreatDocument) -> ThreatDocument:
        if document.document_id in self._docs:
            raise ValueError(f"duplicate document_id: {document.document_id}")
        self._docs[document.document_id] = document
        return document

    def upsert(self, document: ThreatDocument) -> ThreatDocument:
        self._docs[document.document_id] = document
        return document

    def get(self, document_id: str) -> ThreatDocument | None:
        return self._docs.get(document_id)

    def all(self) -> tuple[ThreatDocument, ...]:
        return tuple(self._docs.values())

    def __len__(self) -> int:
        return len(self._docs)
