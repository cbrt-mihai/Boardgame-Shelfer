import time
from operator import getitem

class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

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

def findIndex(name, list):
    for i, elem in enumerate(list):
        if name == elem[0]:
            return i

    return -1

def sortCont(item):
    return item[1]["volume"]

def do_balance(x1r, x2r, x1e, x2e):
    cutoff = min(x2r, x2e)
    lowerSeg = cutoff - max(x1r, x1e)
    upperSeg = x2r - cutoff

    if lowerSeg > upperSeg:
        return True
    return False

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

def prettyPrintDict(containers):
    for container in containers:
        name = container[0]
        dict = container[1]
        games = dict["games"]
        location = dict["location"]
        sizes = dict["sizes"]
        volume = dict["volume"]

        print(f"{name}")
        print("{")
        print(f"\tGames: {games}")
        print(f"\tLocation: {location}")
        print(f"\tSizes: {sizes}")
        print(f"\tVolume: {volume}")
        print("}\n")

def prettyWriteDict(writePath, containers):
    file = open(writePath, "w")
    for container in containers:
        name = container[0]
        dict = container[1]
        games = dict["games"]
        location = dict["location"]
        sizes = dict["sizes"]
        volume = dict["volume"]

        file.write(f"#{name},{sizes[0]},{sizes[1]},{sizes[2]}\n")

        for i, game in enumerate(games):
            file.write(f"{game},{location[i][0][0]},{location[i][0][1]},{location[i][1][0]},{location[i][1][1]}\n")
    file.close()

def detailedPrintDict(containers):
    for container in containers:
        name = container[0]
        dict = container[1]
        games = dict["games"]
        location = dict["location"]
        sizes = dict["sizes"]
        volume = dict["volume"]

        print(f"{name}, [{sizes[0]},{sizes[1]},{sizes[2]}]")

        for i, game in enumerate(games):
            print(f"{game}, [{location[i][0][0]}, {location[i][0][1]}],  [{location[i][1][0]}, {location[i][1][1]}]")
        print()

'''
l1 : x1, y2
r1 : x2, y1
l2 : a1, b2
r2 : a2, b1
'''
def isBad(rect, other, entry):
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

def putItem(unchosenItems, rect, name, containers, orientation, tag):
    containers[i][1]["games"].append(name + tag)
    containers[i][1]["location"].append(rect)
    containers[i][1]["volume"] -= volume
    idx = findIndex(name, unchosenItems)
    print(len(unchosenItems))
    if idx != -1:
        unchosenItems.pop(idx)
    print(len(unchosenItems))
    loc = container[1]["location"]
    print(f"{item} {orientation} -> {rect} -> {loc} -> {container[0]}")

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

def addThroughRotation(unchosenItems, name, containers, orientation, tag, addX, addY):
    rect = createRect(Point(0, 0), Point(addX, addY))

    if (len(container[1]["location"]) == 0):
        putItem(unchosenItems, rect, name, containers, orientation, tag)
        return True

    for k, entry in enumerate(container[1]["location"]):
        for mod in ["r", "u"]:
            st, nd = newRectCoords(mod, entry, addX, addY)

            if nd.x <= maxLength and nd.y <= maxHeight:
                rect = createRect(st, nd)
                for p, other in enumerate(container[1]["location"]):
                    bad = isBad(rect, other, entry)

                    if bad:
                        bad = True
                        break
                if bad == False:
                    loc = putItem(unchosenItems, rect, name, containers, orientation, tag)
                    return True
    return False

# ------- MAIN -------

