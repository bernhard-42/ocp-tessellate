"""A kernel of triangles, segments, points, locations and axes, as a plugin implements
it: no OCCT object anywhere, and its shapes are plain Python objects."""

import numpy as np

from ocp_tessellate.ocp_utils import BoundingBox
from ocp_tessellate.plugin import (
    CURVE_TYPES,
    CoordAxis,
    CoordSystem,
    OcpObject,
    ShowProtocol,
    TessellationProtocol,
    object_color,
    register_show,
)

KERNEL = "toy"


class Triangle:
    """The kernel's body, at the origin."""

    def __init__(self, size=1.0, name=None, color=None, cached=True):
        self.size, self.name, self.color, self.cached = size, name, color, cached


class Segment:
    def __init__(self, start, end):
        self.start, self.end = start, end


class Point:
    def __init__(self, x, y, z):
        self.xyz = (x, y, z)


class ToyLocation:
    def __init__(self, origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, 1)):
        self.origin, self.x_dir, self.z_dir = origin, x_dir, z_dir


class ToyAxis:
    def __init__(self, origin=(0, 0, 0), direction=(0, 0, 1)):
        self.origin, self.direction = origin, direction


class Bag:
    """A container of the kernel: iterable, but no list."""

    def __init__(self, *items):
        self.items = items

    def __iter__(self):
        return iter(self.items)


def _box_of(points):
    flat = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    lo, hi = flat.min(axis=0), flat.max(axis=0)
    return BoundingBox({"xmin": lo[0], "xmax": hi[0], "ymin": lo[1], "ymax": hi[1], "zmin": lo[2], "zmax": hi[2]})


class ToyTessellation(TessellationProtocol):
    def __init__(self):
        self.calls = []

    def tessellate(self, shape, deviation, quality, angular_tolerance, compute_edges=True, compute_uvs=False, normalize_uvs=True, shape_id="", debug=False):
        self.calls.append({"deviation": deviation, "quality": quality, "angular_tolerance": angular_tolerance, "compute_edges": compute_edges})
        s = shape.size
        return {
            "vertices": np.array([0, 0, 0, s, 0, 0, 0, s, 0], dtype=np.float32),
            "triangles": np.array([0, 1, 2], dtype=np.int32),
            "normals": np.array([0, 0, 1] * 3, dtype=np.float32),
            "edges": np.array([0, 0, 0, s, 0, 0, s, 0, 0, 0, s, 0, 0, s, 0, 0, 0, 0], dtype=np.float32),
            "obj_vertices": np.array([0, 0, 0, s, 0, 0, 0, s, 0], dtype=np.float32),
            "face_types": np.array([0], dtype=np.int32),
            "edge_types": np.array([0, 0, 0], dtype=np.int32),
            "triangles_per_face": np.array([1], dtype=np.int32),
            "segments_per_edge": np.array([1, 1, 1], dtype=np.int32),
        }

    def discretize_edges(self, edges, deflection=0.1, shape_id=""):
        pts = np.array([(e.start, e.end) for e in edges], dtype=np.float32)
        return {
            "edges": pts.ravel(),
            "segments_per_edge": np.ones(len(pts), dtype=np.int32),
            "edge_types": np.full(len(pts), CURVE_TYPES["Line"], dtype=np.int32),
            "obj_vertices": pts.reshape(-1, 3).ravel(),
        }

    def convert_vertices(self, vertices, shape_id=""):
        return {"obj_vertices": np.array([v.xyz for v in vertices], dtype=np.float32).ravel()}

    def bounding_box(self, shape):
        items = shape if isinstance(shape, (list, tuple)) else [shape]
        points = []
        for item in items:
            if isinstance(item, Triangle):
                points += [(0, 0, 0), (item.size, item.size, 0)]
            elif isinstance(item, Segment):
                points += [item.start, item.end]
            elif isinstance(item, Point):
                points += [item.xyz]
            else:
                raise TypeError(f"{type(item).__name__} has no extent")
        return _box_of(points)

    def cache_id(self, shape):
        return f"triangle-{shape.size}" if shape.cached else None


class ToyShow(ShowProtocol):
    def is_object(self, obj):
        return isinstance(obj, (Triangle, Segment, Point, ToyLocation, ToyAxis, Bag))

    def line(self, start, end):
        return Segment(start, end)

    def serialize(self, shape):
        return repr(shape).encode("utf-8")

    def convert(self, obj, name, color, alpha, helper_scale):
        if isinstance(obj, ToyLocation):
            return CoordSystem(name, obj.origin, obj.x_dir, obj.z_dir, size=helper_scale, like=obj)
        if isinstance(obj, ToyAxis):
            return CoordAxis(name, obj.origin, obj.direction, color, size=helper_scale, like=obj)
        if isinstance(obj, Triangle):
            return OcpObject("face", obj, name=name, color=object_color(obj, color, alpha))
        if isinstance(obj, Segment):
            return OcpObject("edge", [obj], name=name, color=object_color(obj, color, alpha))
        return OcpObject("vertex", [obj], name=name, color=object_color(obj, color, alpha))

    def get_children(self, obj):
        return [(None, item, None) for item in obj] if isinstance(obj, Bag) else None


TESSELLATION = ToyTessellation()
register_show(KERNEL, TESSELLATION, ToyShow(), api=1)
