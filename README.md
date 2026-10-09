# PlanPortals

**Connect rooms through supported doors. Keep windows and unknown gaps out of the route graph.**

[中文](README.zh-CN.md) · [Releases](https://github.com/crown-sports/planportals/releases)

![Generated plan, typed opening evidence, accepted room connections and actual route decisions](examples/demo.png)

On this generated five-room plan, the actual engine admits **3 door connections**. Bedroom → living → kitchen → study is reachable; the bathroom remains unreachable through its windows and unknown gap. Room geometry and typed candidates are supplied inputs. This package does not include a trained door/window detector.

## Try it

Python 3.10+. No GPU, model or cloud service required.

```bash
python -m pip install "git+https://github.com/crown-sports/planportals.git@v0.1.0"
planportals demo --output runs/demo
```

Inspect the graph JSON and SVG overlay: accepted connections and rejected candidates retain their evidence and reasons.

```bash
planportals build --input /private/scene.json --output runs/result
```

Use your upstream model's original-resolution semantic label mask or typed opening segments. Import wall paths from [WallGraph](https://github.com/crown-sports/wallgraph) and room polygons from [PlanRegions](https://github.com/crown-sports/planregions). [Input contract, adapters and routing API](docs/api.md).

## What it solves

| Evidence | Decision |
| --- | --- |
| A door supported by a wall and two determined rooms | A door connection between those rooms |
| A window | Retain the association; no door connection |
| An untyped gap in a wall prediction | Keep it unknown; no inferred door |
| Competing walls or inconsistent room-side samples | Retain the candidate and explain the ambiguity |
| A door with calibrated width and a width policy | Check the supplied threshold and report the result |

A route is a **sequence of rooms and opening IDs**. It is not a collision-free path inside furnished rooms or a certified accessibility/evacuation assessment. Opening span width is a geometric observation, not independently verified usable door clearance.

## Method and measured boundary

Semantic components → wall support → two-sided room evidence → conservative connection decisions → graph search. Every decision remains inspectable. [Methods](docs/methods.md) · [Architecture](docs/architecture.md).

Generated comparisons include windows, unknown gaps, geometric mismatches and wrong upstream semantics. Correct handling of supplied candidates does not establish end-to-end image recognition accuracy; an incorrectly labelled door can still create a false connection. [Protocol and actual results](docs/validation.md).

## Development

```bash
python -m pip install -e '.[dev]'
pytest
python tools/render_demo.py --check
python tools/release.py --check
```

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Release contents](docs/releasing.md)

MIT for code. Only one code-generated composite figure is included. Real drawings, annotations, datasets and model weights remain outside the release. [Provenance](NOTICE.md).
