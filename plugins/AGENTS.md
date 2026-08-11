# AGENTS.md — authoring plugins

Everything an analysis tool needs lives in its own directory. If you find
yourself editing `src/`, `tests/`, `docs/` or the `Makefile` to make one plugin
work, that is the signal to add a generic declaration instead — see
[the rule](../AGENTS.md#the-rule-that-shapes-this-repo).

## Layout

```
plugins/
  _bases/<image>/          shared base-image bundle (NOT a plugin)
    build.sh Dockerfile.base <shared helpers>.py preflight_checks.py
    README.md AGENTS.md
  <category>/<tool>/       one plugin
    <tool>_worker.py       @xbin.plugin class + xbin.start_worker()
    Dockerfile             required -- this file is what discovery keys on
    xbin-plugin.toml       optional manifest (declare a weight at minimum)
    README.md              what it does, its base image, how to run it standalone
```

`<category>` is the *question the tool answers*, not the tool's family — tools in
the same category compete on the blackboard. Existing categories:
`signature_matching`, `equation_recovery`, `cfg_generation`, `function_boundary`,
`symbol_matching`. Add a new one by using it; nothing in the core enumerates them.

**Keep a plugin flat.** The layout above is the whole of it — a worker, a
Dockerfile, a manifest, a README, and for a prebuilt plugin its `build.sh` and
`.xbin-prebuilt`. Do not add subdirectories to a plugin; if you are reaching for
one, the material probably belongs in a `plugins/_bases/<image>/` bundle shared
with the rest of its family, or in the tool's own upstream repo behind a
submodule. And never add a directory to the repo root — see
[the root-folder rule](../AGENTS.md#do-not-add-folders-to-the-repo-root).

## The three self-descriptions must agree

A plugin describes itself in three places, and the orchestrator prefers the most
explicit: **manifest > decorator > directory name**.

```python
@xbin.plugin(name="my_matcher", category="signature_matching",
             display_name="My Matcher", description="...")
```
```toml
name     = "my_matcher"
category = "signature_matching"
```

`tests/test_plugin_metadata.py` fails if they disagree — a mismatch means
results get scored under one backend name and displayed under another.

## The manifest (`xbin-plugin.toml`)

How a plugin declares what the core would otherwise hardcode. All optional, but
**always declare `weight`** — without it the backend silently scores at the 0.5
fallback.

```toml
name     = "my_matcher"
category = "signature_matching"
weight   = 0.95          # multiplier on raw confidence when scoring hypotheses
shm_size = "1g"          # only if the worker boots an emulator or similar
tiers    = ["smoke"]     # e2e tiers this plugin belongs to
e2e_timeout = 1800       # this plugin's contribution to the tier's timeout

[[mounts]]               # host cache dir -> container path, survives restarts
cache  = "job_outputs"   # a plain name; becomes <CACHE_DIR>/job_outputs
target = "/opt/mytool/job_outputs"
```

Read by [`src/xbin_orchestrator/plugin_manifest.py`](../src/xbin_orchestrator/plugin_manifest.py).

## The Triad

- **Analyzer/Producer** — `on_new_binary(binary_path, requested_goals)` → `xbin.post_result(item_key, data, confidence)`
- **Verifier** (`is_validator=True`) — `on_update(...)` → `xbin.submit_verification(target_id, verdict, ...)`. Attaches an immutable `PASS`/`FAIL`/`ABSTAIN` stamp; **never** changes scores. The target must be an explicit hypothesis id (the `"TOP"` alias is rejected).
- **Ranker** (`is_ranker=True`) — `on_update(...)` → `xbin.update_rank(item_key, target_id, new_score)`. The only role allowed to set scores or ordering.

### `on_update` fires for two different events — handle both

`on_update(category, item_key, new_hypothesis, top_hypothesis)` is called for a
new *result* and for a new *verification stamp*, and the two carry different
payloads:

| Trigger | `new_hypothesis` | `top_hypothesis` |
|---|---|---|
| `post_result` | the posted hypothesis | current top |
| `submit_verification` | **`None`** — a stamp is not a hypothesis | current top, or `None` if the item has none |

**Always guard both parameters.** A verifier that dereferences `new_hypothesis`
unconditionally crashes on the echo of *its own first stamp* and its container
exits — the event loop does not survive an exception in your handler.

```python
def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
    if not top_hypothesis:
        return
    if not new_hypothesis:
        return      # verification-triggered; skip it unless you want stamps
    ...
```

A **verifier** normally wants to skip verification-triggered updates (there is
nothing new to judge). A **ranker** that scores by stamp count wants the
opposite — keep those events, but still guard `top_hypothesis`.

`post_result(..., category=...)` lets one worker post to a different blackboard
than its own, so a tool answering two questions contributes to both without
registering twice.

## Build & runtime

- **SDK injection**: the orchestrator copies your plugin dir into a temp build context and injects `src/` (the SDK), `pyproject.toml` and `README.md`. That's why `COPY src /opt/xbin_sdk` works even though `src/` isn't in your directory. Put it on `PYTHONPATH` rather than `pip install .` to keep the orchestrator's server deps out of the worker.
- **Containers** run with `--network host`, `uploads/` at `/app/uploads`, your declared cache mounts, and `XBIN_ORCHESTRATOR` / `REDIS_HOST` set. Host services are reachable at `127.0.0.1`.
- **Heavy or licensed images**: ship a `.xbin-prebuilt` marker plus your own `build.sh`. The orchestrator then reuses the existing image and skips the build; if the image is missing it errors with a pointer to your `build.sh`. `function_boundary/binja/` is the reference example.
- **Shared base images**: when several plugins across categories share one base, put its build scripts, shared helpers and docs in `plugins/_bases/<image>/`. Name the build file **`Dockerfile.base`** — discovery keys on the exact name `Dockerfile`, so a bundle with a plain `Dockerfile` would appear as a phantom plugin.
- **Worker tunables**: don't add env var names to the core. The operator forwards them via the generic allowlist `XBIN_WORKER_ENV_PASSTHROUGH=VAR1,VAR2`.

## Contributing checks and fixtures

- `preflight_checks.py` — `checks(tier, ctx) -> list[Check]`, discovered and run by `xbin_orchestrator/preflight.py`. `ctx` supplies `ctx.run`, `ctx.port_open`, `ctx.Check`, `ctx.PASS/FAIL/WARN`, `ctx.repo_root`, so you import nothing from the core. Give every check its own remediation string.
- `stage.sh` — stages test fixtures into `uploads/`. `make stage` runs every one it finds. Copy files rather than symlinking: `uploads/` is bind-mounted into containers and an external symlink dangles inside them.

## Gotchas

- Resolve the SDK singleton at call time: use `xbin.post_result(...)`. A module-level `from xbin.sdk import _current_worker` binds to `None`, because the import runs before the `@xbin.plugin` decorator sets it.
- Defer heavy imports (analysis frameworks, JVMs, native libs) into the callbacks. The orchestrator and the test suite import worker modules statically to read their metadata, and must be able to do so without your stack installed.
- Docs go in your plugin's `README.md` / `KNOWN_ISSUES.md`, not in the root `docs/`.
