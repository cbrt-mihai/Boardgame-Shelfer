import copy
from typing import List


# CODES
OK = 0
ITEM_TOO_BIG = 1
ITEM_INTERSECTS = 2
ITEM_OUT_OF_BOUNDS = 3


# Each orientation maps to (top-view UP dimension, top-view RIGHT dimension, vertical dimension).
# "up"/"right" refer to how the box looks from above; "vertical" is the height axis (y).
# In this coordinate system: x = right, y = vertical, z = up (top-view depth).
ORIENTATIONS = {
    "wlr": ("width",  "length", "height"),  # width up, length right, height vertical
    "wlu": ("length", "width",  "height"),  # length up, width right, height vertical
    "hlr": ("height", "length", "width"),   # height up, length right, width vertical
    "hlu": ("length", "height", "width"),   # length up, height right, width vertical
    "hwr": ("height", "width",  "length"),  # height up, width right, length vertical
    "hwu": ("width",  "height", "length"),  # width up, height right, length vertical
}


class Point3D:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x
        self.y = y
        self.z = z

    def __repr__(self):
        return f"P3D({self.x}, {self.y}, {self.z})"


class Item:
    def __init__(self, name: str, length: float, height: float, width: float, stackable: bool, volume: float, top_area: float, short_side_area: float, long_side_area: float) -> None:
        self.name = name
        self.length = length
        self.height = height
        self.width = width
        self.corner1 = Point3D(0, 0, 0)
        self.corner2 = Point3D(length, height, width)
        self.stackable = stackable
        self.volume = volume
        self.top_area = top_area
        self.short_side_area = short_side_area
        self.long_side_area = long_side_area

    def update_corner1(self, x: float, y: float, z: float):
        self.corner1 = Point3D(x, y, z)

    def update_corner2(self, x: float, y: float, z: float):
        self.corner2 = Point3D(x, y, z)

    def update_corners(self, x: float, y: float, z: float, mode: str):
        self.corner1 = Point3D(x, y, z)

        dims = {"length": self.length, "height": self.height, "width": self.width}
        up_dim, right_dim, vertical_dim = ORIENTATIONS[mode]

        self.corner2 = Point3D(
            x + dims[right_dim],
            y + dims[vertical_dim],
            z + dims[up_dim],
        )


    def __repr__(self):
        return f"Item({self.name}, {self.length}, {self.height}, {self.width}, {self.stackable})"


class Bin:
    def __init__(self, name: str, length: float, height: float, width: float,
                 volume: float, contains: List[Item] | None = None) -> None:
        self.name = name
        self.length = length
        self.height = height
        self.width = width
        self.currentVolume = volume
        self.maxVolume = volume
        self.contains = [] if contains is None else contains

    def add_item(self, item: Item):
        self.contains.append(item)

    def remove_item(self, item: Item):
        self.contains.remove(item)

    def update_volume(self, volume: float):
        self.currentVolume -= volume

    def __repr__(self):
        return f"Bin({self.name}, {self.length}, {self.height}, {self.width}, {self.currentVolume}/{self.maxVolume}, {self.contains})"


def load_items(path: str) -> List[Item]:
    items = []
    with open(path, "r") as items_file:
        itemsStr = items_file.readlines()
        for item in itemsStr:
            item = item.strip()

            if item.startswith("#"):
                # print(f"[#] Skipping comment -> {item}")
                continue

            try:
                parts = item.split(",")

                if len(parts) < 4 or len(parts) > 5:
                    print(f"[!] Invalid number of parts -> {item}")
                    continue
                elif len(parts) == 5:
                    name, length, height, width, marked = parts
                else:
                    name, length, height, width = parts
                    marked = ""

                stackable = False
                if marked != "":
                    stackable = True

                name = name.strip()
                length = float(length.strip())
                height = float(height.strip())
                width = float(width.strip())

                volume = length * height * width
                top_area = length * width
                short_side_area = height * width
                long_side_area = length * height

                newItem = Item(name, length, height, width, stackable, volume, top_area, short_side_area, long_side_area)
                items.append(newItem)

                # print(name, length, height, width, stackable, volume, top_area, short_side_area, long_side_area)
            except ValueError:
                print(f"[!] ValueError - Invalid item format: {item}")

    return items


def load_bins(path: str) -> List[Bin]:
    bins = []
    with open(path, "r") as bins_file:
        binsStr = bins_file.readlines()
        for bin in binsStr:
            bin = bin.strip()
            # print(bin)

            if bin.startswith("#"):
                continue
                # print(f"[#] Skipping comment -> {bin}")

            parts = bin.split(",")
            name = parts[0].strip()
            length = float(parts[1].strip())
            height = float(parts[2].strip())
            width = float(parts[3].strip())

            volume = length * height * width

            newBin = Bin(name, length, height, width, volume)
            bins.append(newBin)

    return bins


def item_too_big(item: Item, bin: Bin) -> bool:
    return item.volume > bin.currentVolume


def item_out_of_bounds(item: Item, bin: Bin) -> bool:
    # An item must sit fully inside the bin's physical footprint, not just
    # fit within the bin's remaining *volume*. Volume alone doesn't stop an
    # item from being placed with a corner sticking out past the bin's
    # length/height/width (which is what was causing items to render as
    # oversized/overflowing boxes in the viewer).
    return (
        item.corner1.x < 0
        or item.corner1.y < 0
        or item.corner1.z < 0
        or item.corner2.x > bin.length
        or item.corner2.y > bin.height
        or item.corner2.z > bin.width
    )


