# xbin architecture

Developer-facing notes on how the framework is wired: the blackboard, the
consensus math, and the non-obvious parts of the plugin/Docker system. For the
introduction see [`README.md`](../README.md); for writing a plugin see
[`sdk_reference.md`](sdk_reference.md) and [`grpc_schemas.md`](grpc_schemas.md);
for the test lanes see [`e2e_testing.md`](e2e_testing.md).

Nothing here is specific to any analysis tool. Each plugin documents itself in
its own directory — start at [`plugins/AGENTS.md`](../plugins/AGENTS.md) for the
authoring contract, or a plugin's own `README.md` for what it does.

## What this is

**xbin** is a blackboard-architecture orchestrator for binary analysis.
Specialized workers run as Docker containers and post competing *hypotheses*
about a binary to a central blackboard; the orchestrator computes weighted
consensus and broadcasts updates, and workers react.

Plugins are grouped on disk by the *question they answer* rather than by the
tool that answers it, so tools in the same category compete directly — two CFG
generators post to `cfg_generation`, two signature matchers to
`signature_matching`, and the blackboard scores them against each other.

## Commands

```bash
pip install -e .                      # editable install
xbin-orchestrator                     # start engine: gRPC :50051, REST+dashboard :8000, auto-opens browser
xbin-orchestrator --no-browser        # for headless / CI
xbin-orchestrator --plugin-dir PATH   # load out-of-tree plugin collections (repeatable)
xbin-orchestrator --plugin PATH[:category]  # load a single external plugin dir/file (repeatable)

make bases                            # build every plugins/_bases/*/ base image
make stage                            # run every plugin's stage.sh (fixtures -> uploads/)
make tiers                            # list the e2e tiers the installed plugins define

pytest                                # fast Docker-free lane
pytest tests/test_blackboard.py::test_analyzer_submission -v   # single test
pytest -m e2e                         # full stack (opt-in)

docker compose up                     # full stack (redis + orchestrator) in containers
```

**Tests require a reachable Redis on `localhost:6379`.** `tests/conftest.py`
launches a real orchestrator subprocess (`python -m xbin_orchestrator.main`) and
flushes the DB before each test; the orchestrator's `ensure_redis()` will
`docker run` a container named `xbin-redis` if none is up. Tests exercise the
live gRPC + Redis path, not mocks.

**Regenerating gRPC stubs:** `orchestrator_pb2.py` / `orchestrator_pb2_grpc.py`
are generated (marked `DO NOT EDIT`) and checked in. After editing
`src/xbin_orchestrator/orchestrator.proto`, regenerate with grpcio-tools (a
declared build dep):

```bash
python -m grpc_tools.protoc -I src/xbin_orchestrator \
  --python_out=src/xbin_orchestrator --grpc_python_out=src/xbin_orchestrator \
  src/xbin_orchestrator/orchestrator.proto
```

## Architecture

Three importable packages live under `src/` (all installed by the one
`xbin-orchestrator` distribution):

- **`xbin_orchestrator`** — the central engine. `main.py` is the whole backend: FastAPI REST API + gRPC blackboard servicer + Docker container management, plus the entire web dashboard as one embedded HTML string in the `dashboard()` route. Entry point `xbin-orchestrator` → `xbin_orchestrator.main:main`. `plugin_manifest.py` reads the per-plugin `xbin-plugin.toml`.
- **`xbin`** — the SDK plugins import (`import xbin`). `sdk.py` defines the `Worker` class and the module-level helpers. Deliberately just two modules: the orchestrator injects all of `src/` into *every* plugin build context, so anything added here ships inside every plugin image.
- **`libxbin`** — the Python client library external scripts use to drive the orchestrator and read results.

**Redis is the blackboard** — both persistent state and the pub/sub event bus.
Key conventions:

- `xbin:bb:{category}:{item_key}` → hypothesis state: `{"status", "hypotheses": [...]}`, `hypotheses` sorted by `score` descending (index 0 is the current "truth").
- `xbin:bb_logs:{category}` → audit trail; `xbin:syslogs` → system log.
- `xbin:events` → pub/sub channel carrying `NEW_BINARY` and `BLACKBOARD_UPDATE` events. This is the only thing workers subscribe to.
- `xbin:active_workers`, `xbin:worker_health`, `xbin:plugin_state:{category}:{name}` → fleet/liveness/plugin-state tracking.

**The Triad (plugin roles)** — a plugin is a class decorated with
`@xbin.plugin(...)` that implements callbacks and ends with
`xbin.start_worker()`:

- **Analyzer/Producer**: implements `on_new_binary(binary_path, requested_goals)` → `xbin.post_result(item_key, data, confidence)`.
- **Verifier** (`is_validator=True`): implements `on_update(category, item_key, new_hypothesis, top_hypothesis)` → `xbin.submit_verification(target_id, verdict, confidence=..., evidence=...)` to attach an immutable verification stamp (`PASS`, `FAIL`, `ABSTAIN`). Verifiers never modify hypothesis scores.
- **Ranker** (`is_ranker=True`): implements `on_update(...)` → `xbin.update_rank(item_key, target_id, new_score)` to absolutely override a hypothesis score. Rankers are the only components allowed to calculate scores or ordering.

