"""Versioned JSON input, auditable JSON output and a geometric SVG preview."""

from __future__ import annotations

import json
from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .domain import (
    COORDINATES,
    GraphConfig,
    OpeningCandidate,
    PolygonPart,
    PortalGraph,
    Room,
    SceneInput,
    WallSegment,
)
from .graph import build_graph


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document must be an object")
    return value


def _room(data: dict[str, Any]) -> Room:
    values = dict(data)
    values["parts"] = tuple(PolygonPart(**part) for part in data.get("parts", []))
    return Room(**values)


def scene_from_dict(data: dict[str, Any]) -> SceneInput:
    if data.get("schema_version") != "planportals-input/1":
        raise ValueError("expected schema_version planportals-input/1")
    if data.get("coordinates") != COORDINATES:
        raise ValueError("inputs must share original image-pixel coordinates")
    try:
        scene = SceneInput(
            tuple(_room(room) for room in data["rooms"]),
            tuple(WallSegment(**wall) for wall in data["walls"]),
            tuple(OpeningCandidate(**opening) for opening in data["openings"]),
            (data["image"]["width"], data["image"]["height"]),
            GraphConfig(**data.get("config", {})),
        )
        # Reuse the public validation policy before any outputs are written.
        build_graph(
            scene.rooms, scene.walls, scene.openings, scene.config, image_size=scene.image_size
        )
        return scene
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"invalid scene input: {error}") from error


def read_scene(path: Path) -> SceneInput:
    return scene_from_dict(read_json(path))


def write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )


def read_labelmap(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        labels = np.load(path, allow_pickle=False)
    elif path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as archive:
            if "labels" not in archive:
                raise ValueError("NPZ label map needs a 'labels' array")
            labels = archive["labels"].copy()
    else:
        with Image.open(path) as image:
            if image.mode not in {"1", "L", "P", "I", "I;16", "I;16B", "I;16L"}:
                raise ValueError("label PNG must have one integer channel, not RGB colors")
            labels = np.asarray(image).copy()
        if labels.dtype == np.bool_:
            labels = labels.astype(np.uint8)
    if labels.ndim != 2 or not labels.size or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("label map must be a nonempty 2D integer array")
    if labels.min() < 0:
        raise ValueError("negative labels are not supported")
    return labels


def read_graph(path: Path) -> PortalGraph:
    """Rebuild serialized decisions instead of trusting externally supplied route edges."""
    data = read_json(path)
    if data.get("schema_version") != "planportals/1":
        raise ValueError("expected schema_version planportals/1")
    try:
        scene_data = {
            "schema_version": "planportals-input/1",
            "coordinates": data["coordinates"],
            "image": data["image"],
            "rooms": data["rooms"],
            "walls": data["walls"],
            "config": data["config"],
            "openings": [decision["candidate"] for decision in data["decisions"]],
        }
        scene = scene_from_dict(scene_data)
        graph = build_graph(
            scene.rooms, scene.walls, scene.openings, scene.config, image_size=scene.image_size
        )
        computed = json.loads(json.dumps(graph.to_dict(), allow_nan=False))
        for key in ("decisions", "edges", "adjacency"):
            if data[key] != computed[key]:
                raise ValueError(f"serialized {key} does not match reconstructed evidence")
        return graph
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"invalid graph input: {error}") from error


def _path(points) -> str:
    return "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in points) + " Z"


def graph_svg(graph: PortalGraph) -> str:
    width, height = graph.image_size
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    centers = {}
    colors = ("#edf4ff", "#fff4e3", "#edf7ed", "#f6edff")
    for index, room in enumerate(graph.rooms):
        parts = (PolygonPart(room.points, room.holes), *room.parts)
        paths = [_path(ring) for part in parts for ring in (part.points, *part.holes)]
        path_data = " ".join(paths)
        elements.append(
            f'<path d="{path_data}" fill="{colors[index % len(colors)]}" '
            'fill-rule="evenodd" stroke="#b8bec8" stroke-width="1"/>'
        )
        center = (
            sum(point[0] for point in room.points) / len(room.points),
            sum(point[1] for point in room.points) / len(room.points),
        )
        centers[room.id] = center
        elements.append(
            f'<text x="{center[0]:.3f}" y="{center[1]:.3f}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="18">{escape(room.name)}</text>'
        )
    for wall in graph.walls:
        elements.append(
            f'<line x1="{wall.p1[0]:.3f}" y1="{wall.p1[1]:.3f}" '
            f'x2="{wall.p2[0]:.3f}" y2="{wall.p2[1]:.3f}" '
            f'stroke="#485363" stroke-width="{wall.thickness:.3f}"/>'
        )
    decisions = {decision.candidate.id: decision for decision in graph.decisions}
    for edge in graph.edges:
        candidate = decisions[edge.opening_id].candidate
        midpoint = (
            (candidate.p1[0] + candidate.p2[0]) / 2,
            (candidate.p1[1] + candidate.p2[1]) / 2,
        )
        points = (centers[edge.first], midpoint, centers[edge.second])
        coordinates = " ".join(f"{x:.3f},{y:.3f}" for x, y in points)
        elements.append(
            f'<polyline points="{coordinates}" fill="none" stroke="#7258bd" '
            'stroke-width="3" stroke-dasharray="8 5"/>'
        )
    for decision in graph.decisions:
        candidate = decision.candidate
        color = "#d15c46"
        if decision.traversable:
            color = "#26885b"
        elif candidate.kind == "window" and decision.wall_id:
            color = "#338dc0"
        elif decision.status in {"unresolved", "ambiguous"}:
            color = "#c78a1b"
        elements.append(
            f'<line x1="{candidate.p1[0]:.3f}" y1="{candidate.p1[1]:.3f}" '
            f'x2="{candidate.p2[0]:.3f}" y2="{candidate.p2[1]:.3f}" '
            f'stroke="{color}" stroke-width="7"><title>'
            f"{escape(candidate.id)}: {escape(decision.reason)}</title></line>"
        )
    elements.append(
        '<text x="12" y="25" font-family="sans-serif" font-size="15" fill="#333">'
        "Given semantic candidates; dashed graph is a room sequence only.</text>"
    )
    elements.append("</svg>")
    return "\n".join(elements) + "\n"


def save_graph(graph: PortalGraph, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    write_json(graph.to_dict(), destination / "portals.json")
    (destination / "portals.svg").write_text(graph_svg(graph), encoding="utf-8")


def config_dict(config: GraphConfig) -> dict[str, Any]:
    return asdict(config)
