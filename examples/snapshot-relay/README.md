# Snapshot Relay

A small Elysium-built service that captures macOS screenshots and serves
them over a local HTTP API so other tools (Claude Code agents, automated
test harnesses, etc.) can pick them up.

macOS gates `screencapture` behind a per-bundle Screen Recording
entitlement. By packaging this script as `SnapshotRelay.app`, the user
grants the permission *once* to that bundle and it survives reboots,
reinstalls, and `maturin develop` cycles.

## Run

    # From the repo root, with .venv ready:
    .venv/bin/python -m examples.snapshot-relay

    # Or, for the permission-grantable bundle:
    open examples/snapshot-relay/SnapshotRelay.app

The first capture will trigger macOS's permission prompt. Once granted
(System Settings → Privacy & Security → Screen Recording → Snapshot
Relay), every subsequent request runs unattended.

## HTTP API

Base URL: `http://127.0.0.1:8181`

| Method | Path                                  | What it does                              |
|--------|---------------------------------------|-------------------------------------------|
| GET    | `/`                                   | Status JSON: endpoint, counters, last err |
| POST   | `/capture[?delay=N]`                  | Capture the full screen; returns the path |
| POST   | `/capture/region?x=&y=&w=&h=`         | Capture a region in screen pixels         |
| GET    | `/captures`                           | List filenames currently saved            |
| GET    | `/captures/<filename>`                | Stream a PNG                              |
| DELETE | `/captures`                           | Delete every capture                      |
| DELETE | `/captures/<filename>`                | Delete one                                |

Captures live in `/tmp/elysium-shots/` so any reader (including Claude's
file tools) can read the PNG directly off disk.

### Example

    # Capture full screen, read the path back, then read the PNG.
    curl -s -X POST http://127.0.0.1:8181/capture | jq .
    # {"ok":true,"path":"/tmp/elysium-shots/shot-1715912345678.png", ...}

    # Clean up.
    curl -s -X DELETE http://127.0.0.1:8181/captures

## UI

The window shows the live endpoint, permission state, request/capture
counters, and a live thumbnail of the most recent capture. Buttons:
`Capture now`, `Clear all`, `Copy endpoint`.
