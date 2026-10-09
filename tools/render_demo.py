"""Render a generated scene, actual opening evidence and a door-only room graph.

Candidates are supplied annotations, not image detector predictions. The figure
contrasts a computed all-opening baseline with the actual conservative graph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from planportals import build_graph, find_route
from planportals.demo import demo_scene

PUBLIC_FIGURE = Path(__file__).resolve().parents[1] / "examples/demo.png"
PUBLIC_FIGURE_SHA256 = "32d8e18d1efc392c78ef78ae784d7749df2abad7b4aab894371d09d3f123f873"
SIZE = (1560, 1000)
BG, INK, MUTED = "#edf2f7", "#13273c", "#52677c"
GREEN, BLUE, RED, ORANGE = "#009d8a", "#3476d5", "#db4f45", "#d48a18"


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError as exc:
        raise RuntimeError("Rendering needs Pillow >=10.1 for its bundled scalable font") from exc


def fit_image(image: Image.Image, box: tuple[int, int, int, int]) -> tuple:
    x0, y0, x1, y1 = box
    ratio = min((x1 - x0) / image.width, (y1 - y0) / image.height)
    resized = image.resize(
        (round(image.width * ratio), round(image.height * ratio)), Image.Resampling.LANCZOS
    )
    return resized, ratio, x0 + (x1 - x0 - resized.width) // 2, y0 + (y1 - y0 - resized.height) // 2


def all_opening_route_exists(graph: object, start: str, goal: str) -> bool:
    """Naive baseline: every assigned candidate pair is a passage, regardless of kind."""
    edges = [
        d.room_ids
        for d in graph.decisions
        if None not in d.room_ids and d.room_ids[0] != d.room_ids[1]
    ]
    visited, frontier = {start}, [start]
    while frontier:
        current = frontier.pop()
        for first, second in edges:
            neighbor = second if first == current else first if second == current else None
            if neighbor is not None and neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    return goal in visited


def demo_graph() -> tuple:
    rgb, scene = demo_scene()
    graph = build_graph(
        scene.rooms, scene.walls, scene.openings, scene.config, image_size=scene.image_size
    )
    return rgb, scene, graph


def check_figure(path: Path) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != PUBLIC_FIGURE_SHA256:
        raise ValueError("PNG differs from the reviewed public figure")
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode != "RGB" or image.size != SIZE or image.info:
            raise ValueError("Figure must be a metadata-free 1560x1000 RGB PNG")
        image.load()


def check_graph_demo() -> None:
    """Recompute decisions and routes independently of the reviewed PNG's font."""
    _, _, graph = demo_graph()
    route = find_route(graph, "bedroom", "study")
    blocked = find_route(graph, "living", "bathroom")
    if len(graph.edges) != 3 or route.status != "found" or len(route.opening_ids) != 3:
        raise ValueError("generated scene no longer has the reviewed three-door route")
    if blocked.status != "no_path" or not all_opening_route_exists(graph, "living", "bathroom"):
        raise ValueError("generated scene no longer exposes the all-opening false route")
    if any(d.traversable and d.candidate.kind != "door" for d in graph.decisions):
        raise ValueError("a generated window or unknown gap became traversable")


