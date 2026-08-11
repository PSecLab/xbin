"""The layering invariant, as an executable test.

xbin's core contract is that the orchestrator, the SDK, the client library and
the shared harness know nothing about any particular analysis tool. Plugins
declare what they need (`xbin-plugin.toml`, their own build scripts, their own
preflight checks) and the core reads those declarations generically.

That property is easy to state and easy to erode -- one convenient `if backend
== "..."` and the framework quietly becomes a monolith again. This test makes
the erosion fail CI instead of surviving review.

If a tool name legitimately belongs in one of these files (documentation prose
naming an example, say), add it to ALLOWED with a reason. Do not widen the
pattern.
"""
import os
import re

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Trees and files that must stay tool-agnostic.
#
# `tests/` as a whole is deliberately NOT here: a test legitimately names a
# concrete backend when it constructs a scenario ("post as fid, then as bind_se,
# assert the ordering"). What must stay generic is the shared harness that moved
# in from scripts/ -- it derives its tiers from the manifests and must never
# grow a tool name -- so that one file is listed explicitly.
CORE_PATHS = ["src", "docs", "Makefile", "docker-compose.yml", "pyproject.toml",
              "Dockerfile", os.path.join("tests", "e2e_driver.py")]

# Names of specific analysis tools, base images and vendor stacks. A hit in a
# core file means plugin knowledge has leaked out of plugins/.
#
# The boundaries are (?<![A-Za-z0-9]) rather than \b on purpose: \b treats `_`
# as a word character, so `\bangr\b` silently fails to match `angr_cfg` -- which
# is exactly the form a leaked plugin name usually takes.
TOOL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(bind_se|bind_arbiter|bind_helpers|bind:latest|morpheus|pysyndy|pysindy"
    r"|ghidriff|symbolic_regression|flirt|binja|binaryninja|ghidra|qemu|fastdyn|angr|radare"
    r"|r2pipe|pysr|arducopter|betaflight|bindonly)(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Text files only; skip generated stubs, build artifacts and caches. (*.egg-info
# is regenerated from README.md by `pip install -e .` and is gitignored.)
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}
SKIP_SUFFIXES = (".egg-info",)
SKIP_FILES = {"orchestrator_pb2.py", "orchestrator_pb2_grpc.py"}

# path -> reason. Keep this list short and justified.
ALLOWED = {}


def _iter_core_files():
    for rel in CORE_PATHS:
        path = os.path.join(_REPO_ROOT, rel)
        if os.path.isfile(path):
            yield rel, path
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs
                       if d not in SKIP_DIRS and not d.endswith(SKIP_SUFFIXES)]
            for f in sorted(files):
                if f in SKIP_FILES or f.endswith((".pyc", ".so", ".bin", ".elf")):
                    continue
                full = os.path.join(root, f)
                yield os.path.relpath(full, _REPO_ROOT), full


CORE_FILES = sorted(_iter_core_files())


@pytest.mark.parametrize("rel,path", CORE_FILES, ids=[r for r, _p in CORE_FILES])
def test_core_file_names_no_tool(rel, path):
    if rel in ALLOWED:
        pytest.skip(f"allowlisted: {ALLOWED[rel]}")
    try:
        text = open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        pytest.skip("not a readable text file")

    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        m = TOOL_PATTERN.search(line)
        if m:
            hits.append(f"  {rel}:{i}: {line.strip()[:110]}")

    assert not hits, (
        f"{rel} names specific analysis tools; that knowledge belongs in the "
        f"owning plugin under plugins/:\n" + "\n".join(hits[:10])
        + (f"\n  ... and {len(hits) - 10} more" if len(hits) > 10 else "")
    )


def test_sdk_package_holds_no_plugin_helpers():
    """src/xbin/ is injected into *every* plugin build context, so anything
    added here ships inside unrelated plugin images."""
    sdk_dir = os.path.join(_REPO_ROOT, "src", "xbin")
    modules = {f for f in os.listdir(sdk_dir) if f.endswith(".py")}
    assert modules == {"__init__.py", "sdk.py"}, (
        f"unexpected modules in the SDK package: {sorted(modules - {'__init__.py', 'sdk.py'})}. "
        "Tool-specific helpers belong to the plugin (or its base bundle under "
        "plugins/_bases/), not to the SDK every plugin image carries."
    )
