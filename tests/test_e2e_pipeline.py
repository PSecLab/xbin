"""Opt-in full-stack pipeline test.

Excluded from the default lane; run with `pytest -m e2e`. Needs Docker plus
whatever base images and services the tier's plugins declare.

Drives the real plugin containers through `tests/e2e_driver.py` against the
session orchestrator conftest boots. Every knob is a `--e2e-*` pytest option:

    pytest -m e2e                                   # smoke tier
    pytest -m e2e --e2e-tier full
    pytest -m e2e --e2e-tier heavy --e2e-binary uploads/gs3.bin

`XBIN_E2E_TIER` still works as a fallback for CI that sets env rather than args.

To drive an orchestrator you are already watching in the dashboard, use the
driver's CLI instead -- this suite flushes Redis between tests:

    python tests/e2e_driver.py --tier smoke --attach
"""
import pytest

from tests import e2e_driver

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def test_pipeline(rest_base, e2e_options):
    tier = e2e_options["tier"]
    assert tier in e2e_driver.TIERS, (
        f"unknown tier {tier!r}; the installed plugins define: "
        f"{', '.join(sorted(e2e_driver.TIERS)) or 'none'}"
    )

    rc = e2e_driver.run_tier(**e2e_options)
    assert rc == 0, f"e2e tier '{tier}' failed (rc={rc})"

    # Every category the tier requires must have produced at least one
    # hypothesis. Derived from the manifests, so this keeps holding as plugins
    # move between tiers.
    client = e2e_driver.XbinClient(rest_base)
    for category in e2e_driver.TIERS[tier]["require"]:
        assert client.results(category), f"{category} produced no hypotheses"
