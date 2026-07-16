# xbin | The Intelligent Binary Analysis Blackboard

**xbin** is a decentralized, competitive, and collaborative orchestration framework for binary analysis. 

Instead of a monolithic analyzer, **xbin** uses a **Blackboard Architecture**. Multiple specialized analysis workers (angr, radare2, FLIRT, LLMs) "bid" on binary properties (symbols, CFGs, etc.) by posting hypotheses to a central blackboard. The orchestrator acts as a referee, calculating consensus and notifying the fleet of updates.

## 🧠 Motivation: Why xbin?

Traditional binary analysis tools are often isolated silos. **xbin** changes this by fostering an ecosystem where:
- **Tools Compete**: Multiple backends can solve the same problem (e.g., CFG generation). The blackboard uses weighted confidence to determine the "truth."
- **Tools Collaborate**: A symbol matcher can wait for a CFG generator to finish and then use that graph as context for better matching.
- **Tools Validate**: Specialized plugins can sanity-check or "vouch" for the findings of other tools, preventing "hallucinations".
- **Tools Judge**: "Ranker" plugins dynamically adjust the consensus math based on local heuristics (e.g., heavily rewarding a finding if two specific backends agree).
- **Agentic Ready**: Designed for human-in-the-loop or AI-agent arbitration when tools disagree (Conflict Resolution).
- **Reactive**: The system is entirely event-driven via Redis Pub/Sub. When a binary is uploaded, the fleet reacts instantly.

## 🚀 Features

- **Multi-Analysis Support**: Separate blackboards for `symbol_matching`, `cfg_generation`, `decompilation`, and more.
- **The Triad Architecture**: Build tools as **Producers** (Analyzers), **Verifiers** (Validators), or **Judges** (Rankers).
- **Consensus Visualizer**: Interactive Cytoscape.js graphs that show "vouches" (which tools agreed on which node/edge), checkmarks for verified results, and the active Ranker algorithm.
- **Reactive SDK**: A class-based Python SDK that abstracts away all gRPC/Docker boilerplate.
- **Dynamic Orchestration**: The orchestrator manages its own Redis and sibling plugin containers.
- **Health Monitoring**: Real-time heartbeats and visual "pulse" animations on the dashboard.

## 🛠️ Installation

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the xbin package
pip install .
```

## 🚥 Quick Start

1. **Start the Engine**:
   ```bash
   xbin-orchestrator
   ```
2. **Access the Dashboard**: Open `http://localhost:8000` in your browser.
3. **Deploy the Fleet**: Use the "Plugin Manager" sidebar to start tools like `angr_cfg` or `radare_cfg`.
4. **Analyze**: Upload a binary, select your goals, and watch the blackboard populate in real-time.

## 🧩 External Plugins

Plugins do not have to live in this repo. Point the orchestrator at a plugin
checked out anywhere and it discovers it from the `@xbin.plugin` decorator,
injecting the SDK into the build for you:

```bash
xbin-orchestrator --plugin ~/xbin_external_example     # one plugin
xbin-orchestrator --plugin-dir ~/my-plugins            # a tree of them
```

See [xbin_external_example](https://github.com/PSecLab/xbin_external_example)
for a minimal standalone plugin repo.

A plugin whose image is too heavy for the orchestrator to build (e.g. one
extending a licensed Binary Ninja base) can ship a `.xbin-prebuilt` marker and
its own `build.sh`. The orchestrator then reuses the existing image and skips
the build entirely.

## 🚥 Running an Analysis (end to end)

> 💡 **No binary handy?** A ready-to-use `sample.elf` is bundled in [`examples/`](examples/).

1. **Start the engine** and open the dashboard:
   ```bash
   xbin-orchestrator        # → http://localhost:8000
   ```
2. **Load the binary** — *Choose Binary*.
3. **Select goals** — tick **Boundaries** (`function_boundary`) and
   **Symbols** (`symbol_matching`).
4. **Start the plugins** — e.g. `angr_boundaries` and `radare_boundaries`
   (boundaries) and `flirt_matcher` (symbols), plus any others you want
   competing. Add `--plugin <path>` at startup to bring in external ones.
5. **Start Analysis** 🚀 — the fleet reacts and the blackboard fills in.

## 👩‍💻 How to Add Your Own Tool

The `xbin` SDK makes it trivial to wrap any analysis script into a containerized worker. For a detailed guide and a "Hello World" example, see the **[SDK Reference Guide](docs/sdk_reference.md)**.

### 1. Write the Worker (Quick Example)
```python
import xbin

@xbin.plugin(name="my_analyzer", category="symbol_matching")
class MyAnalyzer:
    def on_new_binary(self, binary_path, requested_goals):
        from xbin.sdk import _current_worker
        _current_worker.post_result(item_key="0x401000", data="main", confidence=0.9)

if __name__ == "__main__":
    xbin.start_worker()
```

### 2. Containerize It
Add a simple `Dockerfile` in your tool's directory:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install xbin-orchestrator
COPY . .
CMD ["python", "my_worker.py"]
```

### 3. Register
Drop your folder into `plugins/<category>/`. The orchestrator will automatically find it and show a **Start** button on the dashboard.

## 📦 Out-of-Tree Plugins

You don't have to keep your plugins inside the `xbin` repository. You can develop them in their own standalone repositories and point the orchestrator to them:

```bash
# Load a standalone plugin folder
xbin-orchestrator --plugin /path/to/my_standalone_tool

# Load a collection of plugins from an external directory
xbin-orchestrator --plugin-dir /path/to/my_plugin_repo
```

When running out-of-tree:
- **Category Inference**: The orchestrator scans your code for `@xbin.plugin(category="...")`.
- **SDK Injection**: \`xbin\` automatically injects the SDK into the build context—no need to manually copy files.
- **Explicit Docker**: You must provide a \`Dockerfile\` in your plugin directory for dependency management.

## 🧪 Testing

The project includes an automated integration test suite using `pytest`. The tests verify the core Blackboard logic, including Analyzer submissions, Validator vouching, and Ranker overrides.

To run the test suite:
```bash
# Ensure pytest is installed
pip install pytest

# Run the suite
pytest tests/ -v
```
The test suite automatically spins up a background Orchestrator and isolated Redis instance for the duration of the run.

## 📡 The RPC Scheme

We use a generalized schema to support any type of analysis without changing the core protocol.

### gRPC Service
Defined in `orchestrator.proto`:
```protobuf
message PostResultRequest {
  string analysis_type = 1; // e.g. "cfg_generation"
  string item_key      = 2; // Unique identifier for the subject (e.g. filename)
  string result_data   = 3; // JSON-encoded analysis payload
  float confidence     = 4; // 0.0 to 1.0
  string backend_name  = 5; // e.g. "angr_cfg"
}
```

### Data Standards
To enable competition and consensus, tools in the same category should follow a shared JSON schema for `result_data`. 
- **`cfg_generation`**: Should return a graph with `nodes` and `edges` lists.
- **`symbol_matching`**: Should return a string or object representing the symbol name.

---
📣 **Feedback Welcome!**
Our RPC and JSON schemes are evolving. If you have suggestions for better multi-tool data structures (especially for lifters and data-flow), please open an issue or reach out!

## 🏗️ Architecture

- **Orchestrator**: FastAPI (REST/Web) + gRPC (Worker Comm) + Docker CLI (Container Management).
- **SDK**: A reactive wrapper using Redis Pub/Sub for events and gRPC for reporting.
- **Blackboard**: Redis-backed global state with per-category hypothesis tracking.

## License
MIT
