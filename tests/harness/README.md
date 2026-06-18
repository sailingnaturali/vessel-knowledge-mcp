# Discovery integration harness

Feeds a fake N2K device through a real local SignalK to validate `vessel-knowledge
discover` end-to-end (sources-tree field names, $source format, the whole pipeline).

## What runs
- `virtual_n2k_device.js` — emits Actisense frames (60928 + 126996 + 127489) on stdout.
- A throwaway local `signalk-server` (from the sibling `signalk-server` repo) configured
  with a pipedProvider: `providers/execute` (runs the emitter) -> `providers/canboatjs`
  -> `providers/n2k-signalk`, `allow_readonly` on, on an ephemeral port.
- `vessel-knowledge discover --signalk http://localhost:<port>` then asserts the proposal.

## Run
    cd vessel-knowledge-mcp
    uv run pytest tests/test_discover_integration.py -m integration -v

Requires Node + the sibling `signalk-server` repo checked out with `node_modules` installed.
The emitter is invoked with `NODE_PATH=<signalk-server>/node_modules` so it can resolve
`@canboat/canboatjs` without a local install in this repo.
Never point this at the boat Pi — it spins its own local server in a temp dir.
