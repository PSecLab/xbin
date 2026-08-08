# `cfg_generation`

Plugins in this category answer **"what is this binary's control flow?"** by
generating a Control Flow Graph for the uploaded target. Tools here compete: they
post to the same blackboard for the same item key and the orchestrator scores
them against each other.

By convention `result_data` is a graph with `nodes` and `edges` lists.

| Plugin | Backend | Weight |
|---|---|---|
| [`angr/`](angr/README.md) | angr | 0.90 |
| [`radare/`](radare/README.md) | radare2 (r2pipe) | 0.85 |
