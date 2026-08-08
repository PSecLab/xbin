# `bind_arbiter` — LLM arbiter (ranker)

The **ranker** for `signature_matching`. When several tools post competing
identifications for the same function, the arbiter reconciles them via a local
ollama endpoint and sets the winning hypothesis's score outright.

Rankers are the only components allowed to change scores or ordering; verifiers
attach stamps and producers only post. See
[`docs/architecture.md`](../../../docs/architecture.md).

- **Base image:** `bind:latest` — see [`../../_bases/bind/`](../../_bases/bind/README.md)
- **Tiers:** `full`, `heavy`
- **Extra services:** ollama on `:11434` with `qwen2.5-coder:7b`. Workers run
  with `--network host`, so a host ollama is reachable at `127.0.0.1:11434`.

With the arbiter running, the category card shows a **`Ranker: bind_arbiter`**
badge; without it, the category falls back to the baseline consensus math.
