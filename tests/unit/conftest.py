import pytest

from environment.actions import BlueAction, RedAction
from environment.scenarios import build_scenario
from environment.simulator import Simulator


def red(t, target, **params):
    return RedAction(action_type=t, target=target, parameters=params)


def blue(t, target, **params):
    return BlueAction(action_type=t, target=target, parameters=params)


def chain(pivot="host_c"):
    """Full successful kill chain for the standard topology."""
    return [
        red("ENUMERATE_PORT", "host_a"), red("DISCOVER_SERVICE", "host_a"),
        red("EXPLOIT_SIMULATED_VULNERABILITY", "host_a", service="web"),
        red("OBTAIN_CREDENTIAL", "host_a"),
        red("DISCOVER_HOST", pivot), red("ENUMERATE_PORT", pivot),
        red("LATERAL_MOVE", pivot, credential_id="cred_svc_backup"),
        red("OBTAIN_CREDENTIAL", pivot),
        red("DISCOVER_HOST", "host_b"),
        red("LATERAL_MOVE", "host_b", credential_id="cred_db_admin"),
        red("ACCESS_SENSITIVE_ASSET", "host_b", asset_id="asset_customer_db"),
        red("COLLECT_DATA", "host_b", asset_id="asset_customer_db"),
        red("EXFILTRATE_SIMULATED_DATA", "host_b", asset_id="asset_customer_db"),
    ]


@pytest.fixture
def sim():
    return Simulator(build_scenario("web_exploit_lateral_exfil", 1))


def run_until(sim, n):
    out = []
    for a in chain()[:n]:
        out.append(sim.apply_red(a))
    return out