if __name__ == "__main__":

    # User variables (change them if you want)
    pathOutput = "output.txt"
    pathItems = "items.txt"
    pathBins = "bins.txt"


    items = []
    bins = []
    containers = {}

    fileItems = open(pathItems, "r")
    for file in fileItems:
        row = file.strip("\n")
        if row.startswith("#"):
            continue

        parts = row.split(",")
        name = parts[0].strip(" ")
        length = float(parts[1].strip(" "))
        height = float(parts[2].strip(" "))
        width = float(parts[3].strip(" "))

        item = [name, length, height, width]
        item.append(float("%.1f" % volume(item)))

        items.append(item)
    fileItems.close()

    fileBins = open(pathBins, "r")
    for file in fileBins:
        row = file.strip("\n")
        if row.startswith("#"):
            continue
        parts = row.split(",")
        name = parts[0].strip(" ")
        length = float(parts[1].strip(" "))
        height = float(parts[2].strip(" "))
        width = float(parts[3].strip(" "))

        bin = [name, length, height, width]
        bin.append(float("%.1f" % (volume(bin))))

        bins.append(bin)
        containers[name] = {}
        containers[name]["games"] = []
        containers[name]["location"] = []
        containers[name]["sizes"] = [bin[1], bin[2], bin[3]]
        containers[name]["volume"] = bin[4]
    fileBins.close()

    items.sort(key=take5th, reverse=True)
    bins.sort(key=take5th, reverse=True)
    containers = sorted(containers.items(),key=lambda x:getitem(x[1],'volume'), reverse=True)

    unchosenItems = items.copy()

    print(unchosenItems)
    print(containers)

    # get the start time
    st = time.time()
    totalItems = len(unchosenItems)

    unchosenCopy = unchosenItems.copy()
    for j, item in enumerate(unchosenCopy):
        name = item[0]
        length = item[1]
        height = item[2]
        width = item[3]
        volume = item[4]
        added = False

        # get the end time
        et = time.time()
        elapsed_time = et - st
        remainingItems = len(unchosenItems)
        print('\nElapsed time:', elapsed_time, 'seconds')
        print(f"{remainingItems} items left, {remainingItems * elapsed_time/max(0.00000001, (totalItems - remainingItems))} seconds left.\n")

        if item not in unchosenItems:
            continue

        containers = sorted(containers, key=lambda x: getitem(x[1], 'volume'), reverse=True)
        print(containers)
        for i, container in enumerate(containers):
            if added:
                break
            else:
                cntName = container[0]

                maxLength = container[1]["sizes"][0]
                maxHeight = container[1]["sizes"][1]
                maxWidth  = container[1]["sizes"][2]

                if length <= maxWidth and width <= maxLength and height <= maxHeight:
                    # If it fits by length, flat (you see width and height)

                    if added:
                        break

                    addX = width
                    addY = height

                    orientation = "fits flat by length"
                    tag = "-flat-len"

                    added = addThroughRotation(unchosenItems, name, containers, orientation, tag, addX, addY)

                if width <= maxWidth and length <= maxLength and height <= maxHeight:
                    # If it fits by width, flat (you see length and height)

                    if added:
                        break

                    addX = length
                    addY = height

                    orientation = "fits flat by width"
                    tag = "-flat-wid"

                    added = addThroughRotation(unchosenItems, name, containers, orientation, tag, addX, addY)

                if length <= maxWidth and width <= maxHeight and height <= maxLength:
                    # If it fits by length, upright (you see width and height)

                    if added:
                        break

                    addX = height
                    addY = width

                    orientation = "fits upright by length"
                    tag = "-upright-len"

                    added = addThroughRotation(unchosenItems, name, containers, orientation, tag, addX, addY)


                if width <= maxWidth and length <= maxHeight and height <= maxLength:
                    # If it fits by width, upright (you see length and height)
                    if added:
                        break

                    addX = height
                    addY = length

                    orientation = "fits upright by width"
                    tag = "-upright-width"

                    added = addThroughRotation(unchosenItems, name, containers, orientation, tag, addX, addY)

        containers.sort(key=sortCont, reverse=True)


    prettyPrintDict(containers)
    prettyWriteDict(pathOutput, containers)
    containers.sort(key=sortCont, reverse=True)
    print(f"Can't fit: {unchosenItems}")
    detailedPrintDict(containers)

    elapsed_time = et - st
    print('Execution time:', elapsed_time, 'seconds')