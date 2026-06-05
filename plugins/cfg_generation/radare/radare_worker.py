import xbin
import r2pipe
import os
import json

@xbin.plugin(name="radare_cfg", category="cfg_generation")
class RadareWorker:
    def on_new_binary(self, binary_path: str):
        filename = os.path.basename(binary_path)
        print(f"[*] Radare starting analysis of {filename}")
        
        try:
            r2 = r2pipe.open(binary_path, flags=['-n'])
            r2.cmd("aa") 
            
            # Extract entire binary graph
            # agj returns all function graphs as JSON
            raw_graphs = r2.cmdj("agj")
            
            nodes = []
            edges = []
            seen_nodes = set()
            
            if raw_graphs:
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
            
            from xbin.sdk import _current_worker
            _current_worker.post_result(
                item_key=filename, 
                data={"nodes": nodes, "edges": edges}, 
                confidence=0.85
            )
            print(f"[+] Radare successfully posted normalized CFG for {filename}")
            r2.quit()
            
        except Exception as e:
            print(f"[-] Radare analysis failed: {e}")

if __name__ == "__main__":
    xbin.start_worker()
