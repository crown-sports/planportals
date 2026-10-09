# API and input contract

PlanPortals receives room geometry, wall segments and typed opening observations. All inputs
must use the same original image coordinates: top-left origin, x right, y down, pixels. Undo
your model's resize and padding before passing its labels or segments to this library.

## Python

```python
from pathlib import Path

from planportals import build_graph, find_route
from planportals.demo import demo_scene
from planportals.io import save_graph

image, scene = demo_scene()
graph = build_graph(
    scene.rooms,
    scene.walls,
    scene.openings,
    scene.config,
    image_size=scene.image_size,
)
save_graph(graph, Path("runs/demo"))
route = find_route(graph, "bedroom", "study")
assert route.room_ids == ("bedroom", "living", "kitchen", "study")
assert find_route(graph, "living", "bathroom").status == "no_path"
```

The domain objects are frozen dataclasses. IDs are nonempty strings and must be unique
within each collection.

| Object | Fields |
| --- | --- |
| `Room` | `id`, `name`, `points`; optional `holes=()`, `parts=()` |
| `PolygonPart` | `points`; optional `holes=()`; used for additional room pieces |
| `WallSegment` | `id`, `p1`, `p2`, `thickness=8.0` in pixels |
| `OpeningCandidate` | `id`, `kind`, `p1`, `p2`; optional `score=None`, `source="unknown"`, `quality_issues=()` |
| `SceneInput` | `rooms`, `walls`, `openings`, `image_size=(width,height)`, `config=GraphConfig()` |

Points are `(x,y)` pairs. Rings accept either winding and may repeat their first point at
the end. Each room's primary polygon is `points` minus `holes`; `parts` adds polygons with
their own holes. Self-intersecting rings, holes outside the exterior, and intersecting,
nested or touching holes are rejected. Cross-room overlap is retained and can make an
opening's room assignment ambiguous.

`kind` is `door`, `window` or `unknown`. `source` describes the upstream evidence, such as
`manual-annotation`, `detector:my-model` or `semantic-mask`. Sources `unknown`, `gap`,
`geometry_gap`, `wall_gap` and `untyped_gap` cannot create passages, even when labelled
`door`; this check ignores surrounding whitespace and case. A supplied score must be in
`[0,1]`. It is an upstream score, not a calibrated correctness probability. A null score
has no score-threshold check.

## JSON

Save this as `scene.json`, then run `planportals build --input scene.json --output runs/result`:

```json
{
  "schema_version": "planportals-input/1",
  "image": {"width": 200, "height": 100},
  "coordinates": {"origin": "top_left", "x": "right", "y": "down", "unit": "px"},
  "rooms": [
    {"id": "a", "name": "A", "points": [[0,0],[100,0],[100,100],[0,100]], "holes": [], "parts": []},
    {"id": "b", "name": "B", "points": [[100,0],[200,0],[200,100],[100,100]]}
  ],
  "walls": [{"id": "divider", "p1": [100,0], "p2": [100,100], "thickness": 8}],
  "openings": [
    {"id": "door-a-b", "kind": "door", "p1": [100,30], "p2": [100,70], "score": 0.9, "source": "manual-annotation"}
  ],
  "config": {}
}
```

`holes` is an array of rings. `parts` is an array of objects shaped as
`{"points": [[x,y], ...], "holes": [...]}`. Config and optional object fields may be omitted;
unknown dataclass fields are rejected. Image dimensions must be positive integers, points
finite, segments nonzero, and coordinates within the declared pixel bounds.

## Upstream adapters

These functions are exported from `planportals`:

| Function | Contract |
| --- | --- |
| `walls_from_wallgraph(data)` | `wallgraph/1` JSON; splits polylines into straight pieces named `wallgraph:<id>:<index>` |
| `rooms_from_planregions(data)` | `planregions/1` JSON; preserves polygon holes and multipart rooms |
| `rooms_from_labelmap(labels, names=None)` | Nonnegative 2D integer NumPy array; zero excluded, other values become string room IDs |
| `openings_from_mask(labels, door_classes, window_classes, min_area=12, *, min_aspect_ratio=1.5)` | Original-resolution hard semantic labels; returns door/window spans, with `score=None` |

