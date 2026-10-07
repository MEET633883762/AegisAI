"""Hosts, assets and credentials. Pure data models; no behavior that touches the outside world."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Privilege(str, Enum):
    USER = "user"
    ADMIN = "admin"


_RANK = {Privilege.USER: 1, Privilege.ADMIN: 2}


def privilege_at_least(have: Privilege | None, need: Privilege) -> bool:
    return have is not None and _RANK[have] >= _RANK[need]


def max_privilege(a: Privilege | None, b: Privilege) -> Privilege:
    return b if a is None or _RANK[b] > _RANK[a] else a


class Host(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    role: str
    segment: str
    isolated: bool = False
    logging_level: int = Field(default=1, ge=1, le=2)  # 1 = basic, 2 = verbose
    login_service: str | None = None  # name of the service used for authentication


class Asset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    host_id: str
    name: str
    critical: bool = False
    required_privilege: Privilege = Privilege.ADMIN
    synthetic: Literal[True] = True  # safety invariant: simulated data only


class Credential(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    principal: str
    privilege: Privilege
    valid_hosts: list[str]
    stored_on: str  # host whose compromise exposes this credential
    requires_privilege: Privilege = Privilege.USER  # privilege needed on stored_on to read it
    active: bool = True
