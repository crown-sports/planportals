"""Retain upstream-label failures and verify the actual route in the public demo."""

import runpy
from pathlib import Path


def test_generated_comparison_retains_wrong_upstream_semantics():
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "tools/evaluate_generated.py")
    )
    report = module["evaluate"](seed=20261009, repeats=2)
    challenge = report["challenge_metrics"]["planportals_semantic_graph"]
    ours = report["metrics"]["planportals_semantic_graph"]
    naive = report["metrics"]["every_candidate_is_a_door"]
    assert report["cases"] == 24
    assert report["route_api_consistency_checks"] == 144
    assert challenge["fp_edges"] > 0 and challenge["fn_edges"] > 0
    assert ours["false_traversable_routes"] < naive["false_traversable_routes"]
    assert "not image detection accuracy" in report["protocol"]


def test_reviewed_figure_and_actual_door_only_routes():
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools/render_demo.py"))
    module["check_figure"](module["PUBLIC_FIGURE"])
    module["check_graph_demo"]()
