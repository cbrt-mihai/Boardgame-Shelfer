#!/usr/bin/env python3
"""
Boardgame Shelfer V4 — pack games onto physical shelves.

Improvements over V3.4:
  - argparse CLI (paths, packing knobs, verbosity, strategy)
  - Config object instead of mutating globals
  - Placement search separated from mutation (quiet dry-run best-fit)
  - Unified stackable / non-stackable packing loop
  - Clear progress + end-of-run summary (fit rate, utilization, unplaced)
  - Optional dual-strategy comparison (--strategy best)
  - Compatible output format for sketch.js / run_shelfer_and_view.py
"""
from __future__ import annotations

import argparse
import copy
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from utils import do_overlap

Rect = List[List[float]]  # [[x1, y1], [x2, y2]]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


class Point:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


def _round1(value: float) -> float:
    return float(f"{value:.1f}")


def create_rect(a: Point, b: Point) -> Rect:
    return [[a.x, a.y], [_round1(b.x), _round1(b.y)]]


def rects_overlap(a: Rect, b: Rect) -> bool:
    l1 = Point(a[0][0], a[1][1])
    r1 = Point(a[1][0], a[0][1])
    l2 = Point(b[0][0], b[1][1])
    r2 = Point(b[1][0], b[0][1])
    return do_overlap(l1, r1, l2, r2)


def vertical_overlap_amount(a: Rect, b: Rect) -> Tuple[float, float]:
    """Return (x_overlap, y_overlap) extents; positive means intersection."""
    x_overlap = min(a[1][0], b[1][0]) - max(a[0][0], b[0][0])
    y_overlap = min(a[1][1], b[1][1]) - max(a[0][1], b[0][1])
    return x_overlap, y_overlap


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Item:
    name: str
    length: float
    height: float
    width: float
    volume: float
    stackable: bool = True


@dataclass
class Bin:
    name: str
    length: float
    height: float
    width: float
    volume: float
    remaining_volume: float = 0.0
    games: List[str] = field(default_factory=list)
    locations: List[Rect] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.remaining_volume == 0.0:
            self.remaining_volume = self.volume

    @property
    def used_volume(self) -> float:
        return max(0.0, self.volume - self.remaining_volume)

    @property
    def utilization(self) -> float:
        if self.volume <= 0:
            return 0.0
        return self.used_volume / self.volume


@dataclass
class PackConfig:
    grid_step: float = 0.1
    support_height_tolerance: float = 1.0
    min_support_ratio: float = 0.5
    fill_large_bins_first: bool = False
    compact: bool = True
    relaxed_bin_prefix: str = "Above"
    vertical_eps: float = 0.5


@dataclass
class PackResult:
    bins: List[Bin]
    unplaced: List[Item]
    placed_count: int
    total_count: int
    elapsed_seconds: float
    strategy: str

    @property
    def fit_rate(self) -> float:
        if self.total_count == 0:
            return 1.0
        return self.placed_count / self.total_count


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_items(path: Path) -> Tuple[List[Item], List[Item]]:
    items: List[Item] = []
    non_stackable: List[Item] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            row = raw.strip()
            if not row or row.startswith("#"):
                continue

            parts = [p.strip() for p in row.split(",")]
            if len(parts) < 4:
                print(f"Warning: {path}:{line_no}: missing dimensions — skipped.", file=sys.stderr)
                continue

            name = parts[0]
            try:
                length = float(parts[1])
                height = float(parts[2])
                width = float(parts[3])
            except ValueError:
                print(f"Warning: {path}:{line_no}: invalid numbers for '{name}' — skipped.", file=sys.stderr)
                continue

            if length <= 0 or height <= 0 or width <= 0:
                print(f"Warning: {path}:{line_no}: non-positive dimensions for '{name}' — skipped.", file=sys.stderr)
                continue

            # A 5th field (commonly "X") marks the game as non-stackable.
            stackable = len(parts) == 4

            vol = _round1(length * height * width)
            item = Item(name=name, length=length, height=height, width=width, volume=vol, stackable=stackable)
            if stackable:
                items.append(item)
            else:
                non_stackable.append(item)

    return items, non_stackable


