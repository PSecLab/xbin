import time
import json
from xbin.sdk import Worker
import threading

def wait_for_key(redis_client, key, timeout=2.0):
    start = time.time()
    while time.time() - start < timeout:
        val = redis_client.get(key)
        if val:
            return json.loads(val)
        time.sleep(0.1)
    return None

def test_analyzer_submission(clean_redis):
    cat = 'signature_matching'
    item = '0x1000'
    
    analyzer = Worker(name='test_analyzer', category=cat, version='1.0')
    assert analyzer.register() is True
    
    analyzer.post_result(item_key=item, data={'size': 42}, confidence=1.0)
    
    state = wait_for_key(clean_redis, f'xbin:bb:{cat}:{item}')
    assert state is not None, "Data was not written to Redis in time"
    assert state['status'] == 'RESOLVED'
    assert len(state['hypotheses']) == 1
    assert state['hypotheses'][0]['data']['size'] == 42
    assert state['hypotheses'][0]['score'] == 0.5  # 1.0 conf * 0.5 default weight

def test_verifier_stamping(clean_redis):
    cat = 'signature_matching'
    item = '0x1001'
    
    # 1. Setup Analyzer
    analyzer = Worker(name='test_analyzer', category=cat, version='1.0')
    analyzer.register()
    analyzer.post_result(item_key=item, data={'size': 42}, confidence=1.0)
    
    # 2. Setup Verifier
    verifier = Worker(name='test_verifier', category=cat, version='1.0', is_validator=True)
    assert verifier.register() is True
    
    # Wait for initial result
    state = wait_for_key(clean_redis, f'xbin:bb:{cat}:{item}')
    hyp_id = state['hypotheses'][0]['id']
    initial_score = state['hypotheses'][0]['score']
    
    # 3. Submit verification stamp
    assert verifier.submit_verification(target_id=hyp_id, verdict="PASS", confidence=1.0, evidence="Valid size", item_key=item) is True
    
    state = wait_for_key(clean_redis, f'xbin:bb:{cat}:{item}')
    assert len(state.get('verifications', [])) == 1
    stamp = state['verifications'][0]
    assert stamp['target_id'] == hyp_id
    assert stamp['verifier_name'] == 'test_verifier'
    assert stamp['verdict'] == 'PASS'
    # Hypothesis score must remain unchanged
    assert state['hypotheses'][0]['score'] == initial_score

def test_ranker_update(clean_redis):
    cat = 'signature_matching'
    item = '0x1002'
    
    # 1. Submit initial result
    analyzer = Worker(name='test_analyzer', category=cat, version='1.0')
    analyzer.register()
    analyzer.post_result(item_key=item, data={'size': 42}, confidence=1.0)
    
    state = wait_for_key(clean_redis, f'xbin:bb:{cat}:{item}')
    hyp_id = state['hypotheses'][0]['id']
    
    # 2. Setup Ranker
    ranker = Worker(name='test_ranker', category=cat, version='1.0', is_ranker=True)
    assert ranker.register() is True
    
    # 3. Use Ranker to override the score
    ranker.update_rank(item_key=item, target_id=hyp_id, new_score=99.9)
    
    # Verify score was updated
    start = time.time()
    state = None
    while time.time() - start < 3.0:
        val = clean_redis.get(f'xbin:bb:{cat}:{item}')
        if val:
            state = json.loads(val)
            if state['hypotheses'][0]['score'] == 99.9:
                break
        time.sleep(0.05)
    assert state is not None
    assert state['hypotheses'][0]['score'] == 99.9
