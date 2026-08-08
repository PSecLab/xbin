# `binja` — Binary Ninja function boundary discovery

Discovers function boundaries with Binary Ninja and posts them to
`function_boundary`.

- **Weight:** `1.0`
- **Prebuilt:** yes — this plugin carries a `.xbin-prebuilt` marker

## Why it is prebuilt

The image bakes in a ~1.2 GB Binary Ninja install **and a license**, which the
orchestrator cannot build for you. The `.xbin-prebuilt` marker tells it to reuse
the existing image and skip the build entirely; if the image is missing it fails
with a pointer back here.

```bash
cp build.conf.example build.conf     # then fill in your Binary Ninja paths
./build.sh                           # -> xbin-plugin-function_boundary-binja
```

To rebuild: re-run `./build.sh`, or
`docker rmi xbin-plugin-function_boundary-binja` first.

`build.conf` is gitignored — it names a local install and license, so only
`build.conf.example` is tracked. Keep the resulting image local; never push it.

This plugin is the reference example for the prebuilt pattern — see
[`../../AGENTS.md`](../../AGENTS.md).
