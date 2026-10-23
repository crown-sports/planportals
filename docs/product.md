# Room connections and closures

[README](../README.md) · [中文](../README.zh-CN.md)

The graph starts with room polygons, wall segments and typed opening candidates. A connection requires a door label, wall support and consistent room membership on both sides. Windows, unknown gaps and ambiguous candidates retain their decisions but do not become edges. [Geometry](../src/planportals/geometry.py) · [Graph construction](../src/planportals/graph.py) · [Tests](../tests/test_portals_graph.py).

`access` compares reachability before and after removing the specified door edges. Rooms that were already unreachable are separate from newly isolated rooms. The serialized graph is checked before routing; a stored traversable flag alone is not trusted. [Input checks](../src/planportals/io.py) · [Closure tests](../tests/test_access.py).

The README figure reads the actual labels, accepted edges and access report from the [shared generated example](workflow.md). Both panels keep the same geometry. The red mark is the blocked opening, green is reachable from the start, salmon is newly isolated and gray was unreachable beforehand. The line inside kitchen/study remains because those rooms are still connected to each other.

A hand-written graph is enough when its edges are already trusted. Here the extra work is deciding which supplied opening can become an edge and keeping the rejected reasons. Graph lines are room adjacency, not obstacle-free routes. An incorrect upstream door label can still create a false connection; the [generated cases](validation.md) include that failure. No detector, usable-clearance certification or evacuation assessment is supplied.
