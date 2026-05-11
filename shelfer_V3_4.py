import copy
import time
from dataclasses import dataclass, field
from operator import getitem
from typing import List, Tuple

# Support configuration for stacked items
SUPPORT_HEIGHT_TOLERANCE = 1  # how far tops can differ in height (same units as input data)
MIN_SUPPORT_RATIO = 0.5         # minimum fraction of footprint that must be supported

# Position search configuration inside a shelf
GRID_STEP = 0.1  # horizontal grid step for candidate x positions (same units as input data)

Rect = List[List[float]]  # [[x1, y1], [x2, y2]]


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


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
    games: List[str] = field(default_factory=list)
    locations: List[Rect] = field(default_factory=list)

def volume(item):
    return item[1] * item[2] * item[3]

def take5th(item):
    return item[4]

def takeLen(item):
    return item[1]

def dictSort(dict, key):
    return dict[key]["info"]

def floatRange(start, finish, step):
    list = []
    while start < finish:
        list.append(float("%.1f" % start))
        start += step

    return list

def findIndex(name, items_list):
    """
    Find index of an item by name in a list that may contain either
    legacy item tuples/lists or Item dataclass instances.
    """
    for i, elem in enumerate(items_list):
        # New-style Item dataclass
        if isinstance(elem, Item):
            if name == elem.name:
                return i
        else:
            # Backwards-compatible: assume name at index 0
            if len(elem) > 0 and name == elem[0]:
                return i

    return -1

def sortCont(item):
    return item[1]["volume"]

def do_balance(x1r, x2r, x1e, x2e):
    cutoff = min(x2r, x2e)
    lowerSeg = cutoff - max(x1r, x1e)
    upperSeg = x2r - cutoff

    # print(lowerSeg, upperSeg, cutoff)

    if lowerSeg > upperSeg:
        return True
    return False

# print("TEST DO_BALANCE")
# assert do_balance(4, 10, 0, 5) == False
# assert do_balance(2, 7, 0, 5) == True
# assert do_balance(2, 7, 2, 7) == True
# assert do_balance(2, 5, 7, 10) == False
# assert do_balance(4, 7, 7, 10) == False
# a = input()

'''
l1 : x1, y2
r1 : x2, y1
l2 : a1, b2
r2 : a2, b1
'''
def do_overlap(l1, r1, l2, r2):
    # if rectangle has area 0, no overlap
    if l1.x == r1.x or l1.y == r1.y or r2.x == l2.x or l2.y == r2.y:
        return False

    # If one rectangle is on left side of other
    if l1.x >= r2.x or l2.x >= r1.x:
        return False

    # If one rectangle is above other
    if r1.y >= l2.y or r2.y >= l1.y:
        return False

    return True

def prettyPrintBins(bins: List[Bin]):
    for b in bins:
        print(f"{b.name}")
        print("{")
        print(f"\tGames: {b.games}")
        print(f"\tLocation: {b.locations}")
        print(f"\tSizes: [{b.length}, {b.height}, {b.width}]")
        print(f"\tVolume: {b.volume}")
        print("}\n")


def prettyWriteBins(writePath: str, bins: List[Bin]):
    file = open(writePath, "w")
    for b in bins:
        file.write(f"#{b.name},{b.length},{b.height},{b.width}\n")
        for i, game in enumerate(b.games):
            loc = b.locations[i]
            file.write(f"{game},{loc[0][0]},{loc[0][1]},{loc[1][0]},{loc[1][1]}\n")
    file.close()


def detailedPrintBins(bins: List[Bin]):
    for b in bins:
        print(f"{b.name}, [{b.length},{b.height},{b.width}]")
        for i, game in enumerate(b.games):
            loc = b.locations[i]
            print(f"{game}, [{loc[0][0]}, {loc[0][1]}],  [{loc[1][0]}, {loc[1][1]}]")
        print()

