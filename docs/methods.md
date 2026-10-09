# Methods, design and evidence

Two nearby rooms may share a wall without having a door between them. PlanPortals receives room geometry, wall segments and typed opening evidence, then asks which connections are supported.

## Processing

1. Normalize caller-provided wall, room and opening observations into one image coordinate system. Semantic label maps can be converted into opening candidates through connected components and principal-axis geometry.
2. Project each candidate onto a compatible wall. A typed opening between two collinear wall ends may use both segments as flanking support; this records a support span without filling the wall mask. Reject competing wall assignments and ambiguous room associations.
3. Sample room membership on both sides of the opening. Retain the evidence and reasons for acceptance, rejection or uncertainty.
4. Add a traversable room edge only for a supported door with a determined pair of rooms. A window or unknown gap cannot establish a door edge. Overlapping door/window claims remain ambiguous and lose their passage edge.
5. Search the accepted graph for a sequence of rooms and opening IDs. This sequence is not a collision-free path through a furnished room. Physical-width policies need valid metric calibration.

The engineering contribution is the separation of geometric adjacency, semantic opening evidence and supported door connections, with inspectable failure decisions. It is not a new graph-search algorithm or an independently trained door detector.

## Related work and dependencies

[roomgraph](https://github.com/aec-platform/roomgraph) extracts walls, openings and room relations from vector PDFs. It demonstrates a related problem; no source or fixture from that repository is incorporated here. Our input boundary is supplied raster-derived or vector observations, with upstream recognition quality evaluated separately.

The original application's opening prototype is an implementation clue, not code copied into this package. Connected components, principal-axis fitting, point-in-polygon geometry and breadth-first search are established methods. NumPy and Pillow retain their licenses. No private network/model source or dataset is distributed.
