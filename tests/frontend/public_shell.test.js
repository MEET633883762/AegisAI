'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..', '..');
const frontend = path.join(root, 'frontend');
const read = name => fs.readFileSync(path.join(frontend, name), 'utf8');

test('landing page exposes the read-only research demo and navigation', () => {
  const html = read('index.html');
  assert.match(html, /<html lang="en">/);
  assert.match(html, /<a class="skip-link" href="#main">/);
  assert.match(html, /href="dashboard\.html"/);
  assert.match(html, /id="research"/);
  assert.match(html, /id="boundaries"/);
  assert.match(html, /precomputed|synthetic/i);
  assert.match(html, /No public simulation runs, uploads, or user-submitted targets/);
  assert.match(html, /does not execute simulations or contact websites/);
  assert.ok(fs.existsSync(path.join(frontend, 'landing.css')));
});

test('dashboard destination preserves assessment import and labels its hardcoded data', () => {
  const html = read('dashboard.html');
  assert.match(html, /href="index\.html"/);
  assert.match(html, /id="assessment-file"/);
  assert.match(html, /id="assessment-results"/);
  assert.match(html, /src="app\.js"/);
  assert.match(html, /src="website_assessment\.js"/);
  assert.match(html, /Earlier illustrative dashboard example \(not verified research results\)/);
  assert.match(html, /Interactive Red \/ Blue Episode/);
  assert.match(html, /four response headers only/);
  assert.match(html, /href="data\/public_demo_episode\.json" download="aegisai-synthetic-episode-v1\.json"/);
});

function makeReport(profile, findings = []) {
  const headers = [
    'Content-Security-Policy', 'X-Content-Type-Options',
    'Referrer-Policy', 'Permissions-Policy'
  ];
  return {
    schema_version: '1.0',
    assessment_type: 'http_security_header_check',
    checked_at_utc: '2026-01-01T00:00:00Z',
    status: findings.length ? 'findings' : 'passed',
    ok: findings.length === 0,
    url: 'http://127.0.0.1:8765/',
    http_status: 200,
    profile,
    checked_headers: headers,
    header_results: headers.map(header => ({
      header, expected_value: 'expected', observed_value: null, present: profile === 'hardened'
    })),
    missing_or_incorrect_headers: findings.map(item => item.id),
    finding_count: findings.length,
    findings,
    limitations: ['Checks configured response headers only.']
  };
}

function makeDashboardHarness() {
  const nodes = new Map();
  let fetchHandler = async () => { throw new Error('Unexpected fetch'); };
  const getNode = id => {
    if (!nodes.has(id)) nodes.set(id, {
      innerHTML: '', textContent: '', files: [], listeners: {},
      addEventListener(type, handler) { this.listeners[type] = handler; },
      replaceChildren() { this.innerHTML = ''; }
    });
    return nodes.get(id);
  };
  class MockFileReader {
    readAsText(file) {
      this.result = file.content;
      queueMicrotask(() => this.onload());
    }
  }
  const sandbox = {
    document: { getElementById: getNode },
    FileReader: MockFileReader,
    Promise, Set, String, Error, JSON, Math,
    fetch: (...args) => fetchHandler(...args)
  };
  vm.runInNewContext(read('website_assessment.js'), sandbox, { filename: 'website_assessment.js' });
  return {
    input: getNode('assessment-file'), status: getNode('assessment-status'),
    results: getNode('assessment-results'), sampleButton: getNode('load-assessment-samples'),
    setFetch(handler) { fetchHandler = handler; }
  };
}

const finding = overrides => ({
  id: 'missing_content_security_policy', severity: 'medium',
  title: 'Missing CSP', description: 'Policy missing.', evidence: 'Not returned.',
  remediation: 'Set a policy.', ...overrides
});
const file = (name, report) => ({ name, content: JSON.stringify(report), size: JSON.stringify(report).length });

