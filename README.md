# xbin | The Intelligent Binary Analysis Blackboard

**xbin** is a decentralized, competitive, and collaborative orchestration framework for binary analysis. 

Instead of a monolithic analyzer, **xbin** uses a **Blackboard Architecture**. Multiple specialized analysis workers (angr, radare2, FLIRT, LLMs) "bid" on binary properties (symbols, CFGs, etc.) by posting hypotheses to a central blackboard. The orchestrator acts as a referee, calculating consensus and notifying the fleet of updates.

## 🧠 Motivation: Why xbin?

Traditional binary analysis tools are often isolated silos. **xbin** changes this by fostering an ecosystem where:
- **Tools Compete**: Multiple backends can solve the same problem (e.g., CFG generation). The blackboard uses weighted confidence to determine the "truth."
- **Tools Collaborate**: A symbol matcher can wait for a CFG generator to finish and then use that graph as context for better matching.
- **Agentic Ready**: Designed for human-in-the-loop or AI-agent arbitration when tools disagree (Conflict Resolution).
- **Reactive**: The system is entirely event-driven via Redis Pub/Sub. When a binary is uploaded, the fleet reacts instantly.

## 🚀 Features

- **Multi-Analysis Support**: Separate blackboards for `symbol_matching`, `cfg_generation`, `decompilation`, and more.
- **Consensus Visualizer**: Interactive Cytoscape.js graphs that show "vouches" (which tools agreed on which node/edge).
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

## 👩‍💻 How to Add Your Own Tool

The `xbin` SDK makes it trivial to wrap any analysis script into a containerized worker.

### 1. Write the Worker
Create a Python file using the `@xbin.plugin` decorator:

```python
import xbin

@xbin.plugin(name="my_custom_tool", category="symbol_matching")
class MyWorker:
    def on_new_binary(self, binary_path):
        # 1. Logic: Open file and analyze
        # 2. Result: Post to blackboard
        from xbin.sdk import _current_worker
        _current_worker.post_result(
            item_key="0x401000", 
            data="my_guessed_symbol", 
            confidence=0.95
        )

    def on_update(self, category, item_key, top_hypothesis):
        # Optional: React when other tools post results
        if category == "cfg_generation" and top_hypothesis['score'] > 0.8:
            print(f"I see a high-conf CFG for {item_key}, let me use it!")

if __name__ == "__main__":
    xbin.start_worker()
```

### 2. Containerize It
Add a simple `Dockerfile` in your tool's directory:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install xbin-orchestrator  # Or copy local src
COPY . .
CMD ["python", "my_worker.py"]
```

### 3. Register
Drop your folder into `plugins/<category>/`. The orchestrator will automatically find it and show a **Start** button on the dashboard.

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
