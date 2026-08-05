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
| (angr)   |  | (radare) |  | (Checks) |  | (Judges) |
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
