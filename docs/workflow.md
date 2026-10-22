# Review one floor plan across four packages

[中文](workflow.zh-CN.md) · [Back to PlanPortals](../README.md)

This example runs the four packages on one generated apartment: extract wall paths, measure rooms, remove a separator and close a door. Wall barriers, six dimensions and opening classes are supplied annotations; no OCR, recognition model, network inference or real drawing is involved.

## Choose a starting point

Install only the package needed for your decision; the combined example below deliberately installs all four.

| Your existing input and next decision | Start with | Hand off when needed |
| --- | --- | --- |
| Binary wall mask → selectable wall paths and junctions | [WallGraph](https://github.com/crown-sports/wallgraph) | Original-grid mask to PlanRegions; paths to PlanMetric/PlanPortals |
| Wall mask or two instance maps → room regions or merge/split review | [PlanRegions](https://github.com/crown-sports/planregions) | Exact pixel areas to PlanMetric; polygons to PlanPortals |
| Pixel geometry + dimension evidence → supported lengths/areas | [PlanMetric](https://github.com/crown-sports/planmetric) | Accepted scale to your measurement display or opening-width policy |
| Rooms + walls + typed openings → room connections and closure impact | [PlanPortals](https://github.com/crown-sports/planportals) | Inspect the room/opening sequence in your application |

If you only have an unlabelled scan, these packages do not supply a complete recognizer. First obtain reviewed masks, dimension observations and door/window candidates. A general vision model can supply candidates, but its answer still needs those coordinate and evidence contracts.

## Run the shared example

Python 3.10+. Clone the current main source for the walkthrough script; this new script is not in the existing v0.2.0 release assets. The four engine dependencies below are pinned to existing releases. No model weights are downloaded.

```bash
git clone https://github.com/crown-sports/planportals.git
cd planportals
python -m venv .venv
source .venv/bin/activate
python -m pip install \
  "git+https://github.com/crown-sports/wallgraph.git@v0.2.0" \
  "git+https://github.com/crown-sports/planregions.git@v0.4.0" \
  "git+https://github.com/crown-sports/planmetric.git@v0.2.0" \
  "git+https://github.com/crown-sports/planportals.git@v0.2.0"
python tools/review_workflow.py --output runs/review
```

On Windows activate with `.venv\Scripts\activate`. After installation, execution is local. Use a fresh output directory: the script rejects an existing destination instead of replacing a prior review.

Expected `summary.json`: **5 regions**, **10 mm/px on each axis**, **3 accepted door connections**. The living region measures **14.3221 m²**, using its exact labelled pixels with wall pixels excluded. Removing one separator section changes **5 regions to 4**, with **1 merge group**. Blocking `door-living-kitchen` from bedroom (region `3`) newly isolates **kitchen and study**; bathroom was already unreachable and is not counted as newly isolated.

| Open this output | What to check |
| --- | --- |
| `runs/review/walls/walls.svg` and `walls.json` | Centerlines and junction IDs from the supplied barrier mask |
| `runs/review/regions/regions.png` and `regions.json` | Five regions on the same 1200×800 pixel grid |
| `runs/review/calibration/evidence.svg`, `measurements.json` | Six supporting dimensions, accepted axis scales and exact pixel-area conversions |
| `runs/review/wall-measurements.json` | Lengths of the extracted centerline paths, not wall-face quantities |
| `runs/review/changes.html` | Living/kitchen merge after the deliberately missing separator |
| `runs/review/portals/portals.svg` and `access.json` | Accepted doors, excluded windows/unknowns and closure reachability |

The partition mask intentionally keeps room separators continuous, including at annotated doors. It is not a claim that a physical door is solid wall. The missing-separator experiment and the temporary-closure experiment are separate changes; neither silently edits the other's evidence.

## Reuse outputs and recognize refusal

Recompute measurements through the published CLI:

```bash
planmetric measure --observations runs/review/observations.json \
  --geometry runs/review/regions/regions.json --output runs/review/measured-again.json
```

Expected exit **0**, with the same room measurements. Missing accepted scales or mismatched image dimensions must be corrected upstream; do not turn a rejection into a guessed scale.

Run the two review gates separately:

```bash
planregions compare --before runs/review/regions/labels.npz \
  --after runs/review/changed-regions/labels.npz \
  --output runs/review/change-gate.json --fail-on merge
planportals access --graph runs/review/portals/portals.json --from-room 3 \
  --blocked-openings door-living-kitchen --output runs/review/access-gate.json \
  --fail-on-newly-isolated
```

Each command intentionally writes its report and exits **1**: the first flags a merge; the second flags two newly isolated rooms. Exit 1 is a review outcome, not a crashed program. Unknown opening IDs or malformed inputs exit **2**.

The combined script also supports `--fail-on-newly-isolated` (exit 1 after writing all outputs). Try `--blocked-opening no-such-door` with a new destination to observe exit 2 and no new output directory.

## Use this on your own work

Replace the synthetic barriers with a reviewed binary mask, dimension observations with your OCR/review output, and opening classes with your typed detections. Keep all four in the **same original image grid**. Preserve input provenance and review rejected evidence. The script is an inspectable integration example, not a batch importer for arbitrary drawings.

A changed region is not automatically an error; consensus does not establish that the dimensions are true; a room route is not a collision-free or certified evacuation route. Each package's `docs/product.md` explains its geometry and links to the relevant implementation.
