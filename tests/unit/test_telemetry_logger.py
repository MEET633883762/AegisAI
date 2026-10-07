from controller.orchestrator import Controller
from environment.scenarios import build_scenario
from telemetry.events import EventType
from telemetry.logger import TelemetryLogger
from tests.unit.conftest import red


def test_logger_is_append_only_and_queries_by_step():
    sim = __import__('environment.simulator', fromlist=['Simulator']).Simulator(
        build_scenario('web_exploit_lateral_exfil', 1)
    )
    sim.apply_red(red('ENUMERATE_PORT', 'host_a'))
    logger = TelemetryLogger()
    logger.ingest(sim.state.events, sim.state.alerts)
    assert len(logger.events()) == 1
    assert logger.events_for_step(0)[0].type is EventType.NETWORK_PROBE
    assert logger.events() == logger.events()


def test_logger_rejects_duplicate_event_ids():
    sim = __import__('environment.simulator', fromlist=['Simulator']).Simulator(
        build_scenario('web_exploit_lateral_exfil', 1)
    )
    sim.apply_red(red('ENUMERATE_PORT', 'host_a'))
    logger = TelemetryLogger()
    logger.ingest(sim.state.events, sim.state.alerts)
    try:
        logger.ingest(sim.state.events, [])
    except ValueError as exc:
        assert 'duplicate telemetry event id' in str(exc)
    else:
        raise AssertionError('duplicate event was accepted')


def test_controller_syncs_events_and_alerts_into_telemetry_sink():
    c = Controller(build_scenario('web_exploit_lateral_exfil', 1))
    result = c.submit_red(red('ENUMERATE_PORT', 'host_a'))
    assert result.accepted
    assert len(c.telemetry_log().events()) == 1
    assert len(c.telemetry_log().alerts()) == 0
    assert c.telemetry_log().event(result.action_result.event_ids[0]) is not None


def test_controller_telemetry_syncs_benign_events_on_advance():
    c = Controller(build_scenario('credential_reuse_known_vuln', 2))
    c.run_turn(red('DISCOVER_HOST', 'host_d'), __import__('tests.unit.conftest', fromlist=['blue']).blue('MONITOR', 'host_d'))
    # run_turn advances if still live, so background events from the next step are captured.
    assert all(e.actor in {'red', 'blue', 'benign'} for e in c.telemetry_log().events())
