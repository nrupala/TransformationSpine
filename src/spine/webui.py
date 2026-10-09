# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
"""Browser UI — the spine served to humans.

A single self-contained page (no build step, no external assets)
served at ``GET /ui``. It talks to the same REST API programs use:
status, transform, ledger verify, connectors. Alongside the agent
surfaces (MCP / A2A / ACP) and the program surfaces (REST, CLI), this
completes the serving set: agents, humans, programs.
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
         padding: 0 1rem; background: #0b1020; color: #e6e9f5; }
  h1 { font-size: 1.5rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
  .card { background: #151b33; border: 1px solid #2a3560; border-radius: 10px;
          padding: 1rem 1.25rem; margin: 1rem 0; }
  label { display: block; margin: .6rem 0 .2rem; font-size: .9rem; color: #aab; }
  input, select, textarea { width: 100%; padding: .5rem; border-radius: 6px;
    border: 1px solid #2a3560; background: #0b1020; color: #e6e9f5; }
  button { margin-top: .8rem; padding: .55rem 1.1rem; border: 0; border-radius: 6px;
           background: #4f7cff; color: white; cursor: pointer; font-weight: 600; }
  pre { white-space: pre-wrap; word-break: break-word; background: #0b1020;
        padding: .75rem; border-radius: 6px; max-height: 320px; overflow: auto; }
  a { color: #8fb0ff; } .row { display: flex; gap: 1rem; } .row > div { flex: 1; }
</style>
</head>
<body>
<h1>TransformationSpine</h1>
<p>Provider-neutral transformation spine — gated cycles, scoped context,
tamper-evident ledger. Agent surfaces:
<a href="/.well-known/agent-card.json">A2A agent card</a> ·
MCP at <code>POST /mcp</code> or <code>spine mcp</code> ·
ACP at <code>/acp/agents</code>.</p>

<div class="card">
  <h2>Status</h2>
  <pre id="status">loading…</pre>
  <button onclick="loadStatus()">Refresh</button>
  <button onclick="verifyLedger()">Verify ledger chain</button>
  <pre id="verify"></pre>
</div>

<div class="card">
  <h2>Run a transformation</h2>
  <label for="intent">Intent</label>
  <textarea id="intent" rows="3" placeholder="What should the spine do?"></textarea>
  <div class="row">
    <div><label for="provider">Provider</label>
    <input id="provider" value="llama.cpp"></div>
    <div><label for="scope">Scope</label>
    <select id="scope"><option>SESSION</option><option>PROJECT</option>
    <option>USER</option><option>SYSTEM</option></select></div>
  </div>
  <button onclick="runTransform()">Transform</button>
  <pre id="result"></pre>
</div>

<div class="card">
  <h2>Connectors</h2>
  <pre id="connectors">loading…</pre>
</div>

<script>
async function j(url, opts) { const r = await fetch(url, opts); return r.json(); }
async function loadStatus() {
  document.getElementById('status').textContent =
    JSON.stringify(await j('/api/v1/status'), null, 2);
}
async function verifyLedger() {
  document.getElementById('verify').textContent =
    JSON.stringify(await j('/api/v1/ledger/verify'), null, 2);
}
async function runTransform() {
  const intent = document.getElementById('intent').value;
  const provider = document.getElementById('provider').value;
  const scope = document.getElementById('scope').value;
  const q = new URLSearchParams({intent, provider, scope});
  const out = await j('/api/v1/transform?' + q, {method: 'POST'});
  document.getElementById('result').textContent = JSON.stringify(out, null, 2);
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
