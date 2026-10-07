"""Deterministic cyber simulator. Applies already-typed actions as pure state transitions.

Nothing here executes code, spawns processes or opens sockets. Policy/authorization is the
Controller's job (Phase 2); the simulator still fails closed on anything unexpected.

Turn protocol (driven by the Controller): apply_red -> apply_blue -> advance_time.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Callable

from environment.actions import (ActionResult, BlueAction, BlueActionType, Outcome, RedAction,
                                 RedActionType, Role, unknown_parameters)
from environment.hosts import Host, Privilege, max_privilege, privilege_at_least
from environment.network import EXTERNAL
from environment.scenarios import Scenario
from environment.state import EnterpriseState, Incident
from telemetry.events import EVENT_RULES, Alert, EventType, TelemetryEvent

_NO_RESPONSE = "No response from target."
_UNKNOWN = "Unknown target."
_NO_ACCESS = "No usable access to target."


def _add(lst: list, item) -> bool:
    """Append if absent. Returns True if the list changed."""
    if item in lst:
        return False
    lst.append(item)
    return True


class EpisodeCompleteError(RuntimeError):
    """Raised when time is advanced after the episode has terminated."""


class Simulator:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.state: EnterpriseState = scenario.initial_state.model_copy(deep=True)
        for hid in scenario.red_initial_known_hosts:
            _add(self.state.red.known_hosts, hid)
        self._pending_events: list[int] = []
        self._pending_changes: list[str] = []
        self._red: dict[RedActionType, Callable[[RedAction], ActionResult]] = {
            RedActionType.DISCOVER_HOST: self._r_discover_host,
            RedActionType.ENUMERATE_PORT: self._r_enumerate_port,
            RedActionType.DISCOVER_SERVICE: self._r_discover_service,
            RedActionType.ATTEMPT_ACCESS: self._r_attempt_access,
            RedActionType.EXPLOIT_SIMULATED_VULNERABILITY: self._r_exploit,
            RedActionType.OBTAIN_CREDENTIAL: self._r_obtain_credential,
            RedActionType.LATERAL_MOVE: self._r_lateral_move,
            RedActionType.ACCESS_SENSITIVE_ASSET: self._r_access_asset,
            RedActionType.COLLECT_DATA: self._r_collect_data,
            RedActionType.EXFILTRATE_SIMULATED_DATA: self._r_exfiltrate,
        }
        self._blue: dict[BlueActionType, Callable[[BlueAction], ActionResult]] = {
            BlueActionType.MONITOR: self._b_monitor,
            BlueActionType.INVESTIGATE_ALERT: self._b_investigate,
            BlueActionType.BLOCK_SOURCE: self._b_block_source,
            BlueActionType.DISABLE_SERVICE: self._b_disable_service,
            BlueActionType.ISOLATE_HOST: self._b_isolate,
            BlueActionType.RESET_CREDENTIAL: self._b_reset_credential,
            BlueActionType.PATCH_SIMULATED_VULNERABILITY: self._b_patch,
            BlueActionType.INCREASE_LOGGING: self._b_increase_logging,
            BlueActionType.RESTORE_SERVICE: self._b_restore,
            BlueActionType.MARK_INCIDENT: self._b_mark_incident,
        }

    # =========================================================================================
    # Public API
    # =========================================================================================
    def apply_red(self, action: RedAction) -> ActionResult:
        if not isinstance(action, RedAction):
            raise TypeError("apply_red requires a RedAction")
        if self.is_done():
            return self._res(Role.RED, action, Outcome.PRECONDITION_FAILED, "Episode has ended.")
        if unknown_parameters(action):  # defense in depth for actions built without validation
            return self._res(Role.RED, action, Outcome.INVALID_PARAMETER, "Unknown parameter.")
        return self._red[action.action_type](action)

    def apply_blue(self, action: BlueAction) -> ActionResult:
        if not isinstance(action, BlueAction):
            raise TypeError("apply_blue requires a BlueAction")
        if self.is_done():
            return self._res(Role.BLUE, action, Outcome.PRECONDITION_FAILED, "Episode has ended.")
        if unknown_parameters(action):
            return self._res(Role.BLUE, action, Outcome.INVALID_PARAMETER, "Unknown parameter.")
        return self._blue[action.action_type](action)

    def advance_time(self) -> list[int]:
        """Advance one step and emit seeded benign background telemetry (the source of false
        positives). Randomness is derived from (seed, step) only, so it is replayable.

        Fails closed: raises EpisodeCompleteError, changing nothing, once the episode is over."""
        if self.is_done():
            raise EpisodeCompleteError("episode already complete; time cannot advance")
        s = self.state
        s.step += 1
        rng = random.Random(f"{s.seed}:{s.step}")
        self._pending_events = []
        for hid in sorted(s.hosts):  # fixed draw count per host regardless of branches
            r_emit, r_kind, r_peer = rng.random(), rng.random(), rng.random()
            host = s.hosts[hid]
            if host.isolated or r_emit >= self.scenario.noise_probability:
                continue
            peers = sorted(h for h in s.hosts if h != hid and not s.hosts[h].isolated)
            src = peers[int(r_peer * len(peers))] if peers else None
            etype = EventType.BENIGN_AUTH_FAILURE if r_kind < 0.3 else EventType.BENIGN_LOGIN
            self._emit(etype, hid, src, "benign", {"user": "employee"})
        ids, self._pending_events = self._pending_events, []
        return ids

    def red_goal_achieved(self) -> bool:
        return self.scenario.target_asset_id in self.state.red.exfiltrated_assets

    def is_done(self) -> bool:
        return self.red_goal_achieved() or self.state.step >= self.scenario.max_steps

    def state_digest(self) -> str:
        blob = json.dumps(self.state.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    # =========================================================================================
    # Internals
    # =========================================================================================
    def _res(self, role: Role, action, outcome: Outcome, message: str) -> ActionResult:
        res = ActionResult(
            role=role, action_type=action.action_type.value, target=action.target,
            success=outcome is Outcome.SUCCESS, outcome=outcome, message=message,
            step=self.state.step, state_changes=self._pending_changes,
            event_ids=self._pending_events)
        self._pending_changes, self._pending_events = [], []
        return res

    def _emit(self, etype: EventType, host: str, src: str | None, actor: str,
              details: dict[str, str] | None = None) -> TelemetryEvent:
        s = self.state
        rule = EVENT_RULES[etype]
        h = s.hosts.get(host)
        visible = (h.logging_level if h else 1) >= rule.min_level
        ev = TelemetryEvent(event_id=s.next_event_id, step=s.step, type=etype, host=host, src=src,
                            actor=actor, details=details or {}, blue_visible=visible)
        s.next_event_id += 1
        s.events.append(ev)
        self._pending_events.append(ev.event_id)
        if visible and rule.alert_type:
            s.alerts.append(Alert(alert_id=s.next_alert_id, step=s.step, type=rule.alert_type,
                                  host=host, severity=rule.severity, evidence_event_ids=[ev.event_id]))
            s.next_alert_id += 1
        return ev

    def _change(self, text: str) -> None:
        self._pending_changes.append(text)

    # ---- Red helpers -------------------------------------------------------------------------
    def _route(self, dst: str, port: int, sources: list[str] | None = None) -> str | None:
        for src in (self.state.foothold_sources() if sources is None else sources):
            if self.state.can_reach(src, dst, port):
                return src
        return None

    def _reachable_services(self, dst: str) -> list[tuple[str, int, str]]:
        """(source, port, service_name) for each running service Red can currently reach."""
        out = []
        for svc in self.state.services_of(dst):
            if svc.running:
                src = self._route(dst, svc.port)
                if src is not None:
                    out.append((src, svc.port, svc.name))
        return out

    def _known_host(self, a: RedAction) -> Host | ActionResult:
        h = self.state.hosts.get(a.target)
        if h is None or a.target not in self.state.red.known_hosts:
            return self._res(Role.RED, a, Outcome.INVALID_TARGET, _UNKNOWN)
        return h

    def _operable(self, host_id: str) -> bool:
        s = self.state
        h = s.hosts.get(host_id)
        return (h is not None and host_id in s.red.compromised and not h.isolated
                and host_id not in s.network.blocked_sources)

    def _grant(self, host_id: str, priv: Privilege) -> None:
        cur = self.state.red.compromised.get(host_id)
        new = max_privilege(cur, priv)
        if new != cur:
            self.state.red.compromised[host_id] = new
            self._change(f"red.compromised[{host_id}]={new.value}")

    def _need_param(self, a, key: str) -> str | ActionResult:
        v = a.parameters.get(key)
        if not v:
            return self._res(Role.RED if isinstance(a, RedAction) else Role.BLUE, a,
                             Outcome.INVALID_PARAMETER, f"Missing parameter: {key}.")
        return v

    # ---- Red transitions ---------------------------------------------------------------------
    def _r_discover_host(self, a: RedAction) -> ActionResult:
        # Unknown and unreachable hosts are indistinguishable (no existence oracle for Red).
        reach = self._reachable_services(a.target) if a.target in self.state.hosts else []
        if not reach:
            return self._res(Role.RED, a, Outcome.UNREACHABLE, _NO_RESPONSE)
        self._emit(EventType.NETWORK_PROBE, a.target, reach[0][0], "red", {"kind": "host"})
        if _add(self.state.red.known_hosts, a.target):
            self._change(f"red.known_hosts+={a.target}")
            return self._res(Role.RED, a, Outcome.SUCCESS, "Host discovered.")
        return self._res(Role.RED, a, Outcome.NO_EFFECT, "Nothing new learned.")

    def _r_enumerate_port(self, a: RedAction) -> ActionResult:
        h = self._known_host(a)
        if isinstance(h, ActionResult):
            return h
        reach = self._reachable_services(a.target)
        if not reach:
            return self._res(Role.RED, a, Outcome.UNREACHABLE, _NO_RESPONSE)
        self._emit(EventType.NETWORK_PROBE, a.target, reach[0][0], "red", {"kind": "port"})
        ports = self.state.red.enumerated_ports.setdefault(a.target, [])
        changed = False
        for _, port, _ in sorted(reach, key=lambda t: t[1]):
            if _add(ports, port):
                changed = True
                self._change(f"red.enumerated_ports[{a.target}]+={port}")
        ports.sort()
        return self._res(Role.RED, a, Outcome.SUCCESS if changed else Outcome.NO_EFFECT,
                         "Open ports found." if changed else "Nothing new learned.")

    def _r_discover_service(self, a: RedAction) -> ActionResult:
        h = self._known_host(a)
        if isinstance(h, ActionResult):
            return h
        known_ports = self.state.red.enumerated_ports.get(a.target)
        if not known_ports:
            return self._res(Role.RED, a, Outcome.PRECONDITION_FAILED,
                             "Enumerate ports on this host first.")
        reach = {port: (src, name) for src, port, name in self._reachable_services(a.target)}
        hits = [(p, reach[p]) for p in sorted(known_ports) if p in reach]
        if not hits:
            return self._res(Role.RED, a, Outcome.UNREACHABLE, _NO_RESPONSE)
        self._emit(EventType.NETWORK_PROBE, a.target, hits[0][1][0], "red", {"kind": "service"})
        names = self.state.red.discovered_services.setdefault(a.target, [])
        changed = False
        for _, (_, name) in hits:
            if _add(names, name):
                changed = True
                self._change(f"red.discovered_services[{a.target}]+={name}")
        return self._res(Role.RED, a, Outcome.SUCCESS if changed else Outcome.NO_EFFECT,
                         "Services identified." if changed else "Nothing new learned.")

    def _authenticate(self, a: RedAction, h: Host, cred_id: str, src: str, lateral: bool) -> ActionResult:
        s = self.state
        cred = s.credentials[cred_id]
        if cred.active and a.target in cred.valid_hosts:
            self._emit(EventType.LATERAL_MOVEMENT if lateral else EventType.AUTH_SUCCESS, a.target,
                       src, "red", {"user": cred.principal, "service": h.login_service or ""})
            self._grant(a.target, cred.privilege)
            return self._res(Role.RED, a, Outcome.SUCCESS, "Access obtained.")
        self._emit(EventType.AUTH_FAILURE, a.target, src, "red",
                   {"user": cred.principal, "service": h.login_service or ""})
        return self._res(Role.RED, a, Outcome.DENIED, "Credential rejected.")

    def _access_common(self, a: RedAction, lateral: bool) -> ActionResult:
        s = self.state
        h = self._known_host(a)
        if isinstance(h, ActionResult):
            return h
        cred_id = self._need_param(a, "credential_id")
        if isinstance(cred_id, ActionResult):
            return cred_id
        if cred_id not in s.red.known_credentials:
            return self._res(Role.RED, a, Outcome.PRECONDITION_FAILED, "Credential not known.")
        if a.target in s.red.compromised:
            return self._res(Role.RED, a, Outcome.NO_EFFECT, "Access already held.")
        svc = s.find_service(a.target, h.login_service) if h.login_service else None
        if svc is None or not svc.running:
            return self._res(Role.RED, a, Outcome.UNREACHABLE, _NO_RESPONSE)
        sources = ([x for x in sorted(s.red.compromised) if x != a.target] if lateral else None)
        src = self._route(a.target, svc.port, sources)
        if src is None:
            return self._res(Role.RED, a, Outcome.UNREACHABLE, _NO_RESPONSE)
        return self._authenticate(a, h, cred_id, src, lateral)

    def _r_attempt_access(self, a: RedAction) -> ActionResult:
        return self._access_common(a, lateral=False)

    def _r_lateral_move(self, a: RedAction) -> ActionResult:
        return self._access_common(a, lateral=True)

    def _r_exploit(self, a: RedAction) -> ActionResult:
        s = self.state
        h = self._known_host(a)
        if isinstance(h, ActionResult):
            return h
        name = self._need_param(a, "service")
        if isinstance(name, ActionResult):
            return name
        if name not in s.red.discovered_services.get(a.target, []):
            return self._res(Role.RED, a, Outcome.PRECONDITION_FAILED, "Service not identified.")
        svc = s.find_service(a.target, name)
        if svc is None or not svc.running:
            return self._res(Role.RED, a, Outcome.UNREACHABLE, _NO_RESPONSE)
        src = self._route(a.target, svc.port)
        if src is None:
            return self._res(Role.RED, a, Outcome.UNREACHABLE, _NO_RESPONSE)
        self._emit(EventType.EXPLOIT_ATTEMPT, a.target, src, "red", {"service": name})
        vuln = s.vulnerabilities.get(svc.vulnerability_id) if svc.vulnerability_id else None
        if vuln is None or vuln.patched:
            return self._res(Role.RED, a, Outcome.NO_EFFECT, "Exploit attempt had no effect.")
        self._grant(a.target, vuln.grants)
        return self._res(Role.RED, a, Outcome.SUCCESS, "Foothold established.")

    def _r_obtain_credential(self, a: RedAction) -> ActionResult:
        s = self.state
        h = self._known_host(a)
        if isinstance(h, ActionResult):
            return h
        if not self._operable(a.target):
            return self._res(Role.RED, a, Outcome.PRECONDITION_FAILED, _NO_ACCESS)
        priv = s.red.compromised[a.target]
        self._emit(EventType.CREDENTIAL_ACCESS, a.target, a.target, "red")
        gained = False
        for cid in sorted(s.credentials):
            c = s.credentials[cid]
            if (c.stored_on == a.target and c.active and privilege_at_least(priv, c.requires_privilege)
                    and _add(s.red.known_credentials, cid)):
                gained = True
                self._change(f"red.known_credentials+={cid}")
        return self._res(Role.RED, a, Outcome.SUCCESS if gained else Outcome.NO_EFFECT,
                         "Credentials obtained." if gained else "No new credentials found.")

    def _asset_step(self, a: RedAction, *, needs: str | None, adds: str, event: EventType,
                    ok_msg: str) -> ActionResult:
        s = self.state
        h = self._known_host(a)
        if isinstance(h, ActionResult):
            return h
        aid = self._need_param(a, "asset_id")
        if isinstance(aid, ActionResult):
            return aid
        if not self._operable(a.target):
            return self._res(Role.RED, a, Outcome.PRECONDITION_FAILED, _NO_ACCESS)
        asset = s.assets.get(aid)
        if asset is None or asset.host_id != a.target:
            return self._res(Role.RED, a, Outcome.INVALID_TARGET, "Asset not found on target.")
        if not privilege_at_least(s.red.compromised[a.target], asset.required_privilege):
            return self._res(Role.RED, a, Outcome.DENIED, "Insufficient privilege.")
        progress = getattr(s.red, adds)
        if needs is not None and aid not in getattr(s.red, needs):
            return self._res(Role.RED, a, Outcome.PRECONDITION_FAILED, "Previous step not completed.")
        if event is EventType.DATA_EXFILTRATION and not s.can_egress(a.target):
            return self._res(Role.RED, a, Outcome.UNREACHABLE, "Outbound connection failed.")
        details = {"destination": "external"} if event is EventType.DATA_EXFILTRATION else {"asset": aid}
        self._emit(event, a.target, a.target, "red", details)
        if _add(progress, aid):
            self._change(f"red.{adds}+={aid}")
            return self._res(Role.RED, a, Outcome.SUCCESS, ok_msg)
        return self._res(Role.RED, a, Outcome.NO_EFFECT, "Already done.")

    def _r_access_asset(self, a: RedAction) -> ActionResult:
        return self._asset_step(a, needs=None, adds="accessed_assets",
                                event=EventType.SENSITIVE_DATA_ACCESS, ok_msg="Asset accessed.")

    def _r_collect_data(self, a: RedAction) -> ActionResult:
        return self._asset_step(a, needs="accessed_assets", adds="collected_assets",
                                event=EventType.DATA_COLLECTION, ok_msg="Data collected.")

    def _r_exfiltrate(self, a: RedAction) -> ActionResult:
        return self._asset_step(a, needs="collected_assets", adds="exfiltrated_assets",
                                event=EventType.DATA_EXFILTRATION, ok_msg="Data exfiltrated.")

    # ---- Blue transitions --------------------------------------------------------------------
    def _bres(self, a: BlueAction, outcome: Outcome, msg: str) -> ActionResult:
        return self._res(Role.BLUE, a, outcome, msg)

    def _b_host(self, a: BlueAction) -> Host | ActionResult:
        h = self.state.hosts.get(a.target)
        return h if h is not None else self._bres(a, Outcome.INVALID_TARGET, _UNKNOWN)

    def _b_service(self, a: BlueAction, h: Host):
        name = a.parameters.get("service")
        if not name:
            return self._bres(a, Outcome.INVALID_PARAMETER, "Missing parameter: service.")
        svc = self.state.find_service(h.id, name)
        return svc if svc is not None else self._bres(a, Outcome.INVALID_TARGET, "Service not found.")

    def _b_monitor(self, a: BlueAction) -> ActionResult:
        return self._bres(a, Outcome.SUCCESS, "Monitoring continues.")

    def _b_investigate(self, a: BlueAction) -> ActionResult:
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        raw = a.parameters.get("alert_id", "")
        alert = next((x for x in self.state.alerts if str(x.alert_id) == raw), None)
        if alert is None or alert.host != a.target:
            return self._bres(a, Outcome.INVALID_TARGET, "Alert not found for target.")
        if alert.investigated:
            return self._bres(a, Outcome.NO_EFFECT, "Alert already investigated.")
        alert.investigated = True
        self._change(f"alert[{alert.alert_id}].investigated=True")
        return self._bres(a, Outcome.SUCCESS, "Alert evidence retrieved.")

    def _b_block_source(self, a: BlueAction) -> ActionResult:
        if a.target != EXTERNAL and a.target not in self.state.hosts:
            return self._bres(a, Outcome.INVALID_TARGET, _UNKNOWN)
        if not _add(self.state.network.blocked_sources, a.target):
            return self._bres(a, Outcome.NO_EFFECT, "Source already blocked.")
        self._change(f"network.blocked_sources+={a.target}")
        self._emit(EventType.SOURCE_BLOCKED, a.target, None, "blue")
        return self._bres(a, Outcome.SUCCESS, "Source blocked.")

    def _b_disable_service(self, a: BlueAction) -> ActionResult:
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        svc = self._b_service(a, h)
        if isinstance(svc, ActionResult):
            return svc
        if not svc.running:
            return self._bres(a, Outcome.NO_EFFECT, "Service already disabled.")
        svc.running = False
        self._change(f"service[{h.id}:{svc.name}].running=False")
        self._emit(EventType.SERVICE_DISABLED, h.id, None, "blue", {"service": svc.name})
        return self._bres(a, Outcome.SUCCESS, "Service disabled.")

    def _b_isolate(self, a: BlueAction) -> ActionResult:
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        if h.isolated:
            return self._bres(a, Outcome.NO_EFFECT, "Host already isolated.")
        h.isolated = True
        self._change(f"host[{h.id}].isolated=True")
        self._emit(EventType.HOST_ISOLATED, h.id, None, "blue")
        return self._bres(a, Outcome.SUCCESS, "Host isolated.")

    def _b_reset_credential(self, a: BlueAction) -> ActionResult:
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        cred = self.state.credentials.get(a.parameters.get("credential_id", ""))
        if cred is None:
            return self._bres(a, Outcome.INVALID_PARAMETER, "Credential not found.")
        if not cred.active:
            return self._bres(a, Outcome.NO_EFFECT, "Credential already reset.")
        cred.active = False
        self._change(f"credential[{cred.id}].active=False")
        self._emit(EventType.CREDENTIAL_RESET, h.id, None, "blue", {"user": cred.principal})
        return self._bres(a, Outcome.SUCCESS, "Credential reset.")

    def _b_patch(self, a: BlueAction) -> ActionResult:
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        svc = self._b_service(a, h)
        if isinstance(svc, ActionResult):
            return svc
        vuln = self.state.vulnerabilities.get(svc.vulnerability_id) if svc.vulnerability_id else None
        if vuln is None or vuln.patched or vuln.id not in self.state.blue_known_vulns:
            return self._bres(a, Outcome.NO_EFFECT, "No applicable patch.")
        vuln.patched = True
        self._change(f"vulnerability[{vuln.id}].patched=True")
        self._emit(EventType.VULNERABILITY_PATCHED, h.id, None, "blue", {"service": svc.name})
        return self._bres(a, Outcome.SUCCESS, "Patch applied.")

    def _b_increase_logging(self, a: BlueAction) -> ActionResult:
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        if h.logging_level >= 2:
            return self._bres(a, Outcome.NO_EFFECT, "Logging already verbose.")
        h.logging_level = 2
        self._change(f"host[{h.id}].logging_level=2")
        self._emit(EventType.LOGGING_INCREASED, h.id, None, "blue")
        return self._bres(a, Outcome.SUCCESS, "Logging increased.")

    def _b_restore(self, a: BlueAction) -> ActionResult:
        """With `service`: re-enable that service. Without: lift host isolation."""
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        if "service" in a.parameters:
            svc = self._b_service(a, h)
            if isinstance(svc, ActionResult):
                return svc
            if svc.running:
                return self._bres(a, Outcome.NO_EFFECT, "Service already running.")
            svc.running = True
            self._change(f"service[{h.id}:{svc.name}].running=True")
            self._emit(EventType.SERVICE_RESTORED, h.id, None, "blue", {"service": svc.name})
            return self._bres(a, Outcome.SUCCESS, "Service restored.")
        if not h.isolated:
            return self._bres(a, Outcome.NO_EFFECT, "Nothing to restore.")
        h.isolated = False
        self._change(f"host[{h.id}].isolated=False")
        self._emit(EventType.HOST_RESTORED, h.id, None, "blue")
        return self._bres(a, Outcome.SUCCESS, "Host restored.")

    def _b_mark_incident(self, a: BlueAction) -> ActionResult:
        h = self._b_host(a)
        if isinstance(h, ActionResult):
            return h
        raw = a.parameters.get("alert_id")
        alert_id = None
        if raw is not None:
            alert = next((x for x in self.state.alerts if str(x.alert_id) == raw), None)
            if alert is None:
                return self._bres(a, Outcome.INVALID_PARAMETER, "Alert not found.")
            alert_id = alert.alert_id
        if any(i.host == h.id for i in self.state.incidents):
            return self._bres(a, Outcome.NO_EFFECT, "Incident already open for host.")
        self.state.incidents.append(Incident(step=self.state.step, host=h.id, alert_id=alert_id))
        self._change(f"incidents+={h.id}")
        self._emit(EventType.INCIDENT_MARKED, h.id, None, "blue")
        return self._bres(a, Outcome.SUCCESS, "Incident recorded.")
