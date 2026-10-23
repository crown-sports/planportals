"""Render four README figures from review_workflow.py output; no invented results.

Run the workflow first, then pass its directory with --input. All figures use
exported pixels, paths, calibration and reachability. See docs/workflow.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZE = (1680, 900)
INK, MUTED, BLUE, RED = "#172b3a", "#526574", "#2465ad", "#b83e32"
COLORS = ("#d9eadc", "#f4dfb7", "#d5e6f4", "#e8dff0", "#e3e7e9")
BOXES = ((40, 196, 820, 716), (860, 196, 1640, 716))


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def centered(draw: ImageDraw.ImageDraw, point: tuple, lines: list[str], size: int = 27) -> None:
    x, y = point
    for index, text in enumerate(lines):
        width = draw.textlength(text, font=font(size))
        draw.text(
            (x - width / 2, y + (index - len(lines) / 2) * (size + 5)),
            text,
            font=font(size),
            fill=INK,
        )


def board(title: str, left: str, right: str) -> tuple:
    image = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 30), title, fill=INK, font=font(43))
    draw.text((40, 96), "Generated apartment / actual exported results", fill=MUTED, font=font(23))
    for box, heading in zip(BOXES, (left, right), strict=True):
        draw.text((box[0], 151), heading, font=font(29), fill=INK)
        draw.rectangle(box, outline="#d6dfe5", width=2)
    return image, draw


def paste(image: Image.Image, source: Image.Image, index: int):
    x0, y0, x1, y1 = BOXES[index]
    ratio = min((x1 - x0) / source.width, (y1 - y0) / source.height)
    image.paste(
        source.resize(
            (round(source.width * ratio), round(source.height * ratio)), Image.Resampling.NEAREST
        ),
        (x0, y0),
    )

    def point(value):
        x, y = (value["x"], value["y"]) if isinstance(value, dict) else value
        return x0 + x * ratio, y0 + y * ratio

    return point


def footer(draw: ImageDraw.ImageDraw, first: str, second: str) -> None:
    draw.text((40, 754), first, font=font(29), fill=INK)
    draw.text((40, 814), second, font=font(23), fill=MUTED)


def region_image(labels: np.ndarray, mask: np.ndarray, colors: dict) -> Image.Image:
    rgb = np.full((*labels.shape, 3), 255, dtype=np.uint8)
    for identity, color in colors.items():
        rgb[labels == int(identity)] = tuple(bytes.fromhex(color.lstrip("#")))
    rgb[mask > 0] = (64, 75, 83)
    return Image.fromarray(rgb)


def draw_names(draw, point, labels, names, extra=None, offsets=None):
    for identity in np.unique(labels):
        if identity == 0:
            continue
        yy, xx = np.nonzero(labels == identity)
        lines = [names[str(identity)].capitalize()]
        if extra:
            lines.append(extra[str(identity)])
        dx, dy = (offsets or {}).get(str(identity), (0, 0))
        centered(draw, point((float(xx.mean()) + dx, float(yy.mean()) + dy)), lines)


def render(source: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("output already exists; choose a new directory")
    inputs = [
        "summary.json",
        "walls/walls.json",
        "walls/walls.png",
        "regions/labels.npz",
        "changed-regions/labels.npz",
        "changed-walls.png",
        "measurements.json",
        "changes.json",
        "portals/portals.json",
        "access.json",
    ]
    paths = {name: source / name for name in inputs}
    data = {
        name: json.loads(path.read_text()) for name, path in paths.items() if path.suffix == ".json"
    }
    with np.load(paths["regions/labels.npz"], allow_pickle=False) as archive:
        labels = archive["labels"].copy()
    with np.load(paths["changed-regions/labels.npz"], allow_pickle=False) as archive:
        changed = archive["labels"].copy()
    with Image.open(paths["walls/walls.png"]) as image:
        mask = np.array(image)
    with Image.open(paths["changed-walls.png"]) as image:
        changed_mask = np.array(image)
    if labels.ndim != 2 or not (labels.shape == changed.shape == mask.shape == changed_mask.shape):
        raise ValueError("workflow maps must share one two-dimensional pixel grid")
    summary, walls = data["summary.json"], data["walls/walls.json"]
    measurement, comparison = data["measurements.json"], data["changes.json"]
    graph, access = data["portals/portals.json"], data["access.json"]
    names = summary["room_names"]
    colors = {identity: COLORS[(int(identity) - 1) % len(COLORS)] for identity in names}
    figures = {}

    # Wall pixels and graph points come from the same WallGraph result.
    count = int(np.count_nonzero(mask))
    image, draw = board(
        "From wall pixels to wall paths",
        "Input: binary wall mask",
        f"Output: {len(walls['segments'])} paths / {len(walls['junctions'])} junctions",
    )
    binary = np.full((*mask.shape, 3), 255, np.uint8)
    binary[mask > 0] = (64, 75, 83)
    paste(image, Image.fromarray(binary), 0)
    binary[mask > 0] = (211, 220, 227)
    point = paste(image, Image.fromarray(binary), 1)
    for segment in walls["segments"]:
        draw.line([point(p) for p in segment["points"]], fill=BLUE, width=4)
    for node in walls["junctions"]:
        x, y = point(node["point"])
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="white", outline=BLUE, width=3)
    footer(
        draw,
        f"{count:,} wall pixels retained; {walls['metadata']['changed_pixels']} changed.",
        f"{mask.shape[1]} x {mask.shape[0]} source grid. "
        "Blue lines and circles are exported geometry; no model used.",
    )
    figures["wallgraph"] = image

    # Preserve colors by overlap group, not by arbitrary after IDs.
    after_colors, after_names = {}, {}
    for group in comparison["groups"]:
        ids = group["before_ids"]
        for identity in group["after_ids"]:
            after_colors[str(identity)] = colors[str(ids[0])] if ids else "#e3e7e9"
            after_names[str(identity)] = " + ".join(names[str(i)] for i in ids) or "new region"
    stats = comparison["summary"]
    image, draw = board(
        "A missing separator joins two rooms",
        f"Before: {stats['before_region_count']} regions",
        f"After: {stats['after_region_count']} regions",
    )
    point = paste(image, region_image(labels, mask, colors), 0)
    draw_names(draw, point, labels, names)
    point = paste(image, region_image(changed, changed_mask, after_colors), 1)
    offsets = {}
    for group in comparison["groups"]:
        if group["kind"] != "merge":
            continue
        # Keep the annotation away from the changed wall; use a source region center.
        largest = max(group["before_ids"], key=lambda i: np.count_nonzero(labels == i))
        by, bx = np.nonzero(labels == largest)
        for identity in group["after_ids"]:
            ay, ax = np.nonzero(changed == identity)
            offsets[str(identity)] = (float(bx.mean() - ax.mean()), float(by.mean() - ay.mean()))
    draw_names(draw, point, changed, after_names, offsets=offsets)
    yy, xx = np.nonzero(mask != changed_mask)
    if len(xx):
        draw.rectangle(
            (
                *point((int(xx.min()) - 12, int(yy.min()) - 12)),
                *point((int(xx.max()) + 12, int(yy.max()) + 12)),
            ),
            outline=RED,
            width=4,
        )
    footer(
        draw,
        f"{stats['group_counts']['merge']} merge group; {len(xx):,} wall pixels removed.",
        "Red box: changed barrier. Colors follow overlapping regions, even when their IDs change.",
    )
    figures["planregions"] = image

    areas = {str(item["id"]): item for item in measurement["measurements"]}
    axes = measurement["calibration"]["axes"]
    for identity, area in areas.items():
        if int(np.count_nonzero(labels == int(identity))) != area["area_px"]:
            raise ValueError("measurement pixel count does not match the label map")
    image, draw = board(
        "From labeled pixels to room areas",
        "Input: region pixel counts",
        "Output: calibrated areas",
    )
    point = paste(image, region_image(labels, mask, colors), 0)
    draw_names(draw, point, labels, names, {i: f"{a['area_px']:,} px" for i, a in areas.items()})
    point = paste(image, region_image(labels, mask, colors), 1)
    draw_names(
        draw, point, labels, names, {i: f"{a['area_mm2'] / 1e6:.2f} sq m" for i, a in areas.items()}
    )
    footer(
        draw,
        f"Accepted scale: x = {axes['x']['mm_per_pixel']:g}, "
        f"y = {axes['y']['mm_per_pixel']:g} mm/px.",
        "Generated dimensions. Area counts labeled pixels, excluding walls; "
        "this is not a site measurement.",
    )
    figures["planmetric"] = image

    # Route overlays use accepted edges. Closure changes edges, not the wall mask.
    origin = access["from_room"]
    baseline = set(access["baseline_reachable_room_ids"])
    reachable = set(access["reachable_room_ids"])
    isolated = set(access["newly_isolated_room_ids"])
    centers = {}
    for identity in names:
        yy, xx = np.nonzero(labels == int(identity))
        centers[identity] = (float(xx.mean()), float(yy.mean()))
    image, draw = board(
        f"Close a door; check access from {names[origin]}",
        f"Before: {len(baseline)} rooms reachable (including start)",
        f"After: {len(reachable)} rooms reachable (including start)",
    )
    for index, reached in enumerate((baseline, reachable)):
        palette = {
            i: "#d9eadc" if i in reached else "#f5d8ce" if index and i in isolated else "#e3e7e9"
            for i in names
        }
        point = paste(image, region_image(labels, mask, palette), index)
        for edge in graph["edges"]:
            if index and edge["opening_id"] in access["blocked_opening_ids"]:
                continue
            draw.line(
                [point(centers[edge["first"]]), point(centers[edge["second"]])],
                fill="#477b59" if edge["first"] in reached else "#aa7368",
                width=5,
            )
        for identity, center in centers.items():
            x, y = point(center)
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="white", outline=INK, width=2)
            label = names[identity].capitalize() + (" (start)" if identity == origin else "")
            centered(draw, (x, y + 42), [label], size=24)
        if index:
            for decision in graph["decisions"]:
                candidate = decision["candidate"]
                if candidate["id"] in access["blocked_opening_ids"]:
                    p1, p2 = point(candidate["p1"]), point(candidate["p2"])
                    draw.line([p1, p2], fill=RED, width=7)
                    cx, cy = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
                    draw.line((cx - 10, cy - 10, cx + 10, cy + 10), fill=RED, width=4)
                    draw.line((cx - 10, cy + 10, cx + 10, cy - 10), fill=RED, width=4)
    lost = ", ".join(names[i] for i in sorted(isolated)) or "none"
    footer(
        draw,
        f"Newly isolated: {lost}. Red mark: closed opening.",
        "Gray rooms were already unreachable. Lines show room connections, "
        "not walking paths; door labels are supplied.",
    )
    figures["planportals"] = image

    output.mkdir(parents=True, exist_ok=False)
    for repo, image in figures.items():
        image.save(output / f"{repo}.png")
    record = {
        "source_kind": "generated workflow; supplied annotations; no detector",
        "input_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
        },
        "figure_sha256": {
            repo: hashlib.sha256((output / f"{repo}.png").read_bytes()).hexdigest()
            for repo in figures
        },
    }
    (output / "figures.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        render(args.input, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Figure error: {error}\n")
    print(f"Four workflow figures saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
