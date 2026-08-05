import os
import time
import xbin

@xbin.plugin(
    name="boundary_validator",
    category="function_boundary",
    display_name="Boundary Validator",
    description="Validates function boundary hypotheses and submits immutable verification stamps.",
    is_validator=True
)
class BoundaryValidator:
    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        if category != "function_boundary":
            return
            
        if new_hypothesis.get('backend') == "boundary_validator":
            return
            
        data = top_hypothesis.get('data', {})
        size = data.get('size', 0)
        
        if size > 16:
            print(f"[VALIDATOR] Function at {item_key} looks valid (size: {size}b). Submitting PASS stamp...")
            xbin.submit_verification(
                target_id=top_hypothesis['id'],
                verdict="PASS",
                confidence=0.9,
                evidence=f"Function size > 16b ({size}b)",
                item_key=item_key,
                category=category
            )
        else:
            print(f"[VALIDATOR] Function at {item_key} is too small ({size}b). Skipping.")

if __name__ == "__main__":
    xbin.start_worker()