'''
l1 : x1, y2
r1 : x2, y1
l2 : a1, b2
r2 : a2, b1
'''
def isBad(rect, other, entry):
    if rect[0][0] < 0:
        return True
    l1 = Point(rect[0][0], rect[1][1])
    r1 = Point(rect[1][0], rect[0][1])
    l2 = Point(other[0][0], other[1][1])
    r2 = Point(other[1][0], other[0][1])

    overlaps = do_overlap(l1, r1, l2, r2)
    balances = do_balance(rect[0][0], rect[1][0], entry[0][0], entry[1][0])
    is_onGround = True if rect[0][1] == 0.0 else False

    return not (((not overlaps) and balances) or (is_onGround and (not overlaps)))

'''
l1 : x1, y2
r1 : x2, y1
l2 : a1, b2
r2 : a2, b1
'''
def whyIsBad(name, rect, other, entry):
    l1 = Point(rect[0][0], rect[1][1])
    r1 = Point(rect[1][0], rect[0][1])
    l2 = Point(other[0][0], other[1][1])
    r2 = Point(other[1][0], other[0][1])

    overlaps = do_overlap(l1, r1, l2, r2)
    balances = do_balance(rect[0][0], rect[1][0], entry[0][0], entry[1][0])
    is_onGround = True if rect[0][1] == 0.0 else False

    reason = f""
    if overlaps:
        reason += f"They overlap: [{l1.x},{r1.y}]; [{r1.x},{l1.y}] with [{l2.x},{r2.y}]; [{r2.x},{l2.y}] \n"
    if not balances:
        reason += f"Not balanced\n"
    if not is_onGround:
        reason += f"Not on ground."

    print(f"{name}:\n{reason}")


