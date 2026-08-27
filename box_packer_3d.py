import copy
from typing import List


# CODES
OK = 0
ITEM_TOO_BIG = 1
ITEM_INTERSECTS = 2


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


def item_intersects(item1: Item, item2: Item) -> bool:
    return item1.corner1.x < item2.corner2.x and item1.corner2.x > item2.corner1.x and item1.corner1.y < item2.corner2.y and item1.corner2.y > item2.corner1.y and item1.corner1.z < item2.corner2.z and item1.corner2.z > item2.corner1.z


def can_add_item_to_bin(item: Item, bin: Bin):
    if item_too_big(item, bin):
        # print(f"[!] Item {item.name} is too large for bin {bin.name}")
        return ITEM_TOO_BIG, False

    for item_in_bin in bin.contains:
        if item_intersects(item, item_in_bin):
            return ITEM_INTERSECTS, False

    return OK, True


def add_items_in_bins(items: List[Item], bins: List[Bin]):
    unplaced_items = copy.copy(items)
    for item in items:
        bins.sort(key=lambda bin: bin.currentVolume)
        placed = False
        for bin in bins:
            if not placed:
                orientations = ["wlr", "wlu", "hlr", "hlu", "hwr", "hwu"]
                for orientation in orientations:
                    item.update_corners(0,0, 0, orientation)
                    code, ok = can_add_item_to_bin(item, bin)
                    if ok:
                        announce_placement(item, bin, "above", orientation)
                        bin.add_item(item)
                        bin.update_volume(item.volume)
                        unplaced_items.remove(item)
                        placed = True
                        break
                    elif code == ITEM_INTERSECTS:
                        for item_in_bin in bin.contains:
                            placements = ["up", "right"]
                            if not placed:
                                for placement in placements:
                                    match placement:
                                        case "up":
                                            item.update_corners(0,0, item_in_bin.corner2.z, orientation)
                                        case "right":
                                            item.update_corners(item_in_bin.corner2.x, item_in_bin.corner2.y, 0, orientation)

                                    code, ok = can_add_item_to_bin(item, bin)
                                    if ok:
                                        announce_placement(item, bin, "above", orientation)
                                        bin.add_item(item)
                                        bin.update_volume(item.volume)
                                        unplaced_items.remove(item)
                                        placed = True
                                        break

                            if not placed:
                                # ABOVE
                                item.update_corners(0, item_in_bin.corner2.y, 0, orientation)
                                code, ok = can_add_item_to_bin(item, bin)
                                if ok:
                                    announce_placement(item, bin, "above", orientation)
                                    bin.add_item(item)
                                    bin.update_volume(item.volume)
                                    unplaced_items.remove(item)
                                    placed = True
                                    break

    items = unplaced_items

    items.sort(key=lambda item: item.volume)
    bins.sort(key=lambda bin: bin.currentVolume)

    return items, bins


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