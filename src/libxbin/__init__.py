"""libxbin: Python client library for xbin binary analysis blackboard orchestrator."""

from .client import XbinClient, AnalysisJob
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

__version__ = "0.2.0"

def connect(
    url: str = "http://localhost:8000",
    grpc_target: str = "localhost:50051",
    auto_spawn: bool = False,
) -> XbinClient:
    """Convenience factory function to connect to an xbin orchestrator."""
    client = XbinClient(url=url, grpc_target=grpc_target)
    if auto_spawn and not client.is_ready():
        client.start_local_orchestrator()
    return client

__all__ = [
    "XbinClient",
    "AnalysisJob",
    "connect",
    "XbinError",
    "XbinConnectionError",
    "AnalysisTimeoutError",
    "PluginError",
    "APIError",
    "PluginInfo",
    "Hypothesis",
    "VerificationStamp",
    "BlackboardItem",
    "ConsensusCFG",
    "CFGNode",
    "CFGEdge",
    "FunctionBoundary",
]
