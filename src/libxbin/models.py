from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

@dataclass
class PluginInfo:
    name: str
    category: str
    status: str
    health: str
    last_beat: float
    is_validator: bool
    is_ranker: bool
    display_name: str
    description: str
    error: Optional[str] = None

@dataclass
class VerificationStamp:
    target_id: str
    verdict: str
    verifier_name: str
    verifier_version: str
    timestamp: float
    confidence: Optional[float] = None
    evidence: Optional[str] = None

@dataclass
class Hypothesis:
    id: str
    backend: str
    score: float
    raw_conf: float
    data: Dict[str, Any]
    verifications: List[VerificationStamp] = field(default_factory=list)
    validators: List[str] = field(default_factory=list)

@dataclass
class BlackboardItem:
    item_key: str
    category: str
    hypotheses: List[Hypothesis]
    top_hypothesis: Optional[Hypothesis] = None
    display_summary: Optional[str] = None

@dataclass
class CFGNode:
    id: str
    label: str
    avg_confidence: float
    vouches: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def backends(self) -> Set[str]:
        """Return the set of worker backend names that vouched for this node."""
        return {v["backend"] for v in self.vouches if "backend" in v}

@dataclass
class CFGEdge:
    id: str
    source: str
    target: str
    avg_confidence: float
    vouches: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def backends(self) -> Set[str]:
        """Return the set of worker backend names that vouched for this edge."""
        return {v["backend"] for v in self.vouches if "backend" in v}

@dataclass
class ConsensusCFG:
    item_key: str
    nodes: Dict[str, CFGNode] = field(default_factory=dict)
    edges: Dict[str, CFGEdge] = field(default_factory=dict)

    def successors(self, node_id: str) -> List[CFGNode]:
        """Return all successor basic block nodes reachable from node_id."""
        succ_ids = [e.target for e in self.out_edges(node_id)]
        return [self.nodes[n_id] for n_id in succ_ids if n_id in self.nodes]

    def predecessors(self, node_id: str) -> List[CFGNode]:
        """Return all predecessor basic block nodes that lead to node_id."""
        pred_ids = [e.source for e in self.in_edges(node_id)]
        return [self.nodes[n_id] for n_id in pred_ids if n_id in self.nodes]

    def out_edges(self, node_id: str) -> List[CFGEdge]:
        """Return outgoing edges originating from node_id."""
        return [e for e in self.edges.values() if e.source == node_id]

    def in_edges(self, node_id: str) -> List[CFGEdge]:
        """Return incoming edges targeting node_id."""
        return [e for e in self.edges.values() if e.target == node_id]

    @property
    def root_nodes(self) -> List[CFGNode]:
        """Return entry basic block nodes (nodes with 0 incoming edges)."""
        target_ids = {e.target for e in self.edges.values()}
        return [n for n_id, n in self.nodes.items() if n_id not in target_ids]

    @property
    def leaf_nodes(self) -> List[CFGNode]:
        """Return exit basic block nodes (nodes with 0 outgoing edges)."""
        source_ids = {e.source for e in self.edges.values()}
        return [n for n_id, n in self.nodes.items() if n_id not in source_ids]

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable dictionary representation of the consensus graph."""
        return {
            "item_key": self.item_key,
            "nodes": [
                {
                    "id": n.id,
                    "label": n.label,
                    "avg_confidence": n.avg_confidence,
                    "backends": list(n.backends),
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.source,
                    "target": e.target,
                    "avg_confidence": e.avg_confidence,
                    "backends": list(e.backends),
                }
                for e in self.edges.values()
            ],
        }

@dataclass
class FunctionBoundary:
    addr: str
    end: str
    size: int
    name_hint: Optional[str] = None
    confidence: float = 1.0
    backend: str = ""
