#!/usr/bin/env python3
"""Preflight readiness checker for the xbin end-to-end pipeline.

Stdlib-only so it runs on a bare `python3` BEFORE any venv exists (checking for
the venv/deps is one of its jobs). Prints an aligned PASS/FAIL/WARN table and
exits nonzero if any *required* check for the chosen tier fails.

The core checks here are the ones that hold for any xbin deployment: docker, a
reachable redis, free (or held) orchestrator ports, and the python deps.

Anything tool-specific -- "is this base image built", "is that model pulled",
"is the emulator inside the image" -- belongs to the plugin that needs it. Drop
a `preflight_checks.py` next to a plugin (or in a `plugins/_bases/*/` bundle)
exposing:

    def checks(tier: str, ctx) -> list[Check]

and this runner discovers and calls it. `ctx` hands over the helpers
(`ctx.run`, `ctx.port_open`, `ctx.Check`, `ctx.PASS/FAIL/WARN`, `ctx.repo_root`)
so a plugin check needs no imports of its own. Each check carries its own
remediation string, so the fix travels with the tool instead of living here.

Three ways in, all running the same `run_checks()`:

  pytest -m preflight --e2e-tier heavy     # the standard route
  xbin-preflight --tier heavy              # console script, after `pip install -e .`
  PYTHONPATH=src python3 -m xbin_orchestrator.preflight --tier heavy

The third exists because this module is **stdlib-only on purpose**: it has to be
able to run on a bare `python3` in a fresh clone, where reporting "you have no
venv and no pytest" is one of its jobs. Keep it dependency-free -- adding an
import from the rest of the package, or anything third-party, breaks that.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import traceback

# src/xbin_orchestrator/ -> repo root is two levels up. Mirrors the same
# computation in main.py, and keeps the plugin walk working from a checkout.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.environ.get("XBIN_PLUGINS_DIR") or os.path.join(REPO_ROOT, "plugins")
PLUGIN_CHECKS_FILE = "preflight_checks.py"

GRPC_PORT = 50051
REST_PORT = 8000

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


class Check:
    def __init__(self, name, result, detail="", required=True):
        self.name, self.result, self.detail, self.required = name, result, detail, required


def _run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except Exception as e:
        return 1, str(e)


def _port_open(port, host="localhost"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


class Context:
    """Handed to every plugin-provided `checks(tier, ctx)`."""
    Check = Check
    PASS, FAIL, WARN = PASS, FAIL, WARN
    run = staticmethod(_run)
    port_open = staticmethod(_port_open)
    repo_root = REPO_ROOT


# --------------------------------------------------------------------------
# Core checks -- true of any xbin deployment, whatever plugins are installed.
# --------------------------------------------------------------------------

def check_docker():
    rc, out = _run(["docker", "version", "--format", "{{.Server.Version}}"], timeout=15)
    return Check("docker daemon", PASS if rc == 0 else FAIL,
                 out.strip() if rc == 0 else "docker not reachable")


def check_redis():
    if not _port_open(6379):
        return Check("redis :6379", FAIL, "not listening")
    if shutil.which("redis-cli"):
        rc, out = _run(["redis-cli", "-p", "6379", "ping"], timeout=10)
        if "PONG" not in out:
            return Check("redis :6379", FAIL, f"ping -> {out.strip()}")
    return Check("redis :6379", PASS, "PONG")


def check_ports(attach):
    # For boot mode the orchestrator must bind :8000/:50051 (must be free).
    # For --attach an orchestrator is expected to already hold them.
    busy = [p for p in (REST_PORT, GRPC_PORT) if _port_open(p)]
    if attach:
        ok = len(busy) == 2
        return Check("orchestrator ports", PASS if ok else WARN,
                     f"in use: {busy} (attach expects a running orchestrator)", required=False)
    ok = not busy
    return Check("orchestrator ports free", PASS if ok else FAIL,
                 "8000/50051 free" if ok else f"in use: {busy} (stop the running orchestrator)")


def check_python_deps():
    missing = [m for m in ("fastapi", "redis", "grpc", "uvicorn", "requests", "pytest")
               if importlib.util.find_spec(m) is None]
    if not missing:
        return Check("python deps", PASS, f"{sys.executable}")
    return Check("python deps", FAIL, f"missing {missing} -> make setup")


# --------------------------------------------------------------------------
# Plugin-contributed checks
# --------------------------------------------------------------------------

def _load_module(path):
    spec = importlib.util.spec_from_file_location(
        "xbin_preflight_" + os.path.basename(os.path.dirname(path)), path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_plugin_checks(tier, plugins_dir=PLUGINS_DIR):
    """Run every `preflight_checks.py` found under the plugins tree.

    A plugin whose check module is broken produces a WARN rather than taking the
    whole preflight down -- a bad check should not be able to block a run that
    does not involve that plugin."""
    results = []
    if not os.path.isdir(plugins_dir):
        return results
    for root, _dirs, files in os.walk(plugins_dir):
        if PLUGIN_CHECKS_FILE not in files:
            continue
        path = os.path.join(root, PLUGIN_CHECKS_FILE)
        label = os.path.relpath(root, plugins_dir)
        try:
            module = _load_module(path)
            produced = module.checks(tier, Context) if module and hasattr(module, "checks") else []
            results.extend(c for c in produced if isinstance(c, Check))
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            results.append(Check(f"{label} checks", WARN,
                                 f"check module failed to run: {e}", required=False))
    return results


def run_checks(tier="smoke", attach=False):
    """Every readiness check for `tier`: the core ones, then each plugin's.

    Importable so the pytest surface (tests/test_preflight.py) reports one test
    per check without re-implementing any of this, and so the table printer in
    main() has no logic of its own.
    """
    checks = [
        check_docker(),
        check_redis(),
        check_ports(attach),
        check_python_deps(),
    ]
    checks.extend(discover_plugin_checks(tier))
    return checks


def main():
    ap = argparse.ArgumentParser(description="xbin preflight checker")
    # Tiers are defined by the installed plugins (xbin-plugin.toml `tiers`), so
    # this is a free-form string rather than a fixed choice list.
    ap.add_argument("--tier", default="smoke",
                    help="end-to-end tier to check for (default: smoke)")
    ap.add_argument("--attach", action="store_true")
    args = ap.parse_args()

    checks = run_checks(args.tier, args.attach)

    print(f"\nxbin preflight  (tier={args.tier}{', attach' if args.attach else ''})")
    print("-" * 72)
    width = max(len(c.name) for c in checks)
    for c in checks:
        tag = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN"}[c.result]
        print(f"  [{tag}] {c.name.ljust(width)}  {c.detail}")
    print("-" * 72)

    failed = [c for c in checks if c.result == FAIL and c.required]
    if failed:
        print(f"PREFLIGHT FAILED: {', '.join(c.name for c in failed)}\n")
        return 1
    warns = [c for c in checks if c.result == WARN]
    print("PREFLIGHT OK" + (f" ({len(warns)} warning(s))" if warns else "") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
