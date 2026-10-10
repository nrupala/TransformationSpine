# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Browser UI — the spine served to humans.

A single self-contained page (no build step, no external assets)
served at ``GET /ui`` and at the site root ``GET /``. Written for a
first-time visitor: plain words on the surface, one obvious action,
the engineering detail one layer down. It talks to the same REST
API programs use: status, transform, ledger verify, connectors.
"""

from __future__ import annotations

UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TransformationSpine</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 880px;
         padding: 0 1rem; background: #0b1020; color: #e6e9f5; line-height: 1.55; }
  h1 { font-size: 1.6rem; margin-bottom: .25rem; }
  h2 { font-size: 1.15rem; margin-top: 0; }
  .lead { font-size: 1.08rem; color: #c9d2f2; }
  .card { background: #151b33; border: 1px solid #2a3560; border-radius: 10px;
          padding: 1.1rem 1.25rem; margin: 1.1rem 0; }
  label { display: block; margin: .6rem 0 .25rem; font-weight: 600; }
  textarea, input, select { width: 100%; padding: .55rem; border-radius: 6px;
    border: 1px solid #2a3560; background: #0b1020; color: #e6e9f5; font-size: 1rem; }
  button { margin-top: .8rem; padding: .6rem 1.2rem; border: 0; border-radius: 6px;
           background: #4f7cff; color: white; cursor: pointer; font-weight: 600;
           font-size: 1rem; }
  button.secondary { background: #22305c; }
  .answer { background: #0b1020; border: 1px solid #2a3560; border-radius: 6px;
            padding: .8rem 1rem; margin-top: .8rem; font-size: 1.05rem;
            white-space: pre-wrap; word-break: break-word; }
  .verdict { margin-top: .7rem; font-weight: 700; }
  .ok { color: #7be495; } .bad { color: #ff9a9a; }
  ul.checks { margin: .4rem 0 0; padding-left: 1.2rem; }
  pre { white-space: pre-wrap; word-break: break-word; background: #0b1020;
        padding: .75rem; border-radius: 6px; max-height: 320px; overflow: auto; }
  a { color: #8fb0ff; } .row { display: flex; gap: 1rem; } .row > div { flex: 1; }
  details { margin-top: .8rem; } summary { cursor: pointer; color: #aab; }
  .muted { color: #aab; font-size: .95rem; }
</style>
</head>
<body>
<h1>TransformationSpine</h1>
<p class="lead">Ask in plain words. The spine has an AI answer your request,
checks the answer before accepting it, and writes the result into a record
that shows if anything in it is ever changed.</p>

<div class="card">
  <h2>Try it</h2>
  <label for="intent">What would you like it to do?</label>
  <textarea id="intent" rows="3">In one short sentence, explain what a
  tamper-evident record is.</textarea>
  <details>
    <summary>Options (provider and scope)</summary>
    <div class="row">
      <div><label for="provider">Provider</label>
      <input id="provider" value="llama.cpp"></div>
      <div><label for="scope">Scope</label>
      <select id="scope"><option>SESSION</option><option>PROJECT</option>
      <option>USER</option><option>SYSTEM</option></select></div>
    </div>
  </details>
  <button onclick="runTransform()">Run it</button>
  <div id="answer" class="answer" style="display:none"></div>
  <div id="verdict" class="verdict"></div>
  <ul id="checks" class="checks"></ul>
  <details id="rawwrap" style="display:none">
    <summary>The full result, as data</summary>
    <pre id="result"></pre>
  </details>
</div>

<div class="card">
  <h2>Check the record</h2>
  <p class="muted">Every run — accepted or not — is written into a
  tamper-evident record. Checking it re-reads the whole chain and
  confirms nothing was altered after the fact.</p>
  <button class="secondary" onclick="verifyLedger()">Check the record now</button>
  <p id="verify" class="verdict"></p>
</div>

<div class="card">
  <h2>What is this?</h2>
  <p>TransformationSpine is the layer that sits between you and AI
  models. It keeps one shared memory of the work, sends each request
  to a suitable model, judges the answer against plain checks, and
  keeps the tamper-evident record you can verify above.</p>
  <p>Programs and AI agents connect to the same spine:
  an <a href="/.well-known/agent-card.json">agent card</a> describes it
  for other agents, MCP tools at <code>POST /mcp</code>, ACP runs at
  <code>/acp/agents</code>.</p>
  <p><a href="https://github.com/nrupala/TransformationSpine">Source on GitHub</a> ·
  <a href="https://aimlds.org/transformationspine">About the product</a></p>
</div>

<details class="card">
  <summary><b>For developers</b> — status, connectors, endpoints</summary>
  <h2>Status</h2>
  <pre id="status">loading…</pre>
  <button class="secondary" onclick="loadStatus()">Refresh status</button>
  <h2>Connectors</h2>
  <pre id="connectors">loading…</pre>
  <p class="muted">Endpoints: <code>POST /api/v1/transform</code> ·
  <code>GET /api/v1/status</code> · <code>GET /api/v1/ledger/verify</code> ·
  <code>GET /api/v1/telemetry</code> · <code>POST /mcp</code></p>
</details>

<script>
async function j(url, opts) { const r = await fetch(url, opts); return r.json(); }
const CHECK_WORDS = {
  transport_success: 'The AI answered',
  output_present: 'The answer is not empty',
  finished_cleanly: 'The answer finished properly',
};
async function loadStatus() {
  document.getElementById('status').textContent =
    JSON.stringify(await j('/api/v1/status'), null, 2);
}
async function verifyLedger() {
  const el = document.getElementById('verify');
  el.textContent = 'Checking…';
  const v = await j('/api/v1/ledger/verify');
  if (v.valid) {
    el.innerHTML = '<span class="ok">The record checks out</span> — ' +
      v.records + ' entries, none altered.';
  } else {
    el.innerHTML = '<span class="bad">The record does not check out</span> — ' +
      'something in it was altered.';
  }
}
async function runTransform() {
  const intent = document.getElementById('intent').value;
  const provider = document.getElementById('provider').value;
  const scope = document.getElementById('scope').value;
  const answerEl = document.getElementById('answer');
  const verdictEl = document.getElementById('verdict');
  const checksEl = document.getElementById('checks');
  answerEl.style.display = 'block';
  answerEl.textContent = 'Working on it…';
  verdictEl.textContent = ''; checksEl.innerHTML = '';
  const q = new URLSearchParams({intent, provider, scope});
  const out = await j('/api/v1/transform?' + q, {method: 'POST'});
  answerEl.textContent = out.output || '(the AI returned no answer)';
  if (out.committed) {
    verdictEl.innerHTML = '<span class="ok">Accepted</span> — every check passed, ' +
      'and this run is now in the record.';
  } else {
    verdictEl.innerHTML = '<span class="bad">Not accepted</span> — the answer did ' +
      'not pass its checks, so nothing was committed. ' +
      'The attempt is still in the record.';
  }
  for (const c of (out.gates && out.gates.checks) || []) {
    const li = document.createElement('li');
    li.textContent = (c.passed ? '✓ ' : '✗ ') + (CHECK_WORDS[c.name] || c.name);
    checksEl.appendChild(li);
  }
  document.getElementById('result').textContent = JSON.stringify(out, null, 2);
  document.getElementById('rawwrap').style.display = 'block';
  loadStatus();
}
async function loadConnectors() {
  const data = await j('/api/v1/connectors');
  document.getElementById('connectors').textContent =
    data.connectors.map(c => c.name + ' [' + c.source + '] tools: ' +
      c.capabilities.join(', ')).join('\\n') || '(none)';
}
loadStatus(); loadConnectors();
</script>
</body>
</html>
"""
