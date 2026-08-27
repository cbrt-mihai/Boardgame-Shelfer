#!/usr/bin/env python3
"""
Boardgame Shelfer V5 — multi-objective packing.

Same physical rules and output.txt format as V4, but replaces the single
greedy pass with multi-start construction + local search driven by
user-selectable profiles (quick / fit / dense / neat / balanced / custom)
and soft score weights.
"""
from __future__ import annotations

import argparse
import copy
import math
import os
import random
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from utils import do_overlap, Point, Item, Bin, Rect


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


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
    x_overlap = min(a[1][0], b[1][0]) - max(a[0][0], b[0][0])
    y_overlap = min(a[1][1], b[1][1]) - max(a[0][1], b[0][1])
    return x_overlap, y_overlap


def rect_area(rect: Rect) -> float:
    return max(0.0, rect[1][0] - rect[0][0]) * max(0.0, rect[1][1] - rect[0][1])


def shared_edge_length(a: Rect, b: Rect) -> float:
    """Length of shared boundary (touching edges), 0 if separated or overlapping interior."""
    ax1, ay1 = a[0]
    ax2, ay2 = a[1]
    bx1, by1 = b[0]
    bx2, by2 = b[1]
    # Vertical shared edge (same x)
    shared = 0.0
    y_lo = max(ay1, by1)
    y_hi = min(ay2, by2)
    if y_hi > y_lo:
        if abs(ax2 - bx1) < 1e-6 or abs(ax1 - bx2) < 1e-6:
            shared += y_hi - y_lo
    # Horizontal shared edge (same y)
    x_lo = max(ax1, bx1)
    x_hi = min(ax2, bx2)
    if x_hi > x_lo:
        if abs(ay2 - by1) < 1e-6 or abs(ay1 - by2) < 1e-6:
            shared += x_hi - x_lo
    return shared


SOFT_KEYS = (
    "utilization",
    "face_fill",
    "contact",
    "support",
    "neatness",
    "waste",
)


@dataclass
class SoftWeights:
    utilization: float = 1.0
    face_fill: float = 1.0
    contact: float = 1.0
    support: float = 1.0
    neatness: float = 1.0
    waste: float = 1.0

    def as_dict(self) -> Dict[str, float]:
        return {k: getattr(self, k) for k in SOFT_KEYS}

    def total(self) -> float:
        return sum(self.as_dict().values())


@dataclass
class SoftBreakdown:
    utilization: float = 0.0
    face_fill: float = 0.0
    contact: float = 0.0
    support: float = 0.0
    neatness: float = 0.0
    waste: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {k: getattr(self, k) for k in SOFT_KEYS}


@dataclass
class PackConfig:
    grid_step: float = 0.1
    support_height_tolerance: float = 1.0
    min_support_ratio: float = 0.5
    compact: bool = True
    relaxed_bin_prefix: str = "Above"
    vertical_eps: float = 0.5
    # Search / objective
    profile: str = "balanced"
    time_limit: float = 15.0
    seed: int = 0
    weights: SoftWeights = field(default_factory=SoftWeights)
    lex_soft_only: bool = False
    # Placement search caps
    max_position_candidates: int = 40
    quick_mode: bool = False
    # Parallelism (process pool; 1 = sequential)
    workers: int = 1


@dataclass
class PackStats:
    constructions: int = 0
    local_moves_accepted: int = 0
    local_moves_tried: int = 0
    time_construct: float = 0.0
    time_search: float = 0.0
    workers: int = 1


@dataclass
class PackResult:
    bins: List[Bin]
    unplaced: List[Item]
    placed_count: int
    total_count: int
    elapsed_seconds: float
    profile: str
    weights: SoftWeights
    soft: SoftBreakdown
    soft_score: float
    stats: PackStats = field(default_factory=PackStats)

    @property
    def fit_rate(self) -> float:
        if self.total_count == 0:
            return 1.0
        return self.placed_count / self.total_count


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


PROFILE_DEFAULTS: Dict[str, Dict] = {
    "quick": {
        "time_limit": 0.0,
        "weights": SoftWeights(utilization=1.0, face_fill=0.0, contact=0.0, support=0.0, neatness=0.0, waste=0.0),
        "quick_mode": True,
        "max_position_candidates": 1,
    },
    "fit": {
        "time_limit": 30.0,
        "weights": SoftWeights(utilization=0.2, face_fill=0.2, contact=0.1, support=0.1, neatness=0.0, waste=0.1),
        "quick_mode": False,
        "max_position_candidates": 24,
    },
    "dense": {
        "time_limit": 30.0,
        "weights": SoftWeights(utilization=3.0, face_fill=3.0, contact=2.0, support=0.5, neatness=0.3, waste=2.5),
        "quick_mode": False,
        "max_position_candidates": 40,
    },
    "neat": {
        "time_limit": 30.0,
        "weights": SoftWeights(utilization=1.0, face_fill=1.0, contact=1.0, support=3.0, neatness=3.5, waste=0.8),
        "quick_mode": False,
        "max_position_candidates": 40,
    },
    "balanced": {
        "time_limit": 15.0,
        "weights": SoftWeights(utilization=1.5, face_fill=1.5, contact=1.0, support=1.2, neatness=1.2, waste=1.0),
        "quick_mode": False,
        "max_position_candidates": 32,
    },
    "custom": {
        "time_limit": 30.0,
        "weights": SoftWeights(utilization=1.0, face_fill=1.0, contact=1.0, support=1.0, neatness=1.0, waste=1.0),
        "quick_mode": False,
        "max_position_candidates": 32,
    },
}