def render_demo() -> tuple[Image.Image, dict]:
    rgb, scene, graph = demo_graph()
    source = Image.fromarray(rgb).convert("RGB")
    route = find_route(graph, "bedroom", "study")
    blocked = find_route(graph, "living", "bathroom")
    naive_found = all_opening_route_exists(graph, "living", "bathroom")
    kinds = Counter(candidate.kind for candidate in scene.openings)
    counts = Counter(decision.status for decision in graph.decisions)
    board = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(board)
    draw.text((40, 28), "Follow the doors.", font=font(44), fill=INK)
    draw.text(
        (42, 90),
        "Connect rooms through supported doors. Keep windows and uncertain gaps out of routes.",
        font=font(22),
        fill=MUTED,
    )
    titles = ("1  Drawing + candidates", "2  Wall and room evidence", "3  Door-only room graph")
    positions = (32, 548, 1064)
    centers = {
        room.id: (
            sum(point[0] for point in room.points) / len(room.points),
            sum(point[1] for point in room.points) / len(room.points),
        )
        for room in scene.rooms
    }
    for index, x0 in enumerate(positions):
        draw.rounded_rectangle((x0, 145, x0 + 464, 720), radius=18, fill="white")
        draw.text((x0 + 18, 164), titles[index], font=font(23), fill=INK)
        resized, ratio, ox, oy = fit_image(source, (x0 + 12, 210, x0 + 452, 605))
        board.paste(resized, (ox, oy))
        draw = ImageDraw.Draw(board)

        def display(
            point: tuple[float, float], ox: int = ox, oy: int = oy, ratio: float = ratio
        ) -> tuple[float, float]:
            return ox + point[0] * ratio, oy + point[1] * ratio

        if index == 0:
            for candidate in scene.openings:
                color = {"door": GREEN, "window": BLUE, "unknown": ORANGE}[candidate.kind]
                draw.line((display(candidate.p1), display(candidate.p2)), fill=color, width=5)
            draw.text(
                (x0 + 18, 628),
                f"{len(scene.rooms)} rooms / {len(scene.openings)} candidates",
                font=font(23),
                fill=INK,
            )
            draw.text(
                (x0 + 18, 665), "Given door / window / unknown labels.", font=font(18), fill=MUTED
            )
        elif index == 1:
            for decision in graph.decisions:
                color = (
                    GREEN
                    if decision.traversable
                    else BLUE
                    if decision.candidate.kind == "window"
                    else ORANGE
                )
                draw.line(
                    (display(decision.candidate.p1), display(decision.candidate.p2)),
                    fill=color,
                    width=5,
                )
                for side in decision.sides:
                    for point, memberships in zip(
                        side.sample_points, side.memberships, strict=True
                    ):
                        px, py = display(point)
                        point_color = color if len(memberships) == 1 else RED
                        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=point_color)
            draw.text((x0 + 18, 628), "Sample both sides of each opening.", font=font(22), fill=INK)
            draw.text(
                (x0 + 18, 665),
                f"{counts['unresolved']} unresolved / {counts['ambiguous']} ambiguous",
                font=font(22),
                fill=ORANGE,
            )
        else:
            # Graph lines are room adjacency, explicitly not a free-space path.
            for edge in graph.edges:
                color = GREEN if edge.opening_id in route.opening_ids else BLUE
                draw.line(
                    (display(centers[edge.first]), display(centers[edge.second])),
                    fill=color,
                    width=5,
                )
            for room_id, center in centers.items():
                px, py = display(center)
                color = RED if room_id == "bathroom" else GREEN
                draw.ellipse((px - 9, py - 9, px + 9, py + 9), fill="white", outline=color, width=3)
            draw.text(
                (x0 + 18, 628),
                f"{len(graph.edges)} supported door edges",
                font=font(23),
                fill=GREEN,
            )
            draw.text(
                (x0 + 18, 665), "Bathroom has no admitted door edge.", font=font(18), fill=RED
            )
    cards = (
        (
            32,
            "Naive: every opening is a door",
            "Route FOUND" if naive_found else "NO PATH",
            "Living -> Bathroom",
            "#fae5e2",
            RED,
        ),
        (
            548,
            "PlanPortals: supported doors",
            "NO PATH" if blocked.status == "no_path" else "Route FOUND",
            "Living -> Bathroom",
            "#dff3ef",
            GREEN,
        ),
        (
            1064,
            "A valid three-door connection",
            "Route FOUND" if route.status == "found" else "NO PATH",
            "Bedroom -> Living -> Kitchen -> Study",
            "#e1eafa",
            BLUE,
        ),
    )
    for x0, heading, verdict, detail, fill, color in cards:
        draw.rounded_rectangle((x0, 750, x0 + 464, 890), radius=18, fill=fill)
        draw.text((x0 + 20, 768), heading, font=font(20), fill=INK)
        draw.text((x0 + 20, 807), verdict, font=font(32), fill=color)
        draw.text((x0 + 20, 855), detail, font=font(17), fill=MUTED)
    draw.text(
        (40, 923),
        "Generated rooms, walls and semantic candidates. "
        "Actual graph and route results; no manual correction.",
        font=font(19),
        fill=MUTED,
    )
    draw.text(
        (40, 958),
        "Room sequences are topological connections, not collision-free navigation. "
        "No image detection accuracy claim.",
        font=font(18),
        fill=MUTED,
    )
    return board, {
        "source": "programmatically generated demo",
        "protocol": "supplied room/wall/semantic candidates; not image detection accuracy",
        "input_size": list(source.size),
        "figure_size": list(SIZE),
        "candidate_kinds": dict(kinds),
        "decision_statuses": dict(counts),
        "door_edges": len(graph.edges),
        "naive_living_to_bathroom": naive_found,
        "living_to_bathroom": blocked.to_dict(),
        "bedroom_to_study": route.to_dict(),
        "result": graph.to_dict(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path, help="optional local graph record")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_figure(args.output or PUBLIC_FIGURE)
        check_graph_demo()
        print(
            "Reviewed figure hash/format and actual three-door/blocked routes verified; "
            "no image detection evaluation"
        )
        return
    if args.output is None:
        parser.error("rendering requires --output")
    board, summary = render_demo()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    board.save(args.output, format="PNG")
    summary["figure_sha256"] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    print(
        f"Rendered actual graph: {summary['door_edges']} door edges, "
        f"bathroom route {summary['living_to_bathroom']['status']}"
    )


if __name__ == "__main__":
    main()
