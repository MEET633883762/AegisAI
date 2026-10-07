"""Typed, untrusted threat-knowledge records used by AegisAI RAG."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    CURATED = "curated"
    THREAT_INTEL = "threat_intel"
    VULNERABILITY = "vulnerability"
    MITRE = "mitre"
    EPISODE = "episode"


class ThreatDocument(BaseModel):
    """Normalized document. Content is DATA only; it is never executable."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=300)
    source_type: SourceType
    external_id: str | None = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=20_000)
    tags: tuple[str, ...] = ()
    mitre_techniques: tuple[str, ...] = ()
    cve_ids: tuple[str, ...] = ()
    trust_level: str = Field(default="untrusted", max_length=50)
    ingested_at: str

    @classmethod
    def create(
        cls, *, document_id: str, source: str, source_type: SourceType,
        title: str, content: str, external_id: str | None = None,
        tags: tuple[str, ...] = (), mitre_techniques: tuple[str, ...] = (),
        cve_ids: tuple[str, ...] = (),
    ) -> "ThreatDocument":
        return cls(
            document_id=document_id, source=source, source_type=source_type,
            external_id=external_id, title=title, content=content,
            tags=tags, mitre_techniques=mitre_techniques, cve_ids=cve_ids,
            ingested_at=datetime.now(timezone.utc).isoformat(),
        )


class RetrievedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document: ThreatDocument
    score: float = Field(ge=0.0)
    matched_terms: tuple[str, ...] = ()
