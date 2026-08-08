import os
import time
import xbin

@xbin.plugin(
    name="boundary_ranker",
    category="function_boundary",
    display_name="Boundary Ranker",
    description="Ranks function boundary candidates based on verifier stamps and raw confidence.",
    is_ranker=True
)
class BoundaryRanker:
    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        if category != "function_boundary":
            return

        # Unlike a verifier, this ranker *wants* verification-triggered updates:
        # it boosts a hypothesis by its PASS-stamp count. So do not skip them --
        # just tolerate the fields they omit. `new_hypothesis` is None on those,
        # and `top_hypothesis` is None for an item with no hypotheses.
        if not top_hypothesis:
            return

        verifications = top_hypothesis.get('verifications', [])
        pass_stamps = [v for v in verifications if v.get('verdict') == 'PASS']
        v_count = len(pass_stamps)
        raw_conf = top_hypothesis.get('raw_conf', 1.0)
        
        new_score = raw_conf + (v_count * 0.5)
        if v_count >= 2:
            new_score += 1.0
            
        if abs(new_score - top_hypothesis.get('score', 0)) > 0.01:
            print(f"[RANKER] Judging {item_key}: {v_count} verifications -> New Score: {new_score}")
            xbin.update_rank(
                item_key=item_key, 
                target_id=top_hypothesis['id'], 
                new_score=new_score
            )

if __name__ == "__main__":
    xbin.start_worker()
