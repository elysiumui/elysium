# input-probe — OS-level input test target

A minimal Elysium window that records the **raw** keyboard/mouse input it
receives from the OS and serves it over HTTP. It exists so CI can inject real
OS events and verify the app actually got them — coverage the launch-only smoke
test can't give (and the gap that let a Windows "typing is dead" bug ship).

```bash
ELYSIUM_PROBE_PORT=8199 python -m examples.input-probe
curl -s http://127.0.0.1:8199/        # {ready, kbd_text, text, raw_events, clicks, ...}
curl -s -XPOST http://127.0.0.1:8199/reset
curl -s -XPOST http://127.0.0.1:8199/quit
```

State fields:

- `kbd_text` — printable text delivered via **`KeyboardInput`** (`code != "ImeCommit"`).
  This is the field that catches the Windows IME regression: with IME enabled,
  Windows routes typed text only through `Ime::Commit`, so `kbd_text` comes back
  empty while the all-source `text` still fills.
- `text` — printable text from any source (KeyboardInput **or** ImeCommit).
- `raw_events` — every `poll_key_event` verbatim (`code`, `pressed`, `mods`, `text`).
- `clicks` / `right_clicks` — mouse presses (via `press_count`), with position.

The driver is [`tests/test_os_input.py`](../../tests/test_os_input.py): it
injects real OS input (xdotool on Linux, pywinauto on Windows) and asserts the
round-trip. Run in CI by [`.github/workflows/input-e2e.yml`](../../.github/workflows/input-e2e.yml).