def resolve_profile(
    profile: str,
    *,
    time_limit: Optional[float],
    seed: int,
    weight_overrides: Dict[str, Optional[float]],
    lex_soft_only: bool,
    pack_kwargs: Dict,
    workers: int = 1,
) -> PackConfig:
    if profile not in PROFILE_DEFAULTS:
        raise ValueError(f"Unknown profile: {profile}")
    base = PROFILE_DEFAULTS[profile]
    weights = copy.deepcopy(base["weights"])
    for key, val in weight_overrides.items():
        if val is not None:
            setattr(weights, key, float(val))

    limit = float(base["time_limit"]) if time_limit is None else float(time_limit)
    quick = bool(base["quick_mode"])
    # Quick is a single pass — parallelism adds overhead only.
    resolved_workers = 1 if quick else max(1, int(workers))
    return PackConfig(
        grid_step=pack_kwargs["grid_step"],
        support_height_tolerance=pack_kwargs["support_height_tolerance"],
        min_support_ratio=pack_kwargs["min_support_ratio"],
        compact=pack_kwargs["compact"],
        profile=profile,
        time_limit=limit,
        seed=seed,
        weights=weights,
        lex_soft_only=lex_soft_only,
        max_position_candidates=int(base["max_position_candidates"]),
        quick_mode=quick,
        workers=resolved_workers,
    )


def default_worker_count() -> int:
    cpu = os.cpu_count() or 4
    return max(1, min(cpu, 8))


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
# Soft scoring
# ---------------------------------------------------------------------------


def _skyline_fragmentation(bin_obj: Bin) -> float:
    """
    Rough empty-skyline fragmentation in [0, 1]: more jagged tops → higher.
    """
    if not bin_obj.locations:
        return 0.0

    # Sample columns and record max occupied y
    step = max(0.5, bin_obj.length / 40.0)
    heights: List[float] = []
    x = 0.0
    while x < bin_obj.length - 1e-9:
        top = 0.0
        for rect in bin_obj.locations:
            if rect[0][0] - 1e-6 <= x < rect[1][0] + 1e-6:
                top = max(top, rect[1][1])
        heights.append(top)
        x += step

    if len(heights) < 2:
        return 0.0

    changes = sum(1 for i in range(1, len(heights)) if abs(heights[i] - heights[i - 1]) > 0.5)
    # Also penalize unused height variance relative to capacity
    mean_h = sum(heights) / len(heights)
    var = sum((h - mean_h) ** 2 for h in heights) / len(heights)
    jagged = changes / max(1, len(heights) - 1)
    spread = min(1.0, math.sqrt(var) / max(1e-6, bin_obj.height))
    return min(1.0, 0.6 * jagged + 0.4 * spread)


def compute_soft_breakdown(
    bins: Sequence[Bin],
    non_stackable: Sequence[Item],
    config: PackConfig,
) -> SoftBreakdown:
    total_vol = sum(b.volume for b in bins) or 1.0
    used_vol = sum(b.used_volume for b in bins)
    utilization = used_vol / total_vol

    total_face = sum(b.face_area for b in bins) or 1.0
    used_face = sum(rect_area(r) for b in bins for r in b.locations)
    face_fill = min(1.0, used_face / total_face)

    # Contact: shared edges / possible perimeter scale
    contact_len = 0.0
    perimeter = 0.0
    for b in bins:
        locs = b.locations
        for rect in locs:
            w = rect[1][0] - rect[0][0]
            h = rect[1][1] - rect[0][1]
            perimeter += 2.0 * (w + h)
        for i in range(len(locs)):
            for j in range(i + 1, len(locs)):
                contact_len += shared_edge_length(locs[i], locs[j])
        # Floor contact
        for rect in locs:
            if abs(rect[0][1]) < 1e-6:
                contact_len += rect[1][0] - rect[0][0]
            if abs(rect[0][0]) < 1e-6:
                contact_len += rect[1][1] - rect[0][1]
    contact = min(1.0, (2.0 * contact_len) / max(1e-6, perimeter)) if perimeter > 0 else 0.0

    # Mean support of stacked boxes
    support_vals: List[float] = []
    for b in bins:
        for idx, rect in enumerate(b.locations):
            if rect[0][1] <= 1e-6:
                continue
            ratio = compute_support_ratio(
                rect, b.locations, b.games, non_stackable, config.support_height_tolerance
            )
            support_vals.append(ratio)
    support = sum(support_vals) / len(support_vals) if support_vals else 1.0

    # Neatness: similar tops clustering + left bias
    neat_parts: List[float] = []
    for b in bins:
        if not b.locations:
            continue
        tops = sorted(r[1][1] for r in b.locations)
        # Cluster tops within 1.0 unit
        clusters = 1
        for i in range(1, len(tops)):
            if tops[i] - tops[i - 1] > 1.0:
                clusters += 1
        top_score = 1.0 - (clusters - 1) / max(1, len(tops))
        # Left alignment: fraction of boxes with x1 near 0 or near another right edge
        aligned = 0
        rights = {0.0}
        for r in b.locations:
            rights.add(_round1(r[1][0]))
        for r in b.locations:
            x1 = _round1(r[0][0])
            if any(abs(x1 - edge) < 0.15 for edge in rights):
                aligned += 1
        align_score = aligned / len(b.locations)
        # Prefer lower average bottom for floor-heavy neat stacks
        avg_y = sum(r[0][1] for r in b.locations) / len(b.locations)
        floor_score = 1.0 - min(1.0, avg_y / max(1e-6, b.height))
        neat_parts.append(0.45 * top_score + 0.35 * align_score + 0.20 * floor_score)
    neatness = sum(neat_parts) / len(neat_parts) if neat_parts else 0.0

    # Waste: inverse skyline fragmentation (weighted by bin volume)
    waste_parts: List[Tuple[float, float]] = []
    for b in bins:
        frag = _skyline_fragmentation(b)
        waste_parts.append((1.0 - frag, b.volume))
    waste = (
        sum(v * w for v, w in waste_parts) / sum(w for _, w in waste_parts)
        if waste_parts
        else 0.0
    )

    return SoftBreakdown(
        utilization=utilization,
        face_fill=face_fill,
        contact=contact,
        support=support,
        neatness=neatness,
        waste=waste,
    )


def soft_score_value(breakdown: SoftBreakdown, weights: SoftWeights) -> float:
    total_w = weights.total()
    if total_w <= 1e-12:
        return 0.0
    return sum(getattr(breakdown, k) * getattr(weights, k) for k in SOFT_KEYS) / total_w