def load_bins(path: Path) -> List[Bin]:
    bins: List[Bin] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            row = raw.strip()
            if not row or row.startswith("#"):
                continue

            parts = [p.strip() for p in row.split(",")]
            if len(parts) < 4:
                print(f"Warning: {path}:{line_no}: missing dimensions — skipped.", file=sys.stderr)
                continue

            name = parts[0]
            try:
                length = float(parts[1])
                height = float(parts[2])
                width = float(parts[3])
            except ValueError:
                print(f"Warning: {path}:{line_no}: invalid numbers for '{name}' — skipped.", file=sys.stderr)
                continue

            if length <= 0 or height <= 0 or width <= 0:
                print(f"Warning: {path}:{line_no}: non-positive dimensions for '{name}' — skipped.", file=sys.stderr)
                continue

            vol = _round1(length * height * width)
            bins.append(Bin(name=name, length=length, height=height, width=width, volume=vol))

    return bins


def write_bins(path: Path, bins: Sequence[Bin]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for b in bins:
            handle.write(f"#{b.name},{b.length},{b.height},{b.width}\n")
            for game, loc in zip(b.games, b.locations):
                handle.write(
                    f"{game},{loc[0][0]},{loc[0][1]},{loc[1][0]},{loc[1][1]}\n"
                )


def print_bin_detail(bins: Sequence[Bin]) -> None:
    for b in bins:
        print(f"{b.name}, [{b.length},{b.height},{b.width}]")
        for game, loc in zip(b.games, b.locations):
            print(f"  {game}, [{loc[0][0]}, {loc[0][1]}], [{loc[1][0]}, {loc[1][1]}]")
        print()


# ---------------------------------------------------------------------------
# Support / validity
# ---------------------------------------------------------------------------


def is_non_stackable_name(name: str, non_stackable: Sequence[Item]) -> bool:
    base = name.split("-")[0]
    return any(ns.name == base for ns in non_stackable)


def compute_support_ratio(
    rect: Rect,
    locations: Sequence[Rect],
    games: Sequence[str],
    non_stackable: Sequence[Item],
    height_tolerance: float,
) -> float:
    """Fraction of rect's footprint supported by boxes whose tops meet its bottom."""
    x1, y1 = rect[0]
    x2, _y2 = rect[1]

    if abs(y1) < 1e-6:
        return 1.0

    intervals: List[List[float]] = []
    for idx, other in enumerate(locations):
        other_name = games[idx].split("-")[0]
        ox1, _oy1 = other[0]
        ox2, oy2 = other[1]

        if abs(oy2 - y1) > height_tolerance:
            continue
        if is_non_stackable_name(other_name, non_stackable):
            continue

        sx1 = max(x1, ox1)
        sx2 = min(x2, ox2)
        if sx1 < sx2:
            intervals.append([sx1, sx2])

    if not intervals:
        return 0.0

    intervals.sort(key=lambda seg: seg[0])
    merged: List[Tuple[float, float]] = []
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))

    supported = sum(end - start for start, end in merged)
    return supported / max(1e-6, x2 - x1)


def placement_is_valid(
    rect: Rect,
    container: Bin,
    non_stackable: Sequence[Item],
    config: PackConfig,
) -> bool:
    if rect[0][0] < 0 or rect[0][1] < 0:
        return False
    if rect[1][0] > container.length + 1e-6 or rect[1][1] > container.height + 1e-6:
        return False

    for other in container.locations:
        if rects_overlap(rect, other):
            return False

    if rect[0][1] > 0.0:
        ratio = compute_support_ratio(
            rect,
            container.locations,
            container.games,
            non_stackable,
            config.support_height_tolerance,
        )
        if ratio < config.min_support_ratio:
            return False

    return True


