# `ghidriff` — Ghidra binary diffing

Diffs the target against a symbolized reference build using ghidriff/BSim and
posts the matched identity per function address to `signature_matching`.

- **Base image:** `bind:latest` — see [`../../_bases/bind/`](../../_bases/bind/README.md)
- **Tiers:** `smoke`, `full`, `heavy`
- **Extra services:** none
- **Reference:** uses `<binary-stem>.reference` next to the uploaded target when
  present (the orchestrator writes it from the upload form); otherwise the
  reference baked into the base image.

```bash
scripts/e2e.sh smoke
```
