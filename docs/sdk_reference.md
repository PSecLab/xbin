# xbin SDK Reference Guide

The `xbin` SDK is a reactive, event-driven framework that allows you to build binary analysis plugins that collaborate via a central blackboard.

## 🏗️ System Architecture

The following diagram illustrates how the **Orchestrator**, **Redis (Blackboard)**, and **Workers** interact:

```text
       +-----------------------+
       |     User Dashboard    |
       |  (FastAPI + Web UI)   |
       +-----------+-----------+
                   | (REST)
       +-----------v-----------+          +-----------------------+
       |     ORCHESTRATOR      | <------> |   REDIS BLACKBOARD    |
       |    (Message Router)   |  (gRPC)  |   (State & Pub/Sub)   |
       +-----------+-----------+          +-----------------------+
                   |
     +-------------+-------------+-------------+
     |             |             |             |
+----v-----+  +----v-----+  +----v-----+  +----v-----+
| Worker A |  | Worker B |  | Validator|  |  Ranker  |
| (Tool A) |  | (Tool B) |  | (Checks) |  | (Judges) |
+----------+  +----------+  +----------+  +----------+
```

## 🔄 The Analysis Lifecycle

1. **Producer** (Analyzer) posts a new hypothesis.
2. **Orchestrator** saves it and broadcasts a `BLACKBOARD_UPDATE`.
3. **Validator** hears the update and decides to "vouch" for it.
4. **Ranker** hears the vouch, applies a custom heuristic, and issues an `update_rank` command.
5. **Orchestrator** applies the new score.

```text
 [ ANALYZER ]          [ ORCHESTRATOR ]          [ VALIDATOR ]          [ RANKER ]
      |                      |                        |                     |
      | -- post_result() --> |                        |                     |
      |                      | -- on_update event --> |                     |
      |                      |                        | -- validation() --> |
      |                      | <----------------------+                     |
      |                      | -- on_update event ------------------------> |
      |                      |                                              |
      |                      | <----------------------- update_rank() ------|
      |                      | -- Score Overridden! --> [ DASHBOARD / UI ]  |
```

## 🚀 Quick Start Example: "The Hello World Worker"

This example shows a plugin that identifies a "Hello World" string and a validator that confirms it.

### The Analyzer (Producer)
This tool searches for a specific string and posts a symbol hypothesis.

```python
import xbin

@xbin.plugin(name="hello_finder", category="symbol_matching")
class HelloFinder:
    def on_new_binary(self, binary_path, requested_goals):
        if "symbol_matching" not in requested_goals:
            return

        with open(binary_path, "rb") as f:
            data = f.read()
            if b"Hello, World!" in data:
                # We found it! Post the result to the blackboard
                xbin.post_result(
                    item_key="0x401000", 
                    data="main_entry_greeting", 
                    confidence=0.8
                )

if __name__ == "__main__":
    xbin.start_worker()
```

### The Validator (Verifier)
### The Verifier
This tool listens for `hello_finder`'s output and attaches an immutable verification stamp.

```python
import xbin

@xbin.plugin(name="hello_verifier", category="symbol_matching", is_validator=True)
class HelloVerifier:
    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        # If the new finding is our target string, attach a PASS stamp!
        if category == "symbol_matching" and new_hypothesis and new_hypothesis['data'] == "main_entry_greeting":
            xbin.submit_verification(
                target_id=new_hypothesis['id'],
                verdict="PASS",
                confidence=0.95,
                evidence="String match verified in target binary"
            )

if __name__ == "__main__":
    xbin.start_worker()
```

### The Ranker (Judge)
Rankers listen to hypotheses and verification stamps and apply global ranking heuristics. Only rankers can modify scores or ordering.

```python
import xbin

@xbin.plugin(name="hello_ranker", category="symbol_matching", is_ranker=True)
class HelloRanker:
    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        # We only care about symbol matching updates
        if category != "symbol_matching":
            return

        # Fetch blackboard state to inspect verifications
        state = xbin.get_analysis(category, item_key)
        if not state:
            return

        verifications = state.get("verifications", [])
        # Heuristic: If we have a PASS verification, boost the hypothesis score
        if any(v["verdict"] == "PASS" for v in verifications if v["target_id"] == top_hypothesis['id']):
            xbin.update_rank(item_key, top_hypothesis['id'], 2.0)

if __name__ == "__main__":
    xbin.start_worker()
```

---

## 🛠️ API Reference

### Decorator: `@xbin.plugin`
Registers your class with the orchestrator.
- `name` (str): Unique tool ID.
- `category` (str): Blackboard category (e.g., `cfg_generation`).
- `is_validator` (bool): Set to `True` for verification-only tools.
- `is_ranker` (bool): Set to `True` for tools that judge and re-rank hypotheses.

