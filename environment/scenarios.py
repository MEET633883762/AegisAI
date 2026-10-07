"""Deterministic scenario templates and experiment metadata.

A (template_id, seed) pair fully determines the initial world. Scenario metadata is
experiment-side descriptive information; it is deliberately not copied into Red/Blue
observations so it cannot become a hidden label or a source of leakage.
"""
from __future__ import annotations

import random
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from environment.hosts import Asset, Credential, Host, Privilege
from environment.network import FirewallRule, Network, NetworkSegment
from environment.services import Service, Vulnerability
from environment.state import EnterpriseState


class ScenarioMetadata(BaseModel):
    """Controlled metadata used for analysis, split design, and reporting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    family: str
    attack_pattern: str
    difficulty: str
    defender_knowledge: str
    telemetry_profile: str


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    template_id: str
    seed: int
    objective: str
    target_asset_id: str
    max_steps: int
    noise_probability: float
    red_initial_known_hosts: list[str]
    initial_state: EnterpriseState
    metadata: ScenarioMetadata


def _build(
    template_id: str,
    seed: int,
    *,
    pivot: str,
    blue_known_vulns: list[str],
    web_logging: int,
    noise_choices: tuple[float, ...],
    metadata: ScenarioMetadata,
    dmz_to_internal_ports: tuple[int, ...] = (22,),
    initial_known_hosts: tuple[str, ...] = ("host_a",),
) -> Scenario:
    rng = random.Random(f"scenario:{template_id}:{seed}")
    web_port = rng.choice((80, 8080))
    noise = rng.choice(noise_choices)

    hosts = {
        "host_a": Host(id="host_a", name="web-server", role="web server", segment="dmz",
                       logging_level=web_logging),
        "host_b": Host(id="host_b", name="database", role="database", segment="internal",
                       login_service="db"),
        "host_c": Host(id="host_c", name="workstation", role="employee workstation",
                       segment="internal", login_service="ssh"),
        "host_d": Host(id="host_d", name="internal-service", role="internal service",
                       segment="internal", login_service="ssh"),
    }
    services = [
        Service(host_id="host_a", name="web", port=web_port, vulnerability_id="vuln_web_001"),
        Service(host_id="host_b", name="db", port=5432),
        Service(host_id="host_c", name="ssh", port=22),
        Service(host_id="host_d", name="ssh", port=22),
        Service(host_id="host_d", name="app", port=8443),
    ]
    vulns = {
        "vuln_web_001": Vulnerability(
            id="vuln_web_001", host_id="host_a", service_name="web",
            label="SIM-WEB-INJECTION-001", grants=Privilege.USER,
        )
    }
    assets = {
        "asset_customer_db": Asset(
            id="asset_customer_db", host_id="host_b",
            name="synthetic customer records", critical=True,
        )
    }
    creds = {
        "cred_svc_backup": Credential(
            id="cred_svc_backup", principal="svc_backup", privilege=Privilege.ADMIN,
            valid_hosts=[pivot], stored_on="host_a", requires_privilege=Privilege.USER,
        ),
        "cred_db_admin": Credential(
            id="cred_db_admin", principal="db_admin", privilege=Privilege.ADMIN,
            valid_hosts=["host_b"], stored_on=pivot, requires_privilege=Privilege.ADMIN,
        ),
    }
    rules = [FirewallRule(src_segment="external", dst_segment="dmz", port=web_port)]
    rules.extend(
        FirewallRule(src_segment="dmz", dst_segment="internal", port=port)
        for port in dmz_to_internal_ports
    )
    rules.extend([
        FirewallRule(src_segment="internal", dst_segment="internal"),
        FirewallRule(src_segment="internal", dst_segment="dmz"),
        FirewallRule(src_segment="internal", dst_segment="external", port=443),
        FirewallRule(src_segment="dmz", dst_segment="external", port=443),
    ])
    network = Network(
        segments=[NetworkSegment(id=s, name=s) for s in ("external", "dmz", "internal")],
        rules=rules,
    )
    state = EnterpriseState(
        seed=seed, hosts=hosts, services=services, vulnerabilities=vulns,
        assets=assets, credentials=creds, network=network,
        blue_known_vulns=list(blue_known_vulns),
    )
    return Scenario(
        scenario_id=f"{template_id}:{seed}", template_id=template_id, seed=seed,
        objective="Exfiltrate the synthetic dataset asset_customer_db from the internal network.",
        target_asset_id="asset_customer_db", max_steps=30, noise_probability=noise,
        red_initial_known_hosts=list(initial_known_hosts), initial_state=state,
        metadata=metadata,
    )


_WEB_UNKNOWN = ScenarioMetadata(
    family="web_exploit",
    attack_pattern="web_vulnerability_to_credential_pivot",
    difficulty="medium",
    defender_knowledge="unknown_web_vulnerability",
    telemetry_profile="basic_logging_low_noise",
)
_WEB_UNKNOWN_NOISY = ScenarioMetadata(
    family="web_exploit",
    attack_pattern="web_vulnerability_to_credential_pivot",
    difficulty="hard",
    defender_knowledge="unknown_web_vulnerability",
    telemetry_profile="verbose_logging_high_noise",
)
_WEB_RESTRICTED = ScenarioMetadata(
    family="web_exploit",
    attack_pattern="web_vulnerability_to_credential_pivot",
    difficulty="hard",
    defender_knowledge="unknown_web_vulnerability",
    telemetry_profile="basic_logging_restricted_lateral_path",
)
_CRED_KNOWN = ScenarioMetadata(
    family="credential_reuse",
    attack_pattern="known_vulnerability_plus_credential_pivot",
    difficulty="medium",
    defender_knowledge="known_web_vulnerability",
    telemetry_profile="verbose_logging_moderate_noise",
)
_CRED_WORKSTATION = ScenarioMetadata(
    family="credential_reuse",
    attack_pattern="known_vulnerability_to_workstation_pivot",
    difficulty="hard",
    defender_knowledge="known_web_vulnerability",
    telemetry_profile="verbose_logging_moderate_noise",
)
_CRED_SERVICE = ScenarioMetadata(
    family="credential_reuse",
    attack_pattern="known_vulnerability_to_service_pivot",
    difficulty="hard",
    defender_knowledge="known_web_vulnerability",
    telemetry_profile="basic_logging_high_noise",
)


def _web_exploit_lateral_exfil(seed: int) -> Scenario:
    return _build(
        "web_exploit_lateral_exfil", seed, pivot="host_c", blue_known_vulns=[],
        web_logging=1, noise_choices=(0.1, 0.2), metadata=_WEB_UNKNOWN,
    )


def _credential_reuse_known_vuln(seed: int) -> Scenario:
    return _build(
        "credential_reuse_known_vuln", seed, pivot="host_d",
        blue_known_vulns=["vuln_web_001"], web_logging=2, noise_choices=(0.2, 0.3),
        metadata=_CRED_KNOWN,
    )


def _web_exploit_high_noise(seed: int) -> Scenario:
    return _build(
        "web_exploit_high_noise", seed, pivot="host_c", blue_known_vulns=[],
        web_logging=2, noise_choices=(0.35, 0.45), metadata=_WEB_UNKNOWN_NOISY,
    )


def _web_exploit_restricted_lateral(seed: int) -> Scenario:
    return _build(
        "web_exploit_restricted_lateral", seed, pivot="host_d", blue_known_vulns=[],
        web_logging=1, noise_choices=(0.1, 0.2), metadata=_WEB_RESTRICTED,
        dmz_to_internal_ports=(8443,),
    )


def _credential_reuse_workstation(seed: int) -> Scenario:
    return _build(
        "credential_reuse_workstation", seed, pivot="host_c",
        blue_known_vulns=["vuln_web_001"], web_logging=2, noise_choices=(0.2, 0.3),
        metadata=_CRED_WORKSTATION,
    )


def _credential_reuse_service(seed: int) -> Scenario:
    return _build(
        "credential_reuse_service", seed, pivot="host_d",
        blue_known_vulns=["vuln_web_001"], web_logging=1, noise_choices=(0.3, 0.4),
        metadata=_CRED_SERVICE,
    )


TEMPLATES: dict[str, Callable[[int], Scenario]] = {
    "web_exploit_lateral_exfil": _web_exploit_lateral_exfil,
    "credential_reuse_known_vuln": _credential_reuse_known_vuln,
    "web_exploit_high_noise": _web_exploit_high_noise,
    "web_exploit_restricted_lateral": _web_exploit_restricted_lateral,
    "credential_reuse_workstation": _credential_reuse_workstation,
    "credential_reuse_service": _credential_reuse_service,
}


def build_scenario(template_id: str, seed: int) -> Scenario:
    if template_id not in TEMPLATES:
        raise KeyError(f"unknown scenario template: {template_id}")
    return TEMPLATES[template_id](seed)
