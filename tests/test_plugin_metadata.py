"""Static guard: a plugin's three descriptions of itself must agree.

Every in-tree plugin describes itself in three places -- the directory it sits
in, the `@xbin.plugin(...)` decorator in its worker, and its `xbin-plugin.toml`
manifest. The orchestrator reads all three (manifest > decorator > directory),
so a disagreement between them is a silently-wrong deployment: results get
scored under one backend name and displayed under another.

Rather than restating the plugin roster here -- which made this file a second
place to update on every plugin change -- the roster is discovered from the
manifests, and the assertions check the three sources against each other.

Worker modules import cleanly without their heavy analysis stacks: every such
import is deferred inside on_new_binary/prepare_config. Base-image bundles under
plugins/_bases/ are on sys.path so `import bind_helpers` and friends resolve.
"""
import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGINS = os.path.join(_REPO_ROOT, "plugins")
BASES = os.path.join(PLUGINS, "_bases")

sys.path.insert(0, os.path.join(_REPO_ROOT, "src", "xbin_orchestrator"))
from plugin_manifest import (DEFAULT_WEIGHT, MANIFEST_NAME,  # noqa: E402
                             iter_plugin_dirs, read_manifest)

# Shared helper modules that base bundles bake into their images live beside the
# build scripts, not in the SDK -- put them on sys.path so a worker that imports
# one can still be loaded here without Docker.
if os.path.isdir(BASES):
    for _b in sorted(os.listdir(BASES)):
        _p = os.path.join(BASES, _b)
        if os.path.isdir(_p):
            sys.path.insert(0, _p)


def _worker_files(plugin_dir):
    return sorted(f for f in os.listdir(plugin_dir)
                  if f.endswith(".py") and "@xbin.plugin" in
                  open(os.path.join(plugin_dir, f), encoding="utf-8", errors="ignore").read())


def _discover():
    """(plugin_dir, manifest, worker_file) for every in-tree plugin."""
    found = []
    for root in sorted(iter_plugin_dirs([PLUGINS])):
        manifest = read_manifest(root)
        workers = _worker_files(root)
        found.append((root, manifest, workers[0] if workers else None))
    return found


DISCOVERED = _discover()
IDS = [os.path.relpath(d, PLUGINS) for d, _m, _w in DISCOVERED]


def _load_worker(plugin_dir, worker_file, mod_name):
    import xbin.sdk as sdk
    sdk._current_worker = None
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(plugin_dir, worker_file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # runs @xbin.plugin(...) -> sets sdk._current_worker
    return sdk._current_worker


def test_some_plugins_discovered():
    assert DISCOVERED, "no plugins discovered under plugins/ -- discovery itself is broken"


@pytest.mark.parametrize("plugin_dir,manifest,worker_file", DISCOVERED, ids=IDS)
def test_every_plugin_has_a_manifest(plugin_dir, manifest, worker_file):
    assert manifest, (
        f"{os.path.relpath(plugin_dir, _REPO_ROOT)} has no readable {MANIFEST_NAME}. "
        "Without one the plugin falls back to the default consensus weight "
        f"({DEFAULT_WEIGHT}) and belongs to no e2e tier."
    )
    assert manifest.get("name"), f"{MANIFEST_NAME} must declare `name`"
    assert manifest.get("category"), f"{MANIFEST_NAME} must declare `category`"


@pytest.mark.parametrize("plugin_dir,manifest,worker_file", DISCOVERED, ids=IDS)
def test_manifest_matches_decorator(plugin_dir, manifest, worker_file):
    assert worker_file, f"{plugin_dir} has a Dockerfile but no @xbin.plugin worker"
    w = _load_worker(plugin_dir, worker_file, f"wk_{manifest.get('name', 'x')}")
    assert w is not None, f"{worker_file} did not register a worker"
    assert w.name == manifest["name"], (
        f"decorator name={w.name!r} but {MANIFEST_NAME} says {manifest['name']!r}")
    assert w.category == manifest["category"], (
        f"decorator category={w.category!r} but {MANIFEST_NAME} says {manifest['category']!r}")


@pytest.mark.parametrize("plugin_dir,manifest,worker_file", DISCOVERED, ids=IDS)
def test_manifest_weight_is_sane(plugin_dir, manifest, worker_file):
    weight = manifest.get("weight")
    assert weight is not None, (
        f"{MANIFEST_NAME} declares no `weight`; the backend would silently score "
        f"at the {DEFAULT_WEIGHT} fallback")
    assert 0.0 <= float(weight) <= 1.0, f"weight {weight} outside [0, 1]"


@pytest.mark.parametrize("plugin_dir,manifest,worker_file", DISCOVERED, ids=IDS)
def test_declared_mounts_are_well_formed(plugin_dir, manifest, worker_file):
    """A mount the core silently drops is worse than one that fails loudly: the
    plugin starts, loses its cache every restart, and nothing says why."""
    from plugin_manifest import manifest_mounts
    declared = manifest.get("mounts", []) or []
    accepted = list(manifest_mounts(manifest, "/tmp/cache"))
    assert len(accepted) == len(declared), (
        f"{len(declared) - len(accepted)} of {len(declared)} [[mounts]] were rejected -- "
        "`cache` must be a plain directory name and `target` an absolute path")


def test_no_duplicate_backend_names():
    """Two plugins sharing a backend name collide in BACKEND_WEIGHTS and in the
    blackboard's per-backend accounting."""
    seen = {}
    for plugin_dir, manifest, _w in DISCOVERED:
        name = manifest.get("name")
        if not name:
            continue
        assert name not in seen, f"backend name {name!r} claimed by both {seen[name]} and {plugin_dir}"
        seen[name] = plugin_dir
