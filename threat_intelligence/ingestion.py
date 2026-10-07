"""Explicit ingestion boundary: no network access is performed by Phase 11."""
from __future__ import annotations

from typing import Iterable
from .models import ThreatDocument
from .normalizer import normalize_document
from .store import KnowledgeStore


class IngestionPipeline:
    """Normalize and validate supplied records before storage."""
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def ingest(self, records: Iterable[dict]) -> tuple[ThreatDocument, ...]:
        added: list[ThreatDocument] = []
        for record in records:
            document = normalize_document(record)
            self.store.add(document)
            added.append(document)
        return tuple(added)
