"""Preflight checks owned by the pysindy base image.

Discovered and run by `scripts/preflight.py`, which passes a context object
carrying the shared helpers -- so this module imports nothing from the core.

The check that matters here is **staleness**. `pysindy:latest` is a derived
image: it is built `FROM bind:latest` and inherits everything from it. Rebuild
`bind:latest` without rebuilding this one and the two silently diverge -- the
plugin's Dockerfile still sets a PYTHONPATH entry that no longer resolves to
anything, and the worker dies at import with a bare ModuleNotFoundError that
says nothing about the real cause.

That is not hypothetical: it is exactly what happened when the shared
`bind_helpers` moved into the `bind:latest` base and this image was left at its
previous build.
"""
import os

IMAGE = os.environ.get("PYSINDY_IMAGE", "pysindy:latest")
BASE = os.environ.get("BIND_IMAGE", "bind:latest")

# Everything the base image is expected to carry forward from bind:latest, plus
# what it adds itself.
_INHERITED = "/opt/xbin_bind/bind_helpers.py"        # from bind:latest
_OWN = "/home/bind/pysyndy/xbin_api.py"              # the sanctioned two-verb seam

_REBUILD = "plugins/_bases/pysindy/build.sh"


def _image_missing(ctx, image):
    rc, _ = ctx.run(["docker", "image", "inspect", image], timeout=15)
    return rc != 0


def _check_image(ctx):
    missing = _image_missing(ctx, IMAGE)
    return ctx.Check(f"{IMAGE} image", ctx.WARN if missing else ctx.PASS,
                     f"missing -> {_REBUILD} (only pysindy needs it)" if missing else "present",
                     required=False)


def _check_not_stale(ctx):
    """Is the derived image older than the base it was built from?

    A newer base means this image predates whatever that rebuild changed."""
    if _image_missing(ctx, IMAGE) or _image_missing(ctx, BASE):
        return ctx.Check(f"{IMAGE} not stale", ctx.WARN, "image(s) missing", required=False)
    rc_i, img_created = ctx.run(["docker", "inspect", "-f", "{{.Created}}", IMAGE], timeout=15)
    rc_b, base_created = ctx.run(["docker", "inspect", "-f", "{{.Created}}", BASE], timeout=15)
    if rc_i != 0 or rc_b != 0:
        return ctx.Check(f"{IMAGE} not stale", ctx.WARN, "could not read image timestamps", required=False)
    img_created, base_created = img_created.strip(), base_created.strip()
    # RFC3339 with a fixed offset sorts lexicographically within one host.
    stale = img_created < base_created
    return ctx.Check(f"{IMAGE} not stale", ctx.FAIL if stale else ctx.PASS,
                     f"built {img_created} but {BASE} is newer ({base_created}) -> re-run {_REBUILD}"
                     if stale else f"newer than {BASE}",
                     required=False)


def _check_contents(ctx):
    """The two imports the pysindy worker makes must both resolve in the image.

    Cheaper and more direct than the timestamp heuristic: it catches a divergence
    however it arose."""
    if _image_missing(ctx, IMAGE):
        return ctx.Check(f"{IMAGE} contents", ctx.WARN, "image missing", required=False)
    rc, _ = ctx.run(["docker", "run", "--rm", "--entrypoint", "/bin/bash", IMAGE, "-lc",
                     f"test -f '{_INHERITED}' && test -f '{_OWN}'"], timeout=60)
    ok = rc == 0
    return ctx.Check(f"{IMAGE} contents", ctx.PASS if ok else ctx.FAIL,
                     "bind_helpers + xbin_api present" if ok
                     else f"missing {_INHERITED} or {_OWN} -> re-run {_REBUILD}",
                     required=False)


def checks(tier, ctx):
    # Not required for any tier: pysindy belongs to none (it needs a
    # non-stripped Cortex-M ELF, which the tiers' raw firmware is not). These
    # surface as warnings so a smoke run is never blocked by them.
    return [
        _check_image(ctx),
        _check_not_stale(ctx),
        _check_contents(ctx),
    ]
