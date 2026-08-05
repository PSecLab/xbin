import os
import time
import xbin

@xbin.plugin(
    name="radare_boundaries",
    category="function_boundary",
    display_name="radare2 Boundaries",
    description="Uses radare2 (r2pipe) to extract function boundary offsets and sizes."
)
class RadareBoundaryWorker:
    def on_new_binary(self, binary_path: str, requested_goals: list):
        if "function_boundary" not in (requested_goals or []):
            return

        filename = os.path.basename(binary_path)
        print(f"[*] Radare2 searching for boundaries in: {filename}")
        
        try:
            import r2pipe
            r2 = r2pipe.open(binary_path, flags=['-n'])
            
            print("[*] Running standard analysis (aa)...")
            r2.cmd("aa")
            
            print("[*] Extracting function boundaries...")
            functions = r2.cmdj("afllj")
            
            if not functions:
                print("[-] No functions found by Radare.")
                return

            count = 0
            for func in functions:
                addr = func['offset']
                size = func.get('size', 0)
                
                xbin.post_result(
                    item_key=hex(addr),
                    data={
                        "end": hex(addr + size),
                        "size": size,
                        "name_hint": func.get('name', f"fcn.{hex(addr)}")
                    },
                    confidence=0.85
                )
                count += 1
                
            print(f"[SUCCESS] Radare2 recovered {count} boundaries for {filename}")
            r2.quit()
            
        except Exception as e:
            print(f"[ERROR] Radare2 boundary analysis failed: {e}")

if __name__ == "__main__":
    xbin.start_worker()
