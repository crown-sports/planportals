"""Original generated apartment: annotations are inputs, never claimed detections."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from .domain import GraphConfig, OpeningCandidate, Room, SceneInput, WallSegment


def demo_scene() -> tuple[np.ndarray, SceneInput]:
    width, height = 1200, 800
    boxes = {
        "living": (70, 70, 560, 380),
        "kitchen": (560, 70, 1130, 380),
        "bedroom": (70, 380, 560, 740),
        "study": (560, 380, 850, 740),
        "bathroom": (850, 380, 1130, 740),
    }
    names = {
        "living": "Living",
        "kitchen": "Kitchen",
        "bedroom": "Bedroom",
        "study": "Study",
        "bathroom": "Bathroom",
    }
    rooms = tuple(
        Room(room_id, names[room_id], ((left, top), (right, top), (right, bottom), (left, bottom)))
        for room_id, (left, top, right, bottom) in boxes.items()
    )
    walls = (
        WallSegment("north", (70, 70), (1130, 70), 12),
        WallSegment("east", (1130, 70), (1130, 740), 12),
        WallSegment("south", (70, 740), (1130, 740), 12),
        WallSegment("west", (70, 70), (70, 740), 12),
        WallSegment("vertical", (560, 70), (560, 740), 10),
        WallSegment("horizontal", (70, 380), (1130, 380), 10),
        WallSegment("bathroom-divider", (850, 380), (850, 740), 10),
    )
    openings = (
        OpeningCandidate(
            "door-living-kitchen", "door", (560, 210), (560, 285), 0.94, "synthetic-annotation"
        ),
        OpeningCandidate(
            "door-living-bedroom", "door", (325, 380), (400, 380), 0.92, "synthetic-annotation"
        ),
        OpeningCandidate(
            "door-kitchen-study", "door", (680, 380), (765, 380), 0.96, "synthetic-annotation"
        ),
        OpeningCandidate(
            "window-north", "window", (250, 70), (390, 70), 0.91, "synthetic-annotation"
        ),
        OpeningCandidate(
            "window-study-bathroom", "window", (850, 570), (850, 655), 0.90, "synthetic-annotation"
        ),
        OpeningCandidate("untyped-wall-gap", "unknown", (970, 380), (1015, 380), source="wall_gap"),
        OpeningCandidate(
            "ambiguous-near-junction", "door", (505, 380), (620, 380), 0.81, "synthetic-annotation"
        ),
    )
    scene = SceneInput(rooms, walls, openings, (width, height), GraphConfig())
    image = Image.new("RGB", (width, height), "#f6f4ef")
    draw = ImageDraw.Draw(image)
    fills = {
        "living": "#eee9df",
        "kitchen": "#e9eeee",
        "bedroom": "#ece9e3",
        "study": "#e9ece5",
        "bathroom": "#e7edf0",
    }
    for room_id, box in boxes.items():
        draw.rectangle(box, fill=fills[room_id])
        left, top, right, bottom = box
        for x in range(left + 28, right, 35):
            draw.line((x, top, x, bottom), fill="#e0ded7", width=1)
    # Furnishing is deliberately independent of the opening annotations.
    draw.rounded_rectangle((130, 115, 340, 175), 10, fill="#fbfaf7", outline="#77736b", width=3)
    for x in (197, 267):
        draw.line((x, 120, x, 168), fill="#aaa69b", width=2)
    draw.rounded_rectangle((170, 210, 325, 285), 7, fill="#b79d76", outline="#675d4c", width=3)
    for box in (
        (145, 195, 175, 225),
        (325, 195, 355, 225),
        (145, 265, 175, 295),
        (325, 265, 355, 295),
    ):
        draw.ellipse(box, fill="#d5ccb9", outline="#787367", width=2)
    draw.rectangle((640, 95, 1095, 155), fill="#f9f9f8", outline="#757a7c", width=3)
    draw.rectangle((1035, 155, 1095, 330), fill="#f9f9f8", outline="#757a7c", width=3)
    draw.rounded_rectangle((670, 108, 752, 144), 4, fill="#a4c5ce", outline="#5f7e85", width=2)
    for x in (860, 895):
        for y in (113, 137):
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), outline="#424846", width=3)
    draw.rectangle((150, 445, 370, 645), fill="#fcfaf6", outline="#77736b", width=3)
    draw.rectangle((155, 450, 365, 495), fill="#d5dedb", outline="#8b9590", width=2)
    draw.line((150, 510, 370, 510), fill="#9e9a8e", width=2)
    draw.rectangle((435, 440, 515, 690), fill="#cfc5b4", outline="#6c655a", width=3)
    for y in (503, 566, 629):
        draw.line((435, y, 515, y), fill="#93897a", width=2)
    draw.rounded_rectangle((610, 475, 800, 555), 5, fill="#b6a184", outline="#6d6355", width=3)
    draw.rectangle((665, 485, 730, 535), fill="#66767c", outline="#3f4d54", width=2)
    draw.ellipse((665, 585, 740, 660), fill="#d3d6cd", outline="#788274", width=3)
    draw.rounded_rectangle((945, 435, 1090, 500), 12, fill="#b6d5df", outline="#65838b", width=3)
    draw.ellipse((915, 595, 960, 665), fill="#fcfcf7", outline="#78888a", width=3)
    for cx, cy in ((455, 135), (1045, 660), (110, 650)):
        draw.ellipse((cx - 26, cy - 26, cx + 26, cy + 26), fill="#8cab78", outline="#58714c")
        draw.line((cx - 18, cy, cx + 18, cy), fill="#58714c", width=2)
    for wall in walls:
        draw.line((*wall.p1, *wall.p2), fill="#353b3d", width=round(wall.thickness))
    for opening in openings:
        if opening.id == "ambiguous-near-junction":
            continue
        p1, p2 = opening.p1, opening.p2
        draw.line((*p1, *p2), fill="#f6f4ef", width=14)
        if opening.kind == "window":
            if p1[0] == p2[0]:
                for offset in (-3, 3):
                    draw.line(
                        (p1[0] + offset, p1[1], p2[0] + offset, p2[1]), fill="#6098aa", width=2
                    )
            else:
                for offset in (-3, 3):
                    draw.line(
                        (p1[0], p1[1] + offset, p2[0], p2[1] + offset), fill="#6098aa", width=2
                    )
        elif opening.kind == "door":
            span = int(abs(p2[0] - p1[0]) + abs(p2[1] - p1[1]))
            if p1[0] == p2[0]:
                draw.line((p1[0], p1[1], p1[0] - span, p1[1]), fill="#656969", width=2)
                draw.arc(
                    (p1[0] - span, p1[1] - span, p1[0] + span, p1[1] + span),
                    90,
                    180,
                    fill="#929895",
                    width=2,
                )
            else:
                draw.line((p1[0], p1[1], p1[0], p1[1] + span), fill="#656969", width=2)
                draw.arc(
                    (p1[0] - span, p1[1] - span, p1[0] + span, p1[1] + span),
                    0,
                    90,
                    fill="#929895",
                    width=2,
                )
    for room in rooms:
        left, top, _, _ = boxes[room.id]
        draw.text((left + 18, top + 24), room.name.upper(), fill="#494f4d")
    draw.line((70, 35, 1130, 35), fill="#858c89", width=1)
    for x in (70, 560, 1130):
        draw.line((x, 25, x, 45), fill="#858c89", width=1)
    draw.text((280, 17), "4900", fill="#737b77")
    draw.text((815, 17), "5700", fill="#737b77")
    draw.text(
        (70, 775),
        "Original generated scene. Door/window annotations are supplied inputs.",
        fill="#4d5550",
    )
    return np.asarray(image), scene
