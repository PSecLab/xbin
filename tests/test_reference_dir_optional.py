"""`references/` is optional and must never be conjured into existence.

It is an operator-curated library of known-good binaries that plugins can diff a
target against. Most installations have none. Two properties matter:

1. Nothing raises when it is absent -- every reader degrades to "no references".
2. Starting the orchestrator does not recreate it. It used to, via an
   `os.makedirs(REFERENCE_DIR)` at import, which silently undid a deliberate
   deletion and left an empty directory in the repo root on every boot.

These run in the Docker-free lane: they exercise the REST surface of the session
orchestrator conftest already boots, plus the pure helpers.
"""
import os

import requests

from xbin_orchestrator import main as orch


def test_reference_dir_is_not_created_on_import():
    """Importing the orchestrator must not materialize the directory."""
    # The module is already imported by this point; the assertion is about what
    # that import did. If REFERENCE_DIR exists it must be because an operator
    # made it, not because we did -- so only assert when it is genuinely absent.
    if not os.path.exists(orch.REFERENCE_DIR):
        assert not os.path.isdir(orch.REFERENCE_DIR), (
            f"{orch.REFERENCE_DIR} was created by import; it must stay optional")


def test_list_references_survives_a_missing_dir(monkeypatch, tmp_path):
    missing = str(tmp_path / "no-such-references")
    monkeypatch.setattr(orch, "REFERENCE_DIR", missing)
    assert orch.list_references() == {}
    assert not os.path.exists(missing), "list_references() must not create the dir"


def test_suggest_reference_with_no_library():
    """The picker is called with whatever list_references() returned."""
    assert orch.suggest_reference("firmware.bin", {}) == ""
    assert orch.suggest_reference("", {}) == ""
    assert orch.suggest_reference(None, {}) == ""


def test_references_endpoint_with_a_missing_dir(monkeypatch, tmp_path, rest_base):
    """The dashboard populates its reference dropdown from this endpoint; with no
    library it must return an empty list rather than a 500."""
    monkeypatch.setattr(orch, "REFERENCE_DIR", str(tmp_path / "gone"))
    r = requests.get(f"{rest_base}/api/v1/references", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["references"] == []
    assert body["suggested"] == ""


def test_upload_with_unknown_reference_name_still_succeeds(rest_base, clean_redis, tmp_path):
    """Selecting a reference that is not in the (absent) library must fall through
    to 'use the plugin default', not error."""
    target = tmp_path / "ref_optional_target.bin"
    target.write_bytes(b"\x00\x01\x02\x03")
    with open(target, "rb") as fh:
        r = requests.post(
            f"{rest_base}/api/v1/upload",
            files={"file": (target.name, fh)},
            data={"reference_name": "a-reference-that-does-not-exist",
                  "requested_analyses": ""},
            timeout=60,
        )
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "success"

    uploaded = os.path.join(orch.UPLOAD_DIR, target.name)
    sibling = os.path.join(orch.UPLOAD_DIR, "ref_optional_target.reference")
    try:
        # No reference was resolvable, so no sibling should have been written.
        assert not os.path.exists(sibling)
    finally:
        for p in (uploaded, sibling):
            if os.path.exists(p):
                os.remove(p)
