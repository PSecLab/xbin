"""Preflight checks owned by the BIND base image.

Discovered and run by `xbin_orchestrator/preflight.py`, which passes a context object
carrying the shared helpers -- so this module imports nothing from the core and
can be moved out-of-tree with the rest of the bundle.

These are the prerequisites the BIND plugin family adds on top of a generic xbin
deployment: the heavy `bind:latest` base, the QEMU/FastDyn stack inside it, the
local LLM the semantic tools and the arbiter call, and the test firmware.

Each check carries its own remediation string, so the pointer to ./rebuild.sh
lives next to rebuild.sh instead of in the core preflight runner.
"""
import json
import os
import urllib.request

BIND_IMAGE = os.environ.get("BIND_IMAGE", "bind:latest")
QEMU_BIN = "/home/bind/Morpheus/qemu/build/qemu-system-arm"
FASTDYN_SO = "/home/bind/Morpheus/qemu/build/tests/tcg/plugins/libvirtual.so"
OLLAMA_URL = os.environ.get("OLLAMA_TAGS_URL", "http://127.0.0.1:11434/api/tags")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DEFAULT_BINARY = os.environ.get(
    "XBIN_TEST_BINARY",
    os.path.join(REPO_ROOT, "submodules", "Morpheus", "example_config", "gs3.bin"),
)

# Tiers this bundle knows how to reason about. `heavy` is the only one that
# needs the emulator; `full` and above need the LLM.
_QEMU_TIERS = ("heavy",)
_OLLAMA_TIERS = ("full", "heavy")

_REBUILD = "plugins/_bases/bind/rebuild.sh"


def _check_bind_image(ctx):
    rc, _ = ctx.run(["docker", "image", "inspect", BIND_IMAGE], timeout=15)
    return ctx.Check(f"{BIND_IMAGE} image", ctx.PASS if rc == 0 else ctx.FAIL,
                     "present" if rc == 0 else f"missing -> {_REBUILD}")


def _check_qemu_in_base(ctx, tier):
    required = tier in _QEMU_TIERS
    rc, _ = ctx.run(["docker", "image", "inspect", BIND_IMAGE], timeout=15)
    if rc != 0:
        return ctx.Check(f"QEMU in {BIND_IMAGE}", ctx.FAIL if required else ctx.WARN,
                         "base image missing", required=required)
    rc, _ = ctx.run(["docker", "run", "--rm", "--entrypoint", "/bin/bash", BIND_IMAGE, "-lc",
                     f"test -f '{QEMU_BIN}' && test -f '{FASTDYN_SO}'"], timeout=60)
    ok = rc == 0
    return ctx.Check(f"QEMU in {BIND_IMAGE}", ctx.PASS if ok else (ctx.FAIL if required else ctx.WARN),
                     "qemu-system-arm+libvirtual present" if ok
                     else f"missing -> {_REBUILD} (needed for the dynamic-run plugins)",
                     required=required)


def _check_bind_helpers(ctx):
    """The thin xbin layer must be on top of the Morpheus stage.

    A base built before the two-stage split (or a stage-1 image mistakenly
    tagged bind:latest) analyses fine but every BIND worker dies on
    `import bind_helpers`, which is a confusing failure to debug from the
    container logs."""
    rc, _ = ctx.run(["docker", "image", "inspect", BIND_IMAGE], timeout=15)
    if rc != 0:
        return ctx.Check("bind_helpers in base", ctx.WARN, "base image missing", required=False)
    rc, _ = ctx.run(["docker", "run", "--rm", "--entrypoint", "/bin/bash", BIND_IMAGE, "-lc",
                     "test -f /opt/xbin_bind/bind_helpers.py"], timeout=60)
    ok = rc == 0
    return ctx.Check("bind_helpers in base", ctx.PASS if ok else ctx.FAIL,
                     "/opt/xbin_bind present" if ok
                     else "missing -> plugins/_bases/bind/build.sh --helpers-only")


def _check_ollama(ctx, tier):
    required = tier in _OLLAMA_TIERS
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("name", "") for m in data.get("models", [])]
        ok = any(OLLAMA_MODEL in m for m in models)
        return ctx.Check("ollama + model", ctx.PASS if ok else (ctx.FAIL if required else ctx.WARN),
                         f"{OLLAMA_MODEL} present" if ok else f"model missing (have: {models})",
                         required=required)
    except Exception as e:
        return ctx.Check("ollama + model", ctx.FAIL if required else ctx.WARN,
                         f"unreachable ({e}); the smoke tier does not need it", required=required)


def _check_test_binary(ctx):
    ok = os.path.exists(DEFAULT_BINARY)
    return ctx.Check("test binary", ctx.PASS if ok else ctx.WARN,
                     DEFAULT_BINARY if ok
                     else f"not found: {DEFAULT_BINARY} (run plugins/_bases/bind/stage.sh)",
                     required=False)


def _check_outdated_instance(ctx):
    # Warn if a container is still running on an outdated (no-QEMU) base.
    rc, out = ctx.run(["docker", "ps", "-q", "--filter", f"ancestor={BIND_IMAGE}"], timeout=15)
    if rc == 0 and out.strip():
        rc2, _ = ctx.run(["docker", "run", "--rm", "--entrypoint", "/bin/bash", BIND_IMAGE, "-lc",
                          f"test -f '{QEMU_BIN}'"], timeout=60)
        if rc2 != 0:
            return ctx.Check("no outdated instance", ctx.WARN,
                             f"a container is running on a no-QEMU {BIND_IMAGE} -> {_REBUILD} kills it",
                             required=False)
    return ctx.Check("no outdated instance", ctx.PASS, "none", required=False)


def checks(tier, ctx):
    return [
        _check_bind_image(ctx),
        _check_bind_helpers(ctx),
        _check_qemu_in_base(ctx, tier),
        _check_ollama(ctx, tier),
        _check_test_binary(ctx),
        _check_outdated_instance(ctx),
    ]
