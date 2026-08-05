#!/usr/bin/env python3
"""Example demonstrating programmatic usage of libxbin to interact with an xbin orchestrator."""

import os
import time
import libxbin

def main():
    print("[*] Connecting to xbin orchestrator at http://localhost:8000...")
    client = libxbin.connect("http://localhost:8000", auto_spawn=True)
    
    if not client.is_ready():
        print("[-] Unable to connect to orchestrator.")
        return
        
    print("[+] Orchestrator is online and healthy!")
    
    # 1. List available plugins
    plugins = client.list_plugins()
    print(f"\n[*] Discovered {len(plugins)} plugins across the fleet:")
    for p in plugins:
        badge = " [RANKER]" if p.is_ranker else " [VALIDATOR]" if p.is_validator else ""
        print(f"  - [{p.category}] {p.display_name} ({p.name}){badge} | Status: {p.status}")

    # 2. Deploy CFG Generation and Function Boundary workers
    print("\n[*] Deploying CFG Generation workers (angr_cfg, radare_cfg)...")
    client.bulk_start("cfg_generation")
    client.bulk_start("function_boundary")

    # 3. Upload sample binary for analysis with CFG generation goal
    sample_path = "examples/sample.elf"
    if os.path.exists(sample_path):
        print(f"\n[*] Submitting {sample_path} for CFG Generation & Boundary analysis...")
        job = client.analyze(
            sample_path,
            goals=["cfg_generation", "function_boundary", "signature_matching"],
            auto_start_plugins=True,
        )
        print(f"[+] Successfully submitted job for target: {job.filename}")
        
        # 4. Wait for analysis workers to process binary and populate blackboard
        print("[*] Waiting for workers to analyze binary and populate blackboard (up to 30s)...")
        try:
            results = job.wait_for_results(timeout=30.0)
            print("[+] Analysis results populated on blackboard!")
        except libxbin.AnalysisTimeoutError:
            print("[!] Timeout reached while waiting for workers (containers may still be building or initializing).")
    
    # 5. Inspect active function boundaries on the blackboard
    boundaries = client.get_function_boundaries()
    print(f"\n[*] Blackboard Function Boundaries: {len(boundaries)}")
    for b in boundaries[:5]:
        print(f"  - Address: {b.addr} | End: {b.end} | Size: {b.size}b | Name Hint: {b.name_hint or 'unknown'}")

    # 6. Fetch and traverse Consensus Control Flow Graph (CFG)
    print("\n[*] Inspecting CFG Generation blackboard items...")
    cfg_bb = client.get_blackboard("cfg_generation")
    print(f"  - Total CFG targets on blackboard: {len(cfg_bb)}")
    for item_key, item in cfg_bb.items():
        print(f"    - Target '{item_key}': {len(item.hypotheses)} hypothesis/hypotheses")
    
    target_key = "sample.elf" if "sample.elf" in cfg_bb else (boundaries[0].addr if boundaries else "sample.elf")
    print(f"\n[*] Fetching Consensus CFG Graph for '{target_key}'...")
    cfg = client.get_cfg(target_key)
    print(f"  - Total CFG Basic Block Nodes: {len(cfg.nodes)}")
    print(f"  - Total Control Flow Edges: {len(cfg.edges)}")
    
    if cfg.root_nodes:
        print(f"  - Entry Basic Block(s): {[n.id for n in cfg.root_nodes]}")
    if cfg.leaf_nodes:
        print(f"  - Exit Basic Block(s): {[n.id for n in cfg.leaf_nodes]}")
        
    for n_id, node in list(cfg.nodes.items())[:3]:
        succs = [s.id for s in cfg.successors(n_id)]
        preds = [p.id for p in cfg.predecessors(n_id)]
        print(f"    - Block [{node.id}] (Label: {node.label}) | Conf: {node.avg_confidence*100:.0f}%")
        print(f"      Predecessors: {preds} --> Successors: {succs}")

    for edge_id, edge in list(cfg.edges.items())[:3]:
        print(f"    - Edge [{edge.source} -> {edge.target}] | Conf: {edge.avg_confidence*100:.0f}% | Tools: {list(edge.backends)}")

if __name__ == "__main__":
    main()
