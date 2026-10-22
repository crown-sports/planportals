"""Local CLI: user-supplied geometry and semantic observations stay on the caller's disk."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from PIL import Image

from .adapters import (
    openings_from_mask,
    rooms_from_labelmap,
    rooms_from_planregions,
    walls_from_wallgraph,
)
from .demo import demo_scene
from .domain import COORDINATES, GraphConfig, SceneInput
from .graph import analyze_access, build_graph, find_route
from .io import read_graph, read_json, read_labelmap, read_scene, save_graph, write_json


def _classes(text: str) -> tuple[int, ...]:
    try:
        return tuple(int(item.strip()) for item in text.split(",") if item.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError("class IDs must be comma-separated integers") from error


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="planportals", description="Attach supplied doors/windows and build room sequences."
    )
    commands = result.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build from JSON or upstream geometry plus labels")
    source = build.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="planportals-input/1 JSON")
    source.add_argument("--wallgraph", type=Path, help="WallGraph walls.json")
    build.add_argument("--planregions", type=Path, help="PlanRegions regions.json")
    build.add_argument("--room-labels", type=Path, help="integer PNG/NPY/NPZ room labels")
    build.add_argument(
        "--opening-mask", type=Path, help="integer door/window labels at native size"
    )
    build.add_argument("--door-classes", type=_classes, default=())
    build.add_argument("--window-classes", type=_classes, default=())
    build.add_argument("--min-opening-area", type=int, default=12)
    build.add_argument("--mm-per-px", type=float)
    build.add_argument("--mm-per-px-y", type=float)
    build.add_argument("--minimum-clearance-mm", type=float)
    build.add_argument("--output", type=Path, required=True)
    route = commands.add_parser("route", help="find a room sequence through accepted doors")
    route.add_argument("--graph", type=Path, required=True)
    route.add_argument("--from-room", required=True)
    route.add_argument("--to-room", required=True)
    route.add_argument("--output", type=Path, help="optional route JSON file")
    route.add_argument("--blocked-openings", nargs="+", default=[])
    route.add_argument("--fail-if-unreachable", action="store_true")
    access = commands.add_parser(
        "access", help="Compare baseline and closure-scenario reachability"
    )
    access.add_argument("--graph", type=Path, required=True)
    access.add_argument("--from-room", required=True)
    access.add_argument("--blocked-openings", nargs="+", default=[])
    access.add_argument("--output", type=Path, required=True)
    access.add_argument("--fail-on-newly-isolated", action="store_true")
    demo = commands.add_parser("demo", help="generate an original annotated scene and its graph")
    demo.add_argument("--output", type=Path, required=True)
    return result


def _upstream_scene(args) -> SceneInput:
    walls_data = read_json(args.wallgraph)
    walls = walls_from_wallgraph(walls_data)
    size = (walls_data["image"]["width"], walls_data["image"]["height"])
    if bool(args.planregions) == bool(args.room_labels):
        raise ValueError("--wallgraph requires exactly one of --planregions or --room-labels")
    if args.planregions:
        regions_data = read_json(args.planregions)
        rooms = rooms_from_planregions(regions_data)
        if regions_data["image"] != walls_data["image"]:
            raise ValueError("wall and room image dimensions differ")
    else:
        labels = read_labelmap(args.room_labels)
        if labels.shape != (size[1], size[0]):
            raise ValueError("room label dimensions differ from wall coordinates")
        rooms = rooms_from_labelmap(labels)
    if not args.opening_mask:
        raise ValueError("upstream mode requires --opening-mask and explicit class IDs")
    return SceneInput(rooms, walls, (), size, GraphConfig())


def _run_build(args) -> dict:
    if args.input:
        if args.planregions or args.room_labels:
            raise ValueError("--planregions/--room-labels are only used with --wallgraph")
        scene = read_scene(args.input)
    else:
        scene = _upstream_scene(args)
    openings = scene.openings
    if args.opening_mask:
        if not args.door_classes and not args.window_classes:
            raise ValueError("opening masks require explicit --door-classes/--window-classes")
        labels = read_labelmap(args.opening_mask)
        if labels.shape != (scene.image_size[1], scene.image_size[0]):
            raise ValueError("opening label dimensions differ from the declared image")
        openings += openings_from_mask(
            labels, args.door_classes, args.window_classes, args.min_opening_area
        )
    elif args.door_classes or args.window_classes:
        raise ValueError("class IDs require --opening-mask")
    overrides = {
        key: getattr(args, key)
        for key in ("mm_per_px", "mm_per_px_y", "minimum_clearance_mm")
        if getattr(args, key) is not None
    }
    config = replace(scene.config, **overrides)
    graph = build_graph(scene.rooms, scene.walls, openings, config, image_size=scene.image_size)
    save_graph(graph, args.output)
    return {
        "rooms": len(graph.rooms),
        "candidates": len(graph.decisions),
        "accepted_door_edges": len(graph.edges),
        "typed_opening_adjacencies": len(graph.adjacency),
        "output": str(args.output),
        "route_meaning": "room sequence only",
    }


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        if args.command == "build":
            result = _run_build(args)
        elif args.command in {"route", "access"}:
            if args.output and (
                args.output.resolve() == args.graph.resolve()
                or (
                    args.output.exists()
                    and args.graph.exists()
                    and args.output.samefile(args.graph)
                )
            ):
                raise ValueError("route/access output must not overwrite the graph")
            graph = read_graph(args.graph)
            blocked = tuple(args.blocked_openings)
            if args.command == "route":
                result = find_route(
                    graph, args.from_room, args.to_room, blocked_opening_ids=blocked
                ).to_dict()
                result["blocked_opening_ids"] = sorted(set(blocked))
            else:
                result = analyze_access(graph, args.from_room, blocked_opening_ids=blocked)
            if args.output:
                write_json(result, args.output)
        else:
            image, scene = demo_scene()
            graph = build_graph(
                scene.rooms, scene.walls, scene.openings, scene.config, image_size=scene.image_size
            )
            save_graph(graph, args.output)
            write_json(scene.to_dict(), args.output / "input.json")
            Image.fromarray(image).save(args.output / "demo.png")
            result = {
                "image": str(args.output / "demo.png"),
                "rooms": len(scene.rooms),
                "accepted_door_edges": len(graph.edges),
                "supplied_observations": "generated semantic annotations, not model predictions",
                "coordinates": dict(COORDINATES),
            }
        print(json.dumps(result, indent=2, allow_nan=False))
        if args.command == "route" and args.fail_if_unreachable and result["status"] == "no_path":
            return 1
        if (
            args.command == "access"
            and args.fail_on_newly_isolated
            and result["newly_isolated_room_ids"]
        ):
            return 1
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        arguments.exit(2, f"planportals: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
