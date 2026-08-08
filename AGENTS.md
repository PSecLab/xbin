# AGENTS.md

Guidance for coding agents working in this repository. `AGENTS.md` is this
project's standard — not `CLAUDE.md` or any other vendor-specific filename — so
one set of instructions serves every agent.

This file is deliberately short. Deeper context lives in nested `AGENTS.md`
files, one per subtree, so an agent only loads what the task actually needs:

| File | Load when you are working on |
|---|---|
| [`src/AGENTS.md`](src/AGENTS.md) | the orchestrator, the SDK, or `libxbin` |
| [`plugins/AGENTS.md`](plugins/AGENTS.md) | authoring or changing any plugin |
| [`plugins/_bases/bind/AGENTS.md`](plugins/_bases/bind/AGENTS.md) | the Morpheus/BIND family or its base image |
| [`plugins/equation_recovery/pysindy/AGENTS.md`](plugins/equation_recovery/pysindy/AGENTS.md) | the pysindy plugin |

## What this is

**xbin** is a blackboard-architecture orchestrator for binary analysis.
Specialized workers run as Docker containers and post competing *hypotheses*
about a binary to a central blackboard; the orchestrator computes weighted
consensus and broadcasts updates, and workers react.

See [`README.md`](README.md) for the introduction and
[`docs/architecture.md`](docs/architecture.md) for how it is wired.

## Repo map

```
src/           orchestrator, SDK, libxbin          -- tool-agnostic
scripts/       preflight + e2e harness             -- tool-agnostic
docs/          framework documentation             -- tool-agnostic
tests/         pytest suites                       -- tool-agnostic
plugins/       every analysis tool, self-contained
  _bases/      shared base-image bundles (build scripts, shared helpers, docs)
  <category>/<tool>/   one plugin: worker, Dockerfile, xbin-plugin.toml, README
submodules/    third-party trees consumed by plugin base images
examples/      runnable demos, incl. a template plugin
```

## The rule that shapes this repo

**The core knows nothing about any specific analysis tool.** No plugin name,
image name, container path, or vendor stack may appear in `src/`, `scripts/`,
`docs/`, the `Makefile`, `docker-compose.yml`, or `pyproject.toml`. Everything a
plugin needs lives in the plugin's own directory.

This is enforced, not merely encouraged:

```bash
pytest tests/test_core_is_plugin_agnostic.py
```

The acceptance test for the whole layout is that the plugin tree can be lifted
out: copying `plugins/_bases/<bundle>/` plus its plugin dirs somewhere else and
starting the orchestrator with `--plugin-dir <that path>` must just work. If a
change would break that, it belongs on the plugin side of the line.

When the core seems to need to know something tool-specific, add a **generic
declaration** the plugin fills in — that is what `xbin-plugin.toml` is for — not
a special case. Existing declarations: consensus `weight`, cache `[[mounts]]`,
`shm_size`, e2e `tiers`, and plugin-provided `preflight_checks.py`.

## Commands

```bash
make setup                            # .venv + pip install -e . pytest (needs python >= 3.11)
make test                             # fast Docker-free lane
make tiers                            # e2e tiers the installed plugins define
make bases                            # build every plugins/_bases/*/ base image
make stage                            # run every plugin's stage.sh (fixtures -> uploads/)
make e2e TIER=smoke                   # full-stack run

xbin-orchestrator                     # gRPC :50051, REST+dashboard :8000
xbin-orchestrator --no-browser        # headless / CI
xbin-orchestrator --plugin-dir PATH   # out-of-tree plugin collection (repeatable)
xbin-orchestrator --plugin PATH[:category]   # single external plugin (repeatable)

pytest tests/test_blackboard.py::test_analyzer_submission -v   # single test
pytest -m e2e                         # full stack (opt-in)
```

Tests need a reachable Redis on `localhost:6379`; `conftest.py` boots a real
orchestrator subprocess and flushes the DB before each test.

## Two things that will bite you

**Keep `libxbin` in sync.** Whenever you change the gRPC protocol
(`orchestrator.proto`), a REST endpoint, or a category's `result_data` payload
schema, update the client bindings in [`src/libxbin/models.py`](src/libxbin/models.py)
and [`src/libxbin/client.py`](src/libxbin/client.py) in the same change.
External scripts bind against those.

**Regenerate gRPC stubs explicitly.** `orchestrator_pb2.py` /
`orchestrator_pb2_grpc.py` are generated (marked `DO NOT EDIT`) and checked in:

```bash
python -m grpc_tools.protoc -I src/xbin_orchestrator \
  --python_out=src/xbin_orchestrator --grpc_python_out=src/xbin_orchestrator \
  src/xbin_orchestrator/orchestrator.proto
```
