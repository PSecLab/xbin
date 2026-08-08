# hello_plugin — a template xbin plugin

The smallest thing that is a real plugin: a worker, a Dockerfile, and a manifest.
Copy the directory, rename the three, and you have a new tool.

```
hello_worker.py     @xbin.plugin class + xbin.start_worker()
Dockerfile          required -- discovery keys on this exact filename
xbin-plugin.toml    manifest: consensus weight, tiers, cache mounts
```

## Run it out-of-tree

The point of this example is that a plugin does not have to live in `plugins/`:

```bash
xbin-orchestrator --plugin examples/hello_plugin:symbol_matching
```

It appears on the dashboard with a **Start** button like any in-tree plugin.
`--plugin-dir <path>` loads a whole tree of them.

## Then what

- Change `category` to the question your tool answers. Tools sharing a category
  compete on the blackboard, so match an existing one where it fits.
- Make it a **verifier** (`is_validator=True`) or a **ranker** (`is_ranker=True`)
  by implementing `on_update(...)` instead — see
  [`../../plugins/AGENTS.md`](../../plugins/AGENTS.md).
- Full guide: [`docs/sdk_reference.md`](../../docs/sdk_reference.md).
