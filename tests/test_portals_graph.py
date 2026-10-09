from dataclasses import replace

import pytest

from planportals import (
    GraphConfig,
    OpeningCandidate,
    PolygonPart,
    Room,
    WallSegment,
    build_graph,
    find_route,
)
from planportals.demo import demo_scene
from planportals.geometry import room_contains


def two_rooms():
    rooms = (
        Room("a", "A", ((0, 0), (100, 0), (100, 100), (0, 100))),
        Room("b", "B", ((100, 0), (200, 0), (200, 100), (100, 100))),
    )
    walls = (WallSegment("divider", (100, 0), (100, 100)),)
    opening = OpeningCandidate("o", "door", (100, 30), (100, 70), 0.9, "detector:example")
    return rooms, walls, opening


def graph_for(opening=None, config=None, walls=None, rooms=None):
    defaults = two_rooms()
    return build_graph(
        rooms or defaults[0],
        walls or defaults[1],
        (opening or defaults[2],),
        config,
        image_size=(200, 100),
    )


def test_supported_door_keeps_evidence_and_topological_route():
    graph = graph_for()
    decision = graph.decisions[0]
    assert decision.traversable
    assert set(decision.room_ids) == {"a", "b"}
    assert len(decision.sides) == 2
    assert all(len(side.sample_points) == 5 for side in decision.sides)
    assert decision.attachments[0].support_wall_ids == ("divider",)
    route = find_route(graph, "a", "b")
    assert route.status == "found"
    assert route.room_ids == ("a", "b") and route.opening_ids == ("o",)
    assert "not a collision-free" in route.to_dict()["meaning"]
    assert decision.width_mm is None and decision.clearance_status == "not_checked"


@pytest.mark.parametrize(
    "kind,source",
    [
        ("window", "detector:example"),
        ("unknown", "detector:example"),
        ("door", "wall_gap"),
        ("door", "wall_gap "),
        ("door", " UNKNOWN "),
        ("door", "unknown"),
    ],
)
def test_windows_and_untyped_sources_cannot_become_passages(kind, source):
    opening = replace(two_rooms()[2], kind=kind, source=source)
    graph = graph_for(opening)
    assert not graph.decisions[0].traversable
    assert graph.edges == ()
    assert find_route(graph, "a", "b").status == "no_path"
    if kind == "window":
        assert len(graph.adjacency) == 1
        assert graph.decisions[0].reason == "window_is_not_a_passage"
    else:
        assert graph.adjacency == ()


def test_conflicting_door_and_window_claims_are_retained_but_never_routed():
    rooms, walls, door = two_rooms()
    window = replace(door, id="window", kind="window", score=0.99)
    graph = build_graph(rooms, walls, (door, window), image_size=(200, 100))
    assert len(graph.decisions) == 2 and not graph.edges and not graph.adjacency
    assert all(decision.reason == "conflicting_semantic_candidates" for decision in graph.decisions)
    assert all(decision.sides and decision.attachments for decision in graph.decisions)


@pytest.mark.parametrize(
    "opening,reason",
    [
        (replace(two_rooms()[2], score=0.1), "upstream_score_below_threshold"),
        (replace(two_rooms()[2], p1=(50, 30), p2=(50, 70)), "no_wall_support"),
        (replace(two_rooms()[2], p1=(80, 30), p2=(120, 70)), "no_wall_support"),
        (
            replace(two_rooms()[2], quality_issues=("component_below_minimum_area",)),
            "invalid_candidate_geometry",
        ),
    ],
)
def test_failed_observations_are_retained(opening, reason):
    graph = graph_for(opening)
    assert len(graph.decisions) == 1
    assert graph.decisions[0].candidate == opening
    assert graph.decisions[0].reason == reason and not graph.edges


def test_competing_parallel_wall_support_is_ambiguous():
    _, walls, _ = two_rooms()
    graph = graph_for(walls=(*walls, WallSegment("nearby", (104, 0), (104, 100))))
    assert graph.decisions[0].reason == "multiple_wall_supports"
    assert len(graph.decisions[0].attachments) == 2 and not graph.edges


def test_door_can_bind_across_two_collinear_wall_flanks_without_filling_geometry():
    rooms, _, opening = two_rooms()
    flanks = (
        WallSegment("upper", (100, 0), (100, 30)),
        WallSegment("lower", (100, 70), (100, 100)),
    )
    graph = graph_for(opening=opening, walls=flanks, rooms=rooms)
    assert graph.decisions[0].traversable
    evidence = next(
        item for item in graph.decisions[0].attachments if item.support_kind == "flanking_walls"
    )
    assert evidence.support_wall_ids == ("lower", "upper")
    assert graph.walls == flanks
    assert find_route(graph, "a", "b").status == "found"
    unknown = graph_for(opening=replace(opening, kind="unknown"), walls=flanks)
    assert not unknown.edges
    assert not any(
        item.support_kind == "flanking_walls" for item in unknown.decisions[0].attachments
    )


def test_multiple_flanking_hypotheses_do_not_create_a_passage():
    flanks = (
        WallSegment("upper", (100, 0), (100, 30)),
        WallSegment("lower", (100, 70), (100, 100)),
        WallSegment("lower-copy", (101, 70), (101, 100)),
    )
    graph = graph_for(walls=flanks)
    assert graph.decisions[0].status == "ambiguous"
    assert graph.decisions[0].reason == "multiple_wall_supports" and not graph.edges


