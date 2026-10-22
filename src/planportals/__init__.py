"""Evidence-preserving door/window attachment and topological room routing."""

from .adapters import (
    openings_from_mask,
    rooms_from_labelmap,
    rooms_from_planregions,
    walls_from_wallgraph,
)
from .domain import (
    AttachmentEvidence,
    GraphConfig,
    OpeningCandidate,
    OpeningDecision,
    PolygonPart,
    PortalGraph,
    Room,
    RoomEdge,
    RouteResult,
    SceneInput,
    SideEvidence,
    WallSegment,
)
from .graph import analyze_access, build_graph, find_route

__version__ = "0.1.0"
__all__ = [
    "AttachmentEvidence",
    "GraphConfig",
    "OpeningCandidate",
    "OpeningDecision",
    "PolygonPart",
    "PortalGraph",
    "Room",
    "RoomEdge",
    "RouteResult",
    "SceneInput",
    "SideEvidence",
    "WallSegment",
    "analyze_access",
    "build_graph",
    "find_route",
    "openings_from_mask",
    "rooms_from_labelmap",
    "rooms_from_planregions",
    "walls_from_wallgraph",
]