test('assessment import compares baseline and hardened reports', async () => {
  const ui = makeDashboardHarness();
  ui.input.files = [
    file('baseline.json', makeReport('baseline', [finding()])),
    file('hardened.json', makeReport('hardened'))
  ];
  await ui.input.listeners.change();
  assert.match(ui.status.textContent, /2 report\(s\) loaded/);
  assert.match(ui.results.innerHTML, /1 finding\(s\) resolved/);
  assert.match(ui.results.innerHTML, /Missing CSP/);
});

test('malformed assessment JSON fails with a clear status and no report rendering', async () => {
  const ui = makeDashboardHarness();
  ui.input.files = [{ name: 'bad.json', content: '{oops', size: 5 }];
  await ui.input.listeners.change();
  assert.match(ui.status.textContent, /Unexpected token|JSON/);
  assert.equal(ui.results.innerHTML, '');
});

test('untrusted report strings are rendered as text, not executable markup', async () => {
  const ui = makeDashboardHarness();
  const hostile = '<img src=x onerror=alert(1)>';
  ui.input.files = [file('baseline.json', makeReport('baseline', [finding({ title: hostile })]))];
  await ui.input.listeners.change();
  assert.match(ui.results.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(ui.results.innerHTML, /<img src=x/);
});

test('unsupported report profile is rejected without leaving stale output', async () => {
  const ui = makeDashboardHarness();
  ui.input.files = [file('valid.json', makeReport('baseline'))];
  await ui.input.listeners.change();
  assert.notEqual(ui.results.innerHTML, '');
  ui.input.files = [file('invalid.json', { ...makeReport('external'), profile: 'external' })];
  await ui.input.listeners.change();
  assert.match(ui.status.textContent, /not a supported local header assessment/);
  assert.equal(ui.results.innerHTML, '');
});

test('report import rejects oversized files and nonnumeric finding counts', async () => {
  const ui = makeDashboardHarness();
  ui.input.files = [{ name: 'large.json', size: 1024 * 1024 + 1, content: '{}' }];
  await ui.input.listeners.change();
  assert.match(ui.status.textContent, /maximum 1 MB/);
  assert.equal(ui.results.innerHTML, '');

  const badCount = { ...makeReport('baseline'), finding_count: '<img src=x onerror=alert(1)>' };
  ui.input.files = [file('bad-count.json', badCount)];
  await ui.input.listeners.change();
  assert.match(ui.status.textContent, /not a supported local header assessment/);
  assert.equal(ui.results.innerHTML, '');
});

test('published baseline and hardened files load from fixed same-origin paths and compare', async () => {
  const ui = makeDashboardHarness();
  const publicReports = Object.fromEntries(['baseline', 'hardened'].map(profile => [
    `data/public_demo_assessment_${profile}.json`,
    JSON.parse(fs.readFileSync(path.join(root, 'frontend', 'data', `public_demo_assessment_${profile}.json`), 'utf8'))
  ]));
  const requested = [];
  ui.setFetch(async (url, options) => {
    requested.push([url, options.credentials]);
    return new Response(JSON.stringify(publicReports[url]), { headers: { 'content-type': 'application/json' } });
  });
  await ui.sampleButton.listeners.click();
  assert.equal(requested.length, 2);
  assert.ok(requested.every(([url]) => Object.hasOwn(publicReports, url)));
  assert.ok(requested.every(([, credentials]) => credentials === 'same-origin'));
  assert.match(ui.status.textContent, /2 published sample reports loaded/);
  assert.match(ui.results.innerHTML, /4 finding\(s\) resolved/);
  assert.match(ui.results.innerHTML, /baseline profile/);
  assert.match(ui.results.innerHTML, /hardened profile/);
});

test('published sample load rejects malformed or oversized declared content safely', async () => {
  const ui = makeDashboardHarness();
  ui.setFetch(async () => ({
    ok: true,
    headers: { get: () => String(1024 * 1024 + 1) },
    json: async () => ({})
  }));
  await ui.sampleButton.listeners.click();
  assert.match(ui.status.textContent, /exceeds the 1 MB size limit/);
  assert.equal(ui.results.innerHTML, '');
});
