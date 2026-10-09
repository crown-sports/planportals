"""Evaluate graph reconstruction from generated semantic opening candidates.

This conditional benchmark supplies rooms, walls and opening candidates. It does
not measure door/window detection on images. Only aggregate results are exported.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from planportals import GraphConfig, OpeningCandidate, Room, WallSegment, build_graph, find_route

CONTRACT_SCENARIOS = (
    "door_window_unknown",
    "connecting_door",
    "low_score_door",
    "misaligned_door",
    "off_wall_door",
    "insufficient_clearance",
    "reversed_endpoints",
    "jittered_candidates",
)
CHALLENGE_SCENARIOS = (
    "window_mislabeled_door",
    "unknown_mislabeled_door",
    "door_mislabeled_window",
    "missing_door_candidate",
)
SCENARIOS = CONTRACT_SCENARIOS + CHALLENGE_SCENARIOS
PAIR_AB, PAIR_AC, PAIR_BD, PAIR_CD = ("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")
PAIRS = tuple(itertools.combinations(("A", "B", "C", "D"), 2))


@dataclass(frozen=True)
class GeneratedCase:
    rooms: tuple[Room, ...]
    walls: tuple[WallSegment, ...]
    openings: tuple[OpeningCandidate, ...]
    config: GraphConfig
    expected_edges: frozenset[tuple[str, str]]
    candidate_pairs: tuple[tuple[str, str], ...]
    image_size: tuple[int, int]


def generate_case(seed: int, scenario: str) -> GeneratedCase:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    rng = random.Random(seed)
    width, height = rng.uniform(340, 440), rng.uniform(250, 330)
    rooms = (
        Room("A", "Living", ((0, 0), (width, 0), (width, height), (0, height))),
        Room("B", "Hall", ((width, 0), (2 * width, 0), (2 * width, height), (width, height))),
        Room("C", "Bedroom", ((0, height), (width, height), (width, 2 * height), (0, 2 * height))),
        Room(
            "D",
            "Kitchen",
            ((width, height), (2 * width, height), (2 * width, 2 * height), (width, 2 * height)),
        ),
    )
    walls = (
        WallSegment("vertical", (width, 0), (width, 2 * height), 8),
        WallSegment("horizontal", (0, height), (2 * width, height), 8),
    )
    centers = (
        (width, height / 2),
        (width / 2, height),
        (1.5 * width, height),
        (width, 1.5 * height),
    )
    kinds = ["door", "window", "unknown", "door"]
    scores = [0.95] * 4
    expected = {PAIR_AB, PAIR_CD}
    clearance = scenario == "insufficient_clearance"
    if scenario in (
        "connecting_door",
        "low_score_door",
        "misaligned_door",
        "off_wall_door",
        "insufficient_clearance",
    ):
        kinds[2] = "door"
    if scenario == "connecting_door":
        expected.add(PAIR_BD)
    if scenario == "low_score_door":
        scores[2] = 0.2
    if scenario == "window_mislabeled_door":
        kinds[1] = "door"
    elif scenario == "unknown_mislabeled_door":
        kinds[2] = "door"
    elif scenario == "door_mislabeled_window":
        kinds[0] = "window"
    candidates = []
    for i, ((cx, cy), kind, score) in enumerate(zip(centers, kinds, scores, strict=True)):
        opening_width = 70 if clearance and i == 2 else rng.uniform(95, 135)
        vertical = i in (0, 3)
        p1 = (cx, cy - opening_width / 2) if vertical else (cx - opening_width / 2, cy)
        p2 = (cx, cy + opening_width / 2) if vertical else (cx + opening_width / 2, cy)
        if scenario == "misaligned_door" and i == 2:
            p1, p2 = (cx, cy - opening_width / 2), (cx, cy + opening_width / 2)
        elif scenario == "off_wall_door" and i == 2:
            p1, p2 = (p1[0], p1[1] + 35), (p2[0], p2[1] + 35)
        elif scenario == "jittered_candidates":
            dx, dy = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
            p1, p2 = (p1[0] + dx, p1[1] + dy), (p2[0] + dx, p2[1] + dy)
        if scenario == "reversed_endpoints":
            p1, p2 = p2, p1
        candidates.append(OpeningCandidate(f"opening-{i}", kind, p1, p2, score, "generated"))
    candidate_pairs = (PAIR_AB, PAIR_AC, PAIR_BD, PAIR_CD)
    if scenario == "missing_door_candidate":
        candidates = candidates[1:]
        candidate_pairs = candidate_pairs[1:]
    config = GraphConfig(mm_per_px=10, minimum_clearance_mm=900) if clearance else GraphConfig()
    return GeneratedCase(
        rooms,
        walls,
        tuple(candidates),
        config,
        frozenset(expected),
        candidate_pairs,
        (math.ceil(2 * width), math.ceil(2 * height)),
    )


def reachable(
    edges: set[tuple[str, str]] | frozenset[tuple[str, str]], start: str, goal: str
) -> bool:
    seen = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for left, right in edges:
            neighbor = right if left == current else left if right == current else None
            if neighbor is not None and neighbor not in seen:
                seen.add(neighbor)
                frontier.append(neighbor)
    return goal in seen


def graph_pairs(graph: object) -> set[tuple[str, str]]:
    """Only admitted door edges mean traversability; typed adjacency includes windows."""
    return {tuple(sorted((edge.first, edge.second))) for edge in graph.edges}


def evaluate(seed: int = 20261009, repeats: int = 20) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    records: dict[str, list[dict]] = defaultdict(list)
    association_counts = {
        "expected_assignable_candidates": 0,
        "assigned_candidates": 0,
        "correct_assigned_room_pairs": 0,
        "correct_assigned_wall_ids": 0,
    }
    route_api_checks = 0
    for scenario_index, scenario in enumerate(SCENARIOS):
        for repetition in range(repeats):
            case = generate_case(seed + scenario_index * 10000 + repetition, scenario)
            graph = build_graph(
                case.rooms, case.walls, case.openings, case.config, image_size=case.image_size
            )
            predicted = graph_pairs(graph)
            expected_by_id = {
                candidate.id: pair
                for candidate, pair in zip(case.openings, case.candidate_pairs, strict=True)
            }
            for decision in graph.decisions:
                i = int(decision.candidate.id.rsplit("-", 1)[1])
                should_assign = not (
                    i == 2 and scenario in ("low_score_door", "misaligned_door", "off_wall_door")
                )
                association_counts["expected_assignable_candidates"] += should_assign
                if None not in decision.room_ids:
                    association_counts["assigned_candidates"] += 1
                    association_counts["correct_assigned_room_pairs"] += (
                        tuple(sorted(decision.room_ids)) == expected_by_id[decision.candidate.id]
                    )
                    association_counts["correct_assigned_wall_ids"] += decision.wall_id == (
                        "vertical" if i in (0, 3) else "horizontal"
                    )
            methods = {
                "planportals_semantic_graph": predicted,
                "every_candidate_is_a_door": set(case.candidate_pairs),
                "every_adjacent_room_is_connected": {PAIR_AB, PAIR_AC, PAIR_BD, PAIR_CD},
            }
            for method, edges in methods.items():
                route_truth = [reachable(case.expected_edges, *pair) for pair in PAIRS]
                route_predictions = [reachable(edges, *pair) for pair in PAIRS]
                row = {
                    "scenario": scenario,
                    "tp_edges": len(edges & case.expected_edges),
                    "fp_edges": len(edges - case.expected_edges),
                    "fn_edges": len(case.expected_edges - edges),
                    "correct_routes": sum(
                        a == b for a, b in zip(route_truth, route_predictions, strict=True)
                    ),
                    "false_traversable_routes": sum(
                        not a and b for a, b in zip(route_truth, route_predictions, strict=True)
                    ),
                    "missed_routes": sum(
                        a and not b for a, b in zip(route_truth, route_predictions, strict=True)
                    ),
                    "route_queries": len(PAIRS),
                }
                records[method].append(row)
            for pair in PAIRS:
                route = find_route(graph, *pair)
                found = bool(route.room_ids)
                if found != reachable(predicted, *pair):
                    raise AssertionError("find_route disagrees with graph connectivity")
                route_api_checks += 1

    def summarize(rows: list[dict]) -> dict:
        counts = {
            key: sum(row[key] for row in rows)
            for key in (
                "tp_edges",
                "fp_edges",
                "fn_edges",
                "correct_routes",
                "false_traversable_routes",
                "missed_routes",
                "route_queries",
            )
        }
        counts["cases"] = len(rows)
        counts["edge_precision"] = (
            counts["tp_edges"] / (counts["tp_edges"] + counts["fp_edges"])
            if counts["tp_edges"] + counts["fp_edges"]
            else None
        )
        counts["edge_recall"] = (
            counts["tp_edges"] / (counts["tp_edges"] + counts["fn_edges"])
            if counts["tp_edges"] + counts["fn_edges"]
            else None
        )
        counts["route_existence_accuracy"] = counts["correct_routes"] / counts["route_queries"]
        return counts

    return {
        "protocol": "generated room/wall/semantic opening candidates; not image detection accuracy",
        "seed": seed,
        "cases": len(SCENARIOS) * repeats,
        "scenarios": {scenario: repeats for scenario in SCENARIOS},
        "baseline_scope": (
            "naive adjacency and treating all supplied opening candidates as doors; "
            "all-candidate baseline uses each generated candidate's intended room pair"
        ),
        "challenge_policy": (
            "wrong or missing upstream semantics remain in the evaluation; "
            "labels are not oracle in challenges"
        ),
        "route_api_consistency_checks": route_api_checks,
        "association_counts": association_counts,
        "metrics": {method: summarize(rows) for method, rows in records.items()},
        "contract_metrics": {
            method: summarize([row for row in rows if row["scenario"] in CONTRACT_SCENARIOS])
            for method, rows in records.items()
        },
        "challenge_metrics": {
            method: summarize([row for row in rows if row["scenario"] in CHALLENGE_SCENARIOS])
            for method, rows in records.items()
        },
        "by_scenario": {
            method: {
                scenario: summarize([row for row in rows if row["scenario"] == scenario])
                for scenario in SCENARIOS
            }
            for method, rows in records.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument(
        "--output", type=Path, required=True, help="aggregate local JSON; no fixture export"
    )
    args = parser.parse_args()
    report = evaluate(args.seed, args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"cases": report["cases"], "metrics": report["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
