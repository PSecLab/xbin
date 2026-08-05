"""Static guard: plugin decorator metadata must not drift from the categories /
backend weights the consensus engine relies on.

Imports each of the five worker modules by path (their Morpheus imports are
deferred inside on_new_binary/prepare_config, so import works without the heavy
bind:latest stack or the submodule) and inspects the Worker the @xbin.plugin
decorator created.
"""
import importlib.util
import os

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGINS = os.path.join(_REPO_ROOT, "plugins")

# Backend names that carry a weight in main.py BACKEND_WEIGHTS (unknown -> 0.5).
WEIGHTED_BACKENDS = {
    "fid", "ghidriff", "bind_se", "symbolic_regression", "pysindy", "bind_arbiter",
    "angr_cfg", "radare_cfg", "angr_boundaries", "radare_boundaries", "binja",
    "boundary_ranker", "boundary_validator", "flirt_matcher"
}

# path -> (name, category, is_ranker, is_validator)
EXPECTED = {
    "signature_matching/fid/fid_worker.py": ("fid", "signature_matching", False, False),
    "signature_matching/ghidriff/ghidriff_worker.py": ("ghidriff", "signature_matching", False, False),
    "signature_matching/bind_arbiter/arbiter_worker.py": ("bind_arbiter", "signature_matching", True, False),
    "equation_recovery/bind_se/bind_se_worker.py": ("bind_se", "equation_recovery", False, False),
    "equation_recovery/symbolic_regression/sr_worker.py": ("symbolic_regression", "equation_recovery", False, False),
    "equation_recovery/pysindy/pysindy_worker.py": ("pysindy", "equation_recovery", False, False),
    "cfg_generation/angr/angr_worker.py": ("angr_cfg", "cfg_generation", False, False),
    "cfg_generation/radare/radare_worker.py": ("radare_cfg", "cfg_generation", False, False),
    "function_boundary/angr/angr_boundary_worker.py": ("angr_boundaries", "function_boundary", False, False),
    "function_boundary/radare/radare_boundary_worker.py": ("radare_boundaries", "function_boundary", False, False),
    "function_boundary/binja/binja_boundary_worker.py": ("binja", "function_boundary", False, False),
    "function_boundary/boundary_ranker/boundary_ranker.py": ("boundary_ranker", "function_boundary", True, False),
    "function_boundary/boundary_validator/boundary_validator.py": ("boundary_validator", "function_boundary", False, True),
    "symbol_matching/flirt/flirt_worker.py": ("flirt_matcher", "symbol_matching", False, False),
}


def _load_worker(rel_path, mod_name):
    import xbin.sdk as sdk
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(PLUGINS, rel_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # runs @xbin.plugin(...) -> sets sdk._current_worker
    return sdk._current_worker


@pytest.mark.parametrize("rel_path,expected", list(EXPECTED.items()))
def test_plugin_metadata(rel_path, expected):
    name, category, is_ranker, is_validator = expected
    w = _load_worker(rel_path, f"wk_{name}")
    assert w is not None, f"{rel_path} did not register a worker"
    assert w.name == name
    assert w.category == category
    assert bool(w.is_ranker) == is_ranker
    assert bool(w.is_validator) == is_validator
    assert w.name in WEIGHTED_BACKENDS, f"{w.name} has no BACKEND_WEIGHTS entry (would fall back to 0.5)"
    assert w.display_name, "display_name should be set on the plugin decorator"


def test_registered_rankers():
    rankers = []
    for rel_path, (name, *_rest) in EXPECTED.items():
        w = _load_worker(rel_path, f"chk_{name}")
        if w.is_ranker:
            rankers.append(w.name)
    assert set(rankers) == {"bind_arbiter", "boundary_ranker"}, f"unexpected rankers: {rankers}"