def assert_bins_valid(bins: Sequence[Bin], config: PackConfig) -> None:
    for b in bins:
        relaxed = b.name.startswith(config.relaxed_bin_prefix)
        for idx, rect in enumerate(b.locations):
            x1, y1 = rect[0]
            x2, y2 = rect[1]
            assert 0.0 <= x1 <= x2 <= b.length + 1e-6, f"{b.name}: bounds X for {b.games[idx]}"
            assert 0.0 <= y1 <= y2 <= b.height + 1e-6, f"{b.name}: bounds Y for {b.games[idx]}"

            for jdx, other in enumerate(b.locations):
                if jdx == idx:
                    continue
                if relaxed:
                    x_ov, y_ov = vertical_overlap_amount(rect, other)
                    assert not (x_ov > 0 and y_ov > config.vertical_eps), (
                        f"{b.name}: overlap {b.games[idx]} vs {b.games[jdx]}"
                    )
                else:
                    assert not rects_overlap(rect, other), (
                        f"{b.name}: overlap {b.games[idx]} vs {b.games[jdx]}"
                    )


# ---------------------------------------------------------------------------
# Placement search
# ---------------------------------------------------------------------------


def candidate_orientations(
    item: Item,
    bin_obj: Bin,
    *,
    stackable_pass: bool,
) -> List[Tuple[float, float, str, str]]:
    """Return (addX, addY, orientation_label, tag) that geometrically fit the bin."""
    length, height, width = item.length, item.height, item.width
    max_l, max_h, max_w = bin_obj.length, bin_obj.height, bin_obj.width
    out: List[Tuple[float, float, str, str]] = []

    # Flat orientations (always considered)
    if length <= max_w and width <= max_l and height <= max_h:
        out.append((width, height, "flat by length", "-flat-len"))
    if width <= max_w and length <= max_l and height <= max_h:
        out.append((length, height, "flat by width", "-flat-wid"))

    # Upright only for stackable packing pass (matches V3.4)
    if stackable_pass:
        if length <= max_w and width <= max_h and height <= max_l:
            out.append((height, width, "upright by length", "-upright-len"))
        if width <= max_w and length <= max_h and height <= max_l:
            out.append((height, length, "upright by width", "-upright-width"))

    return out


def _anchor_points(where: str, entry: Rect, add_x: float, add_y: float) -> Tuple[Point, Point]:
    if where == "r":
        x1, y1 = entry[1][0], entry[0][1]
    else:
        x1, y1 = entry[0][0], entry[1][1]
    return Point(x1, y1), Point(x1 + add_x, y1 + add_y)


def _candidate_x_offsets(container: Bin, add_x: float, config: PackConfig) -> List[float]:
    candidates = set()
    x = 0.0
    while x <= container.length - add_x + 1e-9:
        candidates.add(_round1(x))
        x += config.grid_step

    for other in container.locations:
        ox1, ox2 = other[0][0], other[1][0]
        candidates.add(_round1(ox1))
        candidates.add(_round1(max(0.0, ox2 - add_x)))

    return sorted(candidates)


def find_placement(
    item: Item,
    container: Bin,
    add_x: float,
    add_y: float,
    non_stackable: Sequence[Item],
    config: PackConfig,
) -> Optional[Rect]:
    """
    Find a valid rectangle for the item inside container without mutating state.
    Returns None if no valid spot exists.
    """
    if not container.locations:
        return create_rect(Point(0, 0), Point(add_x, add_y))

    # Non-stackable prefer "up" then "right"; stackable prefer right then up
    priority = ["u", "r"] if not item.stackable else ["r", "u"]

    for mod in priority:
        for entry in container.locations:
            base_st, base_nd = _anchor_points(mod, entry, add_x, add_y)

            for xo in _candidate_x_offsets(container, add_x, config):
                st = Point(base_st.x + xo, base_st.y)
                nd = Point(base_nd.x + xo, base_nd.y)
                if nd.x > container.length + 1e-6 or nd.y > container.height + 1e-6:
                    continue
                rect = create_rect(st, nd)
                if placement_is_valid(rect, container, non_stackable, config):
                    return rect

    return None


