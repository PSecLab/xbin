# `fid` — Ghidra Function ID

Matches functions in the target against Ghidra's Function ID databases, posting
a known-function identity per address to `signature_matching`.

High-precision identity matching, so it carries the category's top consensus
weight (`1.0`). Where `fid` and `ghidriff` post identical data they deduplicate
onto one hypothesis, which is what produces the ✓ / "+N vouches" marker.

- **Base image:** `bind:latest` — see [`../../_bases/bind/`](../../_bases/bind/README.md)
- **Tiers:** `smoke`, `full`, `heavy`
- **Extra services:** none (no LLM, no emulator) — which is what makes it half of the smoke tier
- **Reference:** the FID database is baked into the base image; no upload needed

```bash
plugins/_bases/bind/build.sh     # once
scripts/e2e.sh smoke             # fid + ghidriff end to end
```
