'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawn } = require('node:child_process');
const net = require('node:net');
const test = require('node:test');

const root = path.resolve(__dirname, '..', '..');
const frontend = path.join(root, 'frontend');
const build = path.join(frontend, '.vite-build');
const read = (directory, name) => fs.readFileSync(path.join(directory, name), 'utf8');
const expectedAssets = [
  '_headers', 'index.html', 'dashboard.html', 'privacy.html', 'assets/app.css', 'assets/main.js',
  'assets/public_demo_episode.json', 'assets/public_demo_assessment_baseline.json',
  'assets/public_demo_assessment_hardened.json'
].sort();

async function unusedPort() {
  const socket = net.createServer();
  await new Promise((resolve, reject) => {
    socket.once('error', reject);
    socket.listen(0, '127.0.0.1', resolve);
  });
  const port = socket.address().port;
  await new Promise((resolve, reject) => socket.close((error) => error ? reject(error) : resolve()));
  return port;
}

test('Vite serves the landing page and local dashboard as separate working entries', async () => {
  const packageJson = JSON.parse(read(frontend, 'package.json'));
  assert.match(packageJson.scripts['dev:dashboard'], /--open \/local-dashboard\.html/);

  const port = await unusedPort();
  const origin = `http://127.0.0.1:${port}`;
  const vite = spawn(process.execPath, [
    path.join(frontend, 'node_modules', 'vite', 'bin', 'vite.js'),
    '--host', '127.0.0.1', '--port', String(port), '--strictPort'
  ], { cwd: frontend, stdio: ['ignore', 'pipe', 'pipe'] });
  let output = '';
  vite.stdout.setEncoding('utf8').on('data', (chunk) => { output += chunk; });
  vite.stderr.setEncoding('utf8').on('data', (chunk) => { output += chunk; });

  try {
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt += 1) {
      if (vite.exitCode !== null) break;
      try {
        const response = await fetch(`${origin}/`);
        if (response.ok) { ready = true; break; }
      } catch { /* Vite is still starting. */ }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert.ok(ready, `Vite did not become ready. Output:\n${output}`);

    const landing = await fetch(`${origin}/`);
    const landingHtml = await landing.text();
    assert.equal(landing.status, 200);
    assert.match(landingHtml, /id="app-root"/);
    assert.match(landingHtml, /src="\.\/src\/main\.tsx"/);
    assert.doesNotMatch(landingHtml, /local-dashboard-root/);

    const dashboard = await fetch(`${origin}/local-dashboard.html`);
    const dashboardHtml = await dashboard.text();
    assert.equal(dashboard.status, 200);
    assert.match(dashboardHtml, /id="local-dashboard-root"/);
    assert.match(dashboardHtml, /src="\.\/src\/localDashboard\.tsx"/);
    assert.doesNotMatch(dashboardHtml, /id="app-root"/);

    const refreshedDashboard = await fetch(`${origin}/local-dashboard.html`);
    assert.equal(refreshedDashboard.status, 200, 'direct URL must continue to work on refresh');
    assert.match(await refreshedDashboard.text(), /local-dashboard-root/);

    for (const asset of ['/src/main.tsx', '/src/localDashboard.tsx', '/src/localDashboard/localDashboard.css?direct']) {
      const response = await fetch(`${origin}${asset}`);
      assert.equal(response.status, 200, `Vite asset did not resolve: ${asset}`);
    }
    assert.match(output, /local-dashboard\.html/);
  } finally {
    vite.kill();
  }
});

test('CSP permits only built same-origin script, styles and report loading', () => {
  const headers = read(frontend, '_headers');
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

  const pages = ['index.html', 'dashboard.html', 'privacy.html'].map((name) => read(build, name)).join('\n');
  assert.doesNotMatch(pages, /<script(?![^>]*\bsrc=)/i);
  assert.doesNotMatch(pages, /<style\b/i);
  for (const asset of ['assets/main.js', 'assets/app.css', ...expectedAssets.filter((name) => name.endsWith('.json'))]) {
    assert.ok(fs.existsSync(path.join(build, asset)), `missing built same-origin asset ${asset}`);
  }
  assert.match(pages, /assets\/main\.js/);
  assert.match(pages, /assets\/app\.css/);
  assert.equal(fs.existsSync(path.join(build, 'local-dashboard.html')), false, 'local-only dashboard must not enter the public Vite build');
  assert.doesNotMatch(read(build, 'assets/main.js'), /127\.0\.0\.1:8766|localDashboard|local-dashboard/i);
  const outputText = expectedAssets.map((name) => read(name === '_headers' ? frontend : build, name)).join('\n');
  assert.doesNotMatch(outputText, /C:\\AegisAI|demo_site_assessment_(baseline|hardened)\.json/i);
});

test('public assessment copies remain sanitized and retain their narrow scope', () => {
  for (const profile of ['baseline', 'hardened']) {
    const data = JSON.parse(read(frontend, `data/public_demo_assessment_${profile}.json`));
    assert.equal(data.profile, profile);
    assert.equal(data.publication.synthetic, true);
    assert.equal(data.publication.precomputed, true);
    assert.equal(data.publication.public_execution, false);
    assert.equal(Object.hasOwn(data, 'artifact'), false);
    assert.equal(data.checked_headers.length, 4);
    assert.doesNotMatch(JSON.stringify(data), /[A-Z]:\\\\|Users\\|\/home\//i);
  }
});

test('static publisher emits exactly the allowlist and excludes repository evidence and source', () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'aegisai-static-release-'));
  const output = path.join(temporaryRoot, 'site');
  try {
    execFileSync('python', [path.join(root, 'scripts', 'build_static_site.py'), '--output', output], { cwd: root });
    const actualAssets = [];
    const visit = (directory) => {
      for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
        const full = path.join(directory, entry.name);
        if (entry.isDirectory()) visit(full);
        else actualAssets.push(path.relative(output, full).split(path.sep).join('/'));
      }
    };
    visit(output);
    assert.deepEqual(actualAssets.sort(), expectedAssets);
    assert.equal(fs.existsSync(path.join(output, 'local-dashboard.html')), false);
    for (const excluded of ['server.py', 'results', '.git', 'requirements.txt', 'README.md', 'tests', 'original-reports']) {
      assert.equal(fs.existsSync(path.join(output, excluded)), false);
    }
    const contents = actualAssets.map((asset) => fs.readFileSync(path.join(output, asset), 'utf8')).join('\n');
    assert.doesNotMatch(contents, /C:\\AegisAI|demo_site_assessment_(baseline|hardened)\.json/i);
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
});
