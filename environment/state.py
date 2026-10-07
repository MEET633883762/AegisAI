"""EnterpriseState: the single ground-truth world model. Agents never receive this object."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from environment.hosts import Asset, Credential, Host, Privilege
from environment.network import EXTERNAL, Network, rules_allow
from environment.services import Service, Vulnerability
from telemetry.events import Alert, TelemetryEvent

EGRESS_PORT = 443


class RedProgress(BaseModel):
    """What Red has learned/achieved. Lists (not sets) keep serialization deterministic."""

    model_config = ConfigDict(extra="forbid")

    known_hosts: list[str] = Field(default_factory=list)
    enumerated_ports: dict[str, list[int]] = Field(default_factory=dict)
    discovered_services: dict[str, list[str]] = Field(default_factory=dict)
    known_credentials: list[str] = Field(default_factory=list)
    compromised: dict[str, Privilege] = Field(default_factory=dict)
    accessed_assets: list[str] = Field(default_factory=list)
    collected_assets: list[str] = Field(default_factory=list)
    exfiltrated_assets: list[str] = Field(default_factory=list)


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    host: str
    alert_id: int | None = None


class EnterpriseState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    step: int = 0
    hosts: dict[str, Host]
    services: list[Service]
    vulnerabilities: dict[str, Vulnerability]
    assets: dict[str, Asset]
    credentials: dict[str, Credential]
    network: Network
    blue_known_vulns: list[str] = Field(default_factory=list)  # vulns Blue's scanner knows about
    red: RedProgress = Field(default_factory=RedProgress)
    events: list[TelemetryEvent] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    next_event_id: int = 1
    next_alert_id: int = 1

    # ---- lookups -------------------------------------------------------------------------
    def find_service(self, host_id: str, name: str) -> Service | None:
        for s in self.services:
            if s.host_id == host_id and s.name == name:
                return s
        return None

    def services_of(self, host_id: str) -> list[Service]:
        return [s for s in self.services if s.host_id == host_id]

    # ---- reachability --------------------------------------------------------------------
    def _src_segment(self, src: str) -> str | None:
        if src == EXTERNAL:
            return "external"
        h = self.hosts.get(src)
        return None if h is None or h.isolated else h.segment

    def can_reach(self, src: str, dst: str, port: int) -> bool:
        d = self.hosts.get(dst)
        if d is None or d.isolated or src in self.network.blocked_sources:
            return False
        seg = self._src_segment(src)
        if seg is None:
            return False
        if src == dst:
            return True
        return rules_allow(self.network.rules, seg, d.segment, port)

    def can_egress(self, src: str, port: int = EGRESS_PORT) -> bool:
        if src in self.network.blocked_sources:
            return False
        seg = self._src_segment(src)
        return seg is not None and rules_allow(self.network.rules, seg, "external", port)

    def foothold_sources(self) -> list[str]:
        """Origins Red can act from: the outside plus every compromised host (deterministic order)."""
        return [EXTERNAL, *sorted(self.red.compromised)]
