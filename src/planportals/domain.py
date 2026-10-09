"""Immutable observations and decisions, in one shared image-pixel coordinate system."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Point = tuple[float, float]
Ring = tuple[Point, ...]
OpeningKind = Literal["door", "window", "unknown"]
COORDINATES = {"origin": "top_left", "x": "right", "y": "down", "unit": "px"}


def _identifier(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("IDs must be nonempty strings")


def _point(value: Point) -> Point:
    if len(value) != 2 or not all(math.isfinite(float(v)) for v in value):
        raise ValueError("points must contain two finite coordinates")
    return (float(value[0]), float(value[1]))


def _ring(value: Ring) -> Ring:
    points = tuple(_point(point) for point in value)
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if len(set(points)) < 3:
        raise ValueError("polygon rings need at least three distinct points")
    area = sum(
        p[0] * q[1] - q[0] * p[1] for p, q in zip(points, (*points[1:], points[0]), strict=False)
    )
    if abs(area) < 1e-8:
        raise ValueError("polygon rings must have positive area")
    return points


@dataclass(frozen=True)
class PolygonPart:
    points: Ring
    holes: tuple[Ring, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", _ring(self.points))
        object.__setattr__(self, "holes", tuple(_ring(hole) for hole in self.holes))


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    points: Ring
    holes: tuple[Ring, ...] = ()
    parts: tuple[PolygonPart, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id)
        if not isinstance(self.name, str):
            raise ValueError("room name must be a string")
        object.__setattr__(self, "points", _ring(self.points))
        object.__setattr__(self, "holes", tuple(_ring(hole) for hole in self.holes))
        object.__setattr__(self, "parts", tuple(self.parts))
        if any(not isinstance(part, PolygonPart) for part in self.parts):
            raise ValueError("room parts must be PolygonPart instances")


@dataclass(frozen=True)
class WallSegment:
    id: str
    p1: Point
    p2: Point
    thickness: float = 8.0

    def __post_init__(self) -> None:
        _identifier(self.id)
        object.__setattr__(self, "p1", _point(self.p1))
        object.__setattr__(self, "p2", _point(self.p2))
        if self.p1 == self.p2:
            raise ValueError("wall endpoints must differ")
        if not math.isfinite(self.thickness) or self.thickness <= 0:
            raise ValueError("wall thickness must be finite and positive")


@dataclass(frozen=True)
class OpeningCandidate:
    id: str
    kind: OpeningKind
    p1: Point
    p2: Point
    score: float | None = None
    source: str = "unknown"
    quality_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id)
        if self.kind not in {"door", "window", "unknown"}:
            raise ValueError("opening kind must be door, window or unknown")
        object.__setattr__(self, "p1", _point(self.p1))
        object.__setattr__(self, "p2", _point(self.p2))
        if self.p1 == self.p2:
            raise ValueError("opening endpoints must differ")
        if self.score is not None and (not math.isfinite(self.score) or not 0 <= self.score <= 1):
            raise ValueError("detector scores must be finite in [0,1] or null")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("opening source must be a nonempty string")
        object.__setattr__(self, "quality_issues", tuple(self.quality_issues))
        if any(not isinstance(issue, str) or not issue for issue in self.quality_issues):
            raise ValueError("quality issues must be nonempty strings")


@dataclass(frozen=True)
class GraphConfig:
    attach_distance_px: float = 12.0
    max_angle_deg: float = 15.0
    endpoint_tolerance_px: float = 6.0
    sample_offset_px: float = 8.0
    sample_count: int = 5
    vote_fraction: float = 0.8
    min_opening_width_px: float = 2.0
    max_opening_width_px: float = 400.0
    min_detector_score: float = 0.5
    mm_per_px: float | None = None
    mm_per_px_y: float | None = None
    minimum_clearance_mm: float | None = None

    def __post_init__(self) -> None:
        finite = [
            self.attach_distance_px,
            self.max_angle_deg,
            self.endpoint_tolerance_px,
            self.sample_offset_px,
            self.vote_fraction,
            self.min_opening_width_px,
            self.max_opening_width_px,
            self.min_detector_score,
        ]
        if not all(math.isfinite(v) for v in finite):
            raise ValueError("config numeric values must be finite")
        if self.attach_distance_px < 0 or self.endpoint_tolerance_px < 0:
            raise ValueError("distance tolerances cannot be negative")
        if not 0 <= self.max_angle_deg < 90 or self.sample_offset_px <= 0:
            raise ValueError("angle must be in [0,90); sample offset must be positive")
        if not isinstance(self.sample_count, int) or self.sample_count < 3:
            raise ValueError("sample_count must be an integer >=3")
        if not 0.5 < self.vote_fraction <= 1 or not 0 <= self.min_detector_score <= 1:
            raise ValueError("invalid vote fraction or score threshold")
        if not 0 < self.min_opening_width_px <= self.max_opening_width_px:
            raise ValueError("invalid opening width bounds")
        for value in (self.mm_per_px, self.mm_per_px_y, self.minimum_clearance_mm):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError("metric scales and clearance must be finite and positive")
        if self.mm_per_px_y is not None and self.mm_per_px is None:
            raise ValueError("mm_per_px_y requires mm_per_px")
        if self.minimum_clearance_mm is not None and self.mm_per_px is None:
            raise ValueError("minimum_clearance_mm requires a metric calibration")


@dataclass(frozen=True)
class SceneInput:
    rooms: tuple[Room, ...]
    walls: tuple[WallSegment, ...]
    openings: tuple[OpeningCandidate, ...]
    image_size: tuple[int, int]
    config: GraphConfig = field(default_factory=GraphConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "planportals-input/1",
            "image": {"width": self.image_size[0], "height": self.image_size[1]},
            "coordinates": dict(COORDINATES),
            "rooms": [asdict(room) for room in self.rooms],
            "walls": [asdict(wall) for wall in self.walls],
            "openings": [asdict(opening) for opening in self.openings],
            "config": asdict(self.config),
        }


@dataclass(frozen=True)
class SideEvidence:
    sample_points: tuple[Point, ...]
    memberships: tuple[tuple[str, ...], ...]
    votes: tuple[tuple[str, int], ...]
    room_id: str | None
    status: str


@dataclass(frozen=True)
class AttachmentEvidence:
    wall_id: str
    angle_deg: float
    max_distance_px: float
    overlap_px: float
    projected_p1: Point
    projected_p2: Point
    fully_supported: bool
    support_wall_ids: tuple[str, ...] = ()
    support_kind: str = "continuous_wall"


@dataclass(frozen=True)
class OpeningDecision:
    candidate: OpeningCandidate
    status: str
    reason: str
    wall_id: str | None
    room_ids: tuple[str | None, str | None]
    width_px: float
    width_mm: float | None
    clearance_status: str
    traversable: bool
    attachments: tuple[AttachmentEvidence, ...] = ()
    sides: tuple[SideEvidence, ...] = ()


@dataclass(frozen=True)
class RoomEdge:
    first: str
    second: str
    opening_id: str
    kind: str


@dataclass(frozen=True)
class PortalGraph:
    rooms: tuple[Room, ...]
    walls: tuple[WallSegment, ...]
    decisions: tuple[OpeningDecision, ...]
    edges: tuple[RoomEdge, ...]
    adjacency: tuple[RoomEdge, ...]
    image_size: tuple[int, int]
    config: GraphConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "planportals/1",
            "image": {"width": self.image_size[0], "height": self.image_size[1]},
            "coordinates": dict(COORDINATES),
            "rooms": [asdict(room) for room in self.rooms],
            "walls": [asdict(wall) for wall in self.walls],
            "decisions": [asdict(decision) for decision in self.decisions],
            "edges": [asdict(edge) for edge in self.edges],
            "adjacency": [asdict(edge) for edge in self.adjacency],
            "config": asdict(self.config),
            "semantics": {
                "edges": "room_sequence_via_accepted_doors",
                "adjacency": "accepted_typed_openings_between_rooms",
                "scores": "upstream_detector_scores_not_calibrated_probabilities",
                "clearance": "candidate_span_not_measured_net_free_width",
                "route": "topological_room_sequence_not_collision_free_navigation",
            },
        }


@dataclass(frozen=True)
class RouteResult:
    status: str
    room_ids: tuple[str, ...]
    opening_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "planportals-route/1",
            **asdict(self),
            "meaning": "room sequence, not a collision-free navigation path",
        }
