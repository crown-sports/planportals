# Where PlanPortals fits

**User and decision:** a developer has room/wall geometry and typed opening candidates and wants to inspect connections or the consequence of closing a door. The [shared walkthrough](workflow.md) shows where to start among all four packages and produces measurements, a structural-change report and closure results from one generated apartment.

| Current, checkable value | Evidence | Boundary |
| --- | --- | --- |
| Retain wall support and two-sided room evidence for every candidate | [`geometry.py`](../src/planportals/geometry.py), [`graph.py`](../src/planportals/graph.py), [`test_portals_graph.py`](../tests/test_portals_graph.py) | Wrong upstream semantics can admit a false door |
| Keep windows, unknown gaps and ambiguous candidates out of routes | [`test_portals_graph.py`](../tests/test_portals_graph.py), [generated evaluation](validation.md) | No trained detector or inferred door semantics is supplied |
| Rebuild serialized decisions before routing; compare closures to baseline | [`io.py`](../src/planportals/io.py), [`test_access.py`](../tests/test_access.py) | Rooms already unreachable are not newly isolated; routes are room sequences only |

A hand-written graph or [NetworkX shortest path](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html) is sufficient if your edges are already trusted. PlanPortals addresses the preceding question: which supplied opening has enough geometric and semantic evidence to become an edge, and why? Its graph search is not a new routing algorithm. General vision models remain possible candidate providers; their proposed door class must still be reviewed. No certified accessibility, fire-safety or obstacle-free navigation result is produced.

[Validation](validation.md) uses generated candidates, including deliberately wrong semantics. It demonstrates decision behavior, not image recognition accuracy or user time saved. For the walkthrough, annotations are provided explicitly and the two changes—missing separator and temporary closure—remain separate.

**Next priorities:** collect permissioned opening-association failures and reviewer corrections; then validate false connections and route changes on held-out real plans. An evidence and correction corpus could accumulate useful domain knowledge. The current public algorithms and contracts are reproducible engineering, not evidence of an established proprietary moat or product-market fit.
