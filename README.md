# Boardgame Shelfer

A Python utility that assigns board games to physical shelves from real-world box dimensions. It treats each shelf compartment (a **bin**) as a 3D volume, projects placements onto the shelf face (length × height), and packs boxes with geometric checks: no overlap, enough support when stacking, and optional **non-stackable** games that must not sit under other boxes.

The recommended entry point is **`shelfer_V5.py`** (multi-start + local search with selectable goals). Older scripts (`shelfer_V4.py`, `shelfer_V3_4.py`, `shelfer_V3.py`) remain for comparison.

---

## Table of contents

1. [Quick start](#quick-start)
2. [Requirements](#requirements)
3. [What the program does](#what-the-program-does)
4. [Repository layout](#repository-layout)
5. [Measuring your collection](#measuring-your-collection)
6. [Input files](#input-files)
7. [How packing works](#how-packing-works)
8. [Running Shelfer V5](#running-shelfer-v5)
9. [CLI reference](#cli-reference)
10. [Output format](#output-format)
11. [Reading the summary](#reading-the-summary)
12. [Visualization](#visualization)
13. [Older script versions](#older-script-versions)
14. [Tips and troubleshooting](#tips-and-troubleshooting)
15. [Scope and limitations](#scope-and-limitations)

---

## Quick start

From the project root:

```bash
# Pack with defaults (balanced profile)
python3 shelfer_V5.py

# Quiet summary only
python3 shelfer_V5.py -q

# Maximize how many games fit (30s search)
python3 shelfer_V5.py --profile fit -q

# Denser face packing / fewer gaps
python3 shelfer_V5.py --profile dense -q

# Neater stacks (alignment + support)
python3 shelfer_V5.py --profile neat -q

# Fast single-pass (V4-like)
python3 shelfer_V5.py --profile quick -q

# Pack, then open the local p5.js preview
python3 run_shelfer_and_view.py
```

Example summary (numbers depend on your `items.txt` / `bins.txt`):

```text
========== SUMMARY ==========
Profile:      balanced
Placed:       52/55 (94.5%)
Elapsed:      15.02s
Utilization:  50.1% of shelf volume
Soft score:   0.7123
...
==============================
```

---

## Requirements

- **Python 3.7+** (3.9+ recommended). No third-party packages; only the standard library.
- A terminal in the project root (or pass absolute paths with `-i` / `-b` / `-o`).
- For visualization: a modern browser. **p5.js is vendored** under `p5_libs/`, so the local preview works offline.

Check the help:

```bash
python3 shelfer_V5.py --help
```

---

## What the program does

1. **Loads games** from an items file (name + three dimensions; optional non-stackable flag).
2. **Loads shelves** from a bins file (name + three dimensions per compartment).
3. Builds many candidate layouts (item orders, bin policies, orientations/positions) and **scores** them.
4. Runs **local search** (relocate / swap / reorient / ruin-recreate) within a time budget to improve the score.
5. Optionally **compacts** placements leftward to reduce gaps.
6. Writes a placement file (`output.txt` by default) and prints a terminal summary.

Physical rules match V4 (overlap, support ratio, orientations). V5 adds multi-start search and user-selectable soft goals. It still does **not** guarantee a globally optimal layout.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `shelfer_V5.py` | **Recommended packer** — profiles, soft weights, multi-start + local search. |
| `shelfer_V4.py` | Previous greedy packer (CLI, strategies). |
| `shelfer_V3_4.py` | Structured packer before the V4 CLI. |
| `shelfer_V3.py` | Original packer (legacy). |
| `run_shelfer_and_view.py` | Runs V5, serves the project over HTTP, opens the p5 preview. Extra args are forwarded to V5. |
| `index.html` | Preview page (loads CSS, p5, and `sketch.js`). |
| `style.css` | Preview page layout. |
| `sketch.js` | Draws each bin from `output.txt` and saves PNGs. |
| `p5_libs/p5.js` | Vendored p5.js 1.11.3 (offline). |
| `utils.py` | Shared geometry helpers (e.g. rectangle overlap). |
| `items.txt` | Example game list (centimeters). |
| `bins.txt` | Example shelf compartments (centimeters). |
| `output.txt` | Generated placements (gitignored; created on run). |
| `README.md` | This document. |

---

## Measuring your collection

Use **one unit system everywhere** (the examples use **centimeters**). Measure the outer box, not the insert.

For each game and each shelf compartment, record three numbers:

| Field in files | Physical meaning | Role in packing |
|----------------|------------------|-----------------|
| **length** | Horizontal span along the shelf (left–right on the face you look at) | X axis of the 2D layout |
| **height** | Vertical span (floor of compartment → ceiling) | Y axis of the 2D layout |
| **width** | Depth into the shelf (front → back) | Used for “does it fit in depth?” and volume; not drawn on the 2D face |

```text
          length (X)
     <---------------->
    +------------------+  ^
    |                  |  | height (Y)
    |   shelf face     |  |
    +------------------+  v
           depth = width (Z, into the page)
```

**Important:** A game whose smallest face is still larger than every bin in length or height (or depth for the chosen orientation) will be reported as **unplaced**. That is expected — e.g. a 38.7 cm box cannot enter a 33.5 cm compartment.

---

## Input files

### Items (`items.txt`)

One game per line:

```text
Name, length, height, width
```

Rules:

- Blank lines are ignored.
- Lines starting with `#` are comments.
- Values are comma-separated; spaces around fields are fine.
- **Any 5th field** marks the game as **non-stackable** (conventionally `X`). Non-stackable boxes are packed in a second pass and are not used as support for stacked neighbors.

Examples:

```text
# NAME, LENGTH, HEIGHT, WIDTH
Abyss, 28.5, 7.5, 28.5
Flamecraft, 29.7, 7, 29.7

# Non-stackable (fragile lid, soft box, etc.)
Ankh: Gods of Egypt, 32.4, 28, 32.4, X
Mythic Mischief, 25.1, 12.1, 20.6, X
```

Minimal valid file:

```text
My Game, 30, 8, 30
Another Game, 25, 7, 25, X
```

### Bins (`bins.txt`)

One compartment per line:

```text
Name, length, height, width
```

Same comment / blank-line rules as items. Names should be unique and filesystem-friendly if you use the PNG export (they become canvas download names).

Example (matches the sample furniture):

```text
# NAME, X-LENGTH, Y-HEIGHT, Z-WIDTH/DEPTH
Box_1_1, 33.5, 33.5, 42
Box_1_2, 33.5, 33.5, 42
Box_2_1, 33.5, 33.5, 42
```

### Special bin names: `Above…`

Bins whose names start with **`Above`** get **relaxed compaction**: during the left-slide pass, support checks are loosened so a long top shelf can pack more tightly for visualization. Regular bins keep strict support rules. You do not need this prefix unless you want that behavior.

---

## How packing works

### High-level algorithm (V5)

1. Split items into **stackable** and **non-stackable**.
2. Resolve a **profile** (or custom weights) and a **time budget**.
3. **Construct** many layouts: different item orders, bin policies, and position choices scored by soft goals.
4. **Local search** within the remaining time: relocate, swap, reorient, ruin-and-recreate; accept improvements by lexicographic score.
5. Run a **compaction** pass that slides boxes left when safe (unless `--no-compact`).
6. Validate bounds / overlaps and write the output.

By default the score is **lexicographic**: more games placed first, then a weighted soft score. Use `--lex-soft-only` if you want soft goals to outweigh fit count.

### Soft score components

| Component | Meaning |
|-----------|---------|
| `utilization` | Used box volume ÷ total bin volume |
| `face_fill` | Placed rectangle area ÷ shelf face area |
| `contact` | Shared edges / walls (less fragmentation) |
| `support` | Mean support ratio of stacked boxes |
| `neatness` | Similar tops, left alignment, floor-heavy stacks |
| `waste` | Inverse of jagged empty-skyline (fewer awkward holes) |

### Profiles (`--profile`)

| Profile | Default time | Intent |
|---------|--------------|--------|
| `quick` | one pass | Fast V4-like greedy construction |
| `fit` | 30s | Maximize games placed |
| `dense` | 30s | High fill / fewer gaps |
| `neat` | 30s | Safer, more aligned stacks |
| `balanced` | 15s | Default mix (day-to-day) |
| `custom` | 30s | Start from equal weights; set your own |

Override any weight with `--weight-utilization`, `--weight-face-fill`, `--weight-contact`, `--weight-support`, `--weight-neatness`, `--weight-waste`. Override time with `--time-limit`.

### Orientations

On the shelf face, a placement uses a rectangle of size `(addX × addY)`. Depending on how you rotate the box:

| Tag in output | Meaning (approx.) |
|---------------|-------------------|
| `-flat-len` | Flat; item width along shelf length |
| `-flat-wid` | Flat; item length along shelf length |
| `-upright-len` | Upright (stackable only) |
| `-upright-width` | Upright, alternate axis (stackable only) |

Non-stackable games only use the **flat** orientations (same as V4).

### Support rules

- Boxes on the floor (`y ≈ 0`) are always considered supported.
- A stacked box needs at least **`--min-support-ratio`** (default `0.5`) of its footprint resting on tops of boxes within **`--support-tolerance`** (default `1.0` unit) of its bottom.
- Non-stackable boxes do not contribute support (you cannot stack on them).

---

## Running Shelfer V5

### Default run

```bash
python3 shelfer_V5.py
```

Uses `items.txt`, `bins.txt`, writes `output.txt`, profile `balanced`.

### Custom paths

```bash
python3 shelfer_V5.py \
  -i my_collection/items.txt \
  -b my_collection/bins.txt \
  -o my_collection/layout.txt
```

### Profiles and weights

```bash
python3 shelfer_V5.py --profile fit --time-limit 60 -q
python3 shelfer_V5.py --profile neat --weight-neatness 5 --weight-support 4 -q
python3 shelfer_V5.py --profile custom --weight-face-fill 3 --weight-waste 2 --time-limit 20 -q
python3 shelfer_V5.py --compare-profiles -q
python3 shelfer_V5.py --profile fit --workers 4 --time-limit 20 -q
```

### Quiet vs verbose

```bash
python3 shelfer_V5.py -q
python3 shelfer_V5.py -v
python3 shelfer_V5.py -q --detail
```

### Fail CI / scripts if anything is left out

```bash
python3 shelfer_V5.py -q --strict
echo $?   # 1 if any item unplaced, 0 if all fit
```

### Tune packing knobs

```bash
python3 shelfer_V5.py --grid-step 0.5 -q
python3 shelfer_V5.py --min-support-ratio 0.75 -q
python3 shelfer_V5.py --no-compact -q
```

### Pack and preview in one step

```bash
python3 run_shelfer_and_view.py
python3 run_shelfer_and_view.py --profile dense -q
```

Any arguments after the script name are passed through to `shelfer_V5.py`.

> **Note:** The p5 sketch always loads **`output.txt`** by name. If you pass `-o other.txt`, packing will write that file, but the browser preview still expects `output.txt`. Prefer the default name when visualizing, or copy/rename afterward.

---

## CLI reference

```text
python3 shelfer_V5.py [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-i`, `--items` | `items.txt` | Games input file |
| `-b`, `--bins` | `bins.txt` | Shelves / bins input file |
| `-o`, `--output` | `output.txt` | Placement output file |
| `--profile` | `balanced` | `quick`, `fit`, `dense`, `neat`, `balanced`, `custom` |
| `--time-limit` | profile default | Search budget in seconds |
| `--seed` | `0` | RNG seed for multi-start / local search |
| `--workers` | auto | Parallel process workers (`0`=CPU count up to 8, `1`=sequential) |
| `--weight-*` | profile | Override soft weights (`utilization`, `face-fill`, `contact`, `support`, `neatness`, `waste`) |
| `--lex-soft-only` | off | Soft score may outweigh placed count |
| `--compare-profiles` | off | Run quick/fit/dense/neat/balanced; write the best |
| `--grid-step` | `0.1` | Horizontal position search step |
| `--support-tolerance` | `1.0` | Max height gap between a box bottom and supporter tops |
| `--min-support-ratio` | `0.5` | Minimum supported fraction of a stacked footprint |
| `--no-compact` | off | Skip leftward compaction |
| `-v`, `--verbose` | off | Log search progress |
| `-q`, `--quiet` | off | Suppress progress; print summary only |
| `--detail` | off | Include per-item coordinates in the terminal summary |
| `--strict` | off | Exit status `1` if any item remains unplaced |
| `-h`, `--help` | — | Show help |

`-q` and `-v` cannot be combined.

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | Success (with `--strict`, also means everything placed) |
| `1` | `--strict` and at least one unplaced item |
| `2` | Bad args / missing input / nothing loaded |

---

## Output format

`output.txt` is plain text, consumed by `sketch.js` and easy to parse yourself.

### Structure

```text
#BinName,length,height,width
GameName-orientation-tag,x1,y1,x2,y2
GameName-orientation-tag,x1,y1,x2,y2
#NextBin,...
...
```

- A line starting with `#` introduces a **bin** and its outer dimensions.
- Following lines are **placements** until the next `#` bin header.
- Each placement rectangle is axis-aligned: lower-left `(x1, y1)` to upper-right `(x2, y2)` on the shelf face, origin at the bottom-left of the compartment.
- The game name is followed by an orientation tag such as `-flat-len` or `-upright-width`.

### Example

```text
#Box_1_2,33.5,33.5,42.0
Castles of Burgundy + builds-flat-len,0,0,27.0,23.5
Evolution: Climate-flat-len,0.0,23.5,29.7,32.8
Oracle of Delphi-upright-len,27.0,0,32.6,22.6
#Box_1_1,33.5,33.5,42.0
Rising Sun-flat-len,0,0,32.5,28.0
```

### Parsing tips

- Split on commas.
- Strip a leading `#` from bin headers.
- Orientation tags are the suffix after the last structural hyphens in the name field (e.g. `…-flat-len`). Prefer matching known tags (`-flat-len`, `-flat-wid`, `-upright-len`, `-upright-width`) rather than splitting on every `-`, because game titles may contain hyphens.

---

## Reading the summary

V5 prints a block like:

```text
========== SUMMARY ==========
Profile:      balanced
Placed:       52/55 (94.5%)
Elapsed:      15.02s
Utilization:  50.1% of shelf volume
Soft score:   0.7123
Soft breakdown: utilization=0.501×1.5, face_fill=0.702×1.5, ...
Search:       12 construction(s), 40/800 local moves, construct 6.2s / search 8.8s

Bins:
  Box_1_2                 3 game(s)  util  75.7%  remaining vol 11468.0
  ...

Unplaced (3):
  - Mage Knight (35.6×12.7×35.6)
  ...
==============================
```

| Field | Meaning |
|-------|---------|
| **Profile** | Which optimization profile ran |
| **Placed** | How many games received a valid rectangle |
| **Utilization** | Sum of placed box volumes ÷ sum of bin capacities |
| **Soft score** | Weighted combination of soft components (0–1 scale) |
| **Soft breakdown** | Per-component value × weight (for tuning) |
| **Search** | Constructions tried and local moves accepted/tried |
| **util %** (per bin) | How full that compartment is by volume |
| **remaining vol** | Unused capacity in that bin (same units³ as input) |
| **Unplaced** | Games that never found a legal spot (too large, no support, crowded, etc.) |

Low utilization with many unplaced games often means **geometry**, not “empty space”: leftover volume may be the wrong shape for the remaining boxes.

---

## Visualization

### Local preview (recommended)

```bash
python3 run_shelfer_and_view.py
# or with V5 flags:
python3 run_shelfer_and_view.py --profile neat -q
```

What happens:

1. Runs `shelfer_V5.py` (forwarding your flags).
2. Checks that the output file exists.
3. Starts a local HTTP server on port **8765** (or the next free port).
4. Opens `http://127.0.0.1:<port>/index.html` in your default browser.
5. Waits until you press **Enter** (or Ctrl-C) to stop the server.

Why HTTP? Browsers often block `loadStrings('output.txt')` for pages opened as `file://`. Serving the project folder avoids that. p5.js is loaded from `p5_libs/p5.js`, so **no internet** is required after you have the repo.

### PNG exports

When the sketch runs, it draws one canvas per bin and triggers downloads of PNGs named after each bin. **Allow multiple downloads** in the browser if prompted; otherwise you may only get the first image.

### p5.js web editor (optional)

You can paste `output.txt` into the hosted sketch:

https://editor.p5js.org/cbrt-mihai/sketches/k6b2igNEu

Tips:

- Avoid a trailing blank line at the end of the paste.
- For very long outputs, paste in chunks of roughly 40–60 lines and run the sketch per chunk if the editor struggles.

### Preview without re-packing

If `output.txt` already exists and you only want to view it:

```bash
python3 -m http.server 8765
# then open http://127.0.0.1:8765/index.html
```

(Or run `run_shelfer_and_view.py`, which will re-pack first.)

---

## Older script versions

| Script | Use when |
|--------|----------|
| `shelfer_V5.py` | Day-to-day packing, profiles, visualization helper |
| `shelfer_V4.py` | Greedy baseline / A/B comparison |
| `shelfer_V3_4.py` | Comparing behavior with the pre-CLI structured version |
| `shelfer_V3.py` | Historical / baseline only |

V3.4 / V3 have **no argparse**. Paths are set at the bottom of the file:

```python
pathOutput = "output.txt"
pathItems = "items.txt"
pathBins = "bins.txt"
```

```bash
python3 shelfer_V4.py -q
python3 shelfer_V3_4.py
python3 shelfer_V3.py
```

Physical packing rules in V5 match V4; V5 mainly improves **search**, **profiles**, and **soft objectives**.

---

## Tips and troubleshooting

**A game is always unplaced**

- Check that at least one orientation fits: every bin must be large enough in length, height, **and** depth for some rotation.
- Non-stackable items cannot sit on others and only use flat orientations — they need floor space.
- Try `--profile fit --time-limit 60` or a finer `--grid-step` (e.g. `0.05`).

**Many gaps in the preview**

- Try `--profile dense` or raise `--weight-face-fill` / `--weight-waste`.
- Compaction is on by default; ensure you did not pass `--no-compact`.
- For wide display shelves, name bins with an `Above…` prefix if you want relaxed compaction.

**Stacks look messy**

- Try `--profile neat` or raise `--weight-neatness` and `--weight-support`.

**Preview is blank or fails to load data**

- Use `run_shelfer_and_view.py` or another HTTP server; do not open `index.html` as a local file.
- Confirm `output.txt` exists in the project root and is not empty.
- Confirm `p5_libs/p5.js` is present.

**Names with commas**

- Item/bin names must not contain commas (the format is CSV-like). Use spaces or other punctuation instead.

**Script is slow**

- Use `--profile quick` for a fast pass, or lower `--time-limit`.
- Use `--workers 0` (default) to parallelize multi-start + local-search restarts across CPU cores; `--workers 1` forces sequential.
- Large collections × many bins × small `--grid-step` increases search cost.
- Use `-q` to reduce console I/O, or raise `--grid-step` slightly.

**Want automation**

```bash
python3 shelfer_V5.py -q --strict -o build/layout.txt || echo "Does not fit"
```

---

## Scope and limitations

- V5 is a **heuristic optimizer** (multi-start + local search), not an exhaustive solver. Seed, time limit, and profile change results.
- Depth (`width`) is checked for fit and volume, but the drawn layout is **2D** (length × height).
- Stacking uses a **support-ratio** model, not full 3D physics or friction.
- Results are a planning aid; always sanity-check against real furniture and box condition.
- Some collections simply need larger bins or fewer games — the unplaced list is the signal.

---

## License / contribution

This repository is a personal utility for arranging a board-game collection. Feel free to adapt the scripts to your shelves; when changing packing rules, keep the `output.txt` format stable if you still want the p5 sketch to work.
