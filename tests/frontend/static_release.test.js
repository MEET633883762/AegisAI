'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const test = require('node:test');

const root = path.resolve(__dirname, '..', '..');
const frontend = path.join(root, 'frontend');
const read = name => fs.readFileSync(path.join(frontend, name), 'utf8');
const expectedAssets = [
  '_headers', 'index.html', 'dashboard.html', 'privacy.html', 'landing.css', 'styles.css',
  'website_assessment.css', 'website_assessment.js', 'research_demo.js', 'app.js',
  'data/public_demo_episode.json', 'data/public_demo_assessment_baseline.json',
  'data/public_demo_assessment_hardened.json'
].sort();

test('Cloudflare header policy allows only local required resources and blocks embedding', () => {
  const headers = read('_headers');
  const csp = headers.match(/Content-Security-Policy: (.+)/)?.[1];
  assert.ok(csp);
  for (const directive of [
    "default-src 'self'", "script-src 'self'", "style-src 'self'", "connect-src 'self'",
    "base-uri 'none'", "object-src 'none'", "frame-ancestors 'none'", "form-action 'none'"
  ]) assert.ok(csp.includes(directive), `missing CSP directive ${directive}`);
  assert.match(headers, /X-Content-Type-Options: nosniff/);
  assert.match(headers, /Referrer-Policy: strict-origin-when-cross-origin/);
  assert.match(headers, /Permissions-Policy:/);
  assert.match(headers, /Strict-Transport-Security: max-age=31536000/);

  const pages = ['index.html', 'dashboard.html', 'privacy.html'].map(read).join('\n');
  assert.doesNotMatch(pages, /<script(?![^>]*\bsrc=)/i);
  assert.doesNotMatch(pages, /<style\b/i);
  const scripts = [...pages.matchAll(/<script[^>]+src="([^"]+)"/g)].map(match => match[1]);
  const styles = [...pages.matchAll(/<link[^>]+href="([^"]+)"[^>]*>/g)]
    .map(match => match[1]).filter(href => href.endsWith('.css'));
  for (const asset of [...scripts, ...styles]) {
    assert.ok(!asset.startsWith('http:'), `insecure external asset ${asset}`);
    assert.ok(fs.existsSync(path.join(frontend, asset)), `missing same-origin asset ${asset}`);
  }
  assert.match(read('research_demo.js'), /fetch\('data\/public_demo_episode\.json'/);
  assert.match(read('dashboard.html'), /data\/public_demo_episode\.json" download=/);
  assert.match(read('dashboard.html'), /data\/public_demo_assessment_baseline\.json" download=/);
  assert.match(read('dashboard.html'), /data\/public_demo_assessment_hardened\.json" download=/);
  assert.match(read('dashboard.html'), /href="privacy\.html"/);
});

test('public assessment copies carry labels and contain no local artifact path', () => {
  for (const profile of ['baseline', 'hardened']) {
    const data = JSON.parse(read(`data/public_demo_assessment_${profile}.json`));
    assert.equal(data.profile, profile);
    assert.equal(data.publication.synthetic, true);
    assert.equal(data.publication.precomputed, true);
    assert.equal(data.publication.public_execution, false);
    assert.equal(Object.hasOwn(data, 'artifact'), false);
    assert.equal(data.checked_headers.length, 4);
    assert.doesNotMatch(JSON.stringify(data), /C:\\AegisAI|Users\\|\/home\//i);
  }
});

test('static package contains exactly the allowlist and excludes repository evidence and source', () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'aegisai-static-release-'));
  const output = path.join(temporaryRoot, 'site');
  try {
    execFileSync('python', [path.join(root, 'scripts', 'build_static_site.py'), '--output', output], { cwd: root });
    const actualAssets = [];
    const visit = directory => {
      for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
        const full = path.join(directory, entry.name);
        if (entry.isDirectory()) visit(full);
        else actualAssets.push(path.relative(output, full).split(path.sep).join('/'));
      }
    };
    visit(output);
    assert.deepEqual(actualAssets.sort(), expectedAssets);
    for (const excluded of ['server.py', 'results', '.git', 'requirements.txt', 'README.md', 'tests']) {
      assert.equal(fs.existsSync(path.join(output, excluded)), false);
    }
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
});