def lex_key(
    placed: int,
    soft: float,
    *,
    lex_soft_only: bool,
) -> Tuple[float, float]:
    if lex_soft_only:
        return (soft, float(placed))
    return (float(placed), soft)


def better_lex(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    return a > b


# ---------------------------------------------------------------------------
# Orientations & placement search
# ---------------------------------------------------------------------------


def candidate_orientations(
    item: Item,
    bin_obj: Bin,
    *,
    allow_upright: bool,
) -> List[Tuple[float, float, str]]:
    """Return (addX, addY, tag) that geometrically fit the bin."""
    length, height, width = item.length, item.height, item.width
    max_l, max_h, max_w = bin_obj.length, bin_obj.height, bin_obj.width
    out: List[Tuple[float, float, str]] = []

    if length <= max_w and width <= max_l and height <= max_h:
        out.append((width, height, "-flat-len"))
    if width <= max_w and length <= max_l and height <= max_h:
        out.append((length, height, "-flat-wid"))

    if allow_upright and item.stackable:
        if length <= max_w and width <= max_h and height <= max_l:
            out.append((height, width, "-upright-len"))
        if width <= max_w and length <= max_h and height <= max_l:
            out.append((height, length, "-upright-width"))

    return out


def _anchor_points(where: str, entry: Rect, add_x: float, add_y: float) -> Tuple[Point, Point]:
    if where == "r":
        x1, y1 = entry[1][0], entry[0][1]
    else:
        x1, y1 = entry[0][0], entry[1][1]
    return Point(x1, y1), Point(x1 + add_x, y1 + add_y)


def _candidate_x_offsets(
    container: Bin,
    add_x: float,
    config: PackConfig,
    *,
    coarse: bool = False,
) -> List[float]:
    candidates = set()
    x = 0.0
    if config.quick_mode:
        step = config.grid_step
    elif coarse:
        step = max(config.grid_step, 0.5)
    else:
        step = max(config.grid_step, 0.25)
    while x <= container.length - add_x + 1e-9:
        candidates.add(_round1(x))
        x += step

    for other in container.locations:
        ox1, ox2 = other[0][0], other[1][0]
        candidates.add(_round1(ox1))
        candidates.add(_round1(max(0.0, ox2 - add_x)))

    return sorted(candidates)


def _position_soft_hint(
    rect: Rect,
    container: Bin,
    non_stackable: Sequence[Item],
    config: PackConfig,
    item: Item,
) -> float:
    """Cheap local score for choosing among candidate positions."""
    w = config.weights
    score = 0.0
    # Prefer lower-left (bottom-left bias)
    score += 2.0 * (1.0 - rect[0][1] / max(1e-6, container.height))
    score += 1.0 * (1.0 - rect[0][0] / max(1e-6, container.length))

    if rect[0][1] > 0:
        ratio = compute_support_ratio(
            rect, container.locations, container.games, non_stackable, config.support_height_tolerance
        )
        score += 3.0 * w.support * ratio
    else:
        score += 3.0 * w.support

    # Contact with existing / walls
    contact = 0.0
    if abs(rect[0][1]) < 1e-6:
        contact += rect[1][0] - rect[0][0]
    if abs(rect[0][0]) < 1e-6:
        contact += rect[1][1] - rect[0][1]
    for other in container.locations:
        contact += shared_edge_length(rect, other)
    perim = 2.0 * ((rect[1][0] - rect[0][0]) + (rect[1][1] - rect[0][1]))
    score += 2.0 * w.contact * (contact / max(1e-6, perim))

    # Neatness: align top with existing tops
    if w.neatness > 0 and container.locations:
        top = rect[1][1]
        best_align = min(abs(top - o[1][1]) for o in container.locations)
        score += w.neatness * max(0.0, 1.0 - best_align / max(1.0, container.height * 0.25))

    # Dense: prefer not raising skyline much
    if w.utilization + w.face_fill + w.waste > 0:
        score += (w.utilization + w.face_fill) * (1.0 - rect[1][1] / max(1e-6, container.height))

    # Slight preference to leave less leftover volume (best-fit)
    leftover = container.remaining_volume - item.volume
    score += 0.01 * w.utilization * (1.0 / (1.0 + max(0.0, leftover) / max(1.0, container.volume)))

    return score


def find_all_placements(
    item: Item,
    container: Bin,
    add_x: float,
    add_y: float,
    non_stackable: Sequence[Item],
    config: PackConfig,
    *,
    coarse: bool = False,
) -> List[Rect]:
    """Collect valid placement rectangles (capped)."""
    found: List[Rect] = []
    if not container.locations:
        rect = create_rect(Point(0, 0), Point(add_x, add_y))
        if placement_is_valid(rect, container, non_stackable, config):
            return [rect]
        return []

    priority = ["u", "r"] if not item.stackable else ["r", "u"]
    seen = set()
    x_offsets = _candidate_x_offsets(container, add_x, config, coarse=coarse)
    limit = 8 if coarse else config.max_position_candidates

    def _try_xy(x1: float, y1: float) -> None:
        if len(found) >= limit:
            return
        nd = Point(x1 + add_x, y1 + add_y)
        if nd.x > container.length + 1e-6 or nd.y > container.height + 1e-6:
            return
        if x1 < -1e-6 or y1 < -1e-6:
            return
        key = (_round1(x1), _round1(y1), _round1(nd.x), _round1(nd.y))
        if key in seen:
            return
        seen.add(key)
        rect = create_rect(Point(x1, y1), nd)
        if placement_is_valid(rect, container, non_stackable, config):
            found.append(rect)

    for mod in priority:
        for entry in container.locations:
            base_st, _base_nd = _anchor_points(mod, entry, add_x, add_y)
            y1 = base_st.y
            for x1 in [_round1(base_st.x)] + x_offsets:
                _try_xy(x1, y1)
                if config.quick_mode and found:
                    return found
                if len(found) >= limit:
                    return found

    for x1 in x_offsets:
        _try_xy(x1, 0.0)
        if config.quick_mode and found:
            return found
        if len(found) >= limit:
            break

    return found


def choose_best_placement(
    item: Item,
    container: Bin,
    add_x: float,
    add_y: float,
    non_stackable: Sequence[Item],
    config: PackConfig,
    *,
    coarse: bool = False,
) -> Optional[Rect]:
    candidates = find_all_placements(
        item, container, add_x, add_y, non_stackable, config, coarse=coarse
    )
    if not candidates:
        return None
    if len(candidates) == 1 or config.quick_mode:
        return candidates[0]
    return max(
        candidates,
        key=lambda r: _position_soft_hint(r, container, non_stackable, config, item),
    )


def commit_placement(item: Item, container: Bin, rect: Rect, tag: str) -> None:
    container.games.append(item.name + tag)
    container.locations.append(rect)
    container.remaining_volume = _round1(container.remaining_volume - item.volume)


def find_item_placement(bins: Sequence[Bin], base_name: str) -> Optional[Tuple[int, int]]:
    for b_idx, b in enumerate(bins):
        for i, game in enumerate(b.games):
            if game.split("-")[0] == base_name:
                return b_idx, i
    return None


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
# Construction
# ---------------------------------------------------------------------------


ItemOrderFn = Callable[[List[Item], random.Random], List[Item]]


def _order_volume(items: List[Item], _rng: random.Random) -> List[Item]:
    return sorted(items, key=lambda it: it.volume, reverse=True)


def _order_face(items: List[Item], _rng: random.Random) -> List[Item]:
    return sorted(items, key=lambda it: it.face_area_flat, reverse=True)


def _order_max_side(items: List[Item], _rng: random.Random) -> List[Item]:
    return sorted(items, key=lambda it: (it.max_side, it.volume), reverse=True)


def _order_shuffle(items: List[Item], rng: random.Random) -> List[Item]:
    out = list(items)
    rng.shuffle(out)
    return out


def _order_volume_jitter(items: List[Item], rng: random.Random) -> List[Item]:
    return sorted(items, key=lambda it: it.volume * rng.uniform(0.85, 1.15), reverse=True)


ORDER_FN_BY_NAME: Dict[str, ItemOrderFn] = {
    "volume": _order_volume,
    "face": _order_face,
    "max_side": _order_max_side,
    "jitter": _order_volume_jitter,
    "shuffle": _order_shuffle,
}

ORDER_NAMES = list(ORDER_FN_BY_NAME.keys())


BIN_POLICIES = ("small_first", "large_first", "best_fit", "worst_fit")


def _sort_bins_for_policy(bins: List[Bin], policy: str) -> None:
    if policy == "large_first":
        bins.sort(key=lambda b: b.remaining_volume, reverse=True)
    else:
        bins.sort(key=lambda b: b.remaining_volume, reverse=False)


def _try_place_item(
    item: Item,
    bins: List[Bin],
    non_stackable: Sequence[Item],
    config: PackConfig,
    *,
    allow_upright: bool,
    bin_policy: str,
    coarse: bool = False,
) -> bool:
    _sort_bins_for_policy(bins, bin_policy)

    options: List[Tuple[float, int, Rect, str]] = []
    for b_idx, bin_obj in enumerate(bins):
        for add_x, add_y, tag in candidate_orientations(item, bin_obj, allow_upright=allow_upright):
            rect = choose_best_placement(
                item, bin_obj, add_x, add_y, non_stackable, config, coarse=coarse
            )
            if rect is None:
                continue
            leftover = bin_obj.remaining_volume - item.volume
            hint = _position_soft_hint(rect, bin_obj, non_stackable, config, item)
            if bin_policy == "best_fit":
                rank = leftover
            elif bin_policy == "worst_fit":
                rank = -leftover
            else:
                # Prefer better local soft hint, then tighter leftover
                rank = -hint + 0.0001 * leftover
            options.append((rank, b_idx, rect, tag))

    if not options:
        return False

    options.sort(key=lambda t: t[0])
    _rank, b_idx, rect, tag = options[0]
    commit_placement(item, bins[b_idx], rect, tag)
    return True


def construct_layout(
    stackable: List[Item],
    non_stackable: List[Item],
    bins_template: List[Bin],
    config: PackConfig,
    *,
    order_fn: ItemOrderFn,
    bin_policy: str,
    interleaved: bool,
    rng: random.Random,
    coarse: bool = True,
) -> Tuple[List[Bin], List[Item]]:
    bins = copy.deepcopy(bins_template)
    unplaced: List[Item] = []
    # Fine search for seed constructions; coarse for diverse multi-start speed.
    use_coarse = coarse and (not config.quick_mode)

    if interleaved:
        combined = order_fn(stackable + non_stackable, rng)
        for item in combined:
            allow_up = item.stackable
            ok = _try_place_item(
                item,
                bins,
                non_stackable,
                config,
                allow_upright=allow_up,
                bin_policy=bin_policy,
                coarse=use_coarse,
            )
            if not ok:
                unplaced.append(item)
    else:
        for item in order_fn(stackable, rng):
            ok = _try_place_item(
                item,
                bins,
                non_stackable,
                config,
                allow_upright=True,
                bin_policy=bin_policy,
                coarse=use_coarse,
            )
            if not ok:
                unplaced.append(item)
        for item in order_fn(non_stackable, rng):
            ok = _try_place_item(
                item,
                bins,
                non_stackable,
                config,
                allow_upright=False,
                bin_policy=bin_policy,
                coarse=use_coarse,
            )
            if not ok:
                unplaced.append(item)

    if config.compact:
        compact_bins(bins, non_stackable, config)

    return bins, unplaced


def _item_by_name(all_items: Sequence[Item], name: str) -> Optional[Item]:
    for it in all_items:
        if it.name == name:
            return it
    return None


def _restore_volume(bins: List[Bin], all_items: Sequence[Item]) -> None:
    for b in bins:
        used = 0.0
        for game in b.games:
            base = game.split("-")[0]
            it = _item_by_name(all_items, base)
            if it:
                used += it.volume
        b.remaining_volume = _round1(b.volume - used)


def _placed_items(bins: Sequence[Bin], all_items: Sequence[Item]) -> List[Item]:
    names = {g.split("-")[0] for b in bins for g in b.games}
    return [it for it in all_items if it.name in names]


def evaluate_layout(
    bins: List[Bin],
    unplaced: List[Item],
    all_items: Sequence[Item],
    non_stackable: Sequence[Item],
    config: PackConfig,
) -> Tuple[Tuple[float, float], SoftBreakdown, float]:
    placed = len(all_items) - len(unplaced)
    soft = compute_soft_breakdown(bins, non_stackable, config)
    soft_val = soft_score_value(soft, config.weights)
    key = lex_key(placed, soft_val, lex_soft_only=config.lex_soft_only)
    return key, soft, soft_val


# ---------------------------------------------------------------------------
# Local search
# ---------------------------------------------------------------------------


def _remove_item(bins: List[Bin], item: Item, all_items: Sequence[Item]) -> bool:
    loc = find_item_placement(bins, item.name)
    if loc is None:
        return False
    b_idx, i = loc
    bins[b_idx].games.pop(i)
    bins[b_idx].locations.pop(i)
    _restore_volume(bins, all_items)
    return True


def _try_reinsert(
    item: Item,
    bins: List[Bin],
    non_stackable: Sequence[Item],
    config: PackConfig,
    all_items: Sequence[Item],
    bin_policy: str = "best_fit",
) -> bool:
    allow_up = item.stackable
    ok = _try_place_item(
        item, bins, non_stackable, config, allow_upright=allow_up, bin_policy=bin_policy
    )
    if ok:
        _restore_volume(bins, all_items)
    return ok


def local_search(
    bins: List[Bin],
    unplaced: List[Item],
    stackable: List[Item],
    non_stackable: List[Item],
    config: PackConfig,
    *,
    deadline: float,
    rng: random.Random,
    stats: PackStats,
) -> Tuple[List[Bin], List[Item]]:
    all_items = stackable + non_stackable
    best_bins = copy.deepcopy(bins)
    best_unplaced = list(unplaced)
    best_key, _, best_soft = evaluate_layout(best_bins, best_unplaced, all_items, non_stackable, config)

    current_bins = copy.deepcopy(best_bins)
    current_unplaced = list(best_unplaced)
    current_key = best_key
    current_soft = best_soft

    # Mild annealing on soft score when placed count ties
    temperature = 0.05
    cooling = 0.995

    while time.perf_counter() < deadline:
        stats.local_moves_tried += 1
        op = rng.choice(["relocate", "relocate", "reorient", "swap", "ruin", "place_unplaced"])

        trial_bins = copy.deepcopy(current_bins)
        trial_unplaced = list(current_unplaced)
        changed = False

        if op == "place_unplaced" and trial_unplaced:
            item = rng.choice(trial_unplaced)
            if _try_reinsert(item, trial_bins, non_stackable, config, all_items):
                trial_unplaced = [u for u in trial_unplaced if u.name != item.name]
                changed = True

        elif op == "relocate":
            placed = _placed_items(trial_bins, all_items)
            if not placed:
                continue
            item = rng.choice(placed)
            if _remove_item(trial_bins, item, all_items):
                # Try reinsert elsewhere; if fail, leave unplaced
                if _try_reinsert(item, trial_bins, non_stackable, config, all_items, bin_policy=rng.choice(list(BIN_POLICIES))):
                    changed = True
                else:
                    trial_unplaced.append(item)
                    changed = True

        elif op == "reorient":
            placed = _placed_items(trial_bins, all_items)
            if not placed:
                continue
            item = rng.choice(placed)
            loc = find_item_placement(trial_bins, item.name)
            if loc is None:
                continue
            b_idx, i = loc
            old_game = trial_bins[b_idx].games[i]
            old_tag = old_game[len(item.name) :]
            _remove_item(trial_bins, item, all_items)
            # Force different orientation by trying all and picking different tag if possible
            allow_up = item.stackable
            placed_ok = False
            options: List[Tuple[float, int, Rect, str]] = []
            for bi, bin_obj in enumerate(trial_bins):
                for add_x, add_y, tag in candidate_orientations(item, bin_obj, allow_upright=allow_up):
                    if tag == old_tag and bi == b_idx:
                        continue
                    rect = choose_best_placement(item, bin_obj, add_x, add_y, non_stackable, config)
                    if rect is None:
                        continue
                    hint = _position_soft_hint(rect, bin_obj, non_stackable, config, item)
                    options.append((-hint, bi, rect, tag))
            if options:
                options.sort(key=lambda t: t[0])
                _, bi, rect, tag = options[0]
                commit_placement(item, trial_bins[bi], rect, tag)
                _restore_volume(trial_bins, all_items)
                placed_ok = True
                changed = True
            if not placed_ok:
                # restore original by reinsert any
                if not _try_reinsert(item, trial_bins, non_stackable, config, all_items):
                    trial_unplaced.append(item)
                changed = True

        elif op == "swap":
            placed = _placed_items(trial_bins, all_items)
            if len(placed) < 2:
                continue
            a, b = rng.sample(placed, 2)
            if not _remove_item(trial_bins, a, all_items):
                continue
            if not _remove_item(trial_bins, b, all_items):
                _try_reinsert(a, trial_bins, non_stackable, config, all_items)
                continue
            ok_a = _try_reinsert(a, trial_bins, non_stackable, config, all_items)
            ok_b = _try_reinsert(b, trial_bins, non_stackable, config, all_items)
            if ok_a and ok_b:
                changed = True
            else:
                # rollback by clearing and restoring from current
                trial_bins = copy.deepcopy(current_bins)
                trial_unplaced = list(current_unplaced)

        elif op == "ruin":
            placed = _placed_items(trial_bins, all_items)
            if not placed:
                continue
            n_remove = min(len(placed), rng.randint(2, max(2, min(6, len(placed)))))
            victims = rng.sample(placed, n_remove)
            # Or empty one random non-empty bin
            if rng.random() < 0.4:
                nonempty = [bi for bi, bb in enumerate(trial_bins) if bb.games]
                if nonempty:
                    bi = rng.choice(nonempty)
                    names = [g.split("-")[0] for g in trial_bins[bi].games]
                    victims = [it for it in placed if it.name in names]

            removed: List[Item] = []
            for item in victims:
                if _remove_item(trial_bins, item, all_items):
                    removed.append(item)
            order = _order_volume_jitter(removed, rng)
            still: List[Item] = []
            policy = rng.choice(list(BIN_POLICIES))
            for item in order:
                if not _try_reinsert(item, trial_bins, non_stackable, config, all_items, bin_policy=policy):
                    still.append(item)
            trial_unplaced.extend(still)
            if config.compact:
                compact_bins(trial_bins, non_stackable, config)
            changed = True

        if not changed:
            continue

        # Deduplicate unplaced by name
        seen_u = set()
        deduped: List[Item] = []
        for u in trial_unplaced:
            if u.name not in seen_u:
                seen_u.add(u.name)
                deduped.append(u)
        trial_unplaced = deduped

        trial_key, trial_breakdown, trial_soft = evaluate_layout(
            trial_bins, trial_unplaced, all_items, non_stackable, config
        )

        accept = False
        if better_lex(trial_key, current_key):
            accept = True
        elif (
            abs(trial_key[0] - current_key[0]) < 1e-12
            and trial_soft < current_soft
            and config.profile in ("neat", "dense", "balanced", "custom", "fit")
        ):
            # Annealing: sometimes accept soft regression (same placed)
            delta = current_soft - trial_soft
            if temperature > 1e-6 and rng.random() < math.exp(-delta / temperature):
                accept = True

        if accept:
            stats.local_moves_accepted += 1
            current_bins = trial_bins
            current_unplaced = trial_unplaced
            current_key = trial_key
            current_soft = trial_soft
            if better_lex(current_key, best_key):
                best_bins = copy.deepcopy(current_bins)
                best_unplaced = list(current_unplaced)
                best_key = current_key
                best_soft = current_soft

        temperature *= cooling

    return best_bins, best_unplaced


# ---------------------------------------------------------------------------
# Parallel workers (process pool — picklable top-level callables)
# ---------------------------------------------------------------------------


def _construction_job(
    payload: Tuple,
) -> Tuple[List[Bin], List[Item], Tuple[float, float], SoftBreakdown, float]:
    (
        stackable,
        non_stackable,
        bins_template,
        config,
        order_name,
        policy,
        interleaved,
        coarse,
        seed,
    ) = payload
    rng = random.Random(seed)
    order_fn = ORDER_FN_BY_NAME[order_name]
    bins, unplaced = construct_layout(
        stackable,
        non_stackable,
        bins_template,
        config,
        order_fn=order_fn,
        bin_policy=policy,
        interleaved=interleaved,
        rng=rng,
        coarse=coarse,
    )
    all_items = stackable + non_stackable
    key, soft_bd, soft_val = evaluate_layout(bins, unplaced, all_items, non_stackable, config)
    return bins, unplaced, key, soft_bd, soft_val


def _local_search_job(
    payload: Tuple,
) -> Tuple[List[Bin], List[Item], int, int, Tuple[float, float], SoftBreakdown, float]:
    (
        bins,
        unplaced,
        stackable,
        non_stackable,
        config,
        duration,
        seed,
    ) = payload
    stats = PackStats()
    rng = random.Random(seed)
    deadline = time.perf_counter() + max(0.05, duration)
    out_bins, out_unplaced = local_search(
        bins,
        unplaced,
        stackable,
        non_stackable,
        config,
        deadline=deadline,
        rng=rng,
        stats=stats,
    )
    if config.compact:
        compact_bins(out_bins, non_stackable, config)
    all_items = stackable + non_stackable
    key, soft_bd, soft_val = evaluate_layout(
        out_bins, out_unplaced, all_items, non_stackable, config
    )
    return (
        out_bins,
        out_unplaced,
        stats.local_moves_tried,
        stats.local_moves_accepted,
        key,
        soft_bd,
        soft_val,
    )


# ---------------------------------------------------------------------------
# Top-level pack
# ---------------------------------------------------------------------------


def pack_items(
    stackable: List[Item],
    non_stackable: List[Item],
    bins_template: List[Bin],
    config: PackConfig,
    *,
    verbose: bool = False,
    quiet: bool = False,
) -> PackResult:
    start = time.perf_counter()
    deadline = start + max(0.0, config.time_limit)
    rng = random.Random(config.seed)
    stats = PackStats(workers=config.workers)
    all_items = stackable + non_stackable
    total = len(all_items)
    workers = max(1, config.workers)

    policies = list(BIN_POLICIES)
    interleave_flags = [False] if config.profile != "fit" else [False, True]

    best_bins: Optional[List[Bin]] = None
    best_unplaced: List[Item] = []
    best_key: Tuple[float, float] = (-1.0, -1.0)
    best_soft_bd = SoftBreakdown()
    best_soft_val = -1.0

    construct_deadline = start + (0.0 if config.quick_mode else max(0.0, config.time_limit) * 0.45)

    if not quiet:
        print(
            f"\n--- Constructing layouts (profile={config.profile}, "
            f"time_limit={config.time_limit:.1f}s, workers={workers}) ---"
        )

    # (order_name, policy, interleaved, coarse)
    constructions_plan: List[Tuple[str, str, bool, bool]] = [
        ("volume", "small_first", False, False),
        ("volume", "large_first", False, False),
        ("volume", "best_fit", False, False),
    ]
    if not config.quick_mode:
        for _ in range(40):
            constructions_plan.append(
                (
                    rng.choice(ORDER_NAMES),
                    rng.choice(policies),
                    rng.choice(interleave_flags),
                    True,
                )
            )

    def _consider(
        bins: List[Bin],
        unplaced: List[Item],
        key: Tuple[float, float],
        soft_bd: SoftBreakdown,
        soft_val: float,
    ) -> None:
        nonlocal best_bins, best_unplaced, best_key, best_soft_bd, best_soft_val
        stats.constructions += 1
        if better_lex(key, best_key):
            best_bins = bins
            best_unplaced = unplaced
            best_key = key
            best_soft_bd = soft_bd
            best_soft_val = soft_val
            if verbose:
                placed_part = int(key[0]) if not config.lex_soft_only else int(key[1])
                print(
                    f"  new best construction #{stats.constructions}: "
                    f"placed={placed_part} soft={soft_val:.4f}"
                )

    t_construct_start = time.perf_counter()

    if config.quick_mode or workers == 1:
        for order_name, policy, interleaved, coarse in constructions_plan:
            if (
                stats.constructions > 0
                and not config.quick_mode
                and time.perf_counter() >= construct_deadline
            ):
                break
            bins, unplaced, key, soft_bd, soft_val = _construction_job(
                (
                    stackable,
                    non_stackable,
                    bins_template,
                    config,
                    order_name,
                    policy,
                    interleaved,
                    coarse,
                    rng.randint(0, 2**31 - 1),
                )
            )
            _consider(bins, unplaced, key, soft_bd, soft_val)
            if config.quick_mode:
                break
    else:
        job_idx = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            in_flight = {}
            while job_idx < len(constructions_plan) and len(in_flight) < workers:
                if stats.constructions > 0 and time.perf_counter() >= construct_deadline:
                    break
                order_name, policy, interleaved, coarse = constructions_plan[job_idx]
                fut = pool.submit(
                    _construction_job,
                    (
                        stackable,
                        non_stackable,
                        bins_template,
                        config,
                        order_name,
                        policy,
                        interleaved,
                        coarse,
                        config.seed + 1000 + job_idx,
                    ),
                )
                in_flight[fut] = job_idx
                job_idx += 1

            while in_flight:
                done, _pending = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                for fut in done:
                    del in_flight[fut]
                    bins, unplaced, key, soft_bd, soft_val = fut.result()
                    _consider(bins, unplaced, key, soft_bd, soft_val)

                past_deadline = time.perf_counter() >= construct_deadline
                while (
                    not past_deadline
                    and job_idx < len(constructions_plan)
                    and len(in_flight) < workers
                ):
                    order_name, policy, interleaved, coarse = constructions_plan[job_idx]
                    fut = pool.submit(
                        _construction_job,
                        (
                            stackable,
                            non_stackable,
                            bins_template,
                            config,
                            order_name,
                            policy,
                            interleaved,
                            coarse,
                            config.seed + 1000 + job_idx,
                        ),
                    )
                    in_flight[fut] = job_idx
                    job_idx += 1
                    past_deadline = time.perf_counter() >= construct_deadline

    stats.time_construct = time.perf_counter() - t_construct_start

    if best_bins is None:
        best_bins = copy.deepcopy(bins_template)
        best_unplaced = list(all_items)

    # Local search with remaining time (parallel restarts when workers > 1)
    if not config.quick_mode and time.perf_counter() < deadline:
        remaining = max(0.0, deadline - time.perf_counter())
        if not quiet:
            print(f"--- Local search ({remaining:.1f}s remaining, workers={workers}) ---")
        t_search_start = time.perf_counter()

        if workers == 1:
            best_bins, best_unplaced = local_search(
                best_bins,
                best_unplaced,
                stackable,
                non_stackable,
                config,
                deadline=deadline,
                rng=rng,
                stats=stats,
            )
            if config.compact:
                compact_bins(best_bins, non_stackable, config)
            best_key, best_soft_bd, best_soft_val = evaluate_layout(
                best_bins, best_unplaced, all_items, non_stackable, config
            )
        else:
            # Each worker gets the same wall-clock budget and a different seed.
            duration = remaining
            payloads = [
                (
                    copy.deepcopy(best_bins),
                    list(best_unplaced),
                    stackable,
                    non_stackable,
                    config,
                    duration,
                    config.seed + 5000 + w,
                )
                for w in range(workers)
            ]
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(_local_search_job, payloads))
            for (
                out_bins,
                out_unplaced,
                tried,
                accepted,
                key,
                soft_bd,
                soft_val,
            ) in results:
                stats.local_moves_tried += tried
                stats.local_moves_accepted += accepted
                if better_lex(key, best_key):
                    best_bins = out_bins
                    best_unplaced = out_unplaced
                    best_key = key
                    best_soft_bd = soft_bd
                    best_soft_val = soft_val

        stats.time_search = time.perf_counter() - t_search_start

    assert_bins_valid(best_bins, config)

    placed = total - len(best_unplaced)
    elapsed = time.perf_counter() - start
    return PackResult(
        bins=best_bins,
        unplaced=best_unplaced,
        placed_count=placed,
        total_count=total,
        elapsed_seconds=elapsed,
        profile=config.profile,
        weights=config.weights,
        soft=best_soft_bd,
        soft_score=best_soft_val,
        stats=stats,
    )


