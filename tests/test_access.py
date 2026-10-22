import json
from dataclasses import replace

import pytest

from planportals import RoomEdge, analyze_access, build_graph, find_route
from planportals.cli import main
from planportals.demo import demo_scene
from planportals.io import save_graph


def graph():
    _, scene = demo_scene()
    return build_graph(
        scene.rooms, scene.walls, scene.openings, scene.config, image_size=scene.image_size
    )


def test_closure_isolates_only_newly_disconnected_rooms_without_mutation():
    original = graph()
    before = original.to_dict()
    report = analyze_access(original, "bedroom", blocked_opening_ids=("door-living-kitchen",))
    assert report["reachable_room_ids"] == ["bedroom", "living"]
    assert report["newly_isolated_room_ids"] == ["kitchen", "study"]
    assert "bathroom" in report["unreachable_room_ids"]
    assert original.to_dict() == before
    assert find_route(original, "bedroom", "study").status == "found"
    assert (
        find_route(
            original, "bedroom", "study", blocked_opening_ids=("door-living-kitchen",)
        ).status
        == "no_path"
    )


def test_detour_and_parallel_door_are_not_removed_by_room_pair():
    original = graph()
    # A second supported opening in the test graph is distinct from the closed one.
    decision = replace(
        original.decisions[0], candidate=replace(original.decisions[0].candidate, id="alternate")
    )
    edges = original.edges + (RoomEdge("bedroom", "study", "alternate", "door"),)
    alternate = replace(original, decisions=original.decisions + (decision,), edges=edges)
    result = find_route(alternate, "bedroom", "study", blocked_opening_ids=("door-living-kitchen",))
    assert result.opening_ids == ("alternate",)
    assert not analyze_access(alternate, "bedroom", blocked_opening_ids=("door-living-kitchen",))[
        "newly_isolated_room_ids"
    ]


def test_unknown_closures_and_invalid_origins_are_not_silent():
    with pytest.raises(ValueError, match="unknown blocked"):
        find_route(graph(), "bedroom", "bedroom", blocked_opening_ids=("typo",))
    with pytest.raises(ValueError, match="declared room"):
        analyze_access(graph(), "missing")
    with pytest.raises(ValueError, match="collection"):
        analyze_access(graph(), "bedroom", blocked_opening_ids="door-living-kitchen")


def test_cli_writes_failed_gate_and_preserves_graph(tmp_path):
    save_graph(graph(), tmp_path)
    source = tmp_path / "portals.json"
    output = tmp_path / "access.json"
    args = [
        "access",
        "--graph",
        str(source),
        "--from-room",
        "bedroom",
        "--blocked-openings",
        "door-living-kitchen",
        "--output",
        str(output),
    ]
    assert main(args) == 0
    assert main(args + ["--fail-on-newly-isolated"]) == 1
    assert json.loads(output.read_text())["newly_isolated_room_ids"] == ["kitchen", "study"]
    before = source.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(args[:-1] + [str(source)])
    assert error.value.code == 2 and source.read_bytes() == before
    with pytest.raises(SystemExit) as error:
        main(args + ["--blocked-openings", "unknown"])
    assert error.value.code == 2
    assert (
        main(
            [
                "route",
                "--graph",
                str(source),
                "--from-room",
                "bedroom",
                "--to-room",
                "bathroom",
                "--fail-if-unreachable",
            ]
        )
        == 1
    )
