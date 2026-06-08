import xbin
import os
import time

# Simple Boundary Validator
# Listens for function boundaries and vouches for them if they pass basic checks

@xbin.plugin(name="boundary_validator", category="function_boundary", is_validator=True)
class BoundaryValidator:
    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        # Only care about function boundaries
        if category != "function_boundary":
            return
            
        # Ignore our own vouches to avoid feedback loops
        if new_hypothesis.get('backend') == "boundary_validator":
            return
            
        data = top_hypothesis.get('data', {})
        size = data.get('size', 0)
        
        # Heuristic: Vouch if size is reasonable (> 16 bytes)
        # This demonstrates a validator 'sanity checking' an analyzer's output
        if size > 16:
            print(f"[VALIDATOR] Function at {item_key} looks valid (size: {size}b). Vouching...")
            from xbin.sdk import _current_worker
            
            # Use the new SDK method to vouch for the top hypothesis
            _current_worker.post_validation(
                item_key=item_key, 
                target_id="TOP", 
                confidence=0.9
            )
        else:
            print(f"[VALIDATOR] Function at {item_key} is too small ({size}b). Skipping.")

if __name__ == "__main__":
    xbin.start_worker()
