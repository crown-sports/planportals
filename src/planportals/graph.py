"""Conservative graph construction: retain observations, admit only supported doors."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import replace

from .domain import (
    GraphConfig,
    OpeningCandidate,
    OpeningDecision,
    PortalGraph,
    Room,
    RoomEdge,
    RouteResult,
    WallSegment,
)
from .geometry import attachment, flanking_supports, length, side_evidence, validate_room

UNTYPED_SOURCES = {"unknown", "gap", "geometry_gap", "wall_gap", "untyped_gap"}


def _validate_input(
    rooms: tuple[Room, ...],
    walls: tuple[WallSegment, ...],
    openings: tuple[OpeningCandidate, ...],
    image_size: tuple[int, int],
) -> None:
    if len(image_size) != 2 or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in image_size
    ):
        raise ValueError("image_size must contain positive integer width and height")
    for kind, values in (("room", rooms), ("wall", walls), ("opening", openings)):
        ids = [value.id for value in values]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate {kind} ID")
    for room in rooms:
        validate_room(room)
    points = []
    for room in rooms:
        points.extend(room.points)
        for hole in room.holes:
            points.extend(hole)
        for part in room.parts:
            points.extend(part.points)
            for hole in part.holes:
                points.extend(hole)
    for item in (*walls, *openings):
        points.extend((item.p1, item.p2))
    if any(
        not -0.5 <= point[0] <= image_size[0] or not -0.5 <= point[1] <= image_size[1]
        for point in points
    ):
        raise ValueError("input coordinates exceed the declared image bounds")


def build_graph(
    rooms: tuple[Room, ...],
    walls: tuple[WallSegment, ...],
    openings: tuple[OpeningCandidate, ...],
    config: GraphConfig | None = None,
    *,
    image_size: tuple[int, int],
) -> PortalGraph:
    rooms, walls, openings = tuple(rooms), tuple(walls), tuple(openings)
    config = GraphConfig() if config is None else config
    _validate_input(rooms, walls, openings, image_size)
    decisions, edges, adjacency = [], [], []
    walls_by_id = {wall.id: wall for wall in walls}
    for candidate in openings:
        width = length(candidate.p1, candidate.p2)
        width_mm = None
        if config.mm_per_px is not None:
            scale_y = config.mm_per_px_y or config.mm_per_px
            width_mm = math.hypot(
                (candidate.p2[0] - candidate.p1[0]) * config.mm_per_px,
                (candidate.p2[1] - candidate.p1[1]) * scale_y,
            )
            if not math.isfinite(width_mm):
                raise ValueError("metric opening width is not finite; check calibration magnitude")
        clearance = "not_checked"
        if config.minimum_clearance_mm is not None and width_mm is not None:
            clearance = (
                "span_meets_minimum"
                if width_mm >= config.minimum_clearance_mm
                else "span_below_minimum"
            )
        matches = tuple(
            evidence
            for wall in walls
            if (evidence := attachment(candidate, wall, config)) is not None
        )
        for virtual, evidence in flanking_supports(candidate, walls, config):
            walls_by_id[virtual.id] = virtual
            matches += (evidence,)
        full = tuple(evidence for evidence in matches if evidence.fully_supported)
        competing_partial = (
            tuple(
                evidence
                for evidence in matches
                if not evidence.fully_supported and evidence.wall_id not in full[0].support_wall_ids
            )
            if len(full) == 1
            else ()
        )
        status, reason, wall_id, room_ids = "rejected", "no_wall_support", None, (None, None)
        sides = ()
        traversable = False
        if candidate.quality_issues:
            reason = "invalid_candidate_geometry"
        elif not config.min_opening_width_px <= width <= config.max_opening_width_px:
            reason = "opening_width_out_of_bounds"
        elif candidate.score is not None and candidate.score < config.min_detector_score:
            reason = "upstream_score_below_threshold"
        elif len(full) > 1 or competing_partial:
            status, reason = "ambiguous", "multiple_wall_supports"
        elif not full:
            if len(matches) > 1:
                status, reason = "ambiguous", "crosses_multiple_wall_segments"
            elif matches:
                reason = "extends_beyond_wall_segment"
        else:
            match = full[0]
            wall_id = match.wall_id
            sides = side_evidence(match, walls_by_id[wall_id], rooms, config)
            room_ids = (sides[0].room_id, sides[1].room_id)
            if any(side.status not in {"assigned", "outside"} for side in sides):
                status, reason = "ambiguous", "room_assignment_conflict"
            elif candidate.kind == "unknown" or candidate.source.strip().lower() in UNTYPED_SOURCES:
                status, reason = "unresolved", "semantic_opening_type_required"
            elif room_ids[0] is None or room_ids[1] is None:
                status, reason = "attached", "exterior_or_unassigned_side"
            elif room_ids[0] == room_ids[1]:
                reason = "same_room_both_sides"
            else:
                status = "accepted"
                if candidate.kind == "window":
                    reason = "window_is_not_a_passage"
                elif clearance == "span_below_minimum":
                    reason = "candidate_span_below_requested_clearance"
                else:
                    reason, traversable = "supported_semantic_door", True
                edge = RoomEdge(room_ids[0], room_ids[1], candidate.id, candidate.kind)
                adjacency.append(edge)
                if traversable:
                    edges.append(edge)
        decisions.append(
            OpeningDecision(
                candidate,
                status,
                reason,
                wall_id,
                room_ids,
                width,
                width_mm,
                clearance,
                traversable,
                matches,
                sides,
            )
        )
    conflicts = _semantic_conflicts(tuple(decisions), walls_by_id)
    if conflicts:
        decisions = [
            replace(
                decision,
                status="ambiguous",
                reason="conflicting_semantic_candidates",
                traversable=False,
            )
            if decision.candidate.id in conflicts
            else decision
            for decision in decisions
        ]
        edges = [edge for edge in edges if edge.opening_id not in conflicts]
        adjacency = [edge for edge in adjacency if edge.opening_id not in conflicts]
    return PortalGraph(
        rooms, walls, tuple(decisions), tuple(edges), tuple(adjacency), image_size, config
    )


def _semantic_conflicts(
    decisions: tuple[OpeningDecision, ...], walls: dict[str, WallSegment]
) -> set[str]:
    """Overlapping door/window claims remain ambiguous regardless of detector score."""
    conflicts = set()
    for index, first in enumerate(decisions):
        if first.status not in {"accepted", "attached"} or first.wall_id is None:
            continue
        wall = walls[first.wall_id]
        wall_length = length(wall.p1, wall.p2)
        tangent = ((wall.p2[0] - wall.p1[0]) / wall_length, (wall.p2[1] - wall.p1[1]) / wall_length)
        for second in decisions[index + 1 :]:
            if (
                second.status not in {"accepted", "attached"}
                or second.wall_id != first.wall_id
                or {first.candidate.kind, second.candidate.kind} != {"door", "window"}
            ):
                continue
            intervals = [
                sorted(
                    (point[0] - wall.p1[0]) * tangent[0] + (point[1] - wall.p1[1]) * tangent[1]
                    for point in (decision.candidate.p1, decision.candidate.p2)
                )
                for decision in (first, second)
            ]
            overlap = min(intervals[0][1], intervals[1][1]) - max(intervals[0][0], intervals[1][0])
            minimum_span = min(high - low for low, high in intervals)
            if overlap / minimum_span >= 0.5:
                conflicts.update((first.candidate.id, second.candidate.id))
    return conflicts


def find_route(graph: PortalGraph, from_room: str, to_room: str) -> RouteResult:
    room_ids = {room.id for room in graph.rooms}
    if from_room not in room_ids or to_room not in room_ids:
        raise ValueError("route endpoints must be declared room IDs")
    if from_room == to_room:
        return RouteResult("found", (from_room,), (), "same_room")
    connections: dict[str, list[tuple[str, str]]] = {room_id: [] for room_id in room_ids}
    for edge in graph.edges:
        connections[edge.first].append((edge.second, edge.opening_id))
        connections[edge.second].append((edge.first, edge.opening_id))
    queue = deque([from_room])
    predecessors: dict[str, tuple[str, str] | None] = {from_room: None}
    while queue:
        room_id = queue.popleft()
        for neighbor, opening_id in sorted(connections[room_id]):
            if neighbor in predecessors:
                continue
            predecessors[neighbor] = (room_id, opening_id)
            if neighbor == to_room:
                result_rooms = [to_room]
                result_openings = []
                cursor = to_room
                while (previous := predecessors[cursor]) is not None:
                    cursor, opening = previous
                    result_rooms.append(cursor)
                    result_openings.append(opening)
                return RouteResult(
                    "found",
                    tuple(reversed(result_rooms)),
                    tuple(reversed(result_openings)),
                    "accepted_door_sequence",
                )
            queue.append(neighbor)
    return RouteResult("no_path", (), (), "no_sequence_of_accepted_doors")
