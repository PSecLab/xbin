"""Comprehensive tests for the verifier stamp architecture (Requirement 9).

Proves that:
1. Adding a verification stamp does not change a hypothesis score.
2. Verification stamps are preserved separately from hypotheses and are queryable.
3. Only rankers can change scores or ranking.
4. Multiple verifiers can stamp the same hypothesis independently.
5. FAIL and ABSTAIN verdicts are supported along with PASS.
6. Verification requires an explicit target_id (rejects alias 'TOP' or missing/nonexistent ID).
7. Invalid verdicts are rejected.
"""

import time
import json
from xbin.sdk import Worker

SIG = "signature_matching"


def _wait_for_state(redis_client, cat, item_key, timeout=3.0):
    key = f"xbin:bb:{cat}:{item_key}"
    start = time.time()
    while time.time() - start < timeout:
        val = redis_client.get(key)
        if val:
            return json.loads(val)
        time.sleep(0.05)
    return None


def test_verification_stamp_does_not_change_score(clean_redis):
    cat = SIG
    item = "0x00010000"

    analyzer = Worker(name="fid", category=cat, version="1.0")
    assert analyzer.register() is True
    analyzer.post_result(item_key=item, data={"known_function": "main"}, confidence=1.0)

    state = _wait_for_state(clean_redis, cat, item)
    target_id = state["hypotheses"][0]["id"]
    initial_score = state["hypotheses"][0]["score"]

    verifier = Worker(name="test_verifier", category=cat, version="1.0", is_validator=True)
    assert verifier.register() is True

    # Submit verification stamp
    res = verifier.submit_verification(
        target_id=target_id,
        verdict="PASS",
        confidence=0.95,
        evidence="AST match verified",
        item_key=item,
    )
    assert res is True
    time.sleep(0.2)

    updated = _wait_for_state(clean_redis, cat, item)
    # Score MUST remain unchanged
    assert updated["hypotheses"][0]["score"] == initial_score


def test_stamps_are_preserved_and_queryable(clean_redis):
    cat = SIG
    item = "0x00020000"

    analyzer = Worker(name="fid", category=cat, version="1.0")
    analyzer.register()
    analyzer.post_result(item_key=item, data={"known_function": "memcpy"}, confidence=1.0)

    state = _wait_for_state(clean_redis, cat, item)
    target_id = state["hypotheses"][0]["id"]

    verifier = Worker(name="strict_verifier", category=cat, version="2.1", is_validator=True)
    verifier.register()
    verifier.submit_verification(
        target_id=target_id,
        verdict="PASS",
        confidence=0.9,
        evidence="Length check passed",
        item_key=item,
    )
    time.sleep(0.2)

    # Query via worker get_analysis API
    res = verifier.get_analysis(cat, item)
    assert res is not None
    assert "verifications" in res
    assert len(res["verifications"]) == 1
    stamp = res["verifications"][0]
    assert stamp["target_id"] == target_id
    assert stamp["verifier_name"] == "strict_verifier"
    assert stamp["verifier_version"] == "2.1"
    assert stamp["verdict"] == "PASS"
    assert stamp["confidence"] == 0.9
    assert stamp["evidence"] == "Length check passed"
    assert "timestamp" in stamp

    # Check original hypothesis object in hypotheses array is unmutated
    hyp = res["hypotheses"][0]
    assert "validators" not in hyp or len(hyp.get("validators", [])) == 0


def test_only_ranker_execution_changes_ranking(clean_redis):
    cat = SIG
    item = "0x00030000"

    # Post H1 (score 0.5 - unknown backend) and H2 (score 1.0 - fid)
    _post_worker = Worker(name="radare2", category=cat, version="1.0")
    _post_worker.register()
    _post_worker.post_result(item_key=item, data={"known_function": "func_h1"}, confidence=1.0)

    _post_worker2 = Worker(name="fid", category=cat, version="1.0")
    _post_worker2.register()
    _post_worker2.post_result(item_key=item, data={"known_function": "func_h2"}, confidence=1.0)

    state = _wait_for_state(clean_redis, cat, item)
    # fid (1.0) is top, radare2 (0.5) is second
    assert state["hypotheses"][0]["backend"] == "fid"
    h1_id = next(h["id"] for h in state["hypotheses"] if h["backend"] == "radare2")

    # Verifier stamps H1 with PASS (confidence 1.0)
    verifier = Worker(name="verifier_alpha", category=cat, version="1.0", is_validator=True)
    verifier.register()
    verifier.submit_verification(target_id=h1_id, verdict="PASS", confidence=1.0, item_key=item)
    time.sleep(0.2)

    # Ranking and scores are STILL UNCHANGED (fid is still top)
    st2 = _wait_for_state(clean_redis, cat, item)
    assert st2["hypotheses"][0]["backend"] == "fid"
    assert st2["hypotheses"][0]["score"] == 1.0

    # NOW run a Ranker to update H1's score to 3.0
    ranker = Worker(name="test_ranker", category=cat, version="1.0", is_ranker=True)
    ranker.register()
    ranker.update_rank(item_key=item, target_id=h1_id, new_score=3.0)
    time.sleep(0.2)

    # NOW H1 is top because Ranker updated it
    st3 = _wait_for_state(clean_redis, cat, item)
    assert st3["hypotheses"][0]["backend"] == "radare2"
    assert st3["hypotheses"][0]["score"] == 3.0


