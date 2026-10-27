import type { EpisodeRecord, PublicEpisode } from "./types";
import { useRef, type KeyboardEvent } from "react";
import { describeRecord, explainResult, hostNames, keyMoments } from "./episodeStory";
import { Icon, type IconName } from "./icons";

export function EpisodeWalkthrough({ artifact, selected, onSelect }: { artifact: PublicEpisode; selected: EpisodeRecord; onSelect: (record: EpisodeRecord) => void }) {
  const playerRef = useRef<HTMLDivElement>(null);
  const moments = keyMoments(artifact.records);
  const activeMoment = moments.findIndex((record) => record.id === selected.id);
  const previous = [...moments].reverse().find((r) => r.sequence < selected.sequence);
  const next = moments.find((r) => r.sequence > selected.sequence);
  const story = describeRecord(selected);
  const actor = selected.role === "red" ? "Attacker" : "Defender";
  const navigateWithKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const destinations: Record<string, EpisodeRecord | undefined> = { ArrowLeft: previous, ArrowRight: next, Home: moments[0], End: moments.at(-1) };
    const target = destinations[event.key];
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (target) {
      onSelect(target);
      if (event.target instanceof HTMLElement && event.target.closest(".moment-tabs")) {
        const index = moments.findIndex((record) => record.id === target.id);
        playerRef.current?.querySelectorAll<HTMLButtonElement>(".moment-tabs button")[index]?.focus();
      }
    }
  };
  const momentLabel = (record: EpisodeRecord) => {
    if (!record.result.success) return "Access rejected";
    if (record.role === "blue") return "Defender reacts";
    return ({ ENUMERATE_PORT: "Discovery", EXPLOIT_SIMULATED_VULNERABILITY: "First access", ACCESS_SENSITIVE_ASSET: "Data reached", EXFILTRATE_SIMULATED_DATA: "Final outcome" } as Record<string, string>)[record.action.type] ?? "Recorded moment";
  };
  const nodes: { id: string; icon: IconName; detail: string }[] = [
    { id: "host_a", icon: "server", detail: "Entry point" },
    { id: "host_c", icon: "monitor", detail: "Employee computer" },
    { id: "host_d", icon: "server", detail: "Internal application" },
    { id: "host_b", icon: "database", detail: "Fictional customer records" },
  ];
  return <div className="walkthrough" ref={playerRef} role="region" aria-label="Recorded exercise player" aria-describedby="replay-keyboard-help" tabIndex={0} onKeyDown={navigateWithKeyboard}>
    <div className="replay-toolbar"><span><Icon name="play" />Guided replay</span><small id="replay-keyboard-help">Focus the player · Use ← → to move · Home / End to jump</small><a href="#episode-outcome">View results <Icon name="arrow" /></a></div>
    <div className="moment-tabs" role="group" aria-label="Key moments in the exercise">{moments.map((record, index) => <button key={record.id} type="button" className={index < activeMoment ? "moment-past" : ""} aria-label={`Moment ${index + 1}: ${describeRecord(record).title}`} aria-pressed={record.id === selected.id} onClick={() => onSelect(record)}><span>{index < activeMoment ? <Icon name="check" /> : String(index + 1).padStart(2, "0")}</span>{momentLabel(record)}</button>)}</div>
    <div className={`replay-scene actor-${selected.role}`}>
      <section className="story-copy" aria-live="polite" aria-atomic="true" aria-label="Current moment explained">
        <div className="scene-kicker"><span className={`actor-label ${selected.role}`}><Icon name={selected.role === "red" ? "target" : "shield"} />{actor}'s move</span><span>Record {selected.sequence} / {artifact.records.length}</span></div>
        <h3>{story.title}</h3><p className="story-explanation">{story.explanation}</p>
        <div className="result-callout"><span className="result-label">WHAT HAPPENED</span><p><span className={`result-symbol ${selected.result.success ? "success" : "denied"}`} aria-hidden="true">{selected.result.success ? "✓" : "×"}</span>{explainResult(selected)}</p><small>Simulator record: {selected.result.message}</small></div>
        <div className="walk-controls"><button type="button" onClick={() => previous && onSelect(previous)} disabled={!previous} aria-label="Previous key moment"><span aria-hidden="true">←</span> Back</button><span>{activeMoment >= 0 ? `Moment ${activeMoment + 1} of ${moments.length}` : "Exploring a recorded action"}</span><button type="button" className="next-moment" onClick={() => next && onSelect(next)} disabled={!next} aria-label="Next key moment">Next moment <span aria-hidden="true">→</span></button></div>
        {!next && <button className="restart-walkthrough" type="button" onClick={() => {
          onSelect(moments[0]);
          playerRef.current?.querySelector<HTMLButtonElement>(".moment-tabs button")?.focus();
        }}>↺ Restart walkthrough</button>}
      </section>
      <section className="exercise-map" aria-label="Simplified exercise map"><div className="map-title"><span>THE PRACTICE NETWORK</span><span className="map-replay-label">RECORDED REPLAY</span></div>
        <div className="gate-flow"><span className={`flow-actor ${selected.role}`}><Icon name={selected.role === "red" ? "target" : "shield"} />{actor}</span><Icon name="arrow" /><span className="flow-gate"><Icon name="lock" />Safety gate</span><Icon name="arrow" /><span className="flow-verdict">{selected.authorization.authorized ? "Allowed" : "Denied"}<Icon name={selected.authorization.authorized ? "check" : "lock"} /></span></div>
        <div className="network-nodes">{nodes.map((node) => <div key={node.id} className={`network-node ${selected.action.target === node.id ? `node-active node-${selected.role}` : ""}`}><span className="node-icon"><Icon name={node.icon} /></span><strong>{hostNames[node.id]}</strong><small>{selected.action.target === node.id ? `← ${actor}'s current target` : node.detail}</small></div>)}</div>
        <p className="map-caption"><span className="map-legend-dot" />Highlighted = current target · A simplified view, not live monitoring</p>
      </section>
    </div>
    <div className="gate-explanation"><Icon name="shield" /><p><strong>Every move passes through a safety gate.</strong> The Controller checks what an agent is allowed to do. An allowed attempt can still fail—for example, when a captured login is rejected.</p><span>SIMULATOR ONLY</span></div>
  </div>;
}

export function EpisodeOutcome({ artifact }: { artifact: PublicEpisode }) {
  const detection = artifact.metrics.find((m) => m.id === "detection_rate");
  const mitigation = artifact.metrics.find((m) => m.id === "mitigation_success_rate");
  return <section className="episode-outcome" id="episode-outcome" aria-label="Full episode results">
    <div className="outcome-intro"><span className="eyebrow">THE FULL EPISODE, AT A GLANCE</span><h3>Did the defense stop it?</h3><p>Final results from this one scripted exercise.</p></div>
    <div className="outcome-stat"><Icon name="eye" /><strong>{detection ? `${detection.numerator} of ${detection.denominator}` : "—"}</strong><span>malicious alerts detected</span></div>
    <div className="outcome-stat outcome-warning"><Icon name="shield" /><strong>{mitigation ? `${mitigation.numerator} of ${mitigation.denominator}` : "—"}</strong><span>response-required alerts mitigated</span></div>
    <div className={`outcome-verdict ${artifact.objective_result.achieved ? "goal-reached" : "goal-stopped"}`}><span>ATTACKER'S GOAL</span><strong>{artifact.objective_result.achieved ? "Reached" : "Not reached"}</strong><p>{artifact.objective_result.achieved ? "The simulator recorded synthetic data leaving the network." : "The simulator did not record the data-exfiltration objective."}</p></div>
  </section>;
}
