import xbin
import time

# Mocking a legacy tool
def run_structural_matching(address, raw_bytes):
    return {
        "predicted_name": f"func_at_{hex(address)}",
        "accuracy_ratio": 0.92
    }

@xbin.plugin(name="structural_cfg", version="1.0")
def analyze(task_context: xbin.TaskContext):
    print(f"[*] Analyzing 0x{task_context.address:x}...")
    
    # 1. Run their legacy tool
    result = run_structural_matching(task_context.address, task_context.raw_bytes)
    
    # 2. Return the standard format
    return xbin.Match(
        symbol=result["predicted_name"],
        confidence=result["accuracy_ratio"]
    )

if __name__ == "__main__":
    # In a real scenario, this would register and wait for tasks.
    # For demonstration, we'll trigger a mock analysis manually after registration.
    from xbin.sdk import _current_worker, TaskContext
    
    print("--- SDK Demo ---")
    if _current_worker:
        # Simulate registration
        # _current_worker.register() 
        
        # Simulate receiving a task
        mock_task = TaskContext(address=0x401000, raw_bytes=b"\x90\x90\x90")
        match = analyze(mock_task)
        print(f"[+] Result: {match}")
        
        # In a real run, start_worker() would block and handle the loop
        # xbin.start_worker()
    print("----------------")
