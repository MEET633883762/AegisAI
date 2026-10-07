import pytest

from environment.actions import Outcome
from environment.scenarios import build_scenario
from environment.simulator import Simulator
from telemetry.events import EventType
from tests.unit.conftest import blue, chain, red


def test_full_kill_chain_reaches_goal_for_both_templates():
    for template, pivot in (("web_exploit_lateral_exfil", "host_c"),
                            ("credential_reuse_known_vuln", "host_d")):
        for seed in (1, 2, 3, 4):
            sim = Simulator(build_scenario(template, seed))
            for a in chain(pivot):
                r = sim.apply_red(a)
                assert r.success, (template, seed, a.action_type, r.message)
                if not sim.is_done():
                    sim.advance_time()
            assert sim.red_goal_achieved() and sim.is_done()


def test_firewall_blocks_direct_internal_access(sim):
    # External cannot see or touch internal hosts, even if the id is guessed.
    for h in ("host_b", "host_c", "host_d", "host_zzz"):
        r = sim.apply_red(red("DISCOVER_HOST", h))
        assert r.outcome is Outcome.UNREACHABLE and r.message == "No response from target."
    assert sim.state.red.known_hosts == ["host_a"]


def test_prerequisites_enforced(sim):
    assert sim.apply_red(red("DISCOVER_SERVICE", "host_a")).outcome is Outcome.PRECONDITION_FAILED
    sim.apply_red(red("ENUMERATE_PORT", "host_a"))
    assert (sim.apply_red(red("EXPLOIT_SIMULATED_VULNERABILITY", "host_a", service="web")).outcome
            is Outcome.PRECONDITION_FAILED)  # service not yet identified
    assert sim.apply_red(red("OBTAIN_CREDENTIAL", "host_a")).outcome is Outcome.PRECONDITION_FAILED
    assert (sim.apply_red(red("ENUMERATE_PORT", "host_b")).outcome is Outcome.INVALID_TARGET)
    assert (sim.apply_red(red("EXPLOIT_SIMULATED_VULNERABILITY", "host_a")).outcome
            is Outcome.INVALID_PARAMETER)


def test_lateral_move_needs_known_credential_and_internal_foothold(sim):
    for a in chain()[:3]:  # foothold on host_a, credential not yet obtained
        sim.apply_red(a)
    sim.apply_red(red("DISCOVER_HOST", "host_c"))
    assert (sim.apply_red(red("LATERAL_MOVE", "host_c", credential_id="cred_svc_backup")).outcome
            is Outcome.PRECONDITION_FAILED)
    assert (sim.apply_red(red("LATERAL_MOVE", "host_c")).outcome is Outcome.INVALID_PARAMETER)
    sim.apply_red(red("OBTAIN_CREDENTIAL", "host_a"))
    assert sim.apply_red(red("LATERAL_MOVE", "host_c", credential_id="cred_svc_backup")).success


def test_ids_are_guessable_but_not_trusted_credential_ids_must_be_learned(sim):
    for a in chain()[:3]:
        sim.apply_red(a)
    sim.apply_red(red("DISCOVER_HOST", "host_c"))
    # cred_db_admin exists in the world but Red has not obtained it.
    assert (sim.apply_red(red("LATERAL_MOVE", "host_c", credential_id="cred_db_admin")).outcome
            is Outcome.PRECONDITION_FAILED)


def test_wrong_credential_fails_and_logs_auth_failure(sim):
    for a in chain()[:6]:
        sim.apply_red(a)
    sim.apply_red(red("DISCOVER_HOST", "host_d"))
    r = sim.apply_red(red("LATERAL_MOVE", "host_d", credential_id="cred_svc_backup"))
    assert r.outcome is Outcome.DENIED
    assert sim.state.events[-1].type is EventType.AUTH_FAILURE
    assert "host_d" not in sim.state.red.compromised


