"""Generate one shared floor-plan review with the four optional geometry packages.

Inputs are synthetic annotations, not detector output. See docs/workflow.md.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path


def run(output: Path, blocked_opening: str) -> dict:
    import numpy as np
    from PIL import Image, ImageDraw
    from planmetric.domain import DimensionSpan, DimensionText, Point
    from planmetric.io import observations_to_dict, write_result
    from planmetric.measurement import measure_geometry
    from planmetric.pipeline import calibrate
    from planregions.compare import compare_regions
    from planregions.comparison_view import render_comparison_html
    from planregions.io import save_result as save_regions
    from planregions.pipeline import RegionPipeline
    from wallgraph.io import save_result as save_walls
    from wallgraph.masks import vectorize_mask

    from planportals.adapters import rooms_from_planregions, walls_from_wallgraph
    from planportals.demo import demo_scene
    from planportals.graph import analyze_access, build_graph
    from planportals.io import save_graph, write_json

    if output.exists():
        raise ValueError("output already exists; choose a new directory to preserve prior results")
    _, scene = demo_scene()
    # Rasterize the existing demo's declared barriers, not its furnished RGB image.
    image = Image.new("L", scene.image_size)
    draw = ImageDraw.Draw(image)
    for wall in scene.walls:
        draw.line((*wall.p1, *wall.p2), fill=255, width=round(wall.thickness))
    walls = vectorize_mask(np.asarray(image))
    regions = RegionPipeline().run(walls.mask)
    # Names are supplied from the demo annotations; geometry remains PlanRegions output.
    names = {}
    for room in scene.rooms:
        x = round(sum(point[0] for point in room.points) / len(room.points))
        y = round(sum(point[1] for point in room.points) / len(room.points))
        names[str(int(regions.labels[y, x]))] = room.id
    rooms = tuple(
        replace(room, name=names[room.id]) for room in rooms_from_planregions(regions.to_dict())
    )
    graph = build_graph(
        rooms,
        walls_from_wallgraph(walls.to_dict()),
        scene.openings,
        scene.config,
        image_size=scene.image_size,
    )
    bedroom = next(room.id for room in rooms if room.name == "bedroom")
    access = analyze_access(graph, bedroom, blocked_opening_ids=[blocked_opening])

    # Three declared dimension spans per axis, all at 10 mm/px.
    definitions = (
        ((70, 30), (560, 30)),
        ((560, 30), (1130, 30)),
        ((70, 10), (1130, 10)),
        ((30, 70), (30, 380)),
        ((30, 380), (30, 740)),
        ((10, 70), (10, 740)),
    )
    texts, spans = [], []
    for index, (first, second) in enumerate(definitions):
        x, y = (first[0] + second[0]) / 2, (first[1] + second[1]) / 2
        length = abs(second[0] - first[0]) + abs(second[1] - first[1])
        texts.append(
            DimensionText(
                f"text-{index}", f"{length * 10} mm", (x - 4, y - 4, x + 4, y + 4), role="dimension"
            )
        )
        spans.append(DimensionSpan(f"span-{index}", Point(*first), Point(*second)))
    calibration = calibrate(texts, spans)
    measurements = measure_geometry(calibration, regions.to_dict(), image_size=scene.image_size)
    wall_measurements = measure_geometry(calibration, walls.to_dict(), image_size=scene.image_size)
    changed_mask = walls.mask.copy()
    changed_mask[210:286, 550:571] = 0  # A missing separator joins living and kitchen.
    changed = RegionPipeline().run(changed_mask)
    comparison = compare_regions(regions.labels, changed.labels)
    summary = {
        "basis": "generated barriers, dimensions and typed openings; no recognition model",
        "room_names": names,
        "regions_before": len(regions.regions),
        "regions_after_missing_separator": len(changed.regions),
        "merge_groups": comparison["summary"]["group_counts"]["merge"],
        "scale_mm_per_px": {axis: calibration.axis(axis).mm_per_pixel for axis in ("x", "y")},
        "room_areas_m2": {
            names[str(item["id"])]: item["area_mm2"] / 1_000_000
            for item in measurements["measurements"]
        },
        "accepted_door_connections": len(graph.edges),
        "blocked_opening": blocked_opening,
        "newly_isolated_rooms": [names[identity] for identity in access["newly_isolated_room_ids"]],
    }
    output.mkdir(parents=True, exist_ok=False)
    save_walls(walls, output / "walls")
    save_regions(regions, output / "regions")
    save_regions(changed, output / "changed-regions")
    Image.fromarray(changed_mask).save(output / "changed-walls.png")
    write_result(calibration, output / "calibration", image_size=scene.image_size)
    write_json(
        observations_to_dict(tuple(texts), tuple(spans), image_size=scene.image_size),
        output / "observations.json",
    )
    write_json(measurements, output / "measurements.json")
    write_json(wall_measurements, output / "wall-measurements.json")
    write_json(comparison, output / "changes.json")
    (output / "changes.html").write_text(
        render_comparison_html(regions.labels, changed.labels, comparison), encoding="utf-8"
    )
    save_graph(graph, output / "portals")
    write_json(access, output / "access.json")
    write_json(summary, output / "summary.json")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocked-opening", default="door-living-kitchen")
    parser.add_argument("--fail-on-newly-isolated", action="store_true")
    args = parser.parse_args()
    try:
        summary = run(args.output, args.blocked_opening)
    except (ImportError, ValueError, OSError) as error:
        parser.exit(
            2, f"Workflow error: {error}. See docs/workflow.md for dependencies and inputs.\n"
        )
    print(json.dumps(summary, indent=2, allow_nan=False))
    return int(args.fail_on_newly_isolated and bool(summary["newly_isolated_rooms"]))


if __name__ == "__main__":
    raise SystemExit(main())
