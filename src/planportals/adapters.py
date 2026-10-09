"""Model-independent adapters; callers supply their own labels and detections."""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np

from .domain import COORDINATES, OpeningCandidate, PolygonPart, Room, WallSegment


def _contract(data: dict[str, Any], schema: str) -> tuple[int, int]:
    if data.get("schema_version") != schema or data.get("coordinates") != COORDINATES:
        raise ValueError(f"expected {schema} in original image-pixel coordinates")
    image = data.get("image", {})
    width, height = image.get("width"), image.get("height")
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or isinstance(width, bool)
        or isinstance(height, bool)
        or min(width, height) <= 0
    ):
        raise ValueError("upstream image dimensions must be positive integers")
    return (width, height)


def walls_from_wallgraph(data: dict[str, Any]) -> tuple[WallSegment, ...]:
    """Split each WallGraph polyline into named straight pieces, retaining its ID."""
    _contract(data, "wallgraph/1")
    walls = []
    source_ids = []
    for segment in data.get("segments", []):
        source_id = str(segment["id"])
        source_ids.append(source_id)
        points = tuple((float(point["x"]), float(point["y"])) for point in segment["points"])
        if len(points) < 2:
            raise ValueError("WallGraph segments must have at least two points")
        for index, (p1, p2) in enumerate(zip(points, points[1:], strict=False)):
            walls.append(
                WallSegment(
                    f"wallgraph:{source_id}:{index}", p1, p2, float(segment["thickness_px"])
                )
            )
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("duplicate WallGraph segment ID")
    return tuple(walls)


def rooms_from_planregions(data: dict[str, Any]) -> tuple[Room, ...]:
    """Read PlanRegions geometry, preserving multipart rooms and exclusion holes."""
    _contract(data, "planregions/1")
    rooms = []
    for region in data.get("regions", []):
        parts = tuple(
            PolygonPart(
                tuple(tuple(point) for point in polygon["exterior"]),
                tuple(tuple(tuple(point) for point in hole) for hole in polygon.get("holes", [])),
            )
            for polygon in region["polygons"]
        )
        if not parts:
            raise ValueError("PlanRegions room must have at least one polygon")
        attribute = region.get("attribute", {})
        name = attribute.get("label") or f"Room {region['id']}"
        rooms.append(Room(str(region["id"]), str(name), parts[0].points, parts[0].holes, parts[1:]))
    if len({room.id for room in rooms}) != len(rooms):
        raise ValueError("duplicate PlanRegions room ID")
    return tuple(rooms)


def rooms_from_labelmap(
    labels: np.ndarray, names: dict[int, str] | None = None
) -> tuple[Room, ...]:
    """Exact pixel-cell polygons, merged into rectangles; zero stays excluded.

    Rectangle parts preserve holes and disconnected pieces without contour approximation.
    Coordinates refer to pixel centers, so a pixel at (x,y) occupies x/y +/-0.5.
    For large irregular maps, prefer PlanRegions' compact polygon JSON adapter.
    """
    _validate_labels(labels)
    names = {} if names is None else names
    rectangles: dict[int, list[tuple[int, int, int, int]]] = {}
    active: dict[tuple[int, int, int], tuple[int, int]] = {}
    for y, row in enumerate(labels):
        starts = np.flatnonzero(np.r_[True, row[1:] != row[:-1]])
        ends = np.r_[starts[1:], len(row)]
        present = {
            (int(row[start]), int(start), int(end))
            for start, end in zip(starts, ends, strict=False)
            if row[start] != 0
        }
        for key in set(active) - present:
            start_y, end_y = active.pop(key)
            label, left, right = key
            rectangles.setdefault(label, []).append((left, start_y, right, end_y))
        for key in present:
            start_y = active.get(key, (y, y + 1))[0]
            active[key] = (start_y, y + 1)
    for (label, left, right), (start_y, end_y) in active.items():
        rectangles.setdefault(label, []).append((left, start_y, right, end_y))
    rooms = []
    for label, boxes in sorted(rectangles.items()):
        parts = tuple(
            PolygonPart(
                (
                    (left - 0.5, top - 0.5),
                    (right - 0.5, top - 0.5),
                    (right - 0.5, bottom - 0.5),
                    (left - 0.5, bottom - 0.5),
                )
            )
            for left, top, right, bottom in sorted(boxes)
        )
        rooms.append(
            Room(str(label), names.get(label, f"Room {label}"), parts[0].points, parts=parts[1:])
        )
    return tuple(rooms)


