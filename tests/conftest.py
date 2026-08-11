import pytest
import subprocess
import time
import redis
import os
import sys

# `src` holds the SDK and the orchestrator package; it is not installed in every
# environment the tests run in, so put it on the path explicitly. The e2e helpers
# now live in this package (tests/e2e_driver.py) and need no path juggling.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(_REPO_ROOT, "src"))

from tests.e2e_driver import (  # single readiness gate (see tests/e2e_driver.py)
    GRPC_PORT,
    REST_BASE,
    REST_PORT,
    _port_open,
    wait_for_ready,
)


@pytest.fixture(scope="session")
def e2e_options(request):
    """The `--e2e-*` options as a dict of run_tier() keyword arguments.

    The options themselves are declared in the repo-root conftest.py -- see the
    note there for why they cannot live in this file."""
    opt = request.config.getoption
    tier = opt("--e2e-tier") or os.environ.get("XBIN_E2E_TIER") or "smoke"
    return {
        "tier": tier,
        "binary": opt("--e2e-binary"),
        "reference": opt("--e2e-reference"),
        # Always attach: conftest already booted the session orchestrator, so the
        # driver must drive that one rather than start a second.
        "attach": True,
        "build_timeout": opt("--e2e-build-timeout"),
        "result_timeout": opt("--e2e-result-timeout"),
    }


@pytest.fixture(scope="session", autouse=True)
def orchestrator_server():
    """Start the xbin Orchestrator in the background for integration testing.

    Runs headless (--no-browser) from the repo root so `plugins/` and `uploads/`
    resolve, and gates on a real readiness poll (gRPC :50051 open + REST /health
    200) instead of a blind sleep.
    """
    # Never run against an orchestrator we did not start. The `clean_redis`
    # fixture below flushes the DB directly, so attaching to someone else's
    # instance silently destroys its blackboard and leaves its workers pointing
    # at empty state -- a very confusing way to lose a long analysis run.
    if _port_open(REST_PORT) or _port_open(GRPC_PORT):
        pytest.exit(
            f"An orchestrator is already listening on :{REST_PORT}/:{GRPC_PORT}.\n"
            "The test suite flushes Redis between tests, which would wipe its blackboard.\n"
            "Stop it before running the tests.",
            returncode=1,
        )

    env = os.environ.copy()
    env["PYTHONPATH"] = "src:src/xbin_orchestrator"

    log_path = os.path.join(_REPO_ROOT, "tests", ".orchestrator.log")
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "xbin_orchestrator.main", "--no-browser"],
        cwd=_REPO_ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    if not wait_for_ready(timeout=30):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        log_file.close()
        with open(log_path) as f:
            tail = "".join(f.readlines()[-40:])
        raise RuntimeError(f"Orchestrator failed to become ready in 30s.\n--- log tail ---\n{tail}")

    yield

    # Teardown
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    log_file.close()


@pytest.fixture(autouse=True)
def clean_redis():
    """Ensure a clean Redis state before every test."""
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.flushdb()
    yield r


@pytest.fixture(scope="session")
def rest_base():
    """Base URL of the orchestrator's REST API / dashboard."""
    return REST_BASE
