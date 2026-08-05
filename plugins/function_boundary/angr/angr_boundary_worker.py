import os
import time
import xbin

@xbin.plugin(
    name="angr_boundaries",
    category="function_boundary",
    display_name="angr Boundaries",
    description="Uses angr to recover function boundary start addresses and sizes."
)
class AngrBoundaryWorker:
    def on_new_binary(self, binary_path: str, requested_goals: list):
        if "function_boundary" not in (requested_goals or []):
            return

        print(f"[*] Angr searching for boundaries in: {binary_path}")
        filename = os.path.basename(binary_path)
        
        try:
            import angr
            proj = angr.Project(binary_path, auto_load_libs=False)
            
            print("[*] Running CFGFast to recover boundaries...")
            cfg = proj.analyses.CFGFast()
            
            count = 0
            for addr, func in cfg.kb.functions.items():
                xbin.post_result(
                    item_key=hex(addr),
                    data={
                        "end": hex(addr + func.size),
                        "size": func.size,
                        "name_hint": func.name
                    },
                    confidence=1.0
                )
                count += 1
                
            print(f"[SUCCESS] Recovered {count} function boundaries for {filename}")
            
        except Exception as e:
            print(f"[ERROR] Angr boundary analysis failed: {e}")

if __name__ == "__main__":
    xbin.start_worker()
