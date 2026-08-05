import os
import time
import traceback
import xbin

@xbin.plugin(
    name="radare_cfg",
    category="cfg_generation",
    display_name="radare2 CFG",
    description="Generates Control Flow Graph using radare2."
)
class RadareWorker:
    def on_new_binary(self, binary_path: str, requested_goals: list):
        if "cfg_generation" not in requested_goals:
            print(f"[*] CFG generation not requested for {os.path.basename(binary_path)}. Skipping.")
            return

        import r2pipe

        filename = os.path.basename(binary_path)
        print(f"[*] Radare2 initiating session for {filename}")
        start_time = time.time()
        
        try:
            print(f"[*] Opening {binary_path} with r2pipe (no relocs)...")
            r2 = r2pipe.open(binary_path, flags=['-n'])
            
            print("[*] Running standard analysis (aa)...")
            r2.cmd("aa")
            
            print("[*] Requesting full binary graph (agj)...")
            raw_graphs = r2.cmdj("agj")
            
            nodes = []
            edges = []
            seen_nodes = set()
            
            if not raw_graphs:
                print("[-] No graph data recovered by Radare.")
                return

            print(f"[*] Normalizing graphs for {len(raw_graphs)} functions...")
            
            for graph in raw_graphs:
                for block in graph.get('blocks', []):
                    node_id = hex(block['offset'])
                    if node_id not in seen_nodes:
                        nodes.append({"id": node_id, "label": node_id})
                        seen_nodes.add(node_id)
                    
                    if 'jump' in block:
                        edges.append({"source": node_id, "target": hex(block['jump'])})
                    if 'fail' in block:
                        edges.append({"source": node_id, "target": hex(block['fail'])})
            
            print(f"[+] Recovered {len(nodes)} unique blocks and {len(edges)} transitions.")
            print(f"[+] Total analysis time: {time.time() - start_time:.2f}s")
            
            print(f"[*] Posting consensus-ready results for '{filename}'...")
            xbin.post_result(
                item_key=filename,
                data={"nodes": nodes, "edges": edges},
                confidence=0.85
            )
            print(f"[SUCCESS] Radare2 analysis complete for {filename}")
            r2.quit()
            
        except Exception as e:
            print(f"[ERROR] Radare2 analysis failed: {e}")
            traceback.print_exc()

    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        if category == "cfg_generation":
            print(f"[*] Observed CFG update for {item_key} from {new_hypothesis.get('backend')} (Score: {new_hypothesis.get('score')})")

if __name__ == "__main__":
    xbin.start_worker()
