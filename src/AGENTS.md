# AGENTS.md — the core

Three packages, all installed by the one `xbin-orchestrator` distribution.
**None of them may name a specific analysis tool** — see
[the rule](../AGENTS.md#the-rule-that-shapes-this-repo) and
`tests/test_core_is_plugin_agnostic.py`.

| Package | What it is |
|---|---|
| `xbin_orchestrator` | the engine: FastAPI REST + gRPC servicer + Docker management + the dashboard |
| `xbin` | the SDK plugins import (`import xbin`) |
| `libxbin` | the client library external scripts use |

## `src/xbin/` must stay two modules

`__init__.py` and `sdk.py`, nothing else. The orchestrator injects **all** of
`src/` into **every** plugin build context, so any module added here ships inside
every plugin image — including plugins that could never use it. Tool-specific
helpers belong to the plugin, or to its base-image bundle under
`plugins/_bases/`. There is a test asserting exactly this.

## Redis is the blackboard

State and event bus in one. Key conventions:

- `xbin:bb:{category}:{item_key}` → `{"status", "hypotheses": [...], "verifications": [...]}`, hypotheses sorted by `score` descending (index 0 is the current "truth")
- `xbin:bb_logs:{category}` → audit trail; `xbin:syslogs` → system log
- `xbin:events` → pub/sub carrying `NEW_BINARY` and `BLACKBOARD_UPDATE`; the only channel workers subscribe to
- `xbin:active_workers`, `xbin:worker_health`, `xbin:plugin_state:{category}:{name}` → fleet/liveness/plugin state

## Consensus math

In `XbinOrchestratorServicer.PostResult` / `SubmitVerification` / `UpdateRank`:

- Hypothesis `id` = `sha256(sorted-json of data)[:12]`, so identical data from different backends deduplicates onto one hypothesis.
- `score = confidence * BACKEND_WEIGHTS.get(backend_name, DEFAULT_WEIGHT)`.
  **`BACKEND_WEIGHTS` is built from the plugin manifests**, not written here —
  `refresh_backend_weights()` rebuilds it from every discovered plugin's
  `xbin-plugin.toml`, with `XBIN_BACKEND_WEIGHTS` (JSON) as an operator override.
  Never add a literal entry.
- Status is `CONFLICTED` when the top two hypotheses differ in data and their
  score gap is `<= MARGIN_THRESHOLD` (0.05); otherwise `RESOLVED`.
- Verifiers attach immutable stamps and never touch scores. Rankers are the only
  thing allowed to set a score or reorder.

## Regenerating gRPC stubs

`orchestrator_pb2.py` / `orchestrator_pb2_grpc.py` are generated (`DO NOT EDIT`)
and checked in:

```bash
python -m grpc_tools.protoc -I src/xbin_orchestrator \
  --python_out=src/xbin_orchestrator --grpc_python_out=src/xbin_orchestrator \
  src/xbin_orchestrator/orchestrator.proto
```

Then update `libxbin` — see below.

## Keep `libxbin` in sync

Any change to `orchestrator.proto`, a REST endpoint, or a category's
`result_data` schema must land together with the corresponding update to
`libxbin/models.py` and `libxbin/client.py`. External scripts bind against those
dataclasses; a silent drift there is invisible until someone's script returns
wrong data.

## Gotchas

- **Two-path imports.** `main.py` and `sdk.py` both import their siblings with a
  `try: import X / except ImportError: from . import X` fallback, to cope with
  protobuf's flat import scheme. Keep both paths working when touching imports —
  `plugin_manifest` follows the same pattern.
- **`main()` calls `r.flushdb()` on startup**, so launching the orchestrator
  wipes all blackboard state.
- **The dashboard is one big HTML/JS string literal** inside `main.py:dashboard()`.
  It must stay tool-agnostic too: colour by hashing the backend name
  (`backendColor()`), never by matching on it.
- **Redis is self-managed**: if none is running and the orchestrator is not
  inside Docker, it `docker run`s `xbin-redis`.
- **Discovery precedence** is manifest > `@xbin.plugin` decorator regex >
  directory names, and it keys on a file named *exactly* `Dockerfile`. That exact
  match is what keeps `plugins/_bases/*/Dockerfile.base` bundles from being
  discovered as plugins.
