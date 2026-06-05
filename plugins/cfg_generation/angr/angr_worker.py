import xbin
import angr
import os

@xbin.plugin(name="angr_cfg", category="cfg_generation")
class AngrWorker:
    def on_new_binary(self, binary_path: str):
        print(f"[*] Angr analyzing: {binary_path}")
        try:
            proj = angr.Project(binary_path, auto_load_libs=False)
            cfg = proj.analyses.CFGFast()
            
            # Standardized graph format for merging
            # item_key is the filename
            nodes = []
            edges = []
            
            for node in cfg.graph.nodes():
                nodes.append({"id": hex(node.addr), "label": hex(node.addr)})
            
            for u, v in cfg.graph.edges():
                edges.append({"source": hex(u.addr), "target": hex(v.addr)})
            
            from xbin.sdk import _current_worker
            filename = os.path.basename(binary_path)
            _current_worker.post_result(
                item_key=filename, 
                data={"nodes": nodes, "edges": edges}, 
                confidence=0.9
            )
            print(f"[+] Angr posted normalized CFG for {filename}")
            
        except Exception as e:
            print(f"[-] Angr failed: {e}")

if __name__ == "__main__":
    xbin.start_worker()
