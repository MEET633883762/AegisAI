"""Services and simulated vulnerabilities. A vulnerability is a flag, never real exploit logic."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from environment.hosts import Privilege


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_id: str
    name: str
    port: int = Field(ge=1, le=65535)
    running: bool = True
    vulnerability_id: str | None = None


class Vulnerability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    host_id: str
    service_name: str
    label: str  # synthetic label, not a real CVE
    grants: Privilege
    patched: bool = False
