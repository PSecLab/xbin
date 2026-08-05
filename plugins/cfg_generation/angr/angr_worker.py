import os
import time
import traceback
import xbin

@xbin.plugin(
    name="angr_cfg",
    category="cfg_generation",
    display_name="angr CFG",
    description="Generates Fast Control Flow Graph using angr."
)
class AngrWorker:
    def on_new_binary(self, binary_path: str, requested_goals: list):
        if "cfg_generation" not in requested_goals:
            print(f"[*] CFG generation not requested for {os.path.basename(binary_path)}. Skipping.")
            return

        import angr

        print(f"[*] Angr starting intensive analysis of {binary_path}")
        start_time = time.time()
        
        try:
            print(f"[*] Loading binary into angr project...")
            proj = angr.Project(binary_path, auto_load_libs=False)
            print(f"[+] Project loaded. Architecture: {proj.arch}")
            
            print("[*] Generating Fast Control Flow Graph (CFGFast)...")
            cfg = proj.analyses.CFGFast()
            print(f"[+] CFG generation complete in {time.time() - start_time:.2f}s")
            
            nodes = []
            edges = []
            
            print(f"[*] Normalizing graph data...")
            node_count = 0
            for node in cfg.graph.nodes():
                nodes.append({"id": hex(node.addr), "label": hex(node.addr)})
                node_count += 1
            
            edge_count = 0
            for u, v in cfg.graph.edges():
                edges.append({"source": hex(u.addr), "target": hex(v.addr)})
                edge_count += 1
            
            print(f"[+] Found {node_count} nodes and {edge_count} edges.")
            filename = os.path.basename(binary_path)
            
            print(f"[*] Submitting results to blackboard for '{filename}'...")
            xbin.post_result(
                item_key=filename,
                data={"nodes": nodes, "edges": edges},
                confidence=0.9
            )
            print(f"[SUCCESS] Angr analysis finalized for {filename}")
            
        except Exception as e:
            print(f"[ERROR] Angr analysis failed: {e}")
            traceback.print_exc()

    def on_update(self, category, item_key, new_hypothesis, top_hypothesis):
        if category == "cfg_generation":
            print(f"[*] Observed CFG update for {item_key} from {new_hypothesis.get('backend')} (Score: {new_hypothesis.get('score')})")

if __name__ == "__main__":
    xbin.start_worker()
