"""Normalization and prompt-injection-safe handling for threat documents."""
from __future__ import annotations

import re
from typing import Any

from .models import SourceType, ThreatDocument

_WS = re.compile(r"\s+")
_TAG = re.compile(r"[^a-z0-9_.:-]+", re.I)


def normalize_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("text fields must be strings")
    value = value.replace("\x00", " ")
    return _WS.sub(" ", value).strip()


def normalize_tags(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        raise TypeError("tags must be a sequence or string")
    out = []
    for value in values:
        tag = _TAG.sub("", str(value).strip().lower())
        if tag and tag not in out:
            out.append(tag)
    return tuple(out[:50])


def normalize_document(raw: dict[str, Any]) -> ThreatDocument:
    """Convert an external/curated record into a bounded, typed data record."""
    if not isinstance(raw, dict):
        raise TypeError("document must be a mapping")
    required = {"document_id", "source", "source_type", "title", "content"}
    missing = required - raw.keys()
    if missing:
        raise ValueError(f"missing document fields: {sorted(missing)}")
    source_type = raw["source_type"]
    if not isinstance(source_type, SourceType):
        source_type = SourceType(str(source_type))
    return ThreatDocument.create(
        document_id=normalize_text(str(raw["document_id"]))[:200],
        source=normalize_text(str(raw["source"]))[:300],
        source_type=source_type,
        external_id=(normalize_text(str(raw["external_id"]))[:200] if raw.get("external_id") else None),
        title=normalize_text(str(raw["title"]))[:500],
        content=normalize_text(str(raw["content"]))[:20_000],
        tags=normalize_tags(raw.get("tags")),
        # Mapping is metadata supplied by a trusted curation/verification process.
        mitre_techniques=normalize_tags(raw.get("mitre_techniques")),
        cve_ids=normalize_tags(raw.get("cve_ids")),
    )