### Callbacks (Implemented in your class)

#### `on_new_binary(self, binary_path, requested_goals)`
Called when a new binary is uploaded. `binary_path` is the path inside the container.

#### `on_update(self, category, item_key, new_hypothesis, top_hypothesis)`
Called every time the blackboard changes. Use this to build collaborative tools, Verifiers, or Rankers.

### Methods (via `xbin` module)

#### `xbin.post_result(item_key, data, confidence)`
Submit a new producer hypothesis.
- `item_key`: Unique subject identifier.
- `data`: Any JSON-serializable object.
- `confidence`: Your certainty (0.0 to 1.0).

#### `xbin.submit_verification(target_id, verdict, confidence=None, evidence=None)`
Specifically for Verifiers. Attaches an immutable verification stamp to an explicit hypothesis target ID without modifying hypothesis scores.
- `target_id`: Explicit immutable ID of the hypothesis being verified (alias `"TOP"` is rejected).
- `verdict`: `"PASS"`, `"FAIL"`, or `"ABSTAIN"`.
- `confidence`: Optional float confidence level (0.0 to 1.0).
- `evidence`: Optional explanation or evidence string.

#### `xbin.update_rank(item_key, target_id, new_score)`
Specifically for Rankers. Updates the absolute consensus score of a hypothesis.
- `item_key`: The subject identifier.
- `target_id`: The unique hash ID of the hypothesis.
- `new_score`: The new float score.

#### `xbin.get_analysis(category, item_key=None)`
Fetch current results from the blackboard.
- `category`: The blackboard category to query.
- `item_key`: Optional. Filter for a specific item.

---

## 📋 The Plugin Manifest (`xbin-plugin.toml`)

Drop this next to your `Dockerfile`. It is how a plugin declares the things the
orchestrator would otherwise have to hardcode about it — which is what keeps the
core free of any knowledge of your tool.

Every field is optional; a plugin with no manifest still works and keeps the
defaults. **Always declare `weight`**, though: without it your backend silently
scores at the `0.5` fallback.

```toml
name     = "my_matcher"          # backend name; overrides the decorator + dir name
category = "signature_matching"  # blackboard category
weight   = 0.95                  # multiplier on raw confidence when scoring (0.0-1.0)
shm_size = "1g"                  # only if the worker boots an emulator or similar
tiers    = ["smoke", "full"]     # e2e tiers this plugin belongs to
e2e_timeout = 1800               # this plugin's contribution to the tier's timeout

[[mounts]]                       # persistent cache, survives container restarts
cache  = "job_outputs"           # plain dir name; becomes <CACHE_DIR>/job_outputs
target = "/opt/mytool/job_outputs"   # absolute path inside the container
```

| Field | Default | Effect |
|---|---|---|
| `name`, `category` | decorator, then directory names | Discovery precedence is **manifest > decorator > directory**. |
| `weight` | `0.5` | Feeds `BACKEND_WEIGHTS`; an operator can override with `XBIN_BACKEND_WEIGHTS` (JSON). |
| `shm_size` | `1g` (or `XBIN_DEFAULT_SHM_SIZE`) | `docker run --shm-size`. Docker's own default is 64M. |
| `tiers` | none | Tier membership for `scripts/e2e_driver.py`. A tier's fleet, required categories and timeout are all derived from these. |
| `e2e_timeout` | `1800` | A tier's timeout is the max over its member plugins. |
| `[[mounts]]` | none | `cache` must be a plain directory name and `target` an absolute path, or the entry is rejected. |

The manifest is surfaced on `/api/v1/plugins/available` and through
`libxbin`'s `PluginInfo` (`weight`, `tiers`).

### Beyond the manifest

Two more things a plugin can contribute, both discovered by filename:

- **`preflight_checks.py`** — expose `checks(tier, ctx) -> list[Check]` and
  `scripts/preflight.py` will run it. `ctx` supplies `ctx.run`, `ctx.port_open`,
  `ctx.Check`, `ctx.PASS/FAIL/WARN` and `ctx.repo_root`, so you import nothing
  from the core. Give each check its own remediation string.
- **`stage.sh`** — stages test fixtures into `uploads/`; `make stage` runs every
  one it finds.

### Shared base images

When several plugins share one heavy base image, put its build scripts, shared
helpers and docs in `plugins/_bases/<image>/`, and name the build file
**`Dockerfile.base`**. Discovery keys on the exact filename `Dockerfile`, so a
bundle containing one would be picked up as a phantom plugin.

If the orchestrator cannot build your image at all (a licensed or multi-hour
base), ship a `.xbin-prebuilt` marker plus your own `build.sh`: the orchestrator
then reuses the existing image and skips the build, and errors with a pointer to
your `build.sh` if the image is missing.
