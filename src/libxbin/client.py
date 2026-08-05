import os
import time
import requests
from typing import List, Dict, Any, Optional, Union, Tuple

from .exceptions import (
    XbinError,
    XbinConnectionError,
    AnalysisTimeoutError,
    PluginError,
    APIError,
)
from .models import (
    PluginInfo,
    Hypothesis,
    VerificationStamp,
    BlackboardItem,
    ConsensusCFG,
    CFGNode,
    CFGEdge,
    FunctionBoundary,
)


class AnalysisJob:
    """Represents a submitted binary analysis job on the xbin blackboard."""

    def __init__(self, client: "XbinClient", filename: str, requested_goals: List[str]):
        self.client = client
        self.filename = filename
        self.requested_goals = requested_goals
        self.start_time = time.time()

    def wait_for_results(
        self, timeout: float = 60.0, poll_interval: float = 1.0
    ) -> Dict[str, Dict[str, BlackboardItem]]:
        """Block until results appear on the requested blackboard categories or timeout is reached."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            results = self.get_results()
            if any(len(cat_results) > 0 for cat_results in results.values()):
                return results
            time.sleep(poll_interval)
        
        # Check one final time before raising timeout
        results = self.get_results()
        if any(len(cat_results) > 0 for cat_results in results.values()):
            return results
        raise AnalysisTimeoutError(
            f"No results populated for {self.filename} within {timeout} seconds."
        )

    def get_results(self, category: Optional[str] = None) -> Dict[str, Dict[str, BlackboardItem]]:
        """Fetch current blackboard results for requested goals or a specific category."""
        target_cats = [category] if category else (self.requested_goals or ["signature_matching", "equation_recovery", "cfg_generation", "function_boundary", "symbol_matching"])
        all_results = {}
        for cat in target_cats:
            all_results[cat] = self.client.get_blackboard(cat)
        return all_results

    def get_cfg(self, item_key: str) -> ConsensusCFG:
        """Fetch consensus Control Flow Graph for a specific function/item key."""
        return self.client.get_cfg(item_key)

    def get_boundaries(self) -> List[FunctionBoundary]:
        """Fetch recovered function boundary start addresses and sizes."""
        return self.client.get_function_boundaries()

    def get_summary(self, category: str, item_key: str) -> str:
        """Fetch human-readable summary (Ollama-simplified or backend output) for an item."""
        return self.client.get_summary(category, item_key)


class XbinClient:
    """Client library for interacting with the xbin Multi-Analysis Blackboard Orchestrator."""

    def __init__(
        self,
        url: str = "http://localhost:8000",
        grpc_target: str = "localhost:50051",
        timeout: float = 10.0,
    ):
        self.url = url.rstrip("/")
        self.grpc_target = grpc_target
        self.timeout = timeout

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = f"{self.url}{endpoint}"
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as e:
            raise XbinConnectionError(f"Failed to connect to xbin orchestrator at {url}: {e}") from e

        if resp.status_code >= 400:
            raise APIError(resp.status_code, resp.text)

        try:
            return resp.json()
        except ValueError:
            return resp.text

    def health(self) -> Dict[str, Any]:
        """Query orchestrator health status."""
        return self._request("GET", "/api/v1/health")

    def is_ready(self) -> bool:
        """Return True if orchestrator is online and healthy."""
        try:
            h = self.health()
            return h.get("orchestrator") == "HEALTHY" or h.get("status") == "ok"
        except XbinError:
            return False

    def start_local_orchestrator(self, timeout: float = 10.0) -> bool:
        """Launch local xbin-orchestrator background process if not already running."""
        if self.is_ready():
            return True
        import subprocess, sys
        cmd = [sys.executable, "-m", "xbin_orchestrator.main", "--no-browser"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_ready():
                return True
            time.sleep(0.5)
        return self.is_ready()

    def list_plugins(self) -> List[PluginInfo]:
        """List all discovered plugins, their categories, statuses, and badges."""
        data = self._request("GET", "/api/v1/plugins/available")
        plugins = []
        for p in data.get("plugins", []):
            plugins.append(
                PluginInfo(
                    name=p["name"],
                    category=p["category"],
                    status=p.get("status", "STOPPED"),
                    health=p.get("health", "UNKNOWN"),
                    last_beat=p.get("last_beat", 0.0),
                    is_validator=p.get("is_validator", False),
                    is_ranker=p.get("is_ranker", False),
                    display_name=p.get("display_name", p["name"]),
                    description=p.get("description", ""),
                    error=p.get("error"),
                )
            )
        return plugins

    def start_plugin(self, name: str, category: str) -> Dict[str, Any]:
        """Start a specific worker plugin."""
        return self._request("POST", f"/api/v1/plugins/{name}/start?category={category}")

    def stop_plugin(self, name: str, category: str) -> Dict[str, Any]:
        """Stop a running worker plugin."""
        return self._request("POST", f"/api/v1/plugins/{name}/stop?category={category}")

    def bulk_start(self, category: Optional[str] = None) -> List[str]:
        """Start all available plugins or all plugins in a given category."""
        plugins = self.list_plugins()
        started = []
        for p in plugins:
            if category and p.category != category:
                continue
            if p.status not in ["RUNNING", "BUILDING", "STARTING"]:
                self.start_plugin(p.name, p.category)
                started.append(p.name)
        return started

    def bulk_stop(self, category: Optional[str] = None) -> List[str]:
        """Stop all running plugins or running plugins in a given category."""
        plugins = self.list_plugins()
        stopped = []
        for p in plugins:
            if category and p.category != category:
                continue
            if p.status == "RUNNING":
                self.stop_plugin(p.name, p.category)
                stopped.append(p.name)
        return stopped

    def analyze(
        self,
        binary_path: str,
        goals: Optional[List[str]] = None,
        reference_path: Optional[str] = None,
        reference_name: Optional[str] = None,
        auto_start_plugins: bool = True,
    ) -> AnalysisJob:
        """Alias for upload_binary."""
        return self.upload_binary(binary_path, goals, reference_path, reference_name, auto_start_plugins)

    def upload_binary(
        self,
        binary_path: str,
        goals: Optional[List[str]] = None,
        reference_path: Optional[str] = None,
        reference_name: Optional[str] = None,
        auto_start_plugins: bool = True,
    ) -> AnalysisJob:
        """Announce a binary target to the xbin blackboard fleet for analysis."""
        if not os.path.exists(binary_path):
            raise FileNotFoundError(f"Target binary not found at: {binary_path}")

        default_goals = ["signature_matching", "equation_recovery", "cfg_generation", "function_boundary", "symbol_matching"]
        requested_goals = goals or default_goals
        filename = os.path.basename(binary_path)

        if auto_start_plugins:
            for cat in requested_goals:
                self.bulk_start(category=cat)

        with open(binary_path, "rb") as f:
            files = {"file": (filename, f)}
            data = {"requested_analyses": ",".join(requested_goals)}

            if reference_path and os.path.exists(reference_path):
                ref_filename = os.path.basename(reference_path)
                with open(reference_path, "rb") as rf:
                    files["reference"] = (ref_filename, rf)
                    res = self._request("POST", "/api/v1/upload", data=data, files=files)
            else:
                if reference_name:
                    data["reference_name"] = reference_name
                res = self._request("POST", "/api/v1/upload", data=data, files=files)

        return AnalysisJob(self, filename, requested_goals)

    def get_blackboard(self, category: str) -> Dict[str, BlackboardItem]:
        """Fetch all results stored on the blackboard for a category."""
        data = self._request("GET", f"/api/v1/blackboard/{category}/results")
        raw_results = data.get("results", {})
        parsed = {}

        for item_key, item_data in raw_results.items():
            hypotheses = []
            for h in item_data.get("hypotheses", []):
                verifications = []
                for v in h.get("verifications", []):
                    verifications.append(
                        VerificationStamp(
                            target_id=v.get("target_id", h.get("id", "")),
                            verdict=v.get("verdict", "ABSTAIN"),
                            verifier_name=v.get("verifier_name", "unknown"),
                            verifier_version=v.get("verifier_version", "1.0"),
                            timestamp=v.get("timestamp", 0.0),
                            confidence=v.get("confidence"),
                            evidence=v.get("evidence"),
                        )
                    )
                hypotheses.append(
                    Hypothesis(
                        id=h.get("id", f"{h.get('backend')}-{item_key}"),
                        backend=h.get("backend", "unknown"),
                        score=h.get("score", 0.0),
                        raw_conf=h.get("raw_conf", 1.0),
                        data=h.get("data", {}),
                        verifications=verifications,
                        validators=h.get("validators", []),
                    )
                )

            top_hyp = hypotheses[0] if hypotheses else None
            parsed[item_key] = BlackboardItem(
                item_key=item_key,
                category=category,
                hypotheses=hypotheses,
                top_hypothesis=top_hyp,
                display_summary=item_data.get("display_summary"),
            )

        return parsed

    def get_cfg(self, item_key: str) -> ConsensusCFG:
        """Fetch consensus Control Flow Graph for a function or item key."""
        try:
            data = self._request("GET", f"/api/v1/blackboard/cfg_generation/{item_key}/consensus")
        except APIError as e:
            if e.status_code == 404:
                return ConsensusCFG(item_key=item_key, nodes={}, edges={})
            raise
        nodes = {}
        for n_id, n_data in data.get("nodes", {}).items():
            nodes[n_id] = CFGNode(
                id=n_id,
                label=n_data.get("label", n_id),
                avg_confidence=n_data.get("avgConf", 1.0),
                vouches=n_data.get("vouches", []),
            )
        edges = {}
        for e_id, e_data in data.get("edges", {}).items():
            edges[e_id] = CFGEdge(
                id=e_id,
                source=e_data.get("source", ""),
                target=e_data.get("target", ""),
                avg_confidence=e_data.get("avgConf", 1.0),
                vouches=e_data.get("vouches", []),
            )
        return ConsensusCFG(item_key=item_key, nodes=nodes, edges=edges)

    def get_function_boundaries(self) -> List[FunctionBoundary]:
        """Fetch recovered function boundary start addresses and sizes."""
        blackboard = self.get_blackboard("function_boundary")
        boundaries = []
        for addr, item in blackboard.items():
            if not item.top_hypothesis:
                continue
            data = item.top_hypothesis.data or {}
            boundaries.append(
                FunctionBoundary(
                    addr=addr,
                    end=data.get("end", hex(int(addr, 16) + data.get("size", 0)) if addr.startswith("0x") else "0"),
                    size=data.get("size", 0),
                    name_hint=data.get("name_hint"),
                    confidence=item.top_hypothesis.raw_conf,
                    backend=item.top_hypothesis.backend,
                )
            )
        boundaries.sort(key=lambda b: int(b.addr, 16) if b.addr.startswith("0x") else b.addr)
        return boundaries

    def get_summary(self, category: str, item_key: str) -> str:
        """Fetch human-readable summary for a blackboard item."""
        data = self._request("GET", f"/api/v1/blackboard/{category}/{item_key}/summary")
        return data.get("summary", "")

    def get_audit_trail(self, category: str) -> str:
        """Fetch audit trail log for a category blackboard."""
        data = self._request("GET", f"/api/v1/blackboard/{category}/audit")
        return data.get("logs", "")

    def get_system_logs(self) -> str:
        """Fetch system logs from orchestrator."""
        data = self._request("GET", "/api/v1/system/logs")
        return data.get("logs", "")

    def get_worker_logs(self, tail: int = 80) -> str:
        """Fetch worker container logs."""
        data = self._request("GET", f"/api/v1/workers/logs?tail={tail}")
        return data.get("logs", "")

    def clear_session(self) -> Dict[str, Any]:
        """Clear all blackboard data and reset session."""
        return self._request("POST", "/api/v1/session/clear")
