from .ocp_utils import area, center_of_mass, end_points, point

DEBUG = False


def dump_face(id, f):
    c = center_of_mass(f)
    a = area(f)
    return f"{id}: area: {a:.6f}, center: {c[0]:.6f} , {c[1]:.6f}, {c[2]:.6f}"


def dump_edge(id, e):
    p1, p2 = end_points(e)
    return f"{id}: start: ({p1[0]:.6f} , {p1[1]:.6f}, {p1[2]:.6f}), end: ({p2[0]:.6f} , {p2[1]:.6f}, {p2[2]:.6f})"


def dump_vertex(id, v):
    p = point(v)
    return f"{id}: coords: {p[0]:.6f} , {p[1]:.6f}, {p[2]:.6f}"


class Trace:
    def __init__(self, filename):
        if DEBUG:
            self.file = open(filename, "a")

    def face(self, id, f):
        if DEBUG:
            self.file.write(dump_face(id, f) + "\n")

    def edge(self, id, e):
        if DEBUG:
            self.file.write(dump_edge(id, e) + "\n")

    def vertex(self, id, v):
        if DEBUG:
            self.file.write(dump_vertex(id, v) + "\n")

    def message(self, msg):
        if DEBUG:
            self.file.write(msg + "\n")

    def close(self):
        if DEBUG:
            self.file.close()