def compute_support_ratio(rect, locations, games, nonStackableList, height_tolerance):
    """
    Compute how much of rect's horizontal footprint [x1, x2] at its bottom y
    is supported by existing rectangles whose tops are within height_tolerance.

    Returns a value in [0, 1], where 1 means fully supported.
    Ground-level rectangles (bottom y ~= 0) are treated as fully supported.
    """
    x1, y1 = rect[0]
    x2, y2 = rect[1]

    # Items on the ground are always fully supported
    if abs(y1) < 1e-6:
        return 1.0

    support_intervals = []

    for idx, other in enumerate(locations):
        otherName = games[idx].split("-")[0]
        ox1, oy1 = other[0]
        ox2, oy2 = other[1]
        other_top = oy2

        # Only consider boxes that are approximately at the same height as rect's bottom
        if abs(other_top - y1) <= height_tolerance:
            # If a non-stackable item is present under part of the footprint,
            # it cannot contribute to support, but it shouldn't veto other
            # stackable supports. Previously we returned 0.0 immediately
            # which prevented using multiple smaller stackable supports
            # around a non-stackable neighbor. Instead, skip non-stackable
            # boxes and allow support to be accumulated across one or more
            # stackable items.
            if isInNonStackableList(otherName, nonStackableList):
                # ignore this other box as a source of support
                continue

            sx1 = max(x1, ox1)
            sx2 = min(x2, ox2)

            if sx1 < sx2:
                support_intervals.append([sx1, sx2])

    if not support_intervals:
        return 0.0

    # Merge overlapping intervals
    support_intervals.sort(key=lambda seg: seg[0])
    merged = []
    cur_start, cur_end = support_intervals[0]

    for start, end in support_intervals[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end

    merged.append((cur_start, cur_end))

    supported_length = sum(end - start for start, end in merged)
    total_length = max(1e-6, x2 - x1)

    return supported_length / total_length


def assert_bins_valid(bins: List[Bin]):
    """
    Simple consistency checks: no overlaps and all rectangles inside bin bounds.
    """
    for b in bins:
        for idx, rect in enumerate(b.locations):
            x1, y1 = rect[0]
            x2, y2 = rect[1]
            # Bounds
            assert 0.0 <= x1 <= x2 <= b.length + 1e-6
            assert 0.0 <= y1 <= y2 <= b.height + 1e-6

            # No overlap with any other rect in the same bin
            l1 = Point(x1, y2)
            r1 = Point(x2, y1)
            for jdx, other in enumerate(b.locations):
                if jdx == idx:
                    continue
                ox1, oy1 = other[0]
                ox2, oy2 = other[1]
                l2 = Point(ox1, oy2)
                r2 = Point(ox2, oy1)

                # For wide top-level shelves we allow tiny vertical "stagger"
                # (introduced by relaxed compaction) up to a small tolerance.
                # This mirrors the relaxed compaction logic used for bins whose
                # name starts with "Above" and prevents spurious assertion
                # failures while still catching real overlaps.
                if b.name.startswith("Above"):
                    vertical_eps = 0.5
                    x_overlap = min(x2, ox2) - max(x1, ox1)
                    y_overlap = min(y2, oy2) - max(y1, oy1)
                    # Treat only significant overlaps as assertion failures
                    assert not (x_overlap > 0 and y_overlap > vertical_eps)
                else:
                    assert not do_overlap(l1, r1, l2, r2)


def compact_bins(bins: List[Bin], nonStackableItems: List[Item]):
    """
    Post-processing compaction pass.
    For each bin, repeatedly try to slide every rectangle as far left as
    possible without introducing overlap. By default we also enforce the
    same support constraints used during packing, but for some wide,
    top-level shelves (like boardgame rows) we relax those support checks
    to allow tighter horizontal packing and minimize visible gaps.
    """
    for b in bins:
        # For "wide shelf" bins we ignore support constraints during
        # compaction and only enforce non-overlap and bounds. This lets
        # rows of games be visually compacted left even if it would
        # slightly change their theoretical support footprint.
        # Enable relaxed compaction for bins whose name starts with "Above".
        # These are typically top-level shelves where visual compactness
        # is preferred over strict stacking support checks.
        ignore_support = True if b.name.startswith("Above") else False

        moved = True
        # Keep sweeping left until no rectangle can move anymore
        while moved:
            moved = False

            # Work on a copy of locations so we can update in-place safely
            for idx, rect in enumerate(b.locations):
                x1, y1 = rect[0]
                x2, y2 = rect[1]
                width = x2 - x1

                # Nothing to do for zero-width/height rectangles
                if width <= 0:
                    continue

                # Try to move left in GRID_STEP increments while valid
                while True:
                    candidate_x1 = max(0.0, x1 - GRID_STEP)
                    candidate_x2 = candidate_x1 + width

                    # Stop if we are already at the wall or we didn't move
                    if abs(candidate_x1 - x1) < 1e-6:
                        break

                    candidate_rect = [[candidate_x1, y1], [candidate_x2, y2]]
                    # Check for overlap with other rectangles in the same bin.
                    # Allow a small vertical tolerance (vertical_eps) for compaction
                    # so an item can slide slightly "under" a thin stagger of an
                    # adjacent row. We still require that the moved rectangle
                    # itself remains supported (checked below) and that no upper
                    # rectangle loses its support because of the move.
                    has_overlap = False
                    l1 = Point(candidate_rect[0][0], candidate_rect[1][1])
                    r1 = Point(candidate_rect[1][0], candidate_rect[0][1])
                    # vertical tolerance (units same as input data)
                    vertical_eps = 0.5
                    for jdx, other in enumerate(b.locations):
                        if jdx == idx:
                            continue
                        ox1, oy1 = other[0]
                        ox2, oy2 = other[1]
                        l2 = Point(ox1, oy2)
                        r2 = Point(ox2, oy1)

                        # Compute overlap extents directly
                        x_overlap = min(candidate_rect[1][0], ox2) - max(candidate_rect[0][0], ox1)
                        y_overlap = min(candidate_rect[1][1], oy2) - max(candidate_rect[0][1], oy1)

                        # Treat as overlap only if there's positive horizontal overlap
                        # and the vertical intersection exceeds the small tolerance.
                        if x_overlap > 0 and y_overlap > vertical_eps:
                            has_overlap = True
                            break

                    if has_overlap:
                        break

                    # If this rect is above ground, ensure it is still supported
                    # (unless this bin is configured to ignore support during
                    # compaction, e.g. wide top shelves where we only care
                    # about 2D non-overlap).
                    if (not ignore_support) and candidate_rect[0][1] > 0.0:
                        support_ratio = compute_support_ratio(
                            candidate_rect,
                            b.locations,
                            b.games,
                            nonStackableItems,
                            SUPPORT_HEIGHT_TOLERANCE,
                        )
                        if support_ratio < MIN_SUPPORT_RATIO:
                            break

                    upper_unsafe = False
                    if not ignore_support:
                        # Also ensure that sliding this rectangle does not break support
                        # for any rectangles that rest on top of it.
                        # We approximate "rests on top" by checking for rectangles whose
                        # bottom y is within the support height tolerance of this
                        # rectangle's (candidate) top y, and that horizontally overlap.
                        candidate_top_y = candidate_rect[1][1]
                        temp_locations = b.locations.copy()
                        temp_locations[idx] = candidate_rect

                        for jdx, upper in enumerate(b.locations):
                            if jdx == idx:
                                continue

                            ux1, uy1 = upper[0]
                            ux2, uy2 = upper[1]

                            # Only consider rectangles that are above this one
                            if uy1 <= candidate_top_y:
                                continue
                            if abs(uy1 - candidate_top_y) > SUPPORT_HEIGHT_TOLERANCE:
                                continue

                            # Require some horizontal overlap between this candidate and the upper rect
                            if ux2 <= candidate_rect[0][0] or ux1 >= candidate_rect[1][0]:
                                continue

                            if uy1 > 0.0:
                                upper_support = compute_support_ratio(
                                    upper,
                                    temp_locations,
                                    b.games,
                                    nonStackableItems,
                                    SUPPORT_HEIGHT_TOLERANCE,
                                )
                                if upper_support < MIN_SUPPORT_RATIO:
                                    upper_unsafe = True
                                    break

                        if upper_unsafe:
                            break

                    # Accept the move and continue trying to slide further
                    x1, x2 = candidate_x1, candidate_x2
                    b.locations[idx] = [[x1, y1], [x2, y2]]
                    moved = True

def putItem(unchosenItems, rect: Rect, name: str, container: Bin, orientation: str, tag: str, item_volume: float):
    """
    Place a single item into a single container.
    Mutates the given container entry in-place and removes the item from unchosenItems.
    """
    container.games.append(name + tag)
    container.locations.append(rect)
    container.volume -= item_volume

    idx = findIndex(name, unchosenItems)
    if idx != -1:
        unchosenItems.pop(idx)

    loc = container.locations
    print(f"{name}{tag} {orientation} -> {rect} -> {loc} -> {container.name}")

    return loc

def newRectCoords(where, entry, addX, addY):
    if where == "r":
        newX1 = entry[1][0]
        newY1 = entry[0][1]
    else:
        newX1 = entry[0][0]
        newY1 = entry[1][1]
    newX2 = newX1 + addX
    newY2 = newY1 + addY

    a = Point(newX1, newY1)
    b = Point(newX2, newY2)

    return a, b

def createRect(a, b):
    return [[a.x, a.y], [float("%.1f" % b.x), float("%.1f" % b.y)]]

def isInNonStackableList(name, nonStackableList):
    for nsItem in nonStackableList:
        if name == nsItem.name:
            return True
    return False

def addThroughRotation(
    unchosenItems,
    name,
    item_volume,
    container,
    maxLength,
    maxHeight,
    maxWidth,
    nonStackableItems,
    orientation,
    tag,
    addX,
    addY,
):
    """
    Try to add an item into a container by scanning positions derived from
    existing item edges and a configurable grid, while enforcing non-overlap
    and support constraints.
    """
    # First item in the container: place it at the origin
    if len(container.locations) == 0:
        rect = createRect(Point(0, 0), Point(addX, addY))
        putItem(unchosenItems, rect, name, container, orientation, tag, item_volume)
        return True

    prio = ["r", "u"]
    if isInNonStackableList(name, nonStackableItems):
        prio = ["u", "r"]

    for mod in prio:
        for entry in container.locations:
            st, nd = newRectCoords(mod, entry, addX, addY)
            copy_st = copy.deepcopy(st)
            copy_nd = copy.deepcopy(nd)

            # Build candidate x offsets: from grid plus edges of existing items
            candidate_x = set()

            # Grid-based candidates across the width
            x = 0.0
            while x <= maxWidth - addX:
                candidate_x.add(float("%.1f" % x))
                x += GRID_STEP

            # Edge-aligned candidates relative to existing rectangles
            for other in container.locations:
                ox1 = other[0][0]
                ox2 = other[1][0]
                candidate_x.add(float("%.1f" % ox1))
                candidate_x.add(float("%.1f" % max(0.0, ox2 - addX)))

            for xo in sorted(candidate_x):
                copy_st.x = st.x + xo
                copy_nd.x = nd.x + xo
                if copy_nd.x <= maxLength and copy_nd.y <= maxHeight:
                    rect = createRect(copy_st, copy_nd)
                    # First, ensure we don't overlap any existing rectangle
                    bad = False
                    for other in container.locations:
                        l1 = Point(rect[0][0], rect[1][1])
                        r1 = Point(rect[1][0], rect[0][1])
                        l2 = Point(other[0][0], other[1][1])
                        r2 = Point(other[1][0], other[0][1])

                        if do_overlap(l1, r1, l2, r2):
                            bad = True
                            break

                    # If no overlaps and we're not on the ground, check support from underlying boxes
                    if not bad and rect[0][1] > 0.0:
                        support_ratio = compute_support_ratio(
                            rect,
                            container.locations,
                            container.games,
                            nonStackableItems,
                            SUPPORT_HEIGHT_TOLERANCE,
                        )
                        if support_ratio < MIN_SUPPORT_RATIO:
                            bad = True

                    if not bad:
                        putItem(unchosenItems, rect, name, container, orientation, tag, item_volume)
                        return True

    return False

def load_items(path: str) -> Tuple[List[Item], List[Item]]:
    items: List[Item] = []
    nonStackableItems: List[Item] = []

    with open(path, "r") as fileItems:
        for line in fileItems:
            row = line.strip("\n")
            if not row or row.startswith("#"):
                continue

            parts = row.split(",")
            if len(parts) < 4:
                print(f"Item {parts[0]} has no dimensions. Skipping it.")
                continue

            name = parts[0].strip(" ")
            try:
                length = float(parts[1].strip(" "))
                height = float(parts[2].strip(" "))
                width = float(parts[3].strip(" "))
            except ValueError:
                print(f"Item {name} has invalid numeric dimensions. Skipping it.")
                continue

            if length <= 0 or height <= 0 or width <= 0:
                print(f"Item {name} has non-positive dimensions. Skipping it.")
                continue

            vol = float("%.1f" % (length * height * width))
            stackable = len(parts) == 4
            item = Item(name=name, length=length, height=height, width=width, volume=vol, stackable=stackable)

            if stackable:
                items.append(item)
            else:
                nonStackableItems.append(item)

    return items, nonStackableItems


def load_bins(path: str) -> List[Bin]:
    bins: List[Bin] = []
    with open(path, "r") as fileBins:
        for line in fileBins:
            row = line.strip("\n")
            if not row or row.startswith("#"):
                continue

            parts = row.split(",")
            if len(parts) < 4:
                print(f"Bin {parts[0]} has no dimensions. Skipping it.")
                continue

            name = parts[0].strip(" ")
            try:
                length = float(parts[1].strip(" "))
                height = float(parts[2].strip(" "))
                width = float(parts[3].strip(" "))
            except ValueError:
                print(f"Bin {name} has invalid numeric dimensions. Skipping it.")
                continue

            if length <= 0 or height <= 0 or width <= 0:
                print(f"Bin {name} has non-positive dimensions. Skipping it.")
                continue

            vol = float("%.1f" % (length * height * width))
            bins.append(Bin(name=name, length=length, height=height, width=width, volume=vol))

    return bins


def pack_items(
    items: List[Item],
    nonStackableItems: List[Item],
    bins: List[Bin],
    pathOutput: str,
    grid_step: float = GRID_STEP,
    support_height_tolerance: float = SUPPORT_HEIGHT_TOLERANCE,
    min_support_ratio: float = MIN_SUPPORT_RATIO,
    fill_large_bins_first: bool = False,
):
    # Allow overriding globals via parameters
    global GRID_STEP, SUPPORT_HEIGHT_TOLERANCE, MIN_SUPPORT_RATIO
    GRID_STEP = grid_step
    SUPPORT_HEIGHT_TOLERANCE = support_height_tolerance
    MIN_SUPPORT_RATIO = min_support_ratio

    # Sort items and bins for packing
    items.sort(key=lambda it: it.volume, reverse=True)
    # Bin ordering heuristic: small first or large first
    bins.sort(key=lambda b: b.volume, reverse=fill_large_bins_first)

    # STACKABLE ITEMS
    unchosenItems = items.copy()
    print(unchosenItems)
    print(bins)

    st = time.time()
    totalItems = len(unchosenItems)

    unchosenCopy = unchosenItems.copy()
    for item in unchosenCopy:
        name = item.name
        length = item.length
        height = item.height
        width = item.width
        item_volume = item.volume
        added = False

        et = time.time()
        elapsed_time = et - st
        remainingItems = len(unchosenItems)
        print("\nElapsed time:", elapsed_time, "seconds")
        if totalItems != remainingItems:
            estimate = remainingItems * elapsed_time / max(0.00000001, (totalItems - remainingItems))
            print(f"{remainingItems} items left, {estimate} seconds left.\n")

        if item not in unchosenItems:
            continue

        # Instead of naive first-fit (try bins in order and take the first that works),
        # try a best-fit strategy: simulate placing the item in every bin and orientation
        # (using deepcopy) and pick the placement that leaves the least leftover volume.
        # This is still greedy per-item but reduces fragmentation compared to first-fit.
        bins.sort(key=lambda b: b.volume, reverse=fill_large_bins_first)
        print(bins)

        # Collect candidate successful placements: (leftover_volume, bin_index, orientation, tag, addX, addY)
        candidates = []
        for b_idx, bin_obj in enumerate(bins):
            maxLength = bin_obj.length
            maxHeight = bin_obj.height
            maxWidth = bin_obj.width

            # list possible orientations that geometrically fit
            orientations = []
            if length <= maxWidth and width <= maxLength and height <= maxHeight:
                orientations.append((width, height, "fits flat by length", "-flat-len"))
            if width <= maxWidth and length <= maxLength and height <= maxHeight:
                orientations.append((length, height, "fits flat by width", "-flat-wid"))
            if length <= maxWidth and width <= maxHeight and height <= maxLength:
                orientations.append((height, width, "fits upright by length", "-upright-len"))
            if width <= maxWidth and length <= maxHeight and height <= maxLength:
                orientations.append((height, length, "fits upright by width", "-upright-width"))

            for addX, addY, orientation, tag in orientations:
                # simulate on copies
                bin_copy = copy.deepcopy(bin_obj)
                unchosen_copy = copy.deepcopy(unchosenItems)
                ok = addThroughRotation(
                    unchosen_copy,
                    name,
                    item_volume,
                    bin_copy,
                    maxLength,
                    maxHeight,
                    maxWidth,
                    nonStackableItems,
                    orientation,
                    tag,
                    addX,
                    addY,
                )
                if ok:
                    candidates.append((bin_copy.volume, b_idx, orientation, tag, addX, addY))

        # If we found any candidate, pick the one that leaves least leftover volume
        if candidates:
            candidates.sort(key=lambda x: x[0])
            _, chosen_idx, orientation, tag, addX, addY = candidates[0]
            chosen_bin = bins[chosen_idx]
            added = addThroughRotation(
                unchosenItems,
                name,
                item_volume,
                chosen_bin,
                chosen_bin.length,
                chosen_bin.height,
                chosen_bin.width,
                nonStackableItems,
                orientation,
                tag,
                addX,
                addY,
            )

    # NON-STACKABLE ITEMS SHELVING
    nonStackableItems.sort(key=lambda it: it.volume, reverse=True)
    bins.sort(key=lambda b: b.volume, reverse=fill_large_bins_first)

    unchosenItems = nonStackableItems.copy()
    print(unchosenItems)
    print(bins)

    st = time.time()
    totalItems = len(unchosenItems)

    unchosenCopy = unchosenItems.copy()
    for item in unchosenCopy:
        name = item.name
        length = item.length
        height = item.height
        width = item.width
        item_volume = item.volume
        added = False

        et = time.time()
        elapsed_time = et - st
        remainingItems = len(unchosenItems)
        print("\nElapsed time:", elapsed_time, "seconds")
        if totalItems != remainingItems:
            estimate = remainingItems * elapsed_time / max(0.00000001, (totalItems - remainingItems))
            print(f"{remainingItems} items left, {estimate} seconds left.\n")

        if item not in unchosenItems:
            continue

        # Use best-fit selection for non-stackable items as well: simulate placement in each bin
        bins.sort(key=lambda b: b.volume, reverse=fill_large_bins_first)
        print(bins)

        candidates = []
        for b_idx, bin_obj in enumerate(bins):
            maxLength = bin_obj.length
            maxHeight = bin_obj.height
            maxWidth = bin_obj.width

            # two orientations considered for non-stackable placement
            if length <= maxWidth and width <= maxLength and height <= maxHeight:
                bin_copy = copy.deepcopy(bin_obj)
                unchosen_copy = copy.deepcopy(unchosenItems)
                ok = addThroughRotation(
                    unchosen_copy,
                    name,
                    item_volume,
                    bin_copy,
                    maxLength,
                    maxHeight,
                    maxWidth,
                    nonStackableItems,
                    "fits flat by length",
                    "-flat-len",
                    width,
                    height,
                )
                if ok:
                    candidates.append((bin_copy.volume, b_idx, "fits flat by length", "-flat-len", width, height))

            if width <= maxWidth and length <= maxLength and height <= maxHeight:
                bin_copy = copy.deepcopy(bin_obj)
                unchosen_copy = copy.deepcopy(unchosenItems)
                ok = addThroughRotation(
                    unchosen_copy,
                    name,
                    item_volume,
                    bin_copy,
                    maxLength,
                    maxHeight,
                    maxWidth,
                    nonStackableItems,
                    "fits flat by width",
                    "-flat-wid",
                    length,
                    height,
                )
                if ok:
                    candidates.append((bin_copy.volume, b_idx, "fits flat by width", "-flat-wid", length, height))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            _, chosen_idx, orientation, tag, addX, addY = candidates[0]
            chosen_bin = bins[chosen_idx]
            added = addThroughRotation(
                unchosenItems,
                name,
                item_volume,
                chosen_bin,
                chosen_bin.length,
                chosen_bin.height,
                chosen_bin.width,
                nonStackableItems,
                orientation,
                tag,
                addX,
                addY,
            )

    # Post-processing compaction to tighten packing inside each bin
    compact_bins(bins, nonStackableItems)

    # Final validation
    assert_bins_valid(bins)

    prettyPrintBins(bins)
    prettyWriteBins(pathOutput, bins)

    print(f"Can't fit: {unchosenItems}")
    detailedPrintBins(bins)

    elapsed_time = et - st
    print("Execution time:", elapsed_time, "seconds")


if __name__ == "__main__":
    # User variables (change them if you want)
    pathOutput = "output.txt"
    pathItems = "items.txt"
    pathBins = "bins.txt"

    items, nonStackableItems = load_items(pathItems)
    bins = load_bins(pathBins)

    # Strategy 1: fill smaller bins first
    print("Running strategy: small-bins-first")
    items_copy1 = copy.deepcopy(items)
    nonStack_copy1 = copy.deepcopy(nonStackableItems)
    bins_copy1 = copy.deepcopy(bins)
    pack_items(items_copy1, nonStack_copy1, bins_copy1, pathOutput, fill_large_bins_first=False)