def _validate_labels(labels: np.ndarray) -> None:
    if (
        not isinstance(labels, np.ndarray)
        or labels.ndim != 2
        or not labels.size
        or not np.issubdtype(labels.dtype, np.integer)
        or labels.min() < 0
    ):
        raise ValueError("label maps must be nonempty 2D nonnegative integer arrays")


def _components(binary: np.ndarray):
    """Four-connected components, using only NumPy plus the Python standard library."""
    visited = np.zeros(binary.shape, dtype=bool)
    height, width = binary.shape
    for y, x in np.argwhere(binary):
        y, x = int(y), int(x)
        if visited[y, x]:
            continue
        visited[y, x] = True
        queue = deque([(y, x)])
        points = []
        while queue:
            row, column = queue.popleft()
            points.append((column, row))
            for other_y, other_x in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            ):
                if (
                    0 <= other_y < height
                    and 0 <= other_x < width
                    and binary[other_y, other_x]
                    and not visited[other_y, other_x]
                ):
                    visited[other_y, other_x] = True
                    queue.append((other_y, other_x))
        yield np.asarray(points, dtype=np.float64)


def openings_from_mask(
    label_map: np.ndarray,
    door_classes: tuple[int, ...] | list[int],
    window_classes: tuple[int, ...] | list[int],
    min_area: int = 12,
    *,
    min_aspect_ratio: float = 1.5,
) -> tuple[OpeningCandidate, ...]:
    """Fit principal spans to supplied hard semantic components, without reclassification.

    Tiny and near-square components are retained with quality issues for graph rejection.
    Hard labels carry no confidence score: score is null, never a fabricated probability.
    The span is a mask extent; it is not a measurement of unobstructed door clearance.
    """
    _validate_labels(label_map)
    classes = tuple(door_classes), tuple(window_classes)
    if (
        any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for values in classes
            for value in values
        )
        or set(classes[0]) & set(classes[1])
        or any(len(set(values)) != len(values) for values in classes)
    ):
        raise ValueError("door/window classes must be unique disjoint positive integers")
    if (
        not isinstance(min_area, int)
        or min_area <= 0
        or not np.isfinite(min_aspect_ratio)
        or min_aspect_ratio < 1
    ):
        raise ValueError("invalid component area/aspect ratio thresholds")
    candidates = []
    for kind, class_ids in zip(("door", "window"), classes, strict=False):
        for class_id in sorted(class_ids):
            for index, points in enumerate(_components(label_map == class_id)):
                center = points.mean(axis=0)
                centered = points - center
                covariance = centered.T @ centered / len(points)
                _, vectors = np.linalg.eigh(covariance)
                axis = vectors[:, -1]
                if axis[0] < 0 or (abs(axis[0]) < 1e-8 and axis[1] < 0):
                    axis = -axis
                normal = np.array([-axis[1], axis[0]])
                longitudinal, transverse = centered @ axis, centered @ normal
                major = float(np.ptp(longitudinal)) + 1.0
                minor = float(np.ptp(transverse)) + 1.0
                p1 = center + (float(longitudinal.min()) - 0.5) * axis
                p2 = center + (float(longitudinal.max()) + 0.5) * axis
                issues = []
                if len(points) < min_area:
                    issues.append("component_below_minimum_area")
                if major / minor < min_aspect_ratio:
                    issues.append("component_has_no_clear_long_axis")
                candidates.append(
                    OpeningCandidate(
                        f"mask:{kind}:{class_id}:{index}",
                        kind,
                        tuple(p1),
                        tuple(p2),
                        source="semantic-mask",
                        quality_issues=tuple(issues),
                    )
                )
    return tuple(candidates)
