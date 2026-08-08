# Known issues — orchestrator core

Issues in the framework itself: the orchestrator, the SDK, `libxbin`, and the
shared test harness.

Anything specific to an analysis tool lives with that tool — look for a
`KNOWN_ISSUES.md` in the relevant plugin directory, or in the
`plugins/_bases/<image>/` bundle for a whole plugin family:

```bash
find plugins -name KNOWN_ISSUES.md
```

## Verification status

**Fast Docker-free lane** (`make test` / `pytest`): consensus math, REST API,
plugin manifests, and the layering guard. CI-ready — needs only a reachable
Redis.

---

## Fixed

### `uploads/` not writable by worker containers — FIXED

`uploads/` is bind-mounted into every worker, but the host dir was created with
the orchestrator's ownership and mode 755, while containers run as their own
uid. Workers that cache sidecar files next to the uploaded binary (analysis
databases, precomputed offsets — a common pattern) could not write them, and
crashed per-item on `open(sidecar, "w")`.

**Fix:** the orchestrator makes every directory it bind-mounts into a worker
world-writable on creation (`_make_world_writable` in
`src/xbin_orchestrator/main.py`). This covers `UPLOAD_DIR` and every
manifest-declared `[[mounts]]` cache dir.

---

## Open

None currently tracked against the core.
