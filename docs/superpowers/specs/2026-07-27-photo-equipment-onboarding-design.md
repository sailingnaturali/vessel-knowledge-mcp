# Photo → Equipment Onboarding — Design

- **Date:** 2026-07-27
- **Status:** Approved shape, spec under review
- **Build timing:** Spec now; **implement on-camera** (vessel-knowledge YouTube live-coding session). Nothing is built ahead of the session.
- **Home:** `vessel-knowledge-mcp` (orchestration). Touches `signalk-equipment-registry` (write path) and a new OSS `manual-index` repo.

## Problem

Adding a device to the vessel equipment registry today means hand-editing
`equipment-registry.json` on the Pi. The registry is not a discovery tool and
never will be — an NMEA 0183 device (e.g. the Standard Horizon GX2410GPS feeding
AIS over serial) emits no N2K product-info, so `consumeDiscovery` can't identify
it. The friendly path should be: **take a photo of the device/box, and the agent
pulls the identity, registers it, binds its live data paths, and finds its
manual.**

## Goals

- A person hands Poseidon a photo of a device (or its box label); the agent
  extracts identity, writes an equipment profile to the registry, and offers to
  bind live SignalK sources to it.
- After registration, the agent resolves the device's **manual**: auto-process
  if the model is already verified globally; otherwise a human-in-the-loop gate
  confirms the right manual before processing.
- Verified manuals are a **globally shared** resource (network effect: the first
  owner to confirm a model verifies it for everyone).

## Non-goals (YAGNI)

- **No client-side OCR in v1.** The agent's own vision does extraction. Client
  OCR is a later optimization for the vessel-knowledge app.
- **No self-serve web/PWA capture in v1.** v1 is agent-mediated (hand the photo
  to Poseidon). The app is a later thin client over the same tools.
- **No central hosting of manual PDFs.** The shared index stores *pointers*, not
  content (see §4). Copyright weight stays zero.
- **No image input to MCP tools.** The agent extracts fields from the photo
  natively and passes a structured profile to the tools.

## Two entry points, one write path

The photo flow is one way to **fill** an equipment profile. Because
`register_equipment` takes a structured profile (never an image), a second actor
falls out for free:

- **Owner, from a photo** — agent vision fills one profile from a device/box.
- **Builder, from known specs** — e.g. if Vaan ships our stack, they provision a
  boat's whole equipment list from the SD25 config sheet: many profiles, filled
  from structured data, no camera. This is the *common* provisioning case — you
  don't photograph systems already spec'd on a new build.

