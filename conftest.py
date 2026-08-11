"""Root conftest: command-line options only.

`pytest_addoption` has to live in the **rootdir** conftest, not in
`tests/conftest.py`. pytest parses the command line in two passes, and in the
first pass an unknown option's *value* is treated as a path argument -- so

    pytest -m e2e --e2e-binary uploads/firmware.bin

would make pytest compute its initial conftests from `uploads/`, never load
`tests/conftest.py`, and then reject `--e2e-*` as unrecognized in the second
pass. Declaring them here means they are registered before any argument is
interpreted, whatever the invocation looks like.

Everything else -- fixtures, the orchestrator lifecycle -- stays in
`tests/conftest.py`.
"""


def pytest_addoption(parser):
    """Expose the e2e driver's knobs as pytest options.

    Namespaced `--e2e-*` so they cannot collide with pytest's own options or a
    third-party plugin's. Each maps 1:1 onto a `run_tier()` keyword argument.
    `--e2e-tier` also selects the tier for the `preflight` lane.
    """
    group = parser.getgroup("xbin e2e")
    group.addoption("--e2e-tier", default=None,
                    help="tier for the e2e and preflight lanes (default: $XBIN_E2E_TIER, "
                         "else 'smoke'). Tiers come from the plugin manifests: "
                         "python tests/e2e_driver.py --list-tiers")
    group.addoption("--e2e-binary", default=None,
                    help="binary to analyze (default: auto-discovered from uploads/)")
    group.addoption("--e2e-reference", default=None,
                    help="optional symbolized reference binary")
    # Deliberately no --e2e-attach: the suite flushes Redis between tests, so
    # pointing it at an orchestrator you are watching would wipe its blackboard --
    # the very thing tests/conftest.py's port guard prevents. Attaching is the
    # CLI's job:  python tests/e2e_driver.py --tier smoke --attach
    group.addoption("--e2e-build-timeout", type=float, default=900,
                    help="seconds to wait for plugin images to build and workers to report ready")
    group.addoption("--e2e-result-timeout", type=float, default=None,
                    help="seconds to wait for results (default: the tier's declared timeout)")
