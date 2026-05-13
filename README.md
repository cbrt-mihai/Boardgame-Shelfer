# Boardgame Shelfer

A Python utility that assigns board games to physical shelves from real-world dimensions. It treats each shelf compartment as a bounded region and places boxes using a greedy placement strategy with geometric validity checks (no overlap, stable stacking, and optional non-stackable items).

## Highlights

- **Constraint-aware layout** — Rectangle overlap detection, vertical stacking with balance heuristics, and support for items that must not be stacked (marked in the input file).
- **Data-driven workflow** — Plain-text CSV-style inputs for games (`items.txt`) and shelf bins (`bins.txt`); structured text output for integration or visualization.
- **Heuristic packing** — Items ordered by size; bins considered in a volume-aware order to improve fit on constrained shelves.
- **Optional visualization** — Output can be previewed in a browser-based sketch (p5.js) for quick sanity checks of placements.

## Tech stack

- **Language:** Python 3.7+ (standard library; `shelfer_V3_4.py` uses `dataclasses` and type hints).
- **Core ideas:** 2D rectangle packing on shelf faces, collision detection, stacking and support rules (refined in the v3.4 variant).

## Repository layout

| Path | Purpose |
|------|---------|
| `shelfer_V3.py` | Original shelf-packing implementation. |
| `shelfer_V3_4.py` | Extended (and better!) version with configurable grid search, support-ratio rules for stacks, and clearer structure. |
| `run_shelfer_and_view.py` | Runs `shelfer_V3_4.py`, then serves `index.html` locally and opens the p5.js preview in your browser. |
| `index.html` | Minimal page that loads `style.css`, vendored p5.js, and `sketch.js`. |
| `style.css` | Page layout (margins and canvas display) for the preview. |
| `sketch.js` | p5.js sketch that reads `output.txt` and draws shelf layouts. |
| `p5_libs/p5.js` | p5.js 1.11.3 (full, non-minified build). Ships in-repo so the preview works **without an internet connection**. |
| `utils.py` | Shared helpers (e.g. volume, rectangle overlap). |
| `items.txt` | Example item list with dimensions in **centimeters**. |
| `bins.txt` | Example shelf / bin definitions in **centimeters**. |
| `output.txt` | Generated placement file (default name; ignored by git). Created when you run a shelfer script. |

## Input format

**Items (`items.txt`)** — One game per line: `Name, length, height, width`. Lines starting with `#` are comments. Append `, X` after the width for games that must not be stacked on others (see the example file).

**Bins (`bins.txt`)** — One compartment per line: `Name, length, height, width` (same units). Comment lines use `#`.

All dimensions must use the same unit system (the examples use centimeters).

## Usage

1. Copy or edit `items.txt` and `bins.txt` to match your collection and furniture.
2. Run the desired script from the project root (paths inside the scripts default to the filenames above):

   for the improved newer rules and search behavior
   ```bash
   python3 shelfer_V3_4.py
   ```

   or, for the older, less refined version:

   ```bash
   python3 shelfer_V3.py
   ```

3. Inspect the generated output file (by default `output.txt`; confirm the path configured at the bottom of `shelfer_V3_4.py` or in `shelfer_V3.py` if you use that script).

## Visualization

### Local preview (recommended after `shelfer_V3_4.py`)

From the project root, run:

```bash
python3 run_shelfer_and_view.py
```

This runs `shelfer_V3_4.py`, checks that `output.txt` exists, starts a small local HTTP server (port **8765**, or the next free port if that one is taken), and opens the preview in your default browser. The sketch loads `output.txt` over HTTP, which avoids browser restrictions that often block `loadStrings` when opening HTML from `file://`. **p5.js is loaded from `p5_libs/p5.js` in this repository**, so no internet connection is required for the preview once you have the project files. Press **Enter** in the terminal to stop the server when you are finished.

### p5.js web editor (optional)

You can still use the hosted editor sketch and paste output into the sketch’s `output.txt` pane:

https://editor.p5js.org/cbrt-mihai/sketches/k6b2igNEu

Avoid a trailing blank line at the end of the pasted output. For very long outputs, paste in chunks of roughly 40–60 lines and run the sketch per chunk if needed.

### Visualization Note

No matter which visualizer you choose, local or browser, when the browser window opens, make sure to allow it to download multiple files. Those files are .pngs named after your bins and contain the visualized output from the Python script.

## Scope and limitations

This is a heuristic packer, not an exhaustive optimizer. Results depend on item order, bin order, and the chosen script variant; some collections may not fit entirely or may require adjusted shelf definitions.


