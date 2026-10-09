"""Small, explicit pixel-plane geometry primitives; no learned detector is hidden here."""

from __future__ import annotations

import math

from .domain import (
    AttachmentEvidence,
    GraphConfig,
    OpeningCandidate,
    Point,
    PolygonPart,
    Ring,
    Room,
    SideEvidence,
    WallSegment,
)

EPSILON = 1e-8


def length(p1: Point, p2: Point) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def _cross(p: Point, q: Point, r: Point) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _on_segment(point: Point, p1: Point, p2: Point) -> bool:
    return (
        abs(_cross(p1, p2, point)) <= EPSILON
        and min(p1[0], p2[0]) - EPSILON <= point[0] <= max(p1[0], p2[0]) + EPSILON
        and min(p1[1], p2[1]) - EPSILON <= point[1] <= max(p1[1], p2[1]) + EPSILON
    )


def _segments_touch(a: Point, b: Point, c: Point, d: Point) -> bool:
    first, second = _cross(a, b, c), _cross(a, b, d)
    third, fourth = _cross(c, d, a), _cross(c, d, b)
    if first * second < 0 and third * fourth < 0:
        return True
    return any(
        (
            abs(cross) <= EPSILON and _on_segment(point, p1, p2)
            for cross, point, p1, p2 in (
                (first, c, a, b),
                (second, d, a, b),
                (third, a, c, d),
                (fourth, b, c, d),
            )
        )
    )


def ring_contains(point: Point, ring: Ring, *, boundary: bool = True) -> bool:
    """Ray crossing with an explicit boundary policy."""
    inside = False
    x, y = point
    for p1, p2 in zip(ring, (*ring[1:], ring[0]), strict=False):
        if _on_segment(point, p1, p2):
            return boundary
        if (p1[1] > y) != (p2[1] > y):
            intersection = p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1])
            if x < intersection:
                inside = not inside
    return inside


def room_contains(point: Point, room: Room) -> bool:
    parts = (PolygonPart(room.points, room.holes), *room.parts)
    return any(
        ring_contains(point, part.points)
        and not any(ring_contains(point, hole) for hole in part.holes)
        for part in parts
    )


def validate_room(room: Room) -> None:
    """Reject invalid rings; cross-room overlaps remain visible in sampling evidence."""
    for part in (PolygonPart(room.points, room.holes), *room.parts):
        rings = (part.points, *part.holes)
        for ring in rings:
            pairs = tuple(zip(ring, (*ring[1:], ring[0]), strict=False))
            for first, (a, b) in enumerate(pairs):
                if a == b:
                    raise ValueError(f"room {room.id}: consecutive duplicate polygon vertices")
                for second in range(first + 1, len(pairs)):
                    if second == first + 1 or (first == 0 and second == len(pairs) - 1):
                        continue
                    c, d = pairs[second]
                    if _segments_touch(a, b, c, d):
                        raise ValueError(f"room {room.id}: self-intersecting polygon ring")
        for hole in part.holes:
            if not all(ring_contains(point, part.points, boundary=False) for point in hole):
                raise ValueError(f"room {room.id}: hole must lie strictly inside exterior")
            for a, b in zip(hole, (*hole[1:], hole[0]), strict=False):
                for c, d in zip(part.points, (*part.points[1:], part.points[0]), strict=False):
                    if _segments_touch(a, b, c, d):
                        raise ValueError(f"room {room.id}: hole crosses exterior")
        for index, first_hole in enumerate(part.holes):
            for second_hole in part.holes[index + 1 :]:
                if (
                    ring_contains(first_hole[0], second_hole)
                    or ring_contains(second_hole[0], first_hole)
                    or any(
                        _segments_touch(a, b, c, d)
                        for a, b in zip(first_hole, (*first_hole[1:], first_hole[0]), strict=True)
                        for c, d in zip(
                            second_hole, (*second_hole[1:], second_hole[0]), strict=True
                        )
                    )
                ):
                    raise ValueError(f"room {room.id}: holes must not overlap, nest or touch")


def attachment(
    candidate: OpeningCandidate, wall: WallSegment, config: GraphConfig
) -> AttachmentEvidence | None:
    wall_length = length(wall.p1, wall.p2)
    candidate_length = length(candidate.p1, candidate.p2)
    tangent = (
        (wall.p2[0] - wall.p1[0]) / wall_length,
        (wall.p2[1] - wall.p1[1]) / wall_length,
    )
    opening_direction = (
        (candidate.p2[0] - candidate.p1[0]) / candidate_length,
        (candidate.p2[1] - candidate.p1[1]) / candidate_length,
    )
    cosine = min(1.0, abs(sum(a * b for a, b in zip(tangent, opening_direction, strict=False))))
    angle = math.degrees(math.acos(cosine))
    if angle > config.max_angle_deg + EPSILON:
        return None
    projections = tuple(
        (point[0] - wall.p1[0]) * tangent[0] + (point[1] - wall.p1[1]) * tangent[1]
        for point in (candidate.p1, candidate.p2)
    )
    projected_points = tuple(
        (wall.p1[0] + value * tangent[0], wall.p1[1] + value * tangent[1]) for value in projections
    )
    max_distance = max(
        length(point, projected)
        for point, projected in zip((candidate.p1, candidate.p2), projected_points, strict=False)
    )
    if max_distance > config.attach_distance_px + wall.thickness / 2 + EPSILON:
        return None
    low, high = sorted(projections)
    overlap = max(0.0, min(high, wall_length) - max(low, 0.0))
    if overlap < min(config.min_opening_width_px, high - low) - EPSILON:
        return None
    fully_supported = (
        low >= -config.endpoint_tolerance_px and high <= wall_length + config.endpoint_tolerance_px
    )
    return AttachmentEvidence(
        wall.id,
        angle,
        max_distance,
        overlap,
        projected_points[0],
        projected_points[1],
        fully_supported,
        (wall.id,),
    )


