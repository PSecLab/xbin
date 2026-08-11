"""Deployment readiness, as tests.

Opt-in: `pytest -m preflight`. Excluded from the default lane because these check
the *machine* (Docker, Redis, base images, model availability), not the code --
the fast lane must keep passing on a laptop with none of it running.

Each check the engine produces becomes its own test, named after the check, so a
failure reads as `test_readiness[bind:latest image]` and prints that check's own
remediation string. The engine lives in the orchestrator package
(`xbin_orchestrator.preflight`); the tool-specific checks come from each plugin's
`preflight_checks.py`, discovered at run time.

Select a tier the same way as the e2e lane:

    pytest -m preflight                      # smoke
    pytest -m preflight --e2e-tier heavy     # also requires the emulator, the LLM, ...
"""
import pytest

from xbin_orchestrator.preflight import FAIL, PASS, WARN, run_checks


def _tier(config):
    import os
    return config.getoption("--e2e-tier") or os.environ.get("XBIN_E2E_TIER") or "smoke"


def pytest_generate_tests(metafunc):
    """Run the checks once at collection so each becomes a named test case.

    Collection-time execution is deliberate: it is what lets a failure name the
    specific check rather than hiding every result behind one opaque assertion.
    """
    if "check" not in metafunc.fixturenames:
        return
    tier = _tier(metafunc.config)
    try:
        checks = run_checks(tier)
    except Exception as exc:  # never let a broken check module block collection
        checks = []
        metafunc.parametrize("check", [pytest.param(None, marks=pytest.mark.skip(
            reason=f"preflight engine failed to run: {exc}"))])
        return
    metafunc.parametrize("check", checks, ids=[c.name for c in checks])


@pytest.mark.preflight
def test_readiness(check):
    if check is None:
        pytest.skip("no checks produced")
    if check.result == PASS:
        # A satisfied check is a pass whether or not the tier required it --
        # reporting "PASS: present" as SKIPPED would read as "not checked".
        return
    if check.result == WARN or not check.required:
        # Advisory: surfaced, never fatal. A WARN is how a plugin says "this is
        # missing but your chosen tier does not need it".
        pytest.skip(f"{check.result}: {check.detail}")
    pytest.fail(f"{check.name}: {check.detail}")


@pytest.mark.preflight
def test_plugin_checks_were_discovered(request):
    """The engine must actually find the plugins' contributed checks.

    Without this, a broken discovery walk would look like a clean preflight: the
    four core checks pass and every tool-specific one silently vanishes.
    """
    checks = run_checks(_tier(request.config))
    core = {"docker daemon", "redis :6379", "python deps"}
    contributed = [c for c in checks if c.name not in core and "ports" not in c.name]
    assert contributed, (
        "no plugin contributed any preflight checks -- expected at least one "
        "plugins/**/preflight_checks.py to be discovered"
    )
