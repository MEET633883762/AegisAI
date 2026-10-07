"""Network segments and firewall rules. Evaluation is ordered first-match with default deny."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

EXTERNAL = "external"


class NetworkSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class FirewallRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src_segment: str
    dst_segment: str
    port: int | None = None  # None = any port
    allow: bool = True


class Network(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[NetworkSegment]
    rules: list[FirewallRule]
    blocked_sources: list[str] = []  # set by Blue via BLOCK_SOURCE


def rules_allow(rules: list[FirewallRule], src_segment: str, dst_segment: str, port: int) -> bool:
    for r in rules:
        if r.src_segment == src_segment and r.dst_segment == dst_segment and r.port in (None, port):
            return r.allow
    return False