def test_asset_steps_ordered_and_privilege_checked(sim):
    for a in chain()[:6]:
        sim.apply_red(a)
    sim.apply_red(chain()[6])  # lateral to host_c (admin)
    assert sim.state.red.compromised["host_c"].value == "admin"
    sim.apply_red(chain()[7]); sim.apply_red(chain()[8]); sim.apply_red(chain()[9])
    assert (sim.apply_red(red("COLLECT_DATA", "host_b", asset_id="asset_customer_db")).outcome
            is Outcome.PRECONDITION_FAILED)  # must access first
    assert (sim.apply_red(red("EXFILTRATE_SIMULATED_DATA", "host_b",
                              asset_id="asset_customer_db")).outcome is Outcome.PRECONDITION_FAILED)
    assert (sim.apply_red(red("ACCESS_SENSITIVE_ASSET", "host_b", asset_id="nope")).outcome
            is Outcome.INVALID_TARGET)


def test_failed_attempt_without_state_change_is_not_a_success(sim):
    sim.apply_red(red("ENUMERATE_PORT", "host_a"))
    r = sim.apply_red(red("ENUMERATE_PORT", "host_a"))
    assert r.outcome is Outcome.NO_EFFECT and not r.success


# ---- Blue effects -----------------------------------------------------------------------------
def test_isolating_entry_host_locks_red_out(sim):
    for a in chain()[:2]:
        sim.apply_red(a)
    assert sim.apply_blue(blue("ISOLATE_HOST", "host_a")).success
    r = sim.apply_red(red("EXPLOIT_SIMULATED_VULNERABILITY", "host_a", service="web"))
    assert r.outcome is Outcome.UNREACHABLE and "host_a" not in sim.state.red.compromised


def test_isolating_pivot_blocks_progress_and_restore_reopens(sim):
    for a in chain()[:7]:
        sim.apply_red(a)
    sim.apply_blue(blue("ISOLATE_HOST", "host_c"))
    assert sim.apply_red(red("OBTAIN_CREDENTIAL", "host_c")).outcome is Outcome.PRECONDITION_FAILED
    assert sim.apply_blue(blue("ISOLATE_HOST", "host_c")).outcome is Outcome.NO_EFFECT
    sim.apply_blue(blue("RESTORE_SERVICE", "host_c"))
    assert sim.apply_red(red("OBTAIN_CREDENTIAL", "host_c")).success


def test_block_external_stops_new_access_but_not_internal_footholds(sim):
    for a in chain()[:2]:
        sim.apply_red(a)
    assert sim.apply_blue(blue("BLOCK_SOURCE", "external")).success
    assert (sim.apply_red(red("EXPLOIT_SIMULATED_VULNERABILITY", "host_a", service="web")).outcome
            is Outcome.UNREACHABLE)


def test_block_compromised_source_stops_egress(sim):
    for a in chain()[:12]:
        assert sim.apply_red(a).success
    sim.apply_blue(blue("BLOCK_SOURCE", "host_b"))
    r = sim.apply_red(chain()[12])
    assert r.outcome is Outcome.PRECONDITION_FAILED and not sim.red_goal_achieved()


def test_reset_credential_breaks_lateral_move(sim):
    for a in chain()[:6]:
        sim.apply_red(a)
    assert sim.apply_blue(blue("RESET_CREDENTIAL", "host_a", credential_id="cred_svc_backup")).success
    assert (sim.apply_red(chain()[6]).outcome is Outcome.DENIED)


def test_disable_and_restore_service(sim):
    assert sim.apply_blue(blue("DISABLE_SERVICE", "host_a", service="web")).success
    assert sim.apply_red(red("ENUMERATE_PORT", "host_a")).outcome is Outcome.UNREACHABLE
    assert sim.apply_blue(blue("DISABLE_SERVICE", "host_a", service="web")).outcome is Outcome.NO_EFFECT
    assert sim.apply_blue(blue("RESTORE_SERVICE", "host_a", service="web")).success
    assert sim.apply_red(red("ENUMERATE_PORT", "host_a")).success


