# Architecture

PlanPortals answers a narrow question: given wall geometry, room polygons and semantic
opening observations, which room connections are supported? It keeps the input evidence
and the decision together, so a blocked or uncertain connection can be inspected.

## Responsibilities

| Module | Responsibility |
| --- | --- |
| `domain.py` | Frozen observations, configuration, attachment evidence, graph and route results |
| `adapters.py` | Translate WallGraph, PlanRegions and supplied label maps into domain objects |
| `geometry.py` | Ring validation, pixel membership, wall projections and two-sided sampling |
| `graph.py` | Apply conservative connection policy and breadth-first room search |
| `io.py` | Versioned local JSON, reconstruction checks and SVG preview |
| `cli.py` | Compose adapters and services; no network or private-model dependency |
| `demo.py` | Generate the original drawing and its explicitly supplied observations |

Adapters do not import an upstream package or call a detector. The same graph service
accepts manual observations or another model's output. Domain objects are immutable;
graph construction returns a new result without modifying walls, rooms or masks.

## Construction policy

1. Validate IDs, coordinates, rings and configuration. Keep overlap between distinct
   rooms available for later ambiguity checks.
2. Compare each opening's direction, endpoint distance and projected span with straight
   wall pieces. Partial support alone cannot establish an opening.
3. For typed doors/windows only, consider two collinear wall pieces with facing ends near
   the candidate's ends. Record a temporary supporting span and both original wall IDs.
   This supports door gaps in WallGraph output without drawing a wall over the gap.
4. Reject competing support hypotheses. Across the selected span, sample on both normals
   at half wall thickness plus the configured offset. Keep each membership and vote.
   Multiple rooms on a side, overlapping memberships or insufficient support stay ambiguous.
5. Require a typed source and two distinct assigned rooms. Windows enter opening adjacency
   but never the passage graph. Unknown gaps never supply a door edge. A calibrated
   below-minimum candidate span also stays out of the passage graph.
6. If door and window claims overlap by at least half the smaller projected span on the
   same supporting wall, retain both as ambiguous and remove their graph connections.
7. Search only the admitted door graph with deterministic breadth-first traversal.

The two edge collections have different meanings: `adjacency` describes supported typed
openings between rooms; `edges` describes door connections usable by room-sequence search.
The decision's `traversable` field is the authoritative connection flag. An accepted
window or below-minimum door is still not a passage.

## Boundaries

A wrong upstream door label can still create a false connection when its geometry is
consistent. This library does not learn door semantics, recover a door from arbitrary
ink, or establish image-recognition accuracy. Hard-label components receive no invented
confidence score. Width conversion uses supplied x/y scales and reports the observed
candidate span, not certified usable clearance.

Conservative rejection also has a cost: a door crossing several touching wall pieces,
inaccurate room boundaries, or multiple plausible wall supports may have no edge. The
reason and evidence remain available for correction upstream. A room route does not
account for furniture, within-room travel, door swing, locks or emergency egress rules.

Saved graphs include their observations. Loading them rebuilds the decisions and checks
that stored edges agree, rather than trusting externally edited passage claims. CLI
inputs and outputs stay on the caller's disk; public examples contain one generated
composite figure and no real drawings, dataset annotations or model weights.
