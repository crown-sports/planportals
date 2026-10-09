# Validation and known failures

Version 0.1.0, protocol seed `20261009`. This evaluates graph construction from supplied geometry and typed candidates. It does not measure door/window detection on images or compare against a trained recognition system.

## Reproduce

```bash
python -m pip install -e '.[dev]'
pytest
python tools/render_demo.py --check
python tools/evaluate_generated.py --output /private/portals-evaluation.json
```

The 240 generated cases cover 12 scenarios, 20 cases each. Eight contract scenarios exercise typed doors/windows/gaps, a connecting door, low scores, misalignment, off-wall observations, insufficient width, reversed endpoints and coordinate jitter. Four challenges inject windows or unknown openings mislabelled as doors, doors mislabelled as windows, and missing doors. Six room-pair queries per case produce 1,440 route-existence decisions.

The baselines treat every candidate as a door, or connect every adjacent room. They expose common unsafe graph shortcuts; they are simple baselines, not state-of-the-art recognition methods. The truth is fixed by the generated scene before candidates are corrupted. Routes are assessed as reachable/unreachable room pairs, not physical paths.

## Results

| Method, all 240 cases | Edge precision | Edge recall | Route existence correct | False reachable queries |
| --- | ---: | ---: | ---: | ---: |
| Every candidate is a door | 51.06% | 96.00% | 38.89% | 880 / 1,440 |
| Every adjacent room connects | 52.08% | 100.00% | 38.89% | 880 / 1,440 |
| PlanPortals | 92.00% | 92.00% | 86.11% | 160 / 1,440 |

The 160 contract cases contain 340 true door edges. PlanPortals has 340 true positives, zero false edges and zero missed edges; all 960 route queries agree with the generated truth. The every-candidate baseline adds 300 false edges and makes 560 false-reachable decisions on those same cases.

**The 80 upstream challenge cases retain real failures:** PlanPortals has 120 true edges, 40 false edges and 40 missed edges. Of 480 route queries, 160 are falsely reachable and 40 are missed; route correctness is 58.33%. A confident, geometrically plausible window mislabelled as a door can still become a false edge. Missing or mistyped doors can hide valid routes.

The controlled geometric association check assigns 880/880 candidates to the expected wall and room pair. This concerns supplied geometry; it is not image detection accuracy. The complete result, including semantic failures, matters more than that isolated count.

## Demonstration and integration

The figure uses an original five-room plan and seven supplied candidates. The actual engine admits three doors, retains two windows, leaves an untyped gap unknown and rejects an ambiguous candidate. Bedroom → living → kitchen → study is found. Living → bathroom is unavailable; the naive candidate-as-door graph falsely reports it as reachable.

CLI integration checks use WallGraph paths, PlanRegions room polygons and a generated semantic PNG. They include a typed door between two collinear wall endpoints: both wall segments remain recorded as supporting evidence. Unknown gaps never receive that door inference.

A private integration check takes the first six sorted real annotated SVG drawings, without selecting by visual quality. It converts annotation wall polygons to a mask, uses the WallGraph vectorizer for paths, and supplies annotated room polygons and door/window masks to PlanPortals. Five drawings complete; one fails because a room polygon self-intersects. The five completed drawings contain 61 rooms, 135 wall paths (242 straight segments), 80 opening candidates and 39 accepted door edges. All numeric outputs are finite, and no window forms a traversable edge. An additional probe changes all candidate semantics to unknown and produces zero edges.

This checks real annotation formats and geometry integration. It uses annotated inputs rather than model predictions and has no independent door-to-room connectivity ground truth, so the 39 edges are output counts, not verified true positives. The drawings, annotations, overlays, case identifiers and conversion script remain private.

## Engineering checks

Tests cover room holes and multipart geometry, semantic components, conflicts, ambiguous wall supports, room-side sampling, score/width policies, malformed inputs, finite arithmetic, graph serialization and routes. Release checks validate the reviewed figure against actual graph decisions and permit only one metadata-free generated PNG. CI runs lint, formatting, tests and package builds on Python 3.10 and 3.12.

The output is a conditional room graph. It does not resolve furniture obstacles, verify usable door clearance, or certify evacuation/accessibility compliance.
