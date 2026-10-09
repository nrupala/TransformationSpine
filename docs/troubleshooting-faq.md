# TransformationSpine — Troubleshooting & FAQ

## Log matrix (G10 operability)

| Service | Log file | Contents | Rotation |
|---|---|---|---|
| spine API | `logs/spine.log` (repo-relative, or `$env:SPINE_LOG_DIR`) | JSON-lines: startup, provider registrations, per-request access (`request_id`, `method`, `path`, `status`, `duration_ms`) | 5MB × 5 |
| spine errors | `logs/errors.log` | ERROR+ only (mirror of spine.log errors) | 5MB × 5 |
| port ledger (vendored) | `~/.portledger/logs/portledger.log` + `errors.log` | port allocations/conflicts (see PortLedger docs) | 2MB × 3 |
| CTST ledger | `ledger/` (append-only JSONL) | hash-chained transformation records (audit, not a log) | never |

Log line shape: `{"ts":"...Z","level":"info|warning|error","service":"spine","version":"0.2.0","msg":"...",...ctx}`.
Every API response carries `X-Request-Id`; find its full access line:
```bash
Select-String -Path logs\spine.log -Pattern "<request_id>"
```
Serve with the ledger (no hard-coded port):
```bash
python spine_cli.py --port 0        # allocates + advertises via spine.portledger
```

## Common errors

### `conflicting subparser: provider` (fixed in v0.2.0)
`spine_cli.py` registered the `provider` subparser twice. Fixed; upgrade or
`git pull`. Symptom survived: every CLI invocation crashed at argparse.

### `spine: error: the following arguments are required: command`
Bare invocation is the **serve** mode (v0.2.0+): run `python spine_cli.py
--port 0` with no subcommand to start the API. Use `--no-server` for CLI-only
commands.

### `Could not connect to llama.cpp on :8830`
The local engine stack is down. Start it via the llama-control supervisor:
```powershell
pwsh C:\Users\<you>\.config\opencode\local-engines\llama-control.ps1 -Start
```
The watchdog (`-Watchdog`, auto-spawned by the control server) heals
mesh/orchestrator/embeddings/router within ~10s if they die.

### Port 8000 already in use (or any port conflict)
The spine now allocates through PortLedger: `--port 0` picks the next free
port and advertises it in `~/.portledger/ports.current.json`. Connectors
should read the map, not hard-code 8000. See `portledger --who-used 8000`
to find the occupant.

### `GET /api/v1/status` shows `providers: []`
The llama.cpp handshake failed at startup (see `logs/spine.log` for the
WARN/ERROR line with the error). Check the endpoint env:
`SPINE_LLAMA_ENDPOINT` (default `http://127.0.0.1:8830`) and that the mesh
door (`:8830`) answers `/live`.

## When to ask for help
Attach: the `X-Request-Id` from the failing response, the matching access
line from `logs/spine.log`, and the last 20 lines of `logs/errors.log`.
