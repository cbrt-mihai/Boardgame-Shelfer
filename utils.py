from dataclasses import dataclass, field
from typing import List


class Point:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class Box:
    def __init__(self, corner1: Point3D, corner2: Point3D) -> None:
        self.corner1 = corner1
        self.corner2 = corner2
        self.volume = self.volume()

    def volume(self):
        return (self.corner2.x - self.corner1.x) * (self.corner2.y - self.corner1.y) * (self.corner2.z - self.corner1.z)

    def center(self):
        return (self.corner1.x + self.corner2.x) / 2, (self.corner1.y + self.corner2.y) / 2, (self.corner1.z + self.corner2.z) / 2

    def corners(self):
        return self.corner1, self.corner2

    def top_area(self):
        return (self.corner2.x - self.corner1.x) * (self.corner2.z - self.corner1.z)

    def short_side_area(self):
        return (self.corner2.y - self.corner1.y) * (self.corner2.z - self.corner1.z)

    def long_side_area(self):
        return (self.corner2.x - self.corner1.x) * (self.corner2.y - self.corner1.y)

    def __repr__(self):
        return f"Box({self.corner1}, {self.corner2})"


Rect = List[List[float]]  # [[x1, y1], [x2, y2]]


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

    @property
    def face_area_flat(self) -> float:
        return self.length * self.height

    @property
    def max_side(self) -> float:
        return max(self.length, self.height, self.width)


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

    @property
    def face_area(self) -> float:
        return self.length * self.height


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