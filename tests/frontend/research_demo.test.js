'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { MAX_ARTIFACT_BYTES, parseArtifact, validateArtifact, renderArtifact } = require('../../frontend/research_demo.js');
const { readBoundedResponseText } = require('../../frontend/research_demo.js');

const artifactPath = path.resolve(__dirname, '../../frontend/data/public_demo_episode.json');
const artifactText = fs.readFileSync(artifactPath, 'utf8');
const validArtifact = JSON.parse(artifactText);

test('checked-in public episode sample matches the versioned, role-scoped schema', () => {
  const artifact = parseArtifact(artifactText);
  assert.equal(artifact.labels.synthetic, true);
  assert.equal(artifact.labels.precomputed, true);
  assert.equal(artifact.provenance.seed, 1);
  assert.ok(artifact.records.length > 1);
  assert.ok(artifact.records.some(record => record.role === 'red'));
  assert.ok(artifact.records.some(record => record.role === 'blue'));
  assert.ok(artifact.metrics.every(metric => metric.denominator > 0));
  assert.ok(artifact.records.every(record => record.evidence.every(
    item => item.source === `${record.role}_observation`
  )));
  assert.ok(artifact.records.every(record => !('state_changes' in record) && !('event_ids' in record)));
});

test('malformed JSON is rejected with a bounded parser error', () => {
  assert.throws(() => parseArtifact('{broken'), /not valid JSON/);
});

test('missing required fields are rejected', () => {
  const sample = structuredClone(validArtifact);
  delete sample.provenance.seed;
  assert.throws(() => validateArtifact(sample), /missing required provenance/);
  const missingAction = structuredClone(validArtifact);
  delete missingAction.records[0].action.type;
  assert.throws(() => validateArtifact(missingAction), /invalid structured action/);
});

test('unsupported schema versions are rejected', () => {
  const sample = structuredClone(validArtifact);
  sample.schema_version = '9.9';
  assert.throws(() => validateArtifact(sample), /unsupported type or schema version/);
});

test('oversized artifact JSON is rejected before parsing', () => {
  assert.throws(() => parseArtifact(' '.repeat(MAX_ARTIFACT_BYTES + 1)), /1 MB size limit/);
});

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.textContent = '';
    this.className = '';
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  click() { if (this.listeners.click) this.listeners.click(); }
}

test('HTML and script payloads render only as inert text nodes', () => {
  const sample = structuredClone(validArtifact);
  const payload = '<img src=x onerror=alert(1)><script>alert(2)</script>';
  sample.records[0].action.type = payload;
  sample.records[0].evidence[0].value = payload;
  const ids = [
    'research-demo-status', 'research-demo-timeline', 'research-demo-details',
    'research-demo-metrics', 'research-demo-provenance', 'research-demo-limitations'
  ];
  const nodes = new Map(ids.map(id => [id, new FakeElement('div')]));
  const previousDocument = global.document;
  global.document = {
    getElementById: id => nodes.get(id),
    createElement: tagName => new FakeElement(tagName)
  };
  try {
    renderArtifact(sample);
  } finally {
    global.document = previousDocument;
  }
  const allNodes = [];
  const visit = node => { allNodes.push(node); node.children.forEach(visit); };
  nodes.forEach(visit);
  assert.equal(allNodes.some(node => node.tagName === 'IMG' || node.tagName === 'SCRIPT'), false);
  assert.ok(allNodes.some(node => node.textContent === payload));
});

test('selecting an action shows its role scope, validation, authorization, and evidence', () => {
  const ids = [
    'research-demo-status', 'research-demo-timeline', 'research-demo-details',
    'research-demo-metrics', 'research-demo-provenance', 'research-demo-limitations'
  ];
  const nodes = new Map(ids.map(id => [id, new FakeElement('div')]));
  const previousDocument = global.document;
  global.document = {
    getElementById: id => nodes.get(id),
    createElement: tagName => new FakeElement(tagName)
  };
  try {
    renderArtifact(validArtifact);
    const blueIndex = validArtifact.records.findIndex(record => record.role === 'blue');
    const selectedButton = nodes.get('research-demo-timeline').children[blueIndex].children[0];
    selectedButton.click();
    assert.equal(selectedButton.attributes['aria-pressed'], 'true');
    const detailText = [];
    const visit = node => { detailText.push(node.textContent); node.children.forEach(visit); };
    visit(nodes.get('research-demo-details'));
    const rendered = detailText.join(' ');
    assert.match(rendered, /BLUE OBSERVATION/);
    assert.match(rendered, /Validation/);
    assert.match(rendered, /Controller authorization/);
    assert.match(rendered, /Role-visible evidence/);
    assert.match(rendered, /blue_observation/);
  } finally {
    global.document = previousDocument;
  }
});

test('invalid visibility scope and inconsistent metric denominator are rejected', () => {
  const wrongRole = structuredClone(validArtifact);
  wrongRole.records[0].evidence[0].source = 'blue_observation';
  assert.throws(() => validateArtifact(wrongRole), /outside its role-specific observation/);
  const wrongMetric = structuredClone(validArtifact);
  wrongMetric.metrics[0].denominator = 0;
  assert.throws(() => validateArtifact(wrongMetric), /invalid metric or denominator/);
});

test('metric identifiers must be unique and recorded steps must be in range', () => {
  const duplicateMetric = structuredClone(validArtifact);
  duplicateMetric.metrics[1].id = duplicateMetric.metrics[0].id;
  assert.throws(() => validateArtifact(duplicateMetric), /invalid metric or denominator/);

  const outOfRangeStep = structuredClone(validArtifact);
  outOfRangeStep.records[0].step = outOfRangeStep.provenance.recorded_steps;
  assert.throws(() => validateArtifact(outOfRangeStep), /invalid action timeline entry/);

  const unknownRootField = structuredClone(validArtifact);
  unknownRootField.state_changes = [];
  assert.throws(() => validateArtifact(unknownRootField), /unsupported type or schema version/);
});

test('response body is capped while streaming even when Content-Length is missing or false', async () => {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(MAX_ARTIFACT_BYTES + 1));
      controller.close();
    }
  });
  const response = new Response(body, { headers: { 'content-length': '1' } });
  await assert.rejects(() => readBoundedResponseText(response), /1 MB size limit/);
});

test('bounded stream accepts valid text and rejects responses without a stream', async () => {
  const expected = '{"ok":true}';
  const response = new Response(expected);
  assert.equal(await readBoundedResponseText(response), expected);
  await assert.rejects(
    () => readBoundedResponseText({ headers: new Headers(), body: null }),
    /bounded streaming/
  );
});