The opening adapter uses four-connected components and a principal-axis span. Door and
window class IDs must be positive, unique and disjoint. Other classes are ignored. Tiny
and near-square components remain in the output with `quality_issues` and are rejected
by graph construction; they are not silently discarded. The room-label adapter merges
pixel cells into rectangle parts, preserving holes and disconnected pieces. For large
irregular rooms, upstream polygon JSON is more compact.

```bash
planportals build --wallgraph /private/walls.json \
  --planregions /private/regions.json \
  --opening-mask /private/semantic.png --door-classes 3 --window-classes 4 \
  --output runs/result
```

Use `--room-labels /private/labels.npz` instead of `--planregions` when needed. Label files
may be single-channel integer PNG, NPY or NPZ containing `labels`; RGB preview colors
are rejected. Wall, room and opening image dimensions must agree. `--opening-mask` can
also add candidates to `--input`; do not supply the same observation twice.

## Configuration and units

| `GraphConfig` field | Default | Meaning |
| --- | --- | --- |
| `attach_distance_px` | `12` | Allowed distance beyond the wall's half-thickness |
| `max_angle_deg` / `endpoint_tolerance_px` | `15` / `6` | Direction agreement and segment-end tolerance |
| `sample_offset_px` / `sample_count` / `vote_fraction` | `8` / `5` / `0.8` | Offset beyond half-thickness, samples per side, required support |
| `min_opening_width_px` / `max_opening_width_px` | `2` / `400` | Allowed candidate endpoint span |
| `min_detector_score` | `0.5` | Threshold applied only when a score is supplied |
| `mm_per_px` / `mm_per_px_y` | `None` / `None` | x scale; y scale defaults to the x scale |
| `minimum_clearance_mm` | `None` | Optional minimum candidate-span policy; requires a metric scale |

`width_px` is the endpoint distance of the supplied candidate. With scales `sx,sy`,
`width_mm = hypot(dx*sx, dy*sy)`. This is not independently measured net free door width.
The policy reports `not_checked`, `span_below_minimum` or `span_meets_minimum`; below-minimum
doors stay associated but do not enter the route graph. Invalid scales and numeric
overflow raise `ValueError`. CLI scale flags override the input config:

```bash
planportals build --input /private/scene.json --mm-per-px 10 \
  --mm-per-px-y 12 --minimum-clearance-mm 800 --output runs/result
```

## Results and routing

`save_graph(graph, directory)` writes `portals.json` (`planportals/1`) and `portals.svg`.
The JSON retains rooms, original wall segments, config, all candidate decisions and
evidence. `edges` contains accepted door connections; `adjacency` also contains internal
windows and doors excluded by the width policy. Use `traversable`, not status alone:

| Decision status | Meaning |
| --- | --- |
| `accepted` | Typed opening and two distinct rooms associated; a window still has no passage |
| `attached` | Typed opening supported, but one or both sides lie outside supplied rooms |
| `unresolved` | Wall/room association exists, but semantic opening type is missing |
| `ambiguous` | Competing wall support, inconsistent room-side evidence or conflicting door/window claims |
| `rejected` | Unsupported geometry, quality issues, width/score failure or same room on both sides |

Each decision includes `reason`, `attachments` and `sides`. Attachment records identify
the supporting original wall IDs, projected endpoints, angle, distance and support kind.
A `flanking_walls` record describes a temporary association span across two wall ends;
it never fills the wall mask. Side records retain sample coordinates, memberships and votes.

```bash
planportals route --graph runs/result/portals.json \
  --from-room a --to-room b --output runs/route.json
```

`find_route` returns `found` with `room_ids` and `opening_ids`, or `no_path` with empty
sequences. Identical endpoints return one room and no openings. Unknown room IDs are
errors. Routes are undirected, shortest by number of accepted doors, and represent
room sequences rather than collision-free paths. Loading graph JSON reconstructs its
decisions and rejects tampered edges. API validation raises `ValueError`; CLI failures
exit with code `2`, while a valid `no_path` result exits with code `0`.
