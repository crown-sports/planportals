import json

import numpy as np
import pytest
from PIL import Image
from test_portals_graph import two_rooms

from planportals import (
    GraphConfig,
    build_graph,
    openings_from_mask,
    rooms_from_labelmap,
    rooms_from_planregions,
    walls_from_wallgraph,
)
from planportals.cli import main
from planportals.domain import COORDINATES, SceneInput
from planportals.geometry import room_contains
from planportals.io import read_graph, read_labelmap, read_scene, save_graph, write_json


def test_hard_semantic_masks_create_typed_spans_with_no_fabricated_score():
    labels = np.zeros((100, 200), np.uint8)
    labels[20:45, 98:103] = 3
    labels[60:85, 98:103] = 4
    labels[1:15, 1:15] = 9  # An unrequested class must not become a door.
    openings = openings_from_mask(labels, (3,), (4,))
    assert len(openings) == 2
    assert {opening.kind for opening in openings} == {"door", "window"}
    assert all(opening.score is None and opening.source == "semantic-mask" for opening in openings)
    rooms, walls, _ = two_rooms()
    graph = build_graph(rooms, walls, openings, image_size=(200, 100))
    assert len(graph.edges) == 1 and len(graph.adjacency) == 2
    assert not next(
        decision for decision in graph.decisions if decision.candidate.kind == "window"
    ).traversable


def test_bad_mask_components_are_retained_as_rejected_observations():
    labels = np.zeros((100, 200), np.uint8)
    labels[30, 100] = 3
    labels[55:70, 95:110] = 4
    openings = openings_from_mask(labels, (3,), (4,), min_area=12)
    assert len(openings) == 2
    assert all(opening.quality_issues for opening in openings)
    rooms, walls, _ = two_rooms()
    graph = build_graph(rooms, walls, openings, image_size=(200, 100))
    assert not graph.edges
    assert all(decision.reason == "invalid_candidate_geometry" for decision in graph.decisions)
    with pytest.raises(ValueError, match="disjoint"):
        openings_from_mask(labels, (3,), (3,))
    with pytest.raises(ValueError, match="integer"):
        openings_from_mask(labels.astype(float), (3,), (4,))


def test_labelmap_adapter_preserves_hole_and_island_pixel_membership():
    labels = np.zeros((12, 15), np.int32)
    labels[1:10, 1:10] = 1
    labels[4:7, 4:7] = 0
    labels[1:3, 12:14] = 1
    labels[10:12, 10:15] = 2
    rooms = rooms_from_labelmap(labels)
    for y in range(labels.shape[0]):
        for x in range(labels.shape[1]):
            assert {room.id for room in rooms if room_contains((x, y), room)} == (
                {str(labels[y, x])} if labels[y, x] else set()
            )


def test_upstream_json_adapters_preserve_geometry_and_reject_wrong_coordinates():
    wall_data = {
        "schema_version": "wallgraph/1",
        "coordinates": dict(COORDINATES),
        "image": {"width": 200, "height": 100},
        "segments": [
            {
                "id": 7,
                "points": [{"x": 100, "y": 0}, {"x": 100, "y": 50}, {"x": 100, "y": 100}],
                "thickness_px": 8,
            }
        ],
    }
    walls = walls_from_wallgraph(wall_data)
    assert [wall.id for wall in walls] == ["wallgraph:7:0", "wallgraph:7:1"]
    region_data = {
        "schema_version": "planregions/1",
        "coordinates": dict(COORDINATES),
        "image": {"width": 200, "height": 100},
        "regions": [
            {
                "id": 1,
                "attribute": {"label": "office"},
                "polygons": [
                    {
                        "exterior": [[0, 0], [90, 0], [90, 100], [0, 100]],
                        "holes": [[[20, 20], [40, 20], [40, 40], [20, 40]]],
                    },
                    {"exterior": [[110, 10], [120, 10], [120, 20], [110, 20]], "holes": []},
                ],
            }
        ],
    }
    room = rooms_from_planregions(region_data)[0]
    assert room.name == "office" and len(room.parts) == 1
    assert not room_contains((30, 30), room) and room_contains((115, 15), room)
    with pytest.raises(ValueError, match="original image-pixel"):
        walls_from_wallgraph({**wall_data, "coordinates": {**COORDINATES, "unit": "mm"}})


