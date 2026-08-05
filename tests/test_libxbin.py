import os
import pytest
import libxbin
from libxbin.exceptions import XbinConnectionError, AnalysisTimeoutError, APIError
from libxbin.models import PluginInfo, BlackboardItem, FunctionBoundary, ConsensusCFG

def test_client_init():
    client = libxbin.connect("http://localhost:8000")
    assert client.url == "http://localhost:8000"
    assert client.grpc_target == "localhost:50051"

def test_client_connection_error():
    dead_client = libxbin.XbinClient("http://127.0.0.1:59999", timeout=0.5)
    assert dead_client.is_ready() is False
    with pytest.raises(XbinConnectionError):
        dead_client.health()

def test_client_health_and_ready(orchestrator_server, rest_base, clean_redis):
    client = libxbin.connect(rest_base)
    assert client.is_ready() is True
    h = client.health()
    assert h.get("orchestrator") == "HEALTHY"

def test_client_list_plugins(orchestrator_server, rest_base, clean_redis):
    client = libxbin.connect(rest_base)
    plugins = client.list_plugins()
    assert len(plugins) >= 14
    
    plugin_names = {p.name for p in plugins}
    expected_names = {
        "fid", "ghidriff", "bind_arbiter", "bind_se", "symbolic_regression",
        "pysindy", "angr_cfg", "radare_cfg", "angr_boundaries", "radare_boundaries",
        "binja", "boundary_ranker", "boundary_validator", "flirt_matcher"
    }
    assert expected_names.issubset(plugin_names)
    
    arbiter = next(p for p in plugins if p.name == "bind_arbiter")
    assert arbiter.is_ranker is True
    assert arbiter.category == "signature_matching"

def test_client_upload_and_job(orchestrator_server, rest_base, clean_redis, tmp_path):
    client = libxbin.connect(rest_base)
    
    # Create dummy binary
    target_path = str(tmp_path / "sample_firmware.bin")
    with open(target_path, "wb") as f:
        f.write(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)
        
    job = client.analyze(
        target_path,
        goals=["signature_matching", "function_boundary"],
    )
    assert job.filename == "sample_firmware.bin"
    assert job.requested_goals == ["signature_matching", "function_boundary"]

def test_client_blackboard_parsing(orchestrator_server, rest_base, clean_redis):
    client = libxbin.connect(rest_base)
    
    # Manually populate Redis state to test parsing in libxbin
    clean_redis.set("xbin:bb:function_boundary:0x400000", '{"hypotheses": [{"id": "h1", "backend": "angr_boundaries", "score": 1.5, "raw_conf": 1.0, "data": {"end": "0x400100", "size": 256, "name_hint": "main"}, "validators": ["boundary_validator"], "verifications": [{"target_id": "h1", "verdict": "PASS", "verifier_name": "boundary_validator", "verifier_version": "1.0", "timestamp": 123456.0, "confidence": 0.9, "evidence": "Valid size"}]}], "display_summary": "main (256 bytes)"}')
    
    blackboard = client.get_blackboard("function_boundary")
    assert "0x400000" in blackboard
    item = blackboard["0x400000"]
    assert isinstance(item, BlackboardItem)
    assert item.top_hypothesis is not None
    assert item.top_hypothesis.backend == "angr_boundaries"
    assert len(item.top_hypothesis.verifications) == 1
    assert item.top_hypothesis.verifications[0].verdict == "PASS"
    
    boundaries = client.get_function_boundaries()
    assert len(boundaries) == 1
    assert boundaries[0].addr == "0x400000"
    assert boundaries[0].size == 256
    assert boundaries[0].name_hint == "main"

def test_client_cfg_parsing(orchestrator_server, rest_base, clean_redis):
    client = libxbin.connect(rest_base)
    
    # Populate a dummy CFG hypothesis
    clean_redis.set("xbin:bb:cfg_generation:0x400000", '{"hypotheses": [{"id": "h_cfg", "backend": "angr_cfg", "score": 1.0, "raw_conf": 1.0, "data": {"nodes": [{"id": "b1", "label": "0x400000"}, {"id": "b2", "label": "0x400010"}], "edges": [{"id": "e1", "source": "b1", "target": "b2"}]}}]}')
    
    cfg = client.get_cfg("0x400000")
    assert isinstance(cfg, ConsensusCFG)
    assert "b1" in cfg.nodes
    assert "b2" in cfg.nodes
    assert "b1->b2" in cfg.edges
    assert cfg.edges["b1->b2"].source == "b1"
    assert cfg.edges["b1->b2"].target == "b2"

    # Test graph traversal helper methods
    succs = cfg.successors("b1")
    assert len(succs) == 1
    assert succs[0].id == "b2"

    preds = cfg.predecessors("b2")
    assert len(preds) == 1
    assert preds[0].id == "b1"

    roots = cfg.root_nodes
    assert len(roots) == 1
    assert roots[0].id == "b1"

    leaves = cfg.leaf_nodes
    assert len(leaves) == 1
    assert leaves[0].id == "b2"

def test_client_system_logs_and_audit(orchestrator_server, rest_base, clean_redis):
    client = libxbin.connect(rest_base)
    sys_logs = client.get_system_logs()
    assert isinstance(sys_logs, str)
    
    audit = client.get_audit_trail("signature_matching")
    assert isinstance(audit, str)