The decorator also takes `display_name=` and `description=` (shown on the
dashboard cards; discovered statically via regex before the plugin starts).
`post_result(item_key, data, confidence, category=...)` accepts an optional
`category` override so one worker can post to a different blackboard than its
own — a tool that answers two questions at once contributes to both without
registering twice.

**Consensus math & verification stamps** live in
`XbinOrchestratorServicer.PostResult` / `SubmitVerification` / `UpdateRank` in `main.py`:

- A hypothesis `id` is `sha256(sorted-json of data)[:12]` → identical data from different backends deduplicates producers. Initial hypothesis `score = confidence * weight`, where the weight is the backend's declared `weight` (see the manifest below); unknown backends fall back to `0.5`.
- **Verifiers**: submit immutable stamps containing `target_id`, `verifier_name`, `verifier_version`, `verdict` (`PASS`/`FAIL`/`ABSTAIN`), optional `confidence`, `evidence`, and `timestamp`. Stamps are stored under `verifications` separately from `hypotheses` and never mutate hypothesis scores or ordering. Verification targets must be explicit immutable IDs (the `"TOP"` alias is rejected).
- Status is `CONFLICTED` when the top two hypotheses differ in data and their score gap is `<= MARGIN_THRESHOLD` (0.05); otherwise `RESOLVED`.
- **Rankers**: are the only components allowed to modify hypothesis scores or ordering, via `update_rank`.

## Plugin system & Docker (the non-obvious part)

The orchestrator **builds and runs each plugin as its own Docker container** —
it shells out to the `docker` CLI, so the daemon must be reachable
(docker-compose mounts the socket).

- **Discovery**: walks `PLUGIN_DIRS` (default `plugins/`) for any directory containing a file named exactly `Dockerfile`. Category/name default to the parent-dir / dir names, but are overridden by a `@xbin.plugin(name=..., category=..., display_name=..., description=...)` regex scan of the source, and then by the `xbin-plugin.toml` manifest — most explicit wins. Plugins are grouped on disk as `plugins/<category>/<tool>/`.
- **The manifest** (`xbin-plugin.toml`, optional): how a plugin declares what the core would otherwise hardcode about it — its consensus `weight`, the caches it wants bind-mounted (`[[mounts]]`), its `shm_size`, and which e2e `tiers` it belongs to. Read by `src/xbin_orchestrator/plugin_manifest.py`. See [`sdk_reference.md`](sdk_reference.md) for the full field list.
- **SDK injection at build time**: `_build_plugin_image` copies the plugin dir into a temp context and injects `src/` (the SDK), `pyproject.toml`, and `README.md`. That's why plugin Dockerfiles can `COPY src /opt/xbin_sdk` — those files aren't in the plugin dir on disk. (`pyproject.toml` declares `readme = "README.md"`, which is why the README rides along.) A plugin can put the SDK on `PYTHONPATH` rather than `pip install .` to avoid pulling the orchestrator's server deps into a worker.
- **Container runtime**: started with `--network host`, `uploads/` mounted to `/app/uploads`, any manifest-declared cache mounts, and env `XBIN_ORCHESTRATOR=localhost:50051`, `REDIS_HOST=localhost`. `--network host` is why a worker can reach a service on the host at `127.0.0.1`.
- **Heavy or licensed base images**: a plugin whose image the orchestrator cannot build (because it extends a licensed or multi-hour base) ships a `.xbin-prebuilt` marker and its own `build.sh`. The orchestrator then reuses the existing image and skips the build entirely; if the image is missing it fails with a pointer to that `build.sh`.
- **Shared base bundles** (`plugins/_bases/<image>/`): when several plugins across different categories share one base image, its build scripts, shared helpers and docs live in a bundle there. Bundles name their build file `Dockerfile.base` precisely so the discovery walk — which keys on the exact name `Dockerfile` — never mistakes them for a plugin.
- **Worker env passthrough**: `XBIN_WORKER_ENV_PASSTHROUGH` is an operator-specified comma-separated allowlist of env vars forwarded from the orchestrator into every worker container when set. Empty by default. This is how a plugin's runtime knobs get tuned at fleet start without any plugin-specific variable name living in the core.

## Notable gotchas

- **`main()` calls `r.flushdb()` on every startup** — launching the orchestrator wipes all blackboard state.
- The orchestrator manages Redis itself: if none is running and it's not inside Docker, it `docker run`s `xbin-redis`.
- `sdk.py` (and `main.py`) has a two-path import fallback to cope with protobuf's flat import scheme; keep both paths working when touching imports.
- Editing the dashboard means editing the large HTML/JS string literal inside `main.py:dashboard()`. Cytoscape.js is still loaded from a CDN.
- Workers reach the SDK singleton either via module helpers (`xbin.post_result(...)`) or `from xbin.sdk import _current_worker`. Prefer the module helpers: they resolve the live singleton at call time, whereas a module-level `from xbin.sdk import _current_worker` binds the name to `None` because the import runs before the decorator sets it.
- **reference-binary convention**: on upload the orchestrator saves an optional uploaded reference as `<binary-stem>.reference` next to the target. Plugins that compare a target against a known-good build look for that sibling and fall back to their own default when it is absent.