def score_result_tuple(result: PackResult) -> Tuple[float, float, float]:
    """Neutral ranking for --compare-profiles (soft weights differ per profile)."""
    total_cap = sum(b.volume for b in result.bins) or 1.0
    util = sum(b.used_volume for b in result.bins) / total_cap
    total_face = sum(b.face_area for b in result.bins) or 1.0
    face = sum(rect_area(r) for b in result.bins for r in b.locations) / total_face
    return (float(result.placed_count), util, face)


def print_summary(result: PackResult, *, show_detail: bool = False) -> None:
    print("\n========== SUMMARY ==========")
    print(f"Profile:      {result.profile}")
    print(f"Placed:       {result.placed_count}/{result.total_count} ({100 * result.fit_rate:.1f}%)")
    print(f"Elapsed:      {result.elapsed_seconds:.2f}s")

    total_cap = sum(b.volume for b in result.bins)
    total_used = sum(b.used_volume for b in result.bins)
    util = (100 * total_used / total_cap) if total_cap else 0.0
    print(f"Utilization:  {util:.1f}% of shelf volume")
    print(f"Soft score:   {result.soft_score:.4f}")

    bd = result.soft.as_dict()
    w = result.weights.as_dict()
    parts = [f"{k}={bd[k]:.3f}×{w[k]:g}" for k in SOFT_KEYS]
    print("Soft breakdown: " + ", ".join(parts))

    print(
        f"Search:       {result.stats.constructions} construction(s), "
        f"{result.stats.local_moves_accepted}/{result.stats.local_moves_tried} local moves, "
        f"{result.stats.workers} worker(s), "
        f"construct {result.stats.time_construct:.2f}s / search {result.stats.time_search:.2f}s"
    )

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
        description="Pack board games onto shelves (Shelfer V5 — multi-objective).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-i", "--items", type=Path, default=Path("items.txt"), help="Items input file")
    p.add_argument("-b", "--bins", type=Path, default=Path("bins.txt"), help="Bins / shelves input file")
    p.add_argument("-o", "--output", type=Path, default=Path("output.txt"), help="Placement output file")
    p.add_argument(
        "--profile",
        choices=("quick", "fit", "dense", "neat", "balanced", "custom"),
        default="balanced",
        help="Optimization profile",
    )
    p.add_argument(
        "--time-limit",
        type=float,
        default=None,
        help="Search time budget in seconds (overrides profile default)",
    )
    p.add_argument("--seed", type=int, default=0, help="RNG seed for multi-start / local search")
    p.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Parallel process workers (0=auto from CPU count, 1=sequential)",
    )
    p.add_argument("--weight-utilization", type=float, default=None, help="Override utilization weight")
    p.add_argument("--weight-face-fill", type=float, default=None, help="Override face_fill weight")
    p.add_argument("--weight-contact", type=float, default=None, help="Override contact weight")
    p.add_argument("--weight-support", type=float, default=None, help="Override support weight")
    p.add_argument("--weight-neatness", type=float, default=None, help="Override neatness weight")
    p.add_argument("--weight-waste", type=float, default=None, help="Override waste weight")
    p.add_argument(
        "--lex-soft-only",
        action="store_true",
        help="Allow soft goals to outweigh placed count (off by default)",
    )
    p.add_argument(
        "--compare-profiles",
        action="store_true",
        help="Run quick+fit+dense+neat+balanced, print comparison, write the best",
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
    p.add_argument("-v", "--verbose", action="store_true", help="Print search progress")
    p.add_argument("-q", "--quiet", action="store_true", help="Only print the final summary")
    p.add_argument("--detail", action="store_true", help="Include per-item coordinates in the summary")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 if any item could not be placed",
    )
    return p