def item_intersects(item1: Item, item2: Item) -> bool:
    return item1.corner1.x < item2.corner2.x and item1.corner2.x > item2.corner1.x and item1.corner1.y < item2.corner2.y and item1.corner2.y > item2.corner1.y and item1.corner1.z < item2.corner2.z and item1.corner2.z > item2.corner1.z


def can_add_item_to_bin(item: Item, bin: Bin):
    if item_too_big(item, bin):
        # print(f"[!] Item {item.name} is too large for bin {bin.name}")
        return ITEM_TOO_BIG, False

    if item_out_of_bounds(item, bin):
        # print(f"[!] Item {item.name} does not fit within bin {bin.name}'s dimensions")
        return ITEM_OUT_OF_BOUNDS, False

    for item_in_bin in bin.contains:
        if item_intersects(item, item_in_bin):
            return ITEM_INTERSECTS, False

    return OK, True


EPS = 1e-6


def resting_y(x1: float, x2: float, z1: float, z2: float, bin: "Bin") -> float:
    """
    Compute the height at which an item with the given (x1..x2, z1..z2)
    footprint would come to rest inside `bin`.

    An item can only be considered "supported" at a height above the floor
    if some single existing item's footprint fully contains this item's
    footprint (i.e. the new item would land flush on top of it, with no
    part of it hanging out over empty space). Otherwise it settles on the
    bin floor (y=0).

    This intentionally does NOT let two adjacent, equal-height items
    jointly support a wider item spanning both of them - that requires
    tracking a footprint union rather than single-item containment, which
    is more than this simple heuristic packer attempts. The tradeoff is a
    few missed placements in exchange for never producing a floating item.

    Note this only decides the *candidate* height to try; can_add_item_to_bin
    still performs the real overlap/bounds check afterwards, so an
    unsupported-but-non-overlapping candidate here can never be silently
    accepted as a false "fit".
    """
    best_y = 0.0
    for existing in bin.contains:
        fully_contains = (
            existing.corner1.x <= x1 + EPS
            and existing.corner2.x >= x2 - EPS
            and existing.corner1.z <= z1 + EPS
            and existing.corner2.z >= z2 - EPS
        )
        if fully_contains and existing.corner2.y > best_y:
            best_y = existing.corner2.y
    return best_y


def add_items_in_bins(items: List[Item], bins: List[Bin]):
    unplaced_items = copy.copy(items)
    for item in items:
        bins.sort(key=lambda b: b.currentVolume)
        placed = False

        for bin in bins:
            if placed:
                break

            orientations = ["wlr", "wlu", "hlr", "hlu", "hwr", "hwu"]
            for orientation in orientations:
                if placed:
                    break

                dims = {"length": item.length, "height": item.height, "width": item.width}
                up_dim, right_dim, _vertical_dim = ORIENTATIONS[orientation]
                right_extent = dims[right_dim]
                up_extent = dims[up_dim]

                # Candidate (x, z) footprint positions: the origin, plus the
                # footprint corners of every item already in the bin. These
                # are the only x/z positions where a new item could conceivably
                # butt up against something already placed.
                candidate_xz = [(0.0, 0.0)]
                for existing in bin.contains:
                    candidate_xz.extend([
                        (existing.corner2.x, existing.corner1.z),
                        (existing.corner1.x, existing.corner2.z),
                        (existing.corner2.x, existing.corner2.z),
                    ])

                for cx, cz in candidate_xz:
                    cy = resting_y(cx, cx + right_extent, cz, cz + up_extent, bin)
                    item.update_corners(cx, cy, cz, orientation)
                    code, ok = can_add_item_to_bin(item, bin)
                    if ok:
                        announce_placement(item, bin, "placed", orientation)
                        bin.add_item(copy.deepcopy(item))
                        bin.update_volume(item.volume)
                        unplaced_items.remove(item)
                        placed = True
                        break

    return unplaced_items, bins


def announce_placement(item: Item, bin: Bin, placement: str, orientation: str):
    print(f"[+] Item {item.name} -> {bin.name} @ {item.corner1} x {item.corner2} - {placement} {orientation}")


def save_placements(path: str, bins: List[Bin]):
    with open(path, "w", encoding="utf-8") as output:
        for bin in bins:
            output.write(
                f"#{bin.name},{bin.length},{bin.height},{bin.width}\n"
            )

            for item in bin.contains:
                output.write(
                    f"{item.name},"
                    f"{item.corner1.x},{item.corner1.y},{item.corner1.z},"
                    f"{item.corner2.x},{item.corner2.y},{item.corner2.z}\n"
                )


def main():
    items_path = "items.txt"
    bins_path = "bins_3D.txt"
    output_path = "output.txt"

    items = load_items(items_path)
    bins = load_bins(bins_path)

    items.sort(key=lambda item: item.volume)
    bins.sort(key=lambda bin: bin.currentVolume)

    # print(items)
    # print(bins)

    items, bins = add_items_in_bins(items, bins)
    save_placements(output_path, bins)

    print(items)
    print(bins)


if __name__ == "__main__":
    main()