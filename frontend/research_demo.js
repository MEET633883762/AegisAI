'use strict';

(function attachResearchDemo(root) {
  const MAX_ARTIFACT_BYTES = 1024 * 1024;
  const MAX_RECORDS = 120;
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const text = value => typeof value === 'string';
  const integer = value => Number.isInteger(value) && value >= 0;

  function parseArtifact(jsonText) {
    if (typeof jsonText !== 'string') throw new Error('Sample artifact must be text.');
    if (new TextEncoder().encode(jsonText).byteLength > MAX_ARTIFACT_BYTES) {
      throw new Error('Sample artifact exceeds the 1 MB size limit.');
    }
    let artifact;
    try {
      artifact = JSON.parse(jsonText);
    } catch {
      throw new Error('Sample artifact is not valid JSON.');
    }
    validateArtifact(artifact);
    return artifact;
  }

  function validateArtifact(artifact) {
    if (!object(artifact) || artifact.schema_version !== '1.0'
      || artifact.artifact_type !== 'aegisai_public_research_episode') {
      throw new Error('Sample artifact has an unsupported type or schema version.');
    }
    if (!object(artifact.labels) || artifact.labels.synthetic !== true
      || artifact.labels.precomputed !== true || artifact.labels.public_execution !== false
      || !text(artifact.labels.display)) {
      throw new Error('Sample artifact is missing its synthetic/read-only labels.');
    }
    const provenance = artifact.provenance;
    if (!object(provenance) || !text(provenance.episode_id) || !text(provenance.scenario_id)
      || !text(provenance.scenario_template) || !integer(provenance.seed)
      || !text(provenance.research_split) || !text(provenance.red_policy)
      || !text(provenance.blue_policy) || !text(provenance.generator)
      || !text(provenance.generation_mode) || !integer(provenance.recorded_steps)) {
      throw new Error('Sample artifact is missing required provenance fields.');
    }
    if (!object(artifact.objective_result) || typeof artifact.objective_result.achieved !== 'boolean'
      || !text(artifact.objective_result.definition) || artifact.objective_result.episode_count !== 1) {
      throw new Error('Sample artifact has an invalid objective result.');
    }
    if (!Array.isArray(artifact.records) || artifact.records.length < 1
      || artifact.records.length > MAX_RECORDS) {
      throw new Error('Sample artifact has an invalid or oversized action timeline.');
    }
    let previousSequence = 0;
    for (const record of artifact.records) {
      if (!object(record) || !/^trace-[1-9][0-9]*$/.test(record.id)
        || !integer(record.sequence) || record.sequence <= previousSequence
        || record.id !== `trace-${record.sequence}` || !integer(record.step)
        || !['red', 'blue'].includes(record.role) || record.visibility_scope !== record.role) {
        throw new Error('Sample artifact contains an invalid action timeline entry.');
      }
      previousSequence = record.sequence;
      if (!object(record.validation) || typeof record.validation.accepted !== 'boolean'
        || !text(record.validation.reason) || !object(record.authorization)
        || typeof record.authorization.authorized !== 'boolean'
        || !text(record.authorization.policy_reason)) {
        throw new Error('Sample artifact is missing validation or Controller authorization data.');
      }
      if (!object(record.action) || !text(record.action.type) || !text(record.action.target)
        || !object(record.action.parameters) || !text(record.action.reason_category)
        || !text(record.action.expected_outcome)
        || Object.keys(record.action.parameters).length > 8
        || Object.values(record.action.parameters).some(value => !text(value))) {
        throw new Error('Sample artifact contains an invalid structured action.');
      }
      if (!object(record.result) || !text(record.result.outcome)
        || typeof record.result.success !== 'boolean' || !text(record.result.message)) {
        throw new Error('Sample artifact is missing its recorded action result.');
      }
      if (!Array.isArray(record.evidence) || record.evidence.length > 50
        || record.evidence.some(item => !object(item)
          || item.source !== `${record.role}_observation`
          || !text(item.reference) || !text(item.value))) {
        throw new Error('Sample artifact contains evidence outside its role-specific observation.');
      }
    }
    if (!Array.isArray(artifact.metrics) || artifact.metrics.length > 20
      || artifact.metrics.some(metric => !object(metric)
        || !/^[a-z][a-z0-9_]{0,63}$/.test(metric.id)
        || !text(metric.label) || !text(metric.definition) || !text(metric.unit)
        || !Number.isFinite(metric.value) || metric.value < 0 || metric.value > 1
        || !integer(metric.numerator) || !integer(metric.denominator) || metric.denominator < 1
        || metric.numerator > metric.denominator
        || Math.abs(metric.value - metric.numerator / metric.denominator) > 1e-9)) {
      throw new Error('Sample artifact contains an invalid metric or denominator.');
    }
    if (!Array.isArray(artifact.limitations) || artifact.limitations.length < 1
      || artifact.limitations.length > 20 || artifact.limitations.some(item => !text(item))) {
      throw new Error('Sample artifact is missing its limitations.');
    }
    return true;
  }

  function appendText(parent, tagName, className, value) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    node.textContent = String(value);
    parent.appendChild(node);
    return node;
  }

  function renderMetric(container, metric) {
    const card = document.createElement('article');
    card.className = 'research-metric';
    appendText(card, 'h3', '', metric.label);
    appendText(card, 'p', 'research-metric-value', `${metric.numerator} / ${metric.denominator} ${metric.unit} · ${(metric.value * 100).toFixed(1)}%`);
    appendText(card, 'p', 'research-metric-definition', metric.definition);
    container.appendChild(card);
  }

  function renderDetails(container, record) {
    container.replaceChildren();
    appendText(container, 'p', 'research-detail-kicker', `${record.role.toUpperCase()} OBSERVATION · STEP ${record.step}`);
    appendText(container, 'h3', 'research-action-title', record.action.type);
    const scope = document.createElement('p');
    scope.className = 'research-scope-note';
    scope.textContent = `Evidence below comes only from the ${record.role.toUpperCase()} role-specific observation.`;
    container.appendChild(scope);

    const summary = document.createElement('dl');
    summary.className = 'research-summary';
    const fields = [
      ['Target', record.action.target],
      ['Validation', `${record.validation.accepted ? 'Accepted' : 'Rejected'} · ${record.validation.reason}`],
      ['Controller authorization', `${record.authorization.authorized ? 'Authorized' : 'Denied'} · ${record.authorization.policy_reason}`],
      ['Recorded result', `${record.result.outcome} · ${record.result.success ? 'success' : 'not successful'}`],
      ['Result message', record.result.message],
      ['Decision category', record.action.reason_category],
      ['Expected intent', record.action.expected_outcome],
    ];
    for (const [label, value] of fields) {
      appendText(summary, 'dt', '', label);
      appendText(summary, 'dd', '', value);
    }
    if (Object.keys(record.action.parameters).length) {
      appendText(summary, 'dt', '', 'Parameters');
      appendText(summary, 'dd', 'research-parameters', Object.entries(record.action.parameters)
        .map(([key, value]) => `${key}: ${value}`).join(' · '));
    }
    container.appendChild(summary);

    appendText(container, 'h4', 'research-evidence-title', `Role-visible evidence (${record.evidence.length})`);
    if (!record.evidence.length) {
      appendText(container, 'p', 'research-muted', 'No evidence items were recorded in this role’s pre-action trace.');
    } else {
      const evidenceList = document.createElement('ul');
      evidenceList.className = 'research-evidence-list';
      for (const item of record.evidence) {
        const entry = document.createElement('li');
        appendText(entry, 'strong', '', `${item.reference} · ${item.source}`);
        appendText(entry, 'span', '', item.value);
        evidenceList.appendChild(entry);
      }
      container.appendChild(evidenceList);
    }
  }

  function renderArtifact(artifact) {
    const status = document.getElementById('research-demo-status');
    const timeline = document.getElementById('research-demo-timeline');
    const details = document.getElementById('research-demo-details');
    const metrics = document.getElementById('research-demo-metrics');
    const provenance = document.getElementById('research-demo-provenance');
    const limitations = document.getElementById('research-demo-limitations');
    timeline.replaceChildren();
    metrics.replaceChildren();
    provenance.replaceChildren();
    limitations.replaceChildren();

    appendText(provenance, 'p', '', artifact.labels.display);
    appendText(provenance, 'p', '', `${artifact.provenance.scenario_id} · seed ${artifact.provenance.seed} · ${artifact.records.length} recorded actions`);
    appendText(provenance, 'p', '', `${artifact.provenance.red_policy} vs ${artifact.provenance.blue_policy} · ${artifact.provenance.research_split}`);
    appendText(provenance, 'p', '', `Episode objective recorded as ${artifact.objective_result.achieved ? 'achieved' : 'not achieved'} in this one sample.`);

    for (const metric of artifact.metrics) renderMetric(metrics, metric);
    for (const limitation of artifact.limitations) appendText(limitations, 'li', '', limitation);

    const controls = [];
    for (const record of artifact.records) {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'research-timeline-button';
      button.setAttribute('aria-pressed', 'false');
      button.textContent = `Step ${record.step} · ${record.role.toUpperCase()} · ${record.action.type} · ${record.result.outcome}`;
      button.addEventListener('click', () => {
        for (const control of controls) control.setAttribute('aria-pressed', 'false');
        button.setAttribute('aria-pressed', 'true');
        renderDetails(details, record);
      });
      controls.push(button);
      item.appendChild(button);
      timeline.appendChild(item);
    }
    if (controls.length) controls[0].click();
    status.textContent = `Loaded ${artifact.records.length} precomputed action records. No actions were executed.`;
  }

  async function loadArtifact() {
    const status = document.getElementById('research-demo-status');
    try {
      status.textContent = 'Loading the precomputed sample…';
      const response = await fetch('data/public_demo_episode.json', { cache: 'no-cache' });
      if (!response.ok) throw new Error(`Sample artifact request failed (${response.status}).`);
      const declaredSize = Number(response.headers.get('content-length'));
      if (Number.isFinite(declaredSize) && declaredSize > MAX_ARTIFACT_BYTES) {
        throw new Error('Sample artifact exceeds the 1 MB size limit.');
      }
      const artifact = parseArtifact(await response.text());
      renderArtifact(artifact);
    } catch (error) {
      status.textContent = `Could not load the sample: ${error.message}`;
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MAX_ARTIFACT_BYTES, parseArtifact, validateArtifact, renderArtifact };
  }
  if (typeof document !== 'undefined' && document.getElementById('research-demo')) {
    loadArtifact();
  }
})(globalThis);
