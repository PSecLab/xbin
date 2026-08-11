# xbin End-to-End Testing Guide

Covers **both** the automated test mechanism and the **manual/visual** walkthrough
of the web dashboard.

Nothing here names a specific analysis tool: the tiers, their plugin fleets and
their prerequisites all come from whatever plugins are installed. For the tier
definitions and prerequisites of the in-tree BIND family, see
[`plugins/_bases/bind/TESTING.md`](../plugins/_bases/bind/TESTING.md).

Three ways to test:

| | What it exercises | Needs |
|---|---|---|
| **Automated fast lane** — `make test` | consensus math, REST API, plugin manifests, the layering guard (Docker-free) | venv + Redis (seconds) |
| **Automated full stack** — `make e2e TIER=<tier>` | upload → real plugin containers → blackboard, with a summary | Docker + whatever the tier's plugins declare |
| **Manual / visual** — the dashboard | what a human sees: fleet health, tables, per-function detail | a browser (+ an SSH tunnel if remote) |

The pieces:

- `src/xbin_orchestrator/preflight.py` — the readiness engine. Runs the core checks (docker, redis, ports, deps) plus every `preflight_checks.py` a plugin contributes. Reached through `pytest -m preflight`, the `xbin-preflight` console script, or `make preflight`.
- `tests/e2e_driver.py` — full-stack driver. Derives its tiers from the plugin manifests. Importable by the tests and runnable as a CLI.
- `tests/` — every lane: `pytest` (fast, Docker-free), `pytest -m e2e` (full stack), `pytest -m preflight` (readiness).
- `Makefile` — thin convenience wrappers over those.

---

## Tiers

Tiers are **not** defined by the harness. Each plugin declares its membership in
its `xbin-plugin.toml`:

```toml
tiers       = ["smoke", "full", "heavy"]
e2e_timeout = 1800
```

and the driver derives the rest — a tier's fleet is the plugins declaring it, its
required categories are those plugins' categories, and its result timeout is the
max of their `e2e_timeout`s. Adding a plugin to a tier is a one-line manifest
edit.

To see what the installed plugins actually define:

```bash
make tiers                            # or: python tests/e2e_driver.py --list-tiers
```

---

## 1. Reach the dashboard from a remote server (SSH tunnel)

If the orchestrator runs on a server, the cleanest way to view its dashboard is
an **SSH local-port-forward** (private, no firewall change). From your laptop:

```bash
ssh -L 8000:localhost:8000 <user>@<server>
```

Keep that session open, then open **http://localhost:8000** in your browser.

- The gRPC port **`:50051` is internal** — worker containers reach it via
  `--network host` at `localhost:50051`. **Do not** forward it.
- Alternatives:
  - **VS Code Remote-SSH**: connect to the server; when the orchestrator starts,
    VS Code auto-forwards `8000` (see the Ports panel).
  - **Background tunnel**: `ssh -fN -L 8000:localhost:8000 <user>@<server>`.

---

## 2. One-time setup

```bash
# 1. Create the Python env (needs python >= 3.11).
make setup                      # override the interpreter with: make setup PYTHON=/path/to/python3.12
source .venv/bin/activate

# 2. Build any base images the installed plugins need (may take hours).
make bases

# 3. Sanity-check prerequisites for the tier you want.
make preflight TIER=smoke

# 4. Stage test fixtures into uploads/.
make stage
```

Preflight verifies Docker, Redis on `:6379`, free ports and the Python deps, then
runs each plugin's own checks — base images, model availability, emulator
support, and so on. Every failed check prints its own remediation.

---

## 3. Launch the orchestrator (headless)

Run from the repo root (`uploads/` and `plugins/` are relative paths), inside
`tmux` so a dropped connection doesn't kill it:

```bash
tmux new -s xbin                 # detach with Ctrl-b then d; reattach: tmux attach -t xbin
cd /path/to/xbin && source .venv/bin/activate
xbin-orchestrator --no-browser
```

Healthy startup prints just two lines (uvicorn is quiet at `log_level=warning`,
so there is **no "Uvicorn running" banner**):

```
[HH:MM:SS] Cleanup stale containers...
[HH:MM:SS] xbin Multi-Analysis Engine Online
```

Confirm readiness from another shell: `curl -s localhost:8000/api/v1/health`
→ `{"orchestrator":"HEALTHY",...}`.

> **Warning:** every orchestrator start runs `flushdb` — it wipes all blackboard
> state. Don't restart mid-test. The header **Clear Session** button also flushes
> (use it deliberately to reset).

---

## 4. Visual walkthrough

Open **http://localhost:8000**.

1. **Dashboard loads.** Top-right shows a green **`Orchestrator: OK`** badge. The
   left sidebar lists the installed plugins grouped into collapsible sections by
   category, all **STOPPED**. A plugin registered as a ranker shows a blue
   **Ranker** badge; a verifier shows a **Validator** badge.