def commit_placement(
    item: Item,
    container: Bin,
    rect: Rect,
    tag: str,
    unplaced: List[Item],
) -> None:
    container.games.append(item.name + tag)
    container.locations.append(rect)
    container.remaining_volume = _round1(container.remaining_volume - item.volume)
    for i, remaining in enumerate(unplaced):
        if remaining.name == item.name:
            unplaced.pop(i)
            break


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


def compact_bins(bins: Sequence[Bin], non_stackable: Sequence[Item], config: PackConfig) -> None:
    for b in bins:
        ignore_support = b.name.startswith(config.relaxed_bin_prefix)
        moved = True
        while moved:
            moved = False
            for idx, rect in enumerate(b.locations):
                x1, y1 = rect[0]
                x2, y2 = rect[1]
                width = x2 - x1
                if width <= 0:
                    continue

                while True:
                    candidate_x1 = max(0.0, x1 - config.grid_step)
                    candidate_x2 = candidate_x1 + width
                    if abs(candidate_x1 - x1) < 1e-6:
                        break

                    candidate = [[candidate_x1, y1], [candidate_x2, y2]]

                    has_overlap = False
                    for jdx, other in enumerate(b.locations):
                        if jdx == idx:
                            continue
                        x_ov, y_ov = vertical_overlap_amount(candidate, other)
                        if x_ov > 0 and y_ov > config.vertical_eps:
                            has_overlap = True
                            break
                    if has_overlap:
                        break

                    if (not ignore_support) and candidate[0][1] > 0.0:
                        ratio = compute_support_ratio(
                            candidate,
                            b.locations,
                            b.games,
                            non_stackable,
                            config.support_height_tolerance,
                        )
                        if ratio < config.min_support_ratio:
                            break

                    if not ignore_support:
                        candidate_top = candidate[1][1]
                        temp_locations = list(b.locations)
                        temp_locations[idx] = candidate
                        upper_unsafe = False
                        for jdx, upper in enumerate(b.locations):
                            if jdx == idx:
                                continue
                            ux1, uy1 = upper[0]
                            ux2, _uy2 = upper[1]
                            if uy1 <= candidate_top:
                                continue
                            if abs(uy1 - candidate_top) > config.support_height_tolerance:
                                continue
                            if ux2 <= candidate[0][0] or ux1 >= candidate[1][0]:
                                continue
                            if uy1 > 0.0:
                                upper_support = compute_support_ratio(
                                    upper,
                                    temp_locations,
                                    b.games,
                                    non_stackable,
                                    config.support_height_tolerance,
                                )
                                if upper_support < config.min_support_ratio:
                                    upper_unsafe = True
                                    break
                        if upper_unsafe:
                            break

                    x1, x2 = candidate_x1, candidate_x2
                    b.locations[idx] = [[x1, y1], [x2, y2]]
                    moved = True


# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------


def _sort_bins(bins: List[Bin], large_first: bool) -> None:
    bins.sort(key=lambda b: b.remaining_volume, reverse=large_first)


def _place_one_item(
    item: Item,
    bins: List[Bin],
    unplaced: List[Item],
    non_stackable: Sequence[Item],
    config: PackConfig,
    *,
    stackable_pass: bool,
    verbose: bool,
) -> bool:
    _sort_bins(bins, config.fill_large_bins_first)

    candidates: List[Tuple[float, int, Rect, str]] = []
    for b_idx, bin_obj in enumerate(bins):
        for add_x, add_y, _label, tag in candidate_orientations(
            item, bin_obj, stackable_pass=stackable_pass
        ):
            rect = find_placement(item, bin_obj, add_x, add_y, non_stackable, config)
            if rect is not None:
                leftover = bin_obj.remaining_volume - item.volume
                candidates.append((leftover, b_idx, rect, tag))

    if not candidates:
        return False

    candidates.sort(key=lambda c: c[0])
    _leftover, chosen_idx, rect, tag = candidates[0]
    chosen = bins[chosen_idx]
    commit_placement(item, chosen, rect, tag, unplaced)
    if verbose:
        print(f"  + {item.name}{tag} -> {chosen.name} @ {rect}")
    return True