def test_patch_requires_known_vuln_and_blocks_exploit():
    # Template 1: vuln unknown to Blue -> no patch available.
    s1 = Simulator(build_scenario("web_exploit_lateral_exfil", 1))
    assert (s1.apply_blue(blue("PATCH_SIMULATED_VULNERABILITY", "host_a", service="web")).outcome
            is Outcome.NO_EFFECT)
    # Template 2: known -> patch works and the exploit has no effect.
    s2 = Simulator(build_scenario("credential_reuse_known_vuln", 1))
    assert s2.apply_blue(blue("PATCH_SIMULATED_VULNERABILITY", "host_a", service="web")).success
    for a in chain("host_d")[:2]:
        s2.apply_red(a)
    r = s2.apply_red(chain("host_d")[2])
    assert r.outcome is Outcome.NO_EFFECT and "host_a" not in s2.state.red.compromised


def test_invalid_blue_targets(sim):
    assert sim.apply_blue(blue("ISOLATE_HOST", "host_zzz")).outcome is Outcome.INVALID_TARGET
    assert sim.apply_blue(blue("BLOCK_SOURCE", "host_zzz")).outcome is Outcome.INVALID_TARGET
    assert (sim.apply_blue(blue("DISABLE_SERVICE", "host_a")).outcome is Outcome.INVALID_PARAMETER)
    assert (sim.apply_blue(blue("RESET_CREDENTIAL", "host_a", credential_id="x")).outcome
            is Outcome.INVALID_PARAMETER)


def test_episode_ends_at_max_steps_and_rejects_further_actions(sim):
    for _ in range(sim.scenario.max_steps):
        sim.advance_time()
    assert sim.is_done()
    assert sim.apply_red(red("DISCOVER_HOST", "host_a")).outcome is Outcome.PRECONDITION_FAILED
    assert sim.apply_blue(blue("MONITOR", "host_a")).outcome is Outcome.PRECONDITION_FAILED


# ---- advance_time fails closed after termination ----------------------------------------------
from environment.simulator import EpisodeCompleteError  # noqa: E402


def test_advance_time_fails_closed_after_max_steps(sim):
    for _ in range(sim.scenario.max_steps):
        sim.advance_time()
    assert sim.is_done() and sim.state.step == sim.scenario.max_steps
    digest, n_events = sim.state_digest(), len(sim.state.events)
    for _ in range(3):
        with pytest.raises(EpisodeCompleteError):
            sim.advance_time()
    assert sim.state.step == sim.scenario.max_steps          # step counter frozen
    assert len(sim.state.events) == n_events                 # no telemetry emitted
    assert sim.state_digest() == digest                      # nothing changed at all


def test_advance_time_fails_closed_after_goal_achieved():
    sim = Simulator(build_scenario("credential_reuse_known_vuln", 3))  # noisy template
    for a in chain("host_d"):
        assert sim.apply_red(a).success
        if not sim.is_done():
            sim.advance_time()
    assert sim.red_goal_achieved() and sim.state.step < sim.scenario.max_steps
    step, digest, n_events = sim.state.step, sim.state_digest(), len(sim.state.events)
    with pytest.raises(EpisodeCompleteError):
        sim.advance_time()
    assert sim.state.step == step and len(sim.state.events) == n_events
    assert sim.state_digest() == digest
    # apply_* also remain closed and non-mutating after termination
    assert sim.apply_blue(blue("ISOLATE_HOST", "host_a")).outcome is Outcome.PRECONDITION_FAILED
    assert sim.state_digest() == digest


def test_advance_time_still_works_on_the_last_live_step(sim):
    for _ in range(sim.scenario.max_steps - 1):
        sim.advance_time()
    assert not sim.is_done()
    sim.advance_time()  # step 29 -> 30 is legal
    assert sim.is_done()