2. **Start the fleet.** Click **Start Fleet** (header), or start individual
   plugins via their per-card toggles for a faster first test. Each card walks
   **BUILDING → STARTING → RUNNING**, then shows a green **READY** flag once
   healthy, with a heartbeat "ping" animation.
   - *First build is slow:* the orchestrator builds each plugin as a `--no-cache`
     thin layer over its base image — allow a few minutes per plugin the first
     time. Plugins marked `.xbin-prebuilt` skip the build entirely.
3. **Announce the target.** Two options:
   - **Server-side (no laptop copy):**
     ```bash
     curl -F file=@uploads/<target> -F requested_analyses=<category> http://localhost:8000/api/v1/upload
     ```
   - **UI picker:** click **📁 Choose Binary** → pick the file (the browser reads
     *your* filesystem, not the server's), tick the goal checkboxes, and click
     **🚀 Start Analysis**. You'll see a **"Binary Announced"** toast.
   - Optionally attach a **Reference Binary** — saved as `<stem>.reference` next
     to the target for plugins that diff against a known-good build.
4. **Watch results.** A card appears per category, with the active
   **`Ranker: <name>`** badge and an **Audit Trail** button, then a table — one
   row per item key. Rows populate within seconds-to-minutes of the workers
   being READY.
5. **Inspect an item.** Click **Details** on a row → a modal lists every
   hypothesis: `#i via <backend> score=.. raw_conf=..`, plus whatever fields that
   category's payload carries.
6. **Consensus signals.** A green **✓ + "+N vouches"** on a row means two tools
   posted identical data (they deduplicate onto one hypothesis). A **Validator**
   plugin's verification stamps appear on the hypothesis. Click **Audit Trail**
   for the per-category log, or a plugin's **Logs** for its container output.

---

## 5. What "success" looks like

- **Setup:** `make setup` succeeds; `xbin-orchestrator` is on PATH.
- **Launch:** the two sys_log lines; `/api/v1/health` → HEALTHY; green
  **Orchestrator: OK** badge.
- **Fleet:** plugin cards reach **RUNNING + READY** with heartbeat pings.
- **Analysis:** "Binary Announced" toast; the results table fills with rows and
  resolved values; Details modals render; the ranker badge is present.

---

## 6. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Full-screen 🔌 **Connection Lost** / **Backend Offline** badge | orchestrator died OR the SSH tunnel dropped | Check the tmux window; re-run `xbin-orchestrator --no-browser`; reopen the tunnel. The page auto-recovers when the backend returns. |
| Plugin card stuck **BUILDING** on first start | first `--no-cache` thin-layer build over a large base | Wait a few minutes; watch `docker ps -a`. Escalate only if it flips to ERROR. |
| Plugin card shows **ERROR** (red line) | build/run failure | Click the card's **Logs**. "image ... missing" means its base image isn't built — run `make bases`. |
| Build fails immediately | the plugin's base image is absent | `make bases`, or the plugin's own `build.sh` if it is `.xbin-prebuilt`. |
| Empty results table after announcing | goal not checked / worker not HEALTHY / a service the plugin needs is down | Confirm the matching goal was checked or passed in the curl; confirm the card is **RUNNING + READY**; run `make preflight TIER=<tier>`. |
| A started plugin posts nothing | no qualifying input, or a missing runtime dependency | Check its **Logs**; the e2e driver also prints a **silent backends** line naming every plugin in the fleet that contributed nothing. |
| Blackboard reset unexpectedly | the orchestrator restarted (`flushdb` on boot) | Don't restart mid-test; use **Clear Session** deliberately. |
| UI file picker can't find the target | the browser reads *your* files, not the server's | Use the server-side `curl` announce, or copy the binary to your machine first. |

---

## 7. Automated runs (recap)

```bash
# Fast, Docker-free lane — run this in CI:
make test                      # == .venv/bin/pytest   (excludes -m e2e)

# Full-stack, one command per tier (boots its own orchestrator, prints a summary):
make tiers                     # what tiers exist
make e2e TIER=<tier>

# Or drive an orchestrator you're already watching in the dashboard:
xbin-orchestrator --no-browser &                     # (in tmux)
python tests/e2e_driver.py --tier smoke --attach   # results appear live in the browser

# As a pytest (against the session orchestrator; opt-in):
pytest -m e2e                  # smoke tier; XBIN_E2E_TIER=<tier> to change
```

The driver polls until the tier's required categories populate, then prints a
per-item summary (top hypothesis, backend, score, RESOLVED/CONFLICTED, vouches)
and a per-backend hypothesis count, plus a **silent backends** line for any
started plugin that produced nothing. It exits nonzero on any plugin crash,
empty required category, or timeout, and dumps the failing container's logs.