def run_with_config(
    stackable: List[Item],
    non_stackable: List[Item],
    bins: List[Bin],
    config: PackConfig,
    *,
    verbose: bool,
    quiet: bool,
) -> PackResult:
    return pack_items(
        copy.deepcopy(stackable),
        copy.deepcopy(non_stackable),
        copy.deepcopy(bins),
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

    pack_kwargs = dict(
        grid_step=args.grid_step,
        support_height_tolerance=args.support_tolerance,
        min_support_ratio=args.min_support_ratio,
        compact=not args.no_compact,
    )
    weight_overrides = {
        "utilization": args.weight_utilization,
        "face_fill": args.weight_face_fill,
        "contact": args.weight_contact,
        "support": args.weight_support,
        "neatness": args.weight_neatness,
        "waste": args.weight_waste,
    }

    if args.workers < 0:
        print("Error: --workers must be >= 0.", file=sys.stderr)
        return 2
    workers = default_worker_count() if args.workers == 0 else args.workers

    if args.compare_profiles:
        profiles = ("quick", "fit", "dense", "neat", "balanced")
        results: List[PackResult] = []
        for prof in profiles:
            if not args.quiet:
                print(f"\n######## Profile: {prof} ########")
            cfg = resolve_profile(
                prof,
                time_limit=args.time_limit,
                seed=args.seed,
                weight_overrides=weight_overrides,
                lex_soft_only=args.lex_soft_only,
                pack_kwargs=pack_kwargs,
                workers=workers,
            )
            # Keep compare runs bounded if user did not set time-limit
            if args.time_limit is None and prof != "quick":
                cfg.time_limit = min(cfg.time_limit, 20.0)
            res = run_with_config(
                stackable, non_stackable, bins, cfg, verbose=args.verbose, quiet=args.quiet
            )
            results.append(res)
            if not args.quiet:
                print_summary(res, show_detail=False)

        print("\n========== PROFILE COMPARISON ==========")
        print(f"{'profile':10s}  {'placed':8s}  {'util%':7s}  {'soft':8s}  {'time':7s}")
        for res in results:
            total_cap = sum(b.volume for b in res.bins) or 1.0
            util = 100.0 * sum(b.used_volume for b in res.bins) / total_cap
            print(
                f"{res.profile:10s}  {res.placed_count:3d}/{res.total_count:<3d}  "
                f"{util:6.1f}  {res.soft_score:7.4f}  {res.elapsed_seconds:6.2f}s"
            )
        print("========================================\n")

        result = max(results, key=score_result_tuple)
        if not args.quiet:
            print(f"Kept profile '{result.profile}' ({result.placed_count}/{result.total_count} placed).")
    else:
        config = resolve_profile(
            args.profile,
            time_limit=args.time_limit,
            seed=args.seed,
            weight_overrides=weight_overrides,
            lex_soft_only=args.lex_soft_only,
            pack_kwargs=pack_kwargs,
            workers=workers,
        )
        if not args.quiet:
            print(
                f"\nRunning profile: {config.profile} "
                f"(time_limit={config.time_limit:.1f}s, seed={config.seed}, "
                f"workers={config.workers})"
            )
            w = config.weights.as_dict()
            print("Weights: " + ", ".join(f"{k}={v:g}" for k, v in w.items()))
        result = run_with_config(
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