def test_candidate_crossing_two_touching_segments_remains_ambiguous():
    walls = (WallSegment("upper", (100, 0), (100, 50)), WallSegment("lower", (100, 50), (100, 100)))
    graph = graph_for(walls=walls)
    assert graph.decisions[0].reason == "crosses_multiple_wall_segments"
    assert not graph.edges


def test_multiroom_votes_and_overlapping_room_membership_remain_visible():
    a, _ = two_rooms()[0]
    rooms = (
        a,
        Room("b", "B", ((100, 0), (200, 0), (200, 50), (100, 50))),
        Room("c", "C", ((100, 50), (200, 50), (200, 100), (100, 100))),
    )
    graph = graph_for(rooms=rooms)
    assert graph.decisions[0].status == "ambiguous"
    assert any(
        side.status in {"multiple_rooms_along_opening", "overlapping_rooms"}
        for side in graph.decisions[0].sides
    )
    overlap = Room("overlap", "Overlap", ((90, 0), (150, 0), (150, 100), (90, 100)))
    graph = graph_for(rooms=(*two_rooms()[0], overlap))
    assert any(side.status == "overlapping_rooms" for side in graph.decisions[0].sides)
    assert not graph.edges


def test_holes_and_disconnected_parts_preserve_room_membership():
    room = Room(
        "a",
        "A",
        ((0, 0), (100, 0), (100, 100), (0, 100)),
        holes=(((20, 20), (80, 20), (80, 80), (20, 80)),),
        parts=(PolygonPart(((120, 20), (150, 20), (150, 50), (120, 50))),),
    )
    assert room_contains((10, 50), room)
    assert not room_contains((50, 50), room)
    assert not room_contains((20, 20), room)
    assert room_contains((140, 30), room)
    assert room_contains((0, 50), room)


def test_metric_clearance_policy_and_anisotropic_conversion_are_explicit():
    graph = graph_for(config=GraphConfig(mm_per_px=10, mm_per_px_y=20, minimum_clearance_mm=900))
    decision = graph.decisions[0]
    assert decision.width_mm == 800
    assert decision.clearance_status == "span_below_minimum"
    assert not graph.edges and len(graph.adjacency) == 1
    assert "not_measured_net_free_width" in graph.to_dict()["semantics"]["clearance"]
    graph = graph_for(config=GraphConfig(mm_per_px=20, minimum_clearance_mm=800))
    assert graph.decisions[0].traversable
    assert graph.decisions[0].clearance_status == "span_meets_minimum"
    with pytest.raises(ValueError, match="requires a metric"):
        GraphConfig(minimum_clearance_mm=800)


def test_extreme_metric_scale_cannot_overflow_into_an_accepted_width_policy():
    with pytest.raises(ValueError, match="metric opening width is not finite"):
        graph_for(config=GraphConfig(mm_per_px=1e308, minimum_clearance_mm=900))


@pytest.mark.parametrize(
    "second_hole",
    [
        ((30, 30), (60, 30), (60, 60), (30, 60)),
        ((25, 25), (35, 25), (35, 35), (25, 35)),
        ((40, 20), (60, 20), (60, 40), (40, 40)),
    ],
)
def test_overlapping_nested_and_touching_holes_are_invalid(second_hole):
    room = Room(
        "holed",
        "Holed",
        ((0, 0), (100, 0), (100, 100), (0, 100)),
        holes=(((20, 20), (40, 20), (40, 40), (20, 40)), second_hole),
    )
    with pytest.raises(ValueError, match="holes must not overlap, nest or touch"):
        build_graph((room,), (), (), image_size=(200, 100))


def test_input_duplicate_ids_invalid_coordinates_and_self_intersections_fail():
    rooms, walls, opening = two_rooms()
    with pytest.raises(ValueError, match="duplicate opening"):
        build_graph(rooms, walls, (opening, opening), image_size=(200, 100))
    with pytest.raises(ValueError, match="duplicate room"):
        build_graph((rooms[0], rooms[0]), walls, (), image_size=(200, 100))
    with pytest.raises(ValueError, match="bounds"):
        graph_for(opening=replace(opening, p1=(-1, 30)))
    with pytest.raises(ValueError, match="finite"):
        WallSegment("nan", (float("nan"), 0), (100, 100))
    bow = Room("bow", "Bow", ((0, 0), (100, 100), (0, 80), (100, 0), (50, 100)))
    with pytest.raises(ValueError, match="self-intersecting"):
        build_graph((bow,), (), (), image_size=(200, 100))
    with pytest.raises(ValueError, match="declared room"):
        find_route(graph_for(), "a", "missing")


def test_generated_demo_has_honest_supplied_observations_and_an_isolated_room():
    image, scene = demo_scene()
    graph = build_graph(
        scene.rooms, scene.walls, scene.openings, scene.config, image_size=scene.image_size
    )
    assert image.shape == (800, 1200, 3) and len(graph.rooms) == 5
    assert len(graph.edges) == 3
    route = find_route(graph, "bedroom", "study")
    assert route.room_ids == ("bedroom", "living", "kitchen", "study")
    assert len(route.opening_ids) == 3
    assert find_route(graph, "living", "bathroom").status == "no_path"