Both funnel into the same `register_equipment` → `setResource` path.
`register_equipment` therefore accepts **one profile or a batch** (builder
provisioning is the same tool called over a spec sheet; partial-failure
reporting so one bad row doesn't sink the batch). Manual resolution (§2) still
runs per instance regardless of how the profile was filled.

## The arc

```
photo ──(agent vision) ─┐
spec sheet ─(builder) ──┴▶ profile(s) ──▶ register_equipment ──▶ registry (Pi, via setResource)
                                              │                       └─▶ optional: bind live SignalK sources
                                              └─▶ resolve_manual(model, upc)
                                                     ├─ verified?    → fetch from mfr URL → process into vessel-knowledge vault
                                                     └─ first-ever?  → agent proposes candidate URL(s)
                                                                       → "Is this the right manual for your <model>?"
                                                                       → yes → process locally + record CANDIDATE
                                                                               → (later) reviewed/tested → PR → shared repo
```

## Components

Three well-bounded units; the agent orchestrates them.

### 1. `register_equipment(profile)` — MCP tool (vessel-knowledge-mcp)

Validates and persists an equipment profile, then optionally binds live data
paths. **Takes a structured profile, never an image** — v1 the agent fills it
from vision, later the app fills it from client OCR. Same tool.

Profile shape (extends the existing `equipment-registry.json` entry format with
provenance fields):

```json
{
  "instance_id": "communication.ais",
  "equipment_id": "standard-horizon-gx2410gps",
  "manufacturer": "Standard Horizon",
  "model": "GX2410GPS",
  "serial": "6E520491",
  "instance": "gx2410",
  "category": "communication",
  "source": "declared",
  "upc": "788026183036",
  "ean": "4909959183030",
  "paths": [
    { "path": "communication.ais", "measurement": "aisTargets" }
  ],
  "manual": { "key": "upc:788026183036", "status": "candidate" }
}
```

- `upc`/`ean`/`manual` are new optional fields; declared entries still win
  identity over discovered ones.
- **Path binding (agent-assisted):** after write, the tool can report live
  SignalK sources that look unbound (e.g. `gx2410-nmea0183.AI` publishing AIS
  targets) and the agent offers to attach them to this instance. This is the
  direct fix to "why didn't the registry pick up my VHF" — binding is explicit,
  not magic.

Writes go through the registry plugin's new `setResource` handler (§3), so the
plugin stays the single owner of the JSON file.

### 2. `resolve_manual(model, upc)` — MCP tool (vessel-knowledge-mcp)

Looks up the **global manual index** (§4), keyed by UPC first, then
manufacturer+model. Returns one of:

- `verified` → `{ manualUrl, sha256 }`. Agent fetches from the manufacturer URL
  and processes into the vessel-knowledge vault.
- `needs_approval` → the agent web-searches the manufacturer site for candidate
  manual URL(s), presents them, and asks the human gate: *"Is this the right
  manual for your `<model>`?"* On confirmation the agent processes the PDF
  locally and records a **candidate** entry (§4) for later moderation.

### 3. Manual processing → vessel-knowledge vault

Fetch the confirmed manual from the manufacturer URL, ingest into
`vessel-knowledge-vault` via the existing `vault-search` pipeline. Reuses what's
already built; no new retrieval infrastructure. After ingest, the agent can
answer questions and `explain_notification` against the manual.

## 3. Registry write path — plugin `setResource` (decision A)

The registry plugin implements only `listResources` today (read-only). It gains
a **`setResource`** handler so writes flow through the SignalK v2 resources API.

- **Single owner:** the plugin both serves and mutates its own JSON file — no
  two-writer race between the plugin and an external file-writer.
- **Auth:** writes need a token; the `poseidon` user JWT (expires 2027-07-11)
  already in `~/.poseidon/.env` covers it. Anonymous read is unchanged.
- **Dual use:** the same write endpoint backs both entry points — one-off photo
  adds *and* **builder provisioning** (a yard shipping our stack loads a whole
  vessel's equipment from its spec sheet in one batch; see "Two entry points").

Rejected: MCP writes the JSON on the Pi directly (two writers → races + forces a
plugin reload). Rejected: MCP calls the resources HTTP API from the Mac (fine,
but the endpoint has to exist in the plugin regardless — A is that endpoint).

## 4. Global manual index — OSS, pointers not PDFs

A new **OSS repo** (`@sailingnaturali/manual-index`, MIT) shipping a JSON
artifact, consumed exactly like `station-corrections` (vendored copy + drift
test; non-JS consumers read `data/index.json` directly).

**Stores verified pointers, not manual content.** A global library that
redistributes copyrighted manual PDFs is the legal problem that keeps
`pilotbook-vault` private. Instead each entry records where the manufacturer's
official manual lives; every vessel fetches and processes it **locally** into its
own vault. The shared thing is the *verification*, which carries no copyright
weight.

Entry shape:

```json
{
  "key": "upc:788026183036",
  "manufacturer": "Standard Horizon",
  "model": "GX2410GPS",
  "manualUrl": "https://www.standardhorizon.com/.../GX2410GPS_OM_EN.pdf",
  "sha256": "<hash of the fetched PDF, pins the exact document>",
  "status": "verified",
  "verifiedBy": "<opaque vessel/owner id>",
  "verifiedDate": "2026-07-14"
}
```

**Moderation pipeline (the network effect, done safely):**

1. A boat's human-gate confirmation produces a **candidate** entry, recorded
   locally and queued for contribution. Until merged it is that vessel's local
   verified entry only.
2. Candidates are **reviewed and tested** (URL resolves, hash matches, it really
   is that model's manual), then merged into the OSS repo by PR.
3. On merge + release, the entry ships in the next `index.json` version and is
   `verified` for every stack user — future owners of that model skip the gate.

For v1 on-camera there is effectively one boat, so the "global store" starts as
this repo seeded from that boat's confirmations — structured to become the
multi-writer shared library, with no premature multi-tenant service.

## Data flow summary

1. Photo → agent vision → `{manufacturer, model, serial, upc, ean, category}`.
2. Agent proposes `instance_id`/`paths`; `register_equipment` writes via
   `setResource`; agent offers to bind matching live SignalK sources.
3. `resolve_manual` → verified (auto-process) or needs_approval (human gate →
   process locally + record candidate).
4. Candidate → review/test → PR → shared `manual-index` → verified for all.

## Error handling

- **Ambiguous/low-confidence extraction:** agent shows the parsed fields and
  asks for confirmation/correction before writing. Never writes silently.
- **No barcode / partial label:** vision fills what it can; missing fields
  (e.g. serial) are left null and can be filled later. UPC/EAN barcodes are the
  reliable spine when present.
- **`resolve_manual` finds no candidate:** register still succeeds; manual is
  left unresolved and can be retried.
- **Manual URL dead / hash mismatch on a "verified" entry:** treat as
  needs_approval, flag the stale entry for the moderation repo.
- **Registry write rejected (401/expired JWT):** surface the token issue per the
  known SignalK access model; do not fall back to direct file writes.

## Testing

Per project policy, TDD the plugin bug/behavior work — failing test first.

- **`setResource` (plugin):** failing test — POST a resource, then `listResources`
  returns it; malformed payload is rejected; anonymous write is refused, JWT
  write accepted.
- **`register_equipment`:** profile round-trips through the registry; validation
  rejects missing required fields (`instance_id`, `category`); provenance fields
  persist.
- **`resolve_manual`:** verified key returns `{manualUrl, sha256}`; miss returns
  `needs_approval`; UPC match preferred over model match.
- **`manual-index`:** JSON-schema validation of entries; vendored-copy drift test
  (mirrors `station-corrections`).

## Phasing

- **v1 (on-camera):** plugin `setResource`; `register_equipment` + live-source
  binding; `resolve_manual` + human-gate flow; manual processing into the vault;
  `manual-index` repo seeded from this boat. Extraction = agent vision.
- **Later:** client-side OCR; self-serve vessel-knowledge app as a thin client
  over the same tools; multi-writer moderation service for `manual-index`.

## Open items

- **Instance-id / path convention for AIS-capable VHF** — confirm the canonical
  SignalK path(s) a GX2410GPS-class device owns (`communication.ais` vs a
  per-source binding) when live source binding lands.
- **Candidate-contribution transport** — how a boat's candidate reaches the OSS
  repo (PR bot vs manual PR). Deferrable; v1 can hand-PR.
