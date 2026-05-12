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