def test_json_round_trip_and_tampered_window_route_are_rejected(tmp_path):
    rooms, walls, opening = two_rooms()
    scene = SceneInput(rooms, walls, (opening,), (200, 100), GraphConfig())
    input_path = tmp_path / "input.json"
    write_json(scene.to_dict(), input_path)
    assert read_scene(input_path) == scene
    graph = build_graph(rooms, walls, (opening,), image_size=(200, 100))
    save_graph(graph, tmp_path)
    assert read_graph(tmp_path / "portals.json") == graph
    payload = json.loads((tmp_path / "portals.json").read_text())
    payload["decisions"][0]["candidate"]["kind"] = "window"
    write_json(payload, tmp_path / "tampered.json")
    with pytest.raises(ValueError, match="reconstructed evidence"):
        read_graph(tmp_path / "tampered.json")


def test_cli_build_mask_route_and_size_rejection(tmp_path, capsys):
    rooms, walls, _ = two_rooms()
    scene = SceneInput(rooms, walls, (), (200, 100))
    input_path = tmp_path / "input.json"
    write_json(scene.to_dict(), input_path)
    labels = np.zeros((100, 200), np.uint8)
    labels[30:70, 98:103] = 3
    mask_path = tmp_path / "semantic.png"
    Image.fromarray(labels).save(mask_path)
    output = tmp_path / "result"
    assert (
        main(
            [
                "build",
                "--input",
                str(input_path),
                "--opening-mask",
                str(mask_path),
                "--door-classes",
                "3",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert read_graph(output / "portals.json").edges
    assert (
        main(
            ["route", "--graph", str(output / "portals.json"), "--from-room", "a", "--to-room", "b"]
        )
        == 0
    )
    assert '"found"' in capsys.readouterr().out
    Image.fromarray(labels[:50]).save(mask_path)
    with pytest.raises(SystemExit) as error:
        main(
            [
                "build",
                "--input",
                str(input_path),
                "--opening-mask",
                str(mask_path),
                "--door-classes",
                "3",
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2
    assert "dimensions differ" in capsys.readouterr().err


def test_color_preview_is_not_a_semantic_label_map(tmp_path):
    path = tmp_path / "colors.png"
    Image.new("RGB", (10, 10), "blue").save(path)
    with pytest.raises(ValueError, match="not RGB"):
        read_labelmap(path)


def test_cli_connects_actual_upstream_contracts_and_semantic_labels(tmp_path):
    wall_data = {
        "schema_version": "wallgraph/1",
        "coordinates": dict(COORDINATES),
        "image": {"width": 200, "height": 100},
        "segments": [
            {"id": 1, "points": [{"x": 100, "y": 0}, {"x": 100, "y": 30}], "thickness_px": 8},
            {"id": 2, "points": [{"x": 100, "y": 70}, {"x": 100, "y": 100}], "thickness_px": 8},
        ],
    }
    rooms, _, _ = two_rooms()
    region_data = {
        "schema_version": "planregions/1",
        "coordinates": dict(COORDINATES),
        "image": {"width": 200, "height": 100},
        "regions": [
            {
                "id": index,
                "attribute": {"label": room.name},
                "polygons": [{"exterior": room.points, "holes": []}],
            }
            for index, room in enumerate(rooms, 1)
        ],
    }
    write_json(wall_data, tmp_path / "walls.json")
    write_json(region_data, tmp_path / "regions.json")
    labels = np.zeros((100, 200), np.uint8)
    labels[30:70, 98:103] = 3
    Image.fromarray(labels).save(tmp_path / "semantics.png")
    assert (
        main(
            [
                "build",
                "--wallgraph",
                str(tmp_path / "walls.json"),
                "--planregions",
                str(tmp_path / "regions.json"),
                "--opening-mask",
                str(tmp_path / "semantics.png"),
                "--door-classes",
                "3",
                "--output",
                str(tmp_path / "graph"),
            ]
        )
        == 0
    )
    graph = read_graph(tmp_path / "graph" / "portals.json")
    assert len(graph.edges) == 1
    assert any(
        evidence.support_kind == "flanking_walls" for evidence in graph.decisions[0].attachments
    )
