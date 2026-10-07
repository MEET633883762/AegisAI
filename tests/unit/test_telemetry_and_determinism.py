import json

from environment.scenarios import build_scenario
from environment.simulator import Simulator
from telemetry.events import EventType
from tests.unit.conftest import blue, chain, red


def _run(template, seed, blue_script=None):
    sim = Simulator(build_scenario(template, seed))
    for i, a in enumerate(chain("host_c" if template.startswith("web") else "host_d")):
        sim.apply_red(a)
        if blue_script and i in blue_script:
            sim.apply_blue(blue_script[i])
        if not sim.is_done():
            sim.advance_time()
    return sim


def test_same_scenario_seed_actions_give_identical_state():
    for t in ("web_exploit_lateral_exfil", "credential_reuse_known_vuln"):
        assert _run(t, 7).state_digest() == _run(t, 7).state_digest()


def test_scenario_construction_is_deterministic_and_seed_sensitive():
    d = lambda s: json.dumps(build_scenario("web_exploit_lateral_exfil", s).model_dump(mode="json"),
                             sort_keys=True)
    assert d(5) == d(5)
    assert len({d(s) for s in range(1, 9)}) > 1  # parameters vary with seed


def test_noise_depends_on_seed_and_is_replayable():
    def noise(seed):
        sim = Simulator(build_scenario("credential_reuse_known_vuln", seed))
        for _ in range(25):
            sim.advance_time()
        return [(e.step, e.host, e.type.value) for e in sim.state.events]
    assert noise(3) == noise(3)
    assert noise(3) != noise(4)
    assert len(noise(3)) > 0


def test_simulator_does_not_mutate_scenario_template():
    sc = build_scenario("web_exploit_lateral_exfil", 1)
    before = sc.model_dump_json()
    sim = Simulator(sc)
    for a in chain():
        sim.apply_red(a)
    assert sc.model_dump_json() == before


def test_basic_logging_hides_exploit_but_verbose_logging_alerts():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))  # host_a basic logging
    for a in chain()[:3]:
        sim.apply_red(a)
    types = {al.type for al in sim.state.alerts}
    assert "exploit_attempt" not in types and "scan_activity" not in types
    hidden = [e for e in sim.state.events if e.type is EventType.EXPLOIT_ATTEMPT]
    assert hidden and not hidden[0].blue_visible  # recorded as ground truth, invisible to Blue

    sim2 = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    assert sim2.apply_blue(blue("INCREASE_LOGGING", "host_a")).success
    for a in chain()[:3]:
        sim2.apply_red(a)
    assert {"scan_activity", "exploit_attempt"} <= {al.type for al in sim2.state.alerts}


def test_logging_increase_is_not_retroactive():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    for a in chain()[:3]:
        sim.apply_red(a)
    n = len(sim.state.alerts)
    sim.apply_blue(blue("INCREASE_LOGGING", "host_a"))
    assert len(sim.state.alerts) == n


def test_kill_chain_generates_high_signal_alerts_even_with_basic_logging():
    sim = _run("web_exploit_lateral_exfil", 1)
    types = {al.type for al in sim.state.alerts}
    assert {"lateral_movement", "sensitive_data_access", "data_exfiltration"} <= types


def test_false_positive_alerts_come_only_from_benign_events():
    sim = Simulator(build_scenario("credential_reuse_known_vuln", 2))
    for _ in range(30):
        sim.advance_time()
    by_id = {e.event_id: e for e in sim.state.events}
    fps = [al for al in sim.state.alerts if by_id[al.evidence_event_ids[0]].actor == "benign"]
    assert fps and all(a.type == "auth_anomaly" for a in fps)
    assert all(e.actor == "benign" for e in sim.state.events)  # no Red activity in this run


def test_investigate_reveals_evidence_and_mark_incident():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    sim.apply_blue(blue("INCREASE_LOGGING", "host_a"))
    sim.apply_red(red("ENUMERATE_PORT", "host_a"))
    al = sim.state.alerts[0]
    assert sim.apply_blue(blue("INVESTIGATE_ALERT", "host_a", alert_id=str(al.alert_id))).success
    assert sim.state.alerts[0].investigated
    assert sim.apply_blue(blue("INVESTIGATE_ALERT", "host_b", alert_id=str(al.alert_id))).outcome.value \
        == "invalid_target"
    assert sim.apply_blue(blue("MARK_INCIDENT", "host_a", alert_id=str(al.alert_id))).success
    assert sim.apply_blue(blue("MARK_INCIDENT", "host_a")).outcome.value == "no_effect"


def test_action_result_audit_fields_populated():
    sim = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    r = sim.apply_red(red("ENUMERATE_PORT", "host_a"))
    assert r.state_changes and r.event_ids and r.step == 0