def pack_items(
    stackable: List[Item],
    non_stackable: List[Item],
    bins: List[Bin],
    config: PackConfig,
    *,
    verbose: bool = False,
    quiet: bool = False,
) -> PackResult:
    start = time.perf_counter()
    all_items = stackable + non_stackable
    total = len(all_items)
    placed = 0

    def run_pass(source: List[Item], *, stackable_pass: bool, label: str) -> List[Item]:
        nonlocal placed
        ordered = sorted(source, key=lambda it: it.volume, reverse=True)
        unplaced = list(ordered)
        working = list(ordered)
        pass_start = time.perf_counter()

        if not quiet:
            print(f"\n--- {label}: {len(working)} item(s) ---")

        for i, item in enumerate(working, start=1):
            if item not in unplaced:
                continue

            if not quiet and (verbose or i == 1 or i % 5 == 0 or i == len(working)):
                elapsed = time.perf_counter() - pass_start
                print(f"[{i}/{len(working)}] {item.name}  ({elapsed:.1f}s)")

            ok = _place_one_item(
                item,
                bins,
                unplaced,
                non_stackable,
                config,
                stackable_pass=stackable_pass,
                verbose=verbose,
            )
            if ok:
                placed += 1
            elif not quiet:
                print(f"  ! could not place {item.name}")

        return unplaced

    left_stackable = run_pass(stackable, stackable_pass=True, label="Stackable")
    left_non = run_pass(non_stackable, stackable_pass=False, label="Non-stackable")

    if config.compact:
        if not quiet:
            print("\nCompacting bins…")
        compact_bins(bins, non_stackable, config)

    assert_bins_valid(bins, config)

    elapsed = time.perf_counter() - start
    strategy = "large-bins-first" if config.fill_large_bins_first else "small-bins-first"
    return PackResult(
        bins=bins,
        unplaced=left_stackable + left_non,
        placed_count=placed,
        total_count=total,
        elapsed_seconds=elapsed,
        strategy=strategy,
    )


def score_result(result: PackResult) -> Tuple[int, float]:
    """Higher is better: more placed, then more volume used."""
    used = sum(b.used_volume for b in result.bins)
    return result.placed_count, used


def print_summary(result: PackResult, *, show_detail: bool = False) -> None:
    print("\n========== SUMMARY ==========")
    print(f"Strategy:     {result.strategy}")
    print(f"Placed:       {result.placed_count}/{result.total_count} ({100 * result.fit_rate:.1f}%)")
    print(f"Elapsed:      {result.elapsed_seconds:.2f}s")

    total_cap = sum(b.volume for b in result.bins)
    total_used = sum(b.used_volume for b in result.bins)
    util = (100 * total_used / total_cap) if total_cap else 0.0
    print(f"Utilization:  {util:.1f}% of shelf volume")

    print("\nBins:")
    for b in result.bins:
        n = len(b.games)
        print(
            f"  {b.name:20s}  {n:3d} game(s)  "
            f"util {100 * b.utilization:5.1f}%  "
            f"remaining vol {b.remaining_volume:.1f}"
        )

    if result.unplaced:
        print(f"\nUnplaced ({len(result.unplaced)}):")
        for item in result.unplaced:
            flag = "" if item.stackable else " [non-stackable]"
            print(f"  - {item.name} ({item.length}×{item.height}×{item.width}){flag}")
    else:
        print("\nAll items placed.")

    if show_detail:
        print("\n--- Placement detail ---")
        print_bin_detail(result.bins)

    print("==============================\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pack board games onto shelves (Shelfer V4).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-i", "--items", type=Path, default=Path("items.txt"), help="Items input file")
    p.add_argument("-b", "--bins", type=Path, default=Path("bins.txt"), help="Bins / shelves input file")
    p.add_argument("-o", "--output", type=Path, default=Path("output.txt"), help="Placement output file")
    p.add_argument(
        "--strategy",
        choices=("small", "large", "best"),
        default="small",
        help="Bin fill order: small-first, large-first, or try both and keep the better fit",
    )
    p.add_argument("--grid-step", type=float, default=0.1, help="Horizontal search grid step")
    p.add_argument(
        "--support-tolerance",
        type=float,
        default=1.0,
        help="Max height gap between stacked box bottoms/tops",
    )
    p.add_argument(
        "--min-support-ratio",
        type=float,
        default=0.5,
        help="Minimum supported fraction of a stacked footprint",
    )
    p.add_argument("--no-compact", action="store_true", help="Skip leftward compaction pass")
    p.add_argument("-v", "--verbose", action="store_true", help="Print each successful placement")
    p.add_argument("-q", "--quiet", action="store_true", help="Only print the final summary")
    p.add_argument("--detail", action="store_true", help="Include per-item coordinates in the summary")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 if any item could not be placed",
    )
    return p