def flanking_supports(
    candidate: OpeningCandidate, walls: tuple[WallSegment, ...], config: GraphConfig
) -> tuple[tuple[WallSegment, AttachmentEvidence], ...]:
    """Attach a typed opening between facing ends of two collinear wall pieces.

    The temporary span is an association hypothesis only. No wall mask or geometry is filled.
    Both candidate ends must approach the corresponding wall ends; arbitrary long empty
    distances between two unrelated walls do not become inferred doors.
    """
    if candidate.kind == "unknown":
        return ()
    nearby_walls = tuple(
        wall
        for wall in walls
        if min(
            length(endpoint, point)
            for endpoint in (wall.p1, wall.p2)
            for point in (candidate.p1, candidate.p2)
        )
        <= config.endpoint_tolerance_px + config.attach_distance_px + wall.thickness
    )
    hypotheses = []
    for first_index, first in enumerate(nearby_walls):
        first_length = length(first.p1, first.p2)
        tangent = (
            (first.p2[0] - first.p1[0]) / first_length,
            (first.p2[1] - first.p1[1]) / first_length,
        )
        for second in nearby_walls[first_index + 1 :]:
            second_length = length(second.p1, second.p2)
            other_tangent = (
                (second.p2[0] - second.p1[0]) / second_length,
                (second.p2[1] - second.p1[1]) / second_length,
            )
            cosine = min(1.0, abs(sum(a * b for a, b in zip(tangent, other_tangent, strict=False))))
            if math.degrees(math.acos(cosine)) > min(5.0, config.max_angle_deg) + EPSILON:
                continue
            projections = tuple(
                (point[0] - first.p1[0]) * tangent[0] + (point[1] - first.p1[1]) * tangent[1]
                for point in (second.p1, second.p2)
            )
            distance = max(
                abs((point[0] - first.p1[0]) * -tangent[1] + (point[1] - first.p1[1]) * tangent[0])
                for point in (second.p1, second.p2)
            )
            if distance > max(1.0, min(first.thickness, second.thickness) / 2):
                continue
            second_low, second_high = sorted(projections)
            if second_low > first_length + EPSILON:
                low, high = first_length, second_low
            elif second_high < -EPSILON:
                low, high = second_high, 0.0
            else:
                continue
            gap_width = high - low
            end_tolerance = (
                config.endpoint_tolerance_px + min(first.thickness, second.thickness) / 2
            )
            if gap_width > config.max_opening_width_px + 2 * end_tolerance:
                continue
            candidate_projections = sorted(
                (point[0] - first.p1[0]) * tangent[0] + (point[1] - first.p1[1]) * tangent[1]
                for point in (candidate.p1, candidate.p2)
            )
            if (
                abs(candidate_projections[0] - low) > end_tolerance
                or abs(candidate_projections[1] - high) > end_tolerance
            ):
                continue
            source_ids = tuple(sorted((first.id, second.id)))
            virtual = WallSegment(
                "flanking:" + "|".join(f"{len(value)}:{value}" for value in source_ids),
                (first.p1[0] + low * tangent[0], first.p1[1] + low * tangent[1]),
                (first.p1[0] + high * tangent[0], first.p1[1] + high * tangent[1]),
                (first.thickness + second.thickness) / 2,
            )
            evidence = attachment(candidate, virtual, config)
            if evidence is not None and evidence.fully_supported:
                evidence = AttachmentEvidence(
                    evidence.wall_id,
                    evidence.angle_deg,
                    evidence.max_distance_px,
                    evidence.overlap_px,
                    evidence.projected_p1,
                    evidence.projected_p2,
                    True,
                    source_ids,
                    "flanking_walls",
                )
                hypotheses.append((virtual, evidence))
    return tuple(hypotheses)


def side_evidence(
    match: AttachmentEvidence,
    wall: WallSegment,
    rooms: tuple[Room, ...],
    config: GraphConfig,
) -> tuple[SideEvidence, SideEvidence]:
    wall_length = length(wall.p1, wall.p2)
    normal = (
        -(wall.p2[1] - wall.p1[1]) / wall_length,
        (wall.p2[0] - wall.p1[0]) / wall_length,
    )
    offset = wall.thickness / 2 + config.sample_offset_px
    results = []
    for sign in (-1, 1):
        points = []
        memberships = []
        votes: dict[str, int] = {}
        for index in range(config.sample_count):
            fraction = (index + 0.5) / config.sample_count
            point = (
                match.projected_p1[0]
                + fraction * (match.projected_p2[0] - match.projected_p1[0])
                + sign * offset * normal[0],
                match.projected_p1[1]
                + fraction * (match.projected_p2[1] - match.projected_p1[1])
                + sign * offset * normal[1],
            )
            points.append(point)
            membership = tuple(sorted(room.id for room in rooms if room_contains(point, room)))
            memberships.append(membership)
            for room_id in membership:
                votes[room_id] = votes.get(room_id, 0) + 1
        room_id = None
        if any(len(membership) > 1 for membership in memberships):
            status = "overlapping_rooms"
        elif len(votes) > 1:
            status = "multiple_rooms_along_opening"
        elif not votes:
            status = "outside"
        else:
            selected, count = next(iter(votes.items()))
            if count / config.sample_count + EPSILON >= config.vote_fraction:
                room_id, status = selected, "assigned"
            else:
                status = "insufficient_room_support"
        results.append(
            SideEvidence(
                tuple(points), tuple(memberships), tuple(sorted(votes.items())), room_id, status
            )
        )
    return (results[0], results[1])
