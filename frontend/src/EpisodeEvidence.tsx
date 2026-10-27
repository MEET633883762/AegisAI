import { useState } from "react";
import type { EpisodeRecord, PublicEpisode } from "./types";
import { describeRecord, hostNames } from "./episodeStory";
import { Icon } from "./icons";

type RoleFilter = "all" | "red" | "blue";

export function EpisodeEvidence({ artifact, selected, onSelect }: {
  artifact: PublicEpisode;
  selected: EpisodeRecord;
  onSelect: (record: EpisodeRecord) => void;
}) {
  const [role, setRole] = useState<RoleFilter>("all");
  const [query, setQuery] = useState("");
  const hasFilters = role !== "all" || query.length > 0;
  const normalizedQuery = query.trim().toLowerCase();
  const records = artifact.records.filter((record) => {
    if (role !== "all" && record.role !== role) return false;
    const searchable = [describeRecord(record).title, record.action.type, record.action.target,
      hostNames[record.action.target] ?? "", record.result.message, record.result.outcome,
      ...record.evidence.map((item) => `${item.reference} ${item.value}`)].join(" ").toLowerCase();
    return searchable.includes(normalizedQuery);
  });
  const selectedVisible = records.some((record) => record.id === selected.id);
  const clearFilters = () => { setRole("all"); setQuery(""); };

  return (
      <details className="technical-evidence" id="episode-evidence"><summary><Icon name="code" /><span>Look under the hood <small>All {artifact.records.length} actions, original evidence & metric definitions</small></span><span className="expand-label" aria-hidden="true"><span className="when-closed">EXPAND +</span><span className="when-open">COLLAPSE −</span></span></summary><div className="evidence-content">
        <section className="research-provenance" aria-label="Sample provenance"><h3>Sample provenance and outcome</h3><p>{artifact.labels.display}</p><p>{artifact.provenance.scenario_id} · seed {artifact.provenance.seed} · {artifact.records.length} recorded actions</p><p>{artifact.provenance.red_policy} vs {artifact.provenance.blue_policy} · {artifact.provenance.research_split}</p><p>Episode objective recorded as {artifact.objective_result.achieved ? "achieved" : "not achieved"} in this one sample.</p></section>
        <section className="research-metrics-section" aria-labelledby="research-metrics-title"><div className="section-head"><h3 id="research-metrics-title">Episode metrics</h3><span className="badge">Single synthetic episode</span></div><div className="research-metrics">{artifact.metrics.map((metric) => <article className="research-metric" key={metric.id}><h3>{metric.label}</h3><p className="research-metric-value">{metric.numerator} / {metric.denominator} {metric.unit} · {(metric.value * 100).toFixed(1)}%</p><p className="research-metric-definition">{metric.definition}</p></article>)}</div></section>
        <div className="evidence-browser-head">
          <div><p className="eyebrow">EXPLORE THE RECORD</p><h3>Find the decision that matters.</h3><p>Filter the timeline, then select an action to inspect exactly what that role knew.</p></div>
          <label htmlFor="episode-action-search">Search recorded actions<input id="episode-action-search" type="search" value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Action, host, result or evidence" /></label>
        </div>
        <div className="evidence-browser-controls">
          <div className="evidence-role-filters" role="group" aria-label="Filter actions by role">
            <button type="button" aria-pressed={role === "all"} onClick={() => setRole("all")}>All roles</button>
            <button type="button" aria-pressed={role === "red"} onClick={() => setRole("red")}><Icon name="target" />Attacker only</button>
            <button type="button" aria-pressed={role === "blue"} onClick={() => setRole("blue")}><Icon name="shield" />Defender only</button>
          </div>
          <span role="status" className="evidence-match-count">Showing {records.length} of {artifact.records.length} actions</span>
          {hasFilters && <button type="button" className="evidence-clear" onClick={clearFilters}>Clear action filters</button>}
        </div>
        <div className="research-demo-grid">
          <section className="research-timeline-panel" aria-labelledby="research-timeline-title">
            <div className="section-head"><h3 id="research-timeline-title">Recorded action timeline</h3><span className="badge">Select a step</span></div>
            {records.length > 0 ? <ol className="research-timeline" aria-label="Precomputed Red and Blue actions">{records.map((record) => <li key={record.id}>
              <button type="button" className="research-timeline-button" aria-pressed={selected.id === record.id} onClick={() => onSelect(record)}>
                <span className={`timeline-role ${record.role}`}>{record.role.toUpperCase()}</span><span>{describeRecord(record).title}<small>Step {record.step} · {record.action.type} · {record.result.outcome}</small></span>
              </button>
            </li>)}</ol> : <div className="evidence-empty"><Icon name="eye" /><h4>No actions match these filters.</h4><p>Try a different search term or clear the filters to see the full episode.</p><button type="button" onClick={clearFilters}>Show all actions</button></div>}
          </section>
          <section className="research-detail-panel" aria-labelledby="research-detail-title">
            <div className="selected-record-heading"><h3 id="research-detail-title">Selected action details</h3><span>Record {selected.sequence} / {artifact.records.length}</span></div>
            {!selectedVisible && <p className="selection-filter-note">The selected action is outside the current filters. <button type="button" onClick={clearFilters}>Show selected action</button></p>}
            <div aria-live="polite" aria-atomic="true"><RecordDetails record={selected} /></div>
          </section>
        </div>
        <section className="research-limitations" aria-labelledby="research-limitations-title"><h3 id="research-limitations-title">Sample limitations</h3><ul>{artifact.limitations.map((limitation, index) => <li key={`${index}-${limitation}`}>{limitation}</li>)}</ul></section>
      </div></details>
  );
}

function RecordDetails({ record }: { record: EpisodeRecord }) {
  return <><p className="research-detail-kicker">{record.role.toUpperCase()} OBSERVATION · STEP {record.step}</p><h4 className="research-action-title">{record.action.type}</h4>
    <p className="research-scope-note">Evidence below comes only from the {record.role.toUpperCase()} role-specific observation.</p>
    <dl className="research-summary"><dt>Target</dt><dd>{record.action.target}</dd><dt>Validation</dt><dd>{record.validation.accepted ? "Accepted" : "Rejected"} · {record.validation.reason}</dd><dt>Controller authorization</dt><dd>{record.authorization.authorized ? "Authorized" : "Denied"} · {record.authorization.policy_reason}</dd><dt>Recorded result</dt><dd>{record.result.outcome} · {record.result.success ? "success" : "not successful"}</dd><dt>Result message</dt><dd>{record.result.message}</dd><dt>Decision category</dt><dd>{record.action.reason_category}</dd><dt>Expected intent</dt><dd>{record.action.expected_outcome}</dd>{Object.keys(record.action.parameters).length > 0 && <><dt>Parameters</dt><dd className="research-parameters">{Object.entries(record.action.parameters).map(([key, value]) => `${key}: ${value}`).join(" · ")}</dd></>}</dl>
    <h5 className="research-evidence-title">Role-visible evidence ({record.evidence.length})</h5>{record.evidence.length === 0 ? <p className="research-muted">No evidence items were recorded in this role’s pre-action trace.</p> : <ul className="research-evidence-list">{record.evidence.map((item, index) => <li key={`${item.reference}-${index}`}><strong>{item.reference} · {item.source}</strong><span>{item.value}</span></li>)}</ul>}
  </>;
}