def test_multiple_verifiers_stamp_independently(clean_redis):
    cat = SIG
    item = "0x00040000"

    analyzer = Worker(name="fid", category=cat, version="1.0")
    analyzer.register()
    analyzer.post_result(item_key=item, data={"known_function": "sha256"}, confidence=1.0)

    state = _wait_for_state(clean_redis, cat, item)
    target_id = state["hypotheses"][0]["id"]
    initial_score = state["hypotheses"][0]["score"]

    v1 = Worker(name="verifier_1", category=cat, version="1.0", is_validator=True)
    v1.register()
    v1.submit_verification(target_id=target_id, verdict="PASS", confidence=0.8, evidence="V1 passed", item_key=item)

    v2 = Worker(name="verifier_2", category=cat, version="2.0", is_validator=True)
    v2.register()
    v2.submit_verification(target_id=target_id, verdict="FAIL", confidence=0.9, evidence="V2 failed on constraint", item_key=item)
    time.sleep(0.2)

    updated = _wait_for_state(clean_redis, cat, item)
    verifications = updated.get("verifications", [])
    assert len(verifications) == 2
    names = [v["verifier_name"] for v in verifications]
    assert "verifier_1" in names and "verifier_2" in names
    verdicts = {v["verifier_name"]: v["verdict"] for v in verifications}
    assert verdicts["verifier_1"] == "PASS"
    assert verdicts["verifier_2"] == "FAIL"

    # Score of hypothesis is still unchanged
    assert updated["hypotheses"][0]["score"] == initial_score


def test_fail_and_abstain_stamps_supported(clean_redis):
    cat = SIG
    item = "0x00050000"

    analyzer = Worker(name="fid", category=cat, version="1.0")
    analyzer.register()
    analyzer.post_result(item_key=item, data={"known_function": "aes_encrypt"}, confidence=1.0)

    state = _wait_for_state(clean_redis, cat, item)
    target_id = state["hypotheses"][0]["id"]

    verifier = Worker(name="checker", category=cat, version="1.0", is_validator=True)
    verifier.register()

    # Submit FAIL
    res_fail = verifier.submit_verification(target_id=target_id, verdict="FAIL", evidence="Mismatch", item_key=item)
    assert res_fail is True

    # Submit ABSTAIN
    res_abstain = verifier.submit_verification(target_id=target_id, verdict="ABSTAIN", evidence="No ground truth", item_key=item)
    assert res_abstain is True
    time.sleep(0.2)

    updated = _wait_for_state(clean_redis, cat, item)
    verdict_list = [v["verdict"] for v in updated.get("verifications", [])]
    assert "FAIL" in verdict_list
    assert "ABSTAIN" in verdict_list


def test_verification_rejects_top_alias_and_invalid_target(clean_redis):
    cat = SIG
    item = "0x00060000"

    analyzer = Worker(name="fid", category=cat, version="1.0")
    analyzer.register()
    analyzer.post_result(item_key=item, data={"known_function": "malloc"}, confidence=1.0)
    _wait_for_state(clean_redis, cat, item)

    verifier = Worker(name="checker", category=cat, version="1.0", is_validator=True)
    verifier.register()

    # 'TOP' alias must be rejected
    res_top = verifier.submit_verification(target_id="TOP", verdict="PASS", item_key=item)
    assert res_top is False

    # Missing / nonexistent ID must be rejected
    res_bogus = verifier.submit_verification(target_id="nonexistent_id_123", verdict="PASS", item_key=item)
    assert res_bogus is False


def test_verification_rejects_invalid_verdict(clean_redis):
    cat = SIG
    item = "0x00070000"

    analyzer = Worker(name="fid", category=cat, version="1.0")
    analyzer.register()
    analyzer.post_result(item_key=item, data={"known_function": "free"}, confidence=1.0)
    state = _wait_for_state(clean_redis, cat, item)
    target_id = state["hypotheses"][0]["id"]

    verifier = Worker(name="checker", category=cat, version="1.0", is_validator=True)
    verifier.register()

    # Invalid verdict 'INVALID_VERDICT' must be rejected
    res = verifier.submit_verification(target_id=target_id, verdict="INVALID_VERDICT", item_key=item)
    assert res is False
