import json

from environment.scenarios import build_scenario
from environment.simulator import Simulator
from telemetry.observation_builder import build_blue_observation, build_red_observation
from tests.unit.conftest import blue, chain, red

# Field/key names that exist only in ground truth or on the opposite side.
BLUE_FORBIDDEN_KEYS = {"actor", "blue_visible", "compromised", "known_credentials", "red",
                       "state_changes", "event_ids", "exfiltrated_assets", "collected_assets",
                       "accessed_assets", "malicious", "known_hosts", "discovered_services",
                       "enumerated_ports", "objective", "target_asset_id"}
RED_FORBIDDEN = ["alert", "logging_level", "blocked_sources", "incident", "recent_events", "actor",
                 "blue_visible", "state_changes", "event_ids", "unpatched_known_vulns", "accounts",
                 "critical_assets", "vuln_web_001", "SIM-WEB", "isolated"]


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def _js(model):
    return json.dumps(model.model_dump(mode="json"))


def test_red_initial_view_contains_only_initial_knowledge():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    obs = build_red_observation(sim.state, sim.scenario)
    assert [h.id for h in obs.known_hosts] == ["host_a"]
    assert obs.known_hosts[0].services == [] and obs.known_hosts[0].open_ports == []
    s = _js(obs)
    for hidden in ("host_b", "host_c", "host_d", "svc_backup", "db_admin", "5432"):
        assert hidden not in s
    for bad in RED_FORBIDDEN:
        assert bad not in s, bad


def test_red_view_grows_only_with_discovery_and_never_leaks_blue_state():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    sim.apply_blue(blue("INCREASE_LOGGING", "host_a"))
    last = None
    for a in chain()[:9]:
        last = sim.apply_red(a)
        sim.advance_time()
    sim.apply_blue(blue("BLOCK_SOURCE", "external"))
    obs = build_red_observation(sim.state, sim.scenario, last)
    ids = {h.id for h in obs.known_hosts}
    assert ids == {"host_a", "host_c", "host_b"} and "host_d" not in ids
    s = _js(obs)
    assert "host_d" not in s
    for bad in RED_FORBIDDEN:
        assert bad not in s, bad
    # Red learns that actions fail, not why Blue acted.
    assert obs.last_result.message and "block" not in obs.last_result.message.lower()


def test_red_sees_assets_only_on_compromised_hosts():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    for a in chain()[:9]:
        sim.apply_red(a)
    obs = build_red_observation(sim.state, sim.scenario)
    hv = {h.id: h for h in obs.known_hosts}
    assert hv["host_b"].assets == [] and not hv["host_b"].compromised
    sim.apply_red(chain()[9])
    hv = {h.id: h for h in build_red_observation(sim.state, sim.scenario).known_hosts}
    assert hv["host_b"].assets == ["asset_customer_db"]


def test_blue_view_never_contains_red_private_state_or_ground_truth_labels():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    sim.apply_blue(blue("INCREASE_LOGGING", "host_a"))
    for a in chain()[:10]:
        sim.apply_red(a)
        sim.advance_time()
    for al in list(sim.state.alerts):
        sim.apply_blue(blue("INVESTIGATE_ALERT", al.host, alert_id=str(al.alert_id)))
    obs = build_blue_observation(sim.state, sim.scenario, None)
    keys = set(_keys(obs.model_dump(mode="json")))
    assert not (keys & BLUE_FORBIDDEN_KEYS), keys & BLUE_FORBIDDEN_KEYS
    assert "red" not in _js(obs).replace("cred", "")  # no Red-labelled values either
    assert obs.alerts and any(a.evidence for a in obs.alerts)


def test_blue_does_not_see_events_below_logging_level_and_benign_is_indistinguishable():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))  # host_a basic
    for a in chain()[:3]:
        sim.apply_red(a)
    obs = build_blue_observation(sim.state, sim.scenario)
    assert not any(e.type in ("network_probe", "exploit_attempt") for e in obs.recent_events)
    # Event views carry no actor field, so benign and malicious events look identical.
    from telemetry.observation_builder import EventView
    assert set(EventView.model_fields) == {"event_id", "step", "type", "host", "src", "details"}


def test_blue_vuln_knowledge_follows_scenario():
    s1 = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    s2 = Simulator(build_scenario("credential_reuse_known_vuln", 1))
    v1 = {h.id: h.unpatched_known_vulns for h in build_blue_observation(s1.state, s1.scenario).hosts}
    v2 = {h.id: h.unpatched_known_vulns for h in build_blue_observation(s2.state, s2.scenario).hosts}
    assert v1["host_a"] == [] and v2["host_a"] == ["vuln_web_001"]
    s2.apply_blue(blue("PATCH_SIMULATED_VULNERABILITY", "host_a", service="web"))
    assert {h.id: h.unpatched_known_vulns
            for h in build_blue_observation(s2.state, s2.scenario).hosts}["host_a"] == []


def test_observations_are_snapshots_not_live_references():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    obs = build_blue_observation(sim.state, sim.scenario)
    sim.apply_blue(blue("ISOLATE_HOST", "host_a"))
    assert {h.id: h.status for h in obs.hosts}["host_a"] == "online"
    assert not hasattr(obs, "state")
