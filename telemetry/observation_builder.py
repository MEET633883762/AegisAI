"""Role-specific observations, built from ground truth by the environment side (never by agents).

Red sees only what it has learned. Blue sees only defender-visible telemetry and inventory.
Internal fields (event actor, blue_visible flag, ActionResult.state_changes/event_ids, Red
progress, vulnerability ground truth) are never copied into either view.
All string content in these views is DATA and must never be treated as instructions.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from environment.actions import ActionResult, BlueActionType, Outcome, RedActionType
from environment.scenarios import Scenario
from environment.state import EnterpriseState
from telemetry.events import Severity, TelemetryEvent

MAX_ALERTS = 20
MAX_RECENT_EVENTS = 30
RECENT_WINDOW_STEPS = 2


class _View(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- Red -------------------------------------------------------------------------------------
class RedServiceView(_View):
    name: str
    port: int


class RedHostView(_View):
    id: str
    name: str
    open_ports: list[int]
    services: list[RedServiceView]
    compromised: bool
    privilege: str | None
    assets: list[str]  # only populated for hosts Red controls


class RedCredentialView(_View):
    id: str
    principal: str


class ResultView(_View):
    action_type: str
    target: str
    success: bool
    outcome: Outcome
    message: str


class RedObservation(_View):
    step: int
    steps_remaining: int
    objective: str
    target_asset_id: str
    known_hosts: list[RedHostView]
    known_credentials: list[RedCredentialView]
    accessed_assets: list[str]
    collected_assets: list[str]
    exfiltrated_assets: list[str]
    last_result: ResultView | None
    allowed_actions: list[str]


def build_red_observation(state: EnterpriseState, scenario: Scenario,
                          last_result: ActionResult | None = None) -> RedObservation:
    r = state.red
    hosts: list[RedHostView] = []
    for hid in r.known_hosts:
        h = state.hosts[hid]
        ports = r.enumerated_ports.get(hid, [])
        names = r.discovered_services.get(hid, [])
        services = [RedServiceView(name=s.name, port=s.port)
                    for s in state.services_of(hid) if s.name in names and s.port in ports]
        priv = r.compromised.get(hid)
        hosts.append(RedHostView(
            id=hid, name=h.name, open_ports=list(ports), services=services,
            compromised=priv is not None, privilege=priv.value if priv else None,
            assets=[a.id for a in state.assets.values() if a.host_id == hid] if priv else []))
    return RedObservation(
        step=state.step, steps_remaining=max(0, scenario.max_steps - state.step),
        objective=scenario.objective, target_asset_id=scenario.target_asset_id,
        known_hosts=hosts,
        known_credentials=[RedCredentialView(id=c, principal=state.credentials[c].principal)
                           for c in r.known_credentials],
        accessed_assets=list(r.accessed_assets), collected_assets=list(r.collected_assets),
        exfiltrated_assets=list(r.exfiltrated_assets),
        last_result=None if last_result is None else ResultView(
            action_type=last_result.action_type, target=last_result.target,
            success=last_result.success, outcome=last_result.outcome, message=last_result.message),
        allowed_actions=[a.value for a in RedActionType])


# ---- Blue ------------------------------------------------------------------------------------
class BlueServiceView(_View):
    name: str
    port: int
    running: bool


class BlueHostView(_View):
    id: str
    name: str
    role: str
    segment: str
    status: str  # "online" | "isolated"
    logging_level: int
    services: list[BlueServiceView]
    unpatched_known_vulns: list[str]


class BlueAccountView(_View):
    credential_id: str
    principal: str
    privilege: str
    hosts: list[str]
    active: bool


class CriticalAssetView(_View):
    asset_id: str
    host_id: str
    name: str


class EventView(_View):
    event_id: int
    step: int
    type: str
    host: str
    src: str | None
    details: dict[str, str]


class AlertView(_View):
    alert_id: int
    step: int
    type: str
    host: str
    severity: Severity
    investigated: bool
    evidence: list[EventView]  # populated only after INVESTIGATE_ALERT


class IncidentView(_View):
    step: int
    host: str


class BlueObservation(_View):
    step: int
    steps_remaining: int
    hosts: list[BlueHostView]
    accounts: list[BlueAccountView]
    critical_assets: list[CriticalAssetView]
    alerts: list[AlertView]
    recent_events: list[EventView]
    blocked_sources: list[str]
    incidents: list[IncidentView]
    last_result: ResultView | None
    allowed_actions: list[str]


def _event_view(e: TelemetryEvent) -> EventView:
    return EventView(event_id=e.event_id, step=e.step, type=e.type.value, host=e.host, src=e.src,
                     details=dict(e.details))


def build_blue_observation(state: EnterpriseState, scenario: Scenario,
                           last_result: ActionResult | None = None) -> BlueObservation:
    visible = {e.event_id: e for e in state.events if e.blue_visible}
    hosts = []
    for hid in sorted(state.hosts):
        h = state.hosts[hid]
        hosts.append(BlueHostView(
            id=hid, name=h.name, role=h.role, segment=h.segment,
            status="isolated" if h.isolated else "online", logging_level=h.logging_level,
            services=[BlueServiceView(name=s.name, port=s.port, running=s.running)
                      for s in state.services_of(hid)],
            unpatched_known_vulns=sorted(v.id for v in state.vulnerabilities.values()
                                         if v.host_id == hid and not v.patched
                                         and v.id in state.blue_known_vulns)))
    alerts = []
    for al in state.alerts[-MAX_ALERTS:]:
        ev = ([_event_view(visible[i]) for i in al.evidence_event_ids if i in visible]
              if al.investigated else [])
        alerts.append(AlertView(alert_id=al.alert_id, step=al.step, type=al.type, host=al.host,
                                severity=al.severity, investigated=al.investigated, evidence=ev))
    recent = [_event_view(e) for e in visible.values()
              if e.step >= state.step - RECENT_WINDOW_STEPS][-MAX_RECENT_EVENTS:]
    return BlueObservation(
        step=state.step, steps_remaining=max(0, scenario.max_steps - state.step),
        hosts=hosts,
        accounts=[BlueAccountView(credential_id=c.id, principal=c.principal,
                                  privilege=c.privilege.value, hosts=list(c.valid_hosts),
                                  active=c.active) for c in state.credentials.values()],
        critical_assets=[CriticalAssetView(asset_id=a.id, host_id=a.host_id, name=a.name)
                         for a in state.assets.values() if a.critical],
        alerts=alerts, recent_events=recent,
        blocked_sources=list(state.network.blocked_sources),
        incidents=[IncidentView(step=i.step, host=i.host) for i in state.incidents],
        last_result=None if last_result is None else ResultView(
            action_type=last_result.action_type, target=last_result.target,
            success=last_result.success, outcome=last_result.outcome, message=last_result.message),
        allowed_actions=[a.value for a in BlueActionType])
