# `libxbin` — Python Frontend Client Library

`libxbin` is the official Python client library for interacting programmatically with the **xbin Multi-Analysis Blackboard Orchestrator**. 

With `libxbin`, external python scripts, CI pipelines, and automated reverse-engineering workflows can announce binaries, control plugin workers, retrieve consensus CFGs and function boundaries, and query blackboard hypotheses directly.

---

## 📦 Installation

`libxbin` is automatically installed when you install the `xbin-orchestrator` package:

```bash
pip install -e .
```

You can import it in any script via:

```python
import libxbin
```

---

## 🚀 Quick Start

### 1. Connecting to the Orchestrator

```python
import libxbin

client = libxbin.connect("http://localhost:8000")

if client.is_ready():
    print("Connected to xbin orchestrator!")
```

### 2. Submitting a Binary for Analysis

```python
# Upload binary and request specific analysis goals
job = client.analyze(
    "firmware.elf",
    goals=["cfg_generation", "function_boundary", "signature_matching"],
    reference_path="reference_arducopter.elf"  # Optional reference binary
)

print(f"Submitted job for {job.filename}")

# Wait for analysis results (blocks up to 60s)
results = job.wait_for_results(timeout=60)
```

### 3. Reading Blackboard Hypotheses & Consensus Data

```python
# Fetch recovered function boundaries
boundaries = client.get_function_boundaries()
for b in boundaries:
    print(f"Function at {b.addr} (size: {b.size}b, hint: {b.name_hint})")

# Fetch consensus CFG for a function address
cfg = client.get_cfg("0x400000")
print(f"CFG Nodes: {len(cfg.nodes)}, Edges: {len(cfg.edges)}")
for edge_id, edge in cfg.edges.items():
    print(f"  {edge.source} -> {edge.target} (Confidence: {edge.avg_confidence*100:.0f}%)")

# Fetch all signature matching hypotheses
blackboard = client.get_blackboard("signature_matching")
for addr, item in blackboard.items():
    top = item.top_hypothesis
    print(f"Address {addr}: {top.backend} matched {top.data.get('known_function')} (Score: {top.score})")
```

### 4. Controlling Plugin Fleet

```python
# List discovered plugins and status
plugins = client.list_plugins()
for p in plugins:
    print(f"Plugin {p.name} [{p.category}] - {p.status}")

# Start or stop specific plugins
client.start_plugin("angr_cfg", "cfg_generation")
client.stop_plugin("radare_cfg", "cfg_generation")

# Start all plugins for a specific category
client.bulk_start("function_boundary")
```

---

## 📚 API Reference Summary

| Method / Property | Description |
| :--- | :--- |
| `libxbin.connect(url, grpc_target)` | Factory function returning an `XbinClient` instance |
| `client.is_ready()` | Returns `True` if orchestrator is online |
| `client.health()` | Returns orchestrator and worker fleet health metadata |
| `client.list_plugins()` | Returns a list of `PluginInfo` objects |
| `client.start_plugin(name, category)` | Starts a worker plugin |
| `client.stop_plugin(name, category)` | Stops a worker plugin |
| `client.bulk_start(category=None)` | Bulk starts plugins |
| `client.bulk_stop(category=None)` | Bulk stops plugins |
| `client.analyze(path, goals=..., ...)` | Submits a binary for analysis and returns an `AnalysisJob` |
| `job.wait_for_results(timeout=60)` | Blocks until results populate on blackboard |
| `client.get_blackboard(category)` | Returns a dictionary of `BlackboardItem` objects for a category |
| `client.get_cfg(item_key)` | Returns `ConsensusCFG` with nodes & edges |
| `client.get_function_boundaries()` | Returns a list of sorted `FunctionBoundary` objects |
| `client.get_summary(category, item_key)` | Returns human-readable Ollama summary |
| `client.get_audit_trail(category)` | Returns raw audit trail logs for a category |
| `client.get_system_logs()` | Returns orchestrator system logs |
| `client.clear_session()` | Flushes blackboard data and resets session |

---

> [!IMPORTANT]
> **Schema & Binding Synchronization**:
> If you update or extend the underlying gRPC protocol (`orchestrator.proto`), REST API routes, or blackboard category JSON payload schemas (`result_data`), you **MUST** update the corresponding Python datatypes and bindings in `libxbin` ([`src/libxbin/models.py`](../src/libxbin/models.py) and [`src/libxbin/client.py`](../src/libxbin/client.py)) so that external scripts and integrations remain synchronized with the orchestrator.