def run_strategy(
    stackable: List[Item],
    non_stackable: List[Item],
    bins_template: List[Bin],
    config: PackConfig,
    *,
    verbose: bool,
    quiet: bool,
) -> PackResult:
    return pack_items(
        copy.deepcopy(stackable),
        copy.deepcopy(non_stackable),
        copy.deepcopy(bins_template),
        config,
        verbose=verbose,
        quiet=quiet,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.quiet and args.verbose:
        print("Choose at most one of --quiet / --verbose.", file=sys.stderr)
        return 2

    for label, path in (("items", args.items), ("bins", args.bins)):
        if not path.is_file():
            print(f"Error: {label} file not found: {path}", file=sys.stderr)
            return 2

    stackable, non_stackable = load_items(args.items)
    bins = load_bins(args.bins)

    if not stackable and not non_stackable:
        print("Error: no items loaded.", file=sys.stderr)
        return 2
    if not bins:
        print("Error: no bins loaded.", file=sys.stderr)
        return 2

    if not args.quiet:
        print(
            f"Loaded {len(stackable)} stackable + {len(non_stackable)} non-stackable "
            f"item(s) into {len(bins)} bin(s)."
        )

    base_kwargs = dict(
        grid_step=args.grid_step,
        support_height_tolerance=args.support_tolerance,
        min_support_ratio=args.min_support_ratio,
        compact=not args.no_compact,
    )

    if args.strategy == "best":
        if not args.quiet:
            print("\nTrying strategy: small-bins-first")
        cfg_small = PackConfig(fill_large_bins_first=False, **base_kwargs)
        res_small = run_strategy(
            stackable, non_stackable, bins, cfg_small, verbose=args.verbose, quiet=args.quiet
        )

        if not args.quiet:
            print("\nTrying strategy: large-bins-first")
        cfg_large = PackConfig(fill_large_bins_first=True, **base_kwargs)
        res_large = run_strategy(
            stackable, non_stackable, bins, cfg_large, verbose=args.verbose, quiet=args.quiet
        )

        result = res_small if score_result(res_small) >= score_result(res_large) else res_large
        if not args.quiet:
            print(
                f"\nKept strategy '{result.strategy}' "
                f"({result.placed_count}/{result.total_count} placed)."
            )
    else:
        large_first = args.strategy == "large"
        config = PackConfig(fill_large_bins_first=large_first, **base_kwargs)
        if not args.quiet:
            label = "large-bins-first" if large_first else "small-bins-first"
            print(f"\nRunning strategy: {label}")
        result = run_strategy(
            stackable, non_stackable, bins, config, verbose=args.verbose, quiet=args.quiet
        )

    write_bins(args.output, result.bins)
    if not args.quiet:
        print(f"Wrote placements to {args.output}")

    print_summary(result, show_detail=args.detail)

    if args.strict and result.unplaced:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
