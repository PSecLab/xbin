"""REST-surface tests (Docker-free).

Exercises the orchestrator's HTTP API against the session orchestrator: the
upload endpoint's NEW_BINARY publish, plugin discovery/metadata shape, health,
and the empty-blackboard responses. Uses tiny in-memory dummy files (never the
real 2MB firmware) so it stays hermetic and fast.
"""
import json
import os
import sys
import time

import pytest
import redis
import requests

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOADS = os.path.join(_REPO_ROOT, "uploads")
PLUGINS = os.path.join(_REPO_ROOT, "plugins")

sys.path.insert(0, os.path.join(_REPO_ROOT, "src", "xbin_orchestrator"))
from plugin_manifest import DEFAULT_WEIGHT, iter_plugin_dirs, read_manifest  # noqa: E402


def _installed_manifests():
    """The on-disk truth about the installed plugins, as the orchestrator reads it."""
    out = {}
    for root in iter_plugin_dirs([PLUGINS]):
        m = read_manifest(root)
        if not m.get("name") or not m.get("category"):
            continue
        source = "".join(
            open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
            for f in sorted(os.listdir(root)) if f.endswith(".py")
        )
        out[root] = {
            "name": m["name"],
            "category": m["category"],
            "weight": m.get("weight", DEFAULT_WEIGHT),
            "is_ranker": "is_ranker=True" in source,
            "is_validator": "is_validator=True" in source,
        }
    return out


def _cleanup(*names):
    for n in names:
        p = os.path.join(UPLOADS, n)
        if os.path.exists(p):
            os.remove(p)


def test_upload_publishes_new_binary(rest_base, clean_redis):
    fname = "e2e_dummy_target.bin"
    goals = "signature_matching,equation_recovery"
    sub = redis.Redis(host="localhost", port=6379, decode_responses=True).pubsub()
    sub.subscribe("xbin:events")
    time.sleep(0.2)  # let the subscription register
    try:
        resp = requests.post(
            f"{rest_base}/api/v1/upload",
            files={"file": (fname, b"\x00\x01dummy-firmware")},
            data={"requested_analyses": goals},
            timeout=30,
        )
        assert resp.json() == {"status": "success"}

        event = None
        deadline = time.time() + 5
        while time.time() < deadline:
            msg = sub.get_message(timeout=1.0)
            if msg and msg.get("type") == "message":
                payload = json.loads(msg["data"])
                if payload.get("type") == "NEW_BINARY":
                    event = payload
                    break
        assert event is not None, "NEW_BINARY was not published"
        assert event["filename"] == fname
        assert event["path"] == f"/app/uploads/{fname}"
        assert event["requested_analyses"] == ["signature_matching", "equation_recovery"]
    finally:
        sub.close()
        _cleanup(fname)


def test_upload_with_reference_writes_sibling(rest_base, clean_redis):
    fname = "e2e_dummy_ref.bin"
    try:
        resp = requests.post(
            f"{rest_base}/api/v1/upload",
            files={
                "file": (fname, b"target-bytes"),
                "reference": ("whatever-name.elf", b"reference-bytes"),
            },
            data={"requested_analyses": "signature_matching"},
            timeout=30,
        )
        assert resp.json() == {"status": "success"}
        # Saved as <stem>.reference regardless of the uploaded name (main.py:151).
        ref_path = os.path.join(UPLOADS, "e2e_dummy_ref.reference")
        assert os.path.exists(ref_path)
        with open(ref_path, "rb") as f:
            assert f.read() == b"reference-bytes"
    finally:
        _cleanup(fname, "e2e_dummy_ref.reference")


def test_health_shape(rest_base, clean_redis):
    d = requests.get(f"{rest_base}/api/v1/health", timeout=10).json()
    assert d["orchestrator"] == "HEALTHY"
    assert isinstance(d["worker_fleet"], list)


def test_plugins_available_shape(rest_base, clean_redis):
    """Discovery reports exactly the installed plugins, with their declared
    weights. The expected set is read from the manifests rather than restated
    here, so this test keeps working as plugins are added or removed -- and
    fails if the API and the on-disk manifests ever disagree."""
    d = requests.get(f"{rest_base}/api/v1/plugins/available", timeout=10).json()
    plugins = {(p["name"], p["category"]): p for p in d["plugins"]}

    manifests = _installed_manifests()
    expected = {(m["name"], m["category"]) for m in manifests.values()}
    assert expected.issubset(set(plugins.keys())), f"missing: {expected - set(plugins.keys())}"

    # Each plugin's consensus weight round-trips from its manifest to the API.
    for m in manifests.values():
        api_weight = plugins[(m["name"], m["category"])]["weight"]
        assert api_weight == pytest.approx(m["weight"]), (
            f"{m['name']}: manifest weight {m['weight']} but API reports {api_weight}")

    # Rankers are discovered statically, before any container runs.
    for m in manifests.values():
        if m["is_ranker"]:
            assert plugins[(m["name"], m["category"])]["is_ranker"] is True
            assert d["rankers"].get(m["category"]) == m["name"]
    # A category with no ranker falls back to the baseline consensus math.
    ranked = {m["category"] for m in manifests.values() if m["is_ranker"]}
    for category in {m["category"] for m in manifests.values()} - ranked:
        assert d["rankers"].get(category) == "Baseline"

    # Static metadata (display_name) is discovered from source, not invented.
    assert all(p["display_name"] for p in plugins.values())


def test_blackboard_empty(rest_base, clean_redis):
    res = requests.get(f"{rest_base}/api/v1/blackboard/signature_matching/results", timeout=10).json()
    assert res == {"results": {}}
    audit = requests.get(f"{rest_base}/api/v1/blackboard/signature_matching/audit", timeout=10).json()
    assert audit["logs"] == "No history recorded yet."


def test_session_clear(rest_base, clean_redis):
    from xbin.sdk import Worker
    w = Worker(name="fid", category="signature_matching", version="1.0")
    assert w.register() is True
    w.post_result("0x0000abcd", {"known_function": "foo"}, 1.0)
    time.sleep(0.2)
    assert requests.get(
        f"{rest_base}/api/v1/blackboard/signature_matching/results", timeout=10
    ).json()["results"], "seed failed"

    assert requests.post(f"{rest_base}/api/v1/session/clear", timeout=10).json()["status"] == "success"
    assert requests.get(
        f"{rest_base}/api/v1/blackboard/signature_matching/results", timeout=10
    ).json() == {"results": {}}
