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
       |    (Consensus Engine) |  (gRPC)  |   (State & Pub/Sub)   |
       +-----------+-----------+          +-----------------------+
                   |
     +-------------+-------------+
     |             |             |
+----v-----+  +----v-----+  +----v-----+
| Worker A |  | Worker B |  | Validator|
| (angr)   |  | (radare) |  | (LLM/Ref)|
+----------+  +----------+  +----------+
```

## 🔄 The Analysis Lifecycle

1. **Producer** (Analyzer) posts a new hypothesis.
2. **Orchestrator** calculates score and broadcasts a `BLACKBOARD_UPDATE`.
3. **Validator** hears the update and decides to "vouch" for it.
4. **Orchestrator** boosts the original hypothesis score.

```text
 [ ANALYZER ]          [ ORCHESTRATOR ]          [ VALIDATOR ]
      |                      |                        |
      | -- post_result() --> |                        |
      |                      | -- on_update event --> |
      |                      |                        | -- post_validation() --+
      |                      | <----------------------+                        |
      |                      |                                                 |
      |                      | -- Score Boosted! ----> [ DASHBOARD / UI ]      |
```

## 🚀 Quick Start Example: "The Hello World Worker"

This example shows a plugin that identifies a "Hello World" string and a validator that confirms it.

### The Analyzer (Producer)
This tool searches for a specific string and posts a symbol hypothesis.

```python
import xbin
from xbin.sdk import _current_worker

@xbin.plugin(name="hello_finder", category="symbol_matching")
class HelloFinder:
    def on_new_binary(self, binary_path, requested_goals):
        if "symbol_matching" not in requested_goals:
            return

        with open(binary_path, "rb") as f:
            data = f.read()
            if b"Hello, World!" in data:
                # We found it! Post the result to the blackboard
                _current_worker.post_result(
                    item_key="0x401000", 
                    data="main_entry_greeting", 
                    confidence=0.8
                )

if __name__ == "__main__":
    xbin.start_worker()
```

### The Validator (Verifier)
This tool listens for the `hello_finder`'s output and vouches for it if it meets certain criteria.

```python
import xbin
from xbin.sdk import _current_worker

@xbin.plugin(name="hello_validator", category="symbol_matching", is_validator=True)
class HelloValidator:
    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        # We only care about symbol matching updates
        if category != "symbol_matching":
            return

        # If the new finding is our target string, vouch for it!
        if new_hypothesis['data'] == "main_entry_greeting":
            print(f"I agree with {new_hypothesis['backend']}!")
            _current_worker.post_validation(item_key=item_key, target_id="TOP")

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

### Callbacks (Implemented in your class)
#### `on_new_binary(self, binary_path, requested_goals)`
Called once when a binary is uploaded. Use this for initial batch analysis.
- `binary_path`: Local path to the uploaded file.
- `requested_goals`: List of category strings the user requested.

#### `on_update(self, category, item_key, new_hypothesis, top_hypothesis)`
Called every time the blackboard changes. Use this to build collaborative tools (e.g., "Once I see a CFG, start matching symbols").
- `category`: The category that was updated.
- `item_key`: The specific address or filename.
- `new_hypothesis`: The data that just arrived.
- `top_hypothesis`: The current consensus leader for this item.

### Methods (via `xbin.sdk._current_worker`)
#### `post_result(item_key, data, confidence)`
Submit a new finding. If the data is unique, it creates a new hypothesis. If it matches an existing one, it acts as a vouch.
- `item_key`: Unique subject identifier.
- `data`: Any JSON-serializable object.
- `confidence`: Your certainty (0.0 to 1.0).

#### `post_validation(item_key, target_id="TOP", confidence=1.0)`
Specifically for validators. Boosts the score of an existing hypothesis.
- `target_id`: The ID of the hypothesis to vouch for, or `"TOP"` for the leader.

#### `get_analysis(category, item_key=None)`
Manually query the current state of a blackboard.
- `category`: Category to query.
- `item_key`: (Optional) Specific address/item to fetch.
