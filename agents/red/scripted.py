"""Deterministic, observation-driven Red baseline.

The scripted agent is deliberately not given a Simulator or Scenario. It receives only a
RedObservation and emits one typed RedAction. It uses a fixed, auditable priority policy so it
can serve as the baseline for later LLM Red experiments.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from environment.actions import RedAction, RedActionType
from telemetry.observation_builder import RedObservation, RedHostView


@dataclass
class ScriptedRedAgent:
    """Simple deterministic Red policy for the Phase 3 baseline.

    The candidate host list is intentionally explicit and bounded. It is not read from the
    simulator; failed discovery attempts are ordinary observations and do not reveal hidden
    state. The policy never mutates environment state directly.
    """

    candidate_hosts: tuple[str, ...] = ("host_c", "host_d", "host_b")
    _last_action: RedAction | None = field(default=None, init=False, repr=False)
    _attempted_lateral_hosts: set[str] = field(default_factory=set, init=False, repr=False)

    def decide(self, observation: RedObservation) -> RedAction:
        """Return exactly one deterministic action from the observation."""
        if not observation.known_hosts:
            raise ValueError("RedObservation must contain at least one known host")

        # Work toward the objective using only facts visible in the observation.
        for host in observation.known_hosts:
            if not host.open_ports:
                return self._emit(RedActionType.ENUMERATE_PORT, host.id)

        for host in observation.known_hosts:
            if not host.services:
                return self._emit(RedActionType.DISCOVER_SERVICE, host.id)

        # Exploit a discovered vulnerable service on an uncompromised host.
        for host in observation.known_hosts:
            if host.compromised:
                continue
            for service in host.services:
                if service.name == "web":
                    return self._emit(
                        RedActionType.EXPLOIT_SIMULATED_VULNERABILITY,
                        host.id,
                        service=service.name,
                    )

        # Once a foothold exists, obtain credentials from the compromised host.
        for host in observation.known_hosts:
            if host.compromised and not observation.known_credentials:
                return self._emit(RedActionType.OBTAIN_CREDENTIAL, host.id)

        # Probe bounded pivot candidates before looking for the database. The database is not
        # externally reachable in this scenario and should only be discovered after pivoting.
        known_ids = {h.id for h in observation.known_hosts}
        for host_id in self.candidate_hosts[:2]:
            if host_id not in known_ids:
                return self._emit(RedActionType.DISCOVER_HOST, host_id)

        pivot = next((h for h in observation.known_hosts
                      if h.id in self.candidate_hosts[:2] and h.compromised), None)

        # Once a pivot is compromised, first collect the credential stored on that pivot.
        if pivot is not None:
            if len(observation.known_credentials) < 2:
                return self._emit(RedActionType.OBTAIN_CREDENTIAL, pivot.id)
            if "host_b" not in known_ids:
                return self._emit(RedActionType.DISCOVER_HOST, "host_b")

        # If the target asset is visible on a controlled host, complete the data lifecycle
        # before attempting any unrelated lateral movement.
        for host in observation.known_hosts:
            if observation.target_asset_id in host.assets and host.compromised:
                if observation.target_asset_id not in observation.accessed_assets:
                    return self._emit(
                        RedActionType.ACCESS_SENSITIVE_ASSET,
                        host.id,
                        asset_id=observation.target_asset_id,
                    )
                if observation.target_asset_id not in observation.collected_assets:
                    return self._emit(
                        RedActionType.COLLECT_DATA,
                        host.id,
                        asset_id=observation.target_asset_id,
                    )
                if observation.target_asset_id not in observation.exfiltrated_assets:
                    return self._emit(
                        RedActionType.EXFILTRATE_SIMULATED_DATA,
                        host.id,
                        asset_id=observation.target_asset_id,
                    )

        # If the database is known, use the most recently obtained credential for its login.
        db = self._host(observation, "host_b")
        if db is not None and not db.compromised and observation.known_credentials:
            return self._emit(
                RedActionType.LATERAL_MOVE,
                "host_b",
                credential_id=observation.known_credentials[-1].id,
            )

        # Before a pivot is obtained, use the first known credential to attempt lateral movement.
        credential = observation.known_credentials[0] if observation.known_credentials else None
        if credential:
            for host_id in self.candidate_hosts[:2]:
                host = self._host(observation, host_id)
                if host is None or host.compromised or host.id in self._attempted_lateral_hosts:
                    continue
                self._attempted_lateral_hosts.add(host.id)
                return self._emit(
                    RedActionType.LATERAL_MOVE,
                    host.id,
                    credential_id=credential.id,
                )

        # After lateral access, obtain any credential stored on the pivot.
        for host in observation.known_hosts:
            if host.compromised and host.id != "host_a":
                # The simulator exposes only credentials already discovered by Red. A second
                # credential is useful when the pivot stores one; try the bounded action once.
                if len(observation.known_credentials) < 2:
                    return self._emit(RedActionType.OBTAIN_CREDENTIAL, host.id)

        # No useful action is currently visible. MONITOR is not a Red action, so use a bounded
        # discovery probe rather than inventing parameters or touching hidden state.
        return self._emit(RedActionType.DISCOVER_HOST, self.candidate_hosts[0])

    @property
    def last_action(self) -> RedAction | None:
        return self._last_action

    def _emit(self, action_type: RedActionType, target: str, **parameters: str) -> RedAction:
        action = RedAction(
            action_type=action_type,
            target=target,
            parameters=parameters,
            rationale="deterministic scripted baseline policy",
        )
        self._last_action = action
        return action

    @staticmethod
    def _host(observation: RedObservation, host_id: str) -> RedHostView | None:
        return next((h for h in observation.known_hosts if h.id == host_id), None)
