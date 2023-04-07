#
# Copyright 2023 Bernhard Walter
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import io
import itertools
import platform
import sys
import tempfile
from collections.abc import Iterable

import numpy as np
import OCP
from cachetools import LRUCache, cached
from OCP.BinTools import BinTools
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_CompCurve, BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_Copy,
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeVertex,
)
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.gp import gp_Pnt, gp_Quaternion, gp_Trsf, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.Quantity import Quantity_ColorRGBA
from OCP.StlAPI import StlAPI_Writer
from OCP.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_COMPSOLID,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
    TopAbs_WIRE,
)
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location

# Bounding Box
from OCP.TopoDS import (
    TopoDS,
    TopoDS_Builder,
    TopoDS_Compound,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Shape,
    TopoDS_Solid,
    TopoDS_Vertex,
    TopoDS_Wire,
)
from quaternion import rotate_vectors

from .utils import Color, distance

MAX_HASH_KEY = 2147483647

#
# Version
#


def occt_version():
    return OCP.__version__


#
# helpers
#

downcast_LUT = {
    TopAbs_VERTEX: TopoDS.Vertex_s,
    TopAbs_EDGE: TopoDS.Edge_s,
    TopAbs_WIRE: TopoDS.Wire_s,
    TopAbs_FACE: TopoDS.Face_s,
    TopAbs_SHELL: TopoDS.Shell_s,
    TopAbs_SOLID: TopoDS.Solid_s,
    TopAbs_COMPSOLID: TopoDS.CompSolid_s,
    TopAbs_COMPOUND: TopoDS.Compound_s,
}


def downcast(obj):
    d_func = downcast_LUT[obj.ShapeType()]
    return d_func(obj)


def make_compound(objs):
    comp = TopoDS_Compound()
    builder = TopoDS_Builder()
    builder.MakeCompound(comp)

    for obj in objs:
        builder.Add(comp, obj)

    return comp


#
# Library identifiers
#


def _has(obj, attrs):
    return all([hasattr(obj, a) for a in attrs])


def is_cadquery(obj):
    return _has(obj, ["objects", "ctx", "val"])


def is_cadquery_assembly(obj):
    return _has(obj, ["obj", "loc", "name", "children"])


def is_cadquery_massembly(obj):
    return _has(obj, ["obj", "loc", "name", "children", "mates"])


def is_cadquery_sketch(obj):
    return (
        hasattr(obj, "_faces")
        and hasattr(obj, "_edges")
        and hasattr(obj, "_wires")
        and hasattr(obj, "_selection")
    )


def is_vector(obj):
    return hasattr(obj, "wrapped") and isinstance(obj.wrapped, gp_Vec)


def is_massembly(obj):
    return _has(obj, ["obj", "loc", "name", "children", "mates"])


def is_wrapped(obj):
    return hasattr(obj, "wrapped")


def is_build123d(obj):
    return _has(obj, ["_obj", "_obj_name"])


def is_build123d_shape(obj):
    return _has(obj, ["wrapped", "children"])


def is_build123d_compound(obj):
    return is_build123d_shape(obj) and isinstance(obj, Iterable)


def is_build123d_assembly(obj):
    return (
        (is_build123d_compound(obj) or is_build123d_shape(obj))
        and hasattr(obj, "children")
        and isinstance(obj.children, (list, tuple))
        and len(obj.children) > 0
        # and (
        #     (len(obj.children) == 0 and obj.parent is not None)
        #     or (len(obj.children) > 0 and obj.parent is None)
        # )
    )


def is_alg123d(obj):
    return _has(obj, ["wrapped", "dim"])


#
# Caching helpers for bounding box
#


def make_key(objs, loc=None, optimal=False):  # pylint: disable=unused-argument
    # optimal is not used and as such ignored
    if not isinstance(objs, (tuple, list)):
        objs = [objs]

    key = (tuple((s.HashCode(MAX_HASH_KEY) for s in objs)), loc_to_tq(loc))
    return key


def get_size(obj):
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum([get_size(v) + len(k) for k, v in obj.items()])
    elif isinstance(obj, (tuple, list)):
        size += sum([get_size(i) for i in obj])
    return size


cache = LRUCache(maxsize=16 * 1024 * 1024, getsizeof=get_size)


#
# Bounding Box
#


class BoundingBox(object):
    def __init__(self, obj=None, optimal=False):
        self.optimal = optimal
        if obj is None:
            self.xmin = self.xmax = self.ymin = self.ymax = self.zmin = self.zmax = 0
        elif isinstance(obj, BoundingBox):
            self.xmin = obj.xmin
            self.xmax = obj.xmax
            self.ymin = obj.ymin
            self.ymax = obj.ymax
            self.zmin = obj.zmin
            self.zmax = obj.zmax
        elif isinstance(obj, dict):
            self.xmin = obj["xmin"]
            self.xmax = obj["xmax"]
            self.ymin = obj["ymin"]
            self.ymax = obj["ymax"]
            self.zmin = obj["zmin"]
            self.zmax = obj["zmax"]
        else:
            bbox = self._bounding_box(obj)
            self.xmin, self.xmax, self.ymin, self.ymax, self.zmin, self.zmax = bbox

        self._calc()

    def _center_of_mass(self, obj):
        Properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(obj, Properties)
        com = Properties.CentreOfMass()
        return (com.X(), com.Y(), com.Z())

    def _bounding_box(self, obj, tol=1e-6):
        bbox = Bnd_Box()
        if self.optimal:
            BRepTools.Clean_s(obj)
            BRepBndLib.AddOptimal_s(obj, bbox)
        else:
            BRepBndLib.Add_s(obj, bbox)
        if not bbox.IsVoid():
            values = bbox.Get()
            return (values[0], values[3], values[1], values[4], values[2], values[5])
        else:
            c = self._center_of_mass(obj)
            bb = (
                c[0] - tol,
                c[0] + tol,
                c[1] - tol,
                c[1] + tol,
                c[2] - tol,
                c[2] + tol,
            )
            print("\nVoid Bounding Box", bb)
            return bb

    def _calc(self):
        self.xsize = self.xmax - self.xmin
        self.ysize = self.ymax - self.ymin
        self.zsize = self.zmax - self.zmin
        self.center = (
            self.xmin + self.xsize / 2.0,
            self.ymin + self.ysize / 2.0,
            self.zmin + self.zsize / 2.0,
        )
        self.max = max(
            [
                abs(x)
                for x in (
                    self.xmin,
                    self.xmax,
                    self.ymin,
                    self.ymax,
                    self.zmin,
                    self.zmax,
                )
            ]
        )

    def is_empty(self):
        return (
            (abs(self.xmax - self.xmin) < 0.01)
            and (abs(self.ymax - self.ymin) < 0.01)
            and (abs(self.zmax - self.zmin) < 0.01)
        )

    def max_dist_from_center(self):
        return max(
            [
                distance(self.center, v)
                for v in itertools.product(
                    (self.xmin, self.xmax),
                    (self.ymin, self.ymax),
                    (self.zmin, self.zmax),
                )
            ]
        )

    def max_dist_from_origin(self):
        return max(
            [
                np.linalg.norm(v)
                for v in itertools.product(
                    (self.xmin, self.xmax),
                    (self.ymin, self.ymax),
                    (self.zmin, self.zmax),
                )
            ]
        )

    def update(self, bb, minimize=False):
        lower, upper = (max, min) if minimize else (min, max)

        if isinstance(bb, BoundingBox):
            self.xmin = lower(bb.xmin, self.xmin)
            self.xmax = upper(bb.xmax, self.xmax)
            self.ymin = lower(bb.ymin, self.ymin)
            self.ymax = upper(bb.ymax, self.ymax)
            self.zmin = lower(bb.zmin, self.zmin)
            self.zmax = upper(bb.zmax, self.zmax)
        elif isinstance(bb, dict):
            self.xmin = lower(bb["xmin"], self.xmin)
            self.xmax = upper(bb["xmax"], self.xmax)
            self.ymin = lower(bb["ymin"], self.ymin)
            self.ymax = upper(bb["ymax"], self.ymax)
            self.zmin = lower(bb["zmin"], self.zmin)
            self.zmax = upper(bb["zmax"], self.zmax)
        else:
            raise "Wrong bounding box param"

        self._calc()

    def to_dict(self):
        return {
            "xmin": float(self.xmin),
            "xmax": float(self.xmax),
            "ymin": float(self.ymin),
            "ymax": float(self.ymax),
            "zmin": float(self.zmin),
            "zmax": float(self.zmax),
        }

    def __repr__(self):
        return "{xmin:%.2f, xmax:%.2f, ymin:%.2f, ymax:%.2f, zmin:%.2f, zmax:%.2f}" % (
            self.xmin,
            self.xmax,
            self.ymin,
            self.ymax,
            self.zmin,
            self.zmax,
        )


@cached(cache, key=make_key)
def bounding_box(objs, loc=None, optimal=False):
    if isinstance(objs, (list, tuple)):
        compound = make_compound(objs)
    else:
        compound = objs

    return BoundingBox(
        compound if loc is None else compound.Moved(loc), optimal=optimal
    )


def np_bbox(p, t, q):
    if p.size == 0:
        return None

    n_p = p.reshape(-1, 3)
    if t is None and q is None:
        v = n_p
    else:
        n_t = np.asarray(t)
        n_q = np.quaternion(q[-1], *q[:-1])
        v = rotate_vectors([n_q], n_p)[0] + n_t

    bbmin = np.min(v, axis=0)
    bbmax = np.max(v, axis=0)
    return {
        "xmin": bbmin[0],
        "xmax": bbmax[0],
        "ymin": bbmin[1],
        "ymax": bbmax[1],
        "zmin": bbmin[2],
        "zmax": bbmax[2],
    }


def length(edge_or_wire):
    if isinstance(edge_or_wire, TopoDS_Edge):
        c = BRepAdaptor_Curve(edge_or_wire)
    else:
        c = BRepAdaptor_CompCurve(edge_or_wire)
    return GCPnts_AbscissaPoint.Length_s(c)


# Export STL


def write_stl_file(compound, filename, tolerance=None, angular_tolerance=None):
    # Remove previous mesh data
    BRepTools.Clean_s(compound)

    mesh = BRepMesh_IncrementalMesh(compound, tolerance, True, angular_tolerance)
    mesh.Perform()

    writer = StlAPI_Writer()

    result = writer.Write(compound, filename)

    # Remove the mesh data again
    BRepTools.Clean_s(compound)
    return result


# OCP serialisation


def serialize(shape):
    if shape is None:
        return None

    if platform.system() == "Darwin":
        with tempfile.NamedTemporaryFile() as tf:
            BinTools.Write_s(shape, tf.name)
            with open(tf.name, "rb") as fd:
                buffer = fd.read()
    else:
        bio = io.BytesIO()
        BinTools.Write_s(shape, bio)
        buffer = bio.getvalue()
    return buffer


def deserialize(buffer):
    if buffer is None:
        return None

    shape = TopoDS_Shape()
    if platform.system() == "Darwin":
        with tempfile.NamedTemporaryFile() as tf:
            with open(tf.name, "wb") as fd:
                fd.write(buffer)
            BinTools.Read_s(shape, tf.name)
    else:
        bio = io.BytesIO(buffer)
        BinTools.Read_s(shape, bio)
    return shape


# OCP types and accessors


def is_line(topods_edge):
    c = BRepAdaptor_Curve(topods_edge)
    return c.GetType() == GeomAbs_CurveType.GeomAbs_Line


def _get_topo(shape, topo):
    explorer = TopExp_Explorer(shape, topo)
    hashes = {}
    while explorer.More():
        item = explorer.Current()
        hash_value = item.HashCode(MAX_HASH_KEY)
        if hashes.get(hash_value) is None:
            hashes[hash_value] = True
            yield downcast(item)
        explorer.Next()


def get_solids(shape):
    return _get_topo(shape, TopAbs_SOLID)


def get_faces(shape):
    return _get_topo(shape, TopAbs_FACE)


def get_wires(shape):
    return _get_topo(shape, TopAbs_WIRE)


def get_edges(shape):
    return _get_topo(shape, TopAbs_EDGE)


def get_vertices(shape):
    return _get_topo(shape, TopAbs_VERTEX)


def get_downcasted_shape(shape):
    if next(get_solids(shape), None) is not None:
        objs = get_solids(shape)

    elif next(get_faces(shape), None) is not None:
        objs = get_faces(shape)

    elif next(get_wires(shape), None) is not None:
        objs = get_wires(shape)

    elif next(get_edges(shape), None) is not None:
        objs = get_edges(shape)

    elif next(get_vertices(shape), None) is not None:
        objs = get_vertices(shape)

    else:
        raise NotImplementedError("Unknow TopoDS Compound")

    return [downcast(obj) for obj in objs]


# Check TopLoc_Location


def is_toploc_location(obj):
    return isinstance(obj, TopLoc_Location)


# Check TopoDS shapes


def is_topods_shape(topods_shape):
    return isinstance(topods_shape, TopoDS_Shape)


def is_topods_compound(topods_shape):
    return isinstance(topods_shape, TopoDS_Compound)


def is_topods_solid(topods_shape):
    return isinstance(topods_shape, TopoDS_Solid)


def is_topods_face(topods_shape):
    return isinstance(topods_shape, TopoDS_Face)


def is_topods_wire(topods_shape):
    return isinstance(topods_shape, TopoDS_Wire)


def is_topods_edge(topods_shape):
    return isinstance(topods_shape, TopoDS_Edge)


def is_topods_vertex(topods_shape):
    return isinstance(topods_shape, TopoDS_Vertex)


def is_compound_list(topods_list):
    return all([is_topods_compound(obj) for obj in topods_list])


def is_solid_list(topods_list):
    return all([is_topods_solid(obj) for obj in topods_list])


def is_face_list(topods_list):
    return all([is_topods_face(obj) for obj in topods_list])


def is_wire_list(topods_list):
    return all([is_topods_wire(obj) for obj in topods_list])


def is_edge_list(topods_list):
    return all([is_topods_edge(obj) for obj in topods_list])


def is_vertex_list(topods_list):
    return all([is_topods_vertex(obj) for obj in topods_list])


def is_compound(obj):
    return hasattr(obj, "wrapped") and is_topods_compound(obj.wrapped)


def unroll_compound(compound):
    result = []
    for o in compound:
        if is_compound(o):
            result.extend(unroll_compound(o))
        else:
            result.extend(get_downcasted_shape(o.wrapped))
    return result


def is_mixed_compound(compound):
    if not isinstance(compound, Iterable):
        return False
    u_compound = unroll_compound(compound)
    return len(set([o.__class__.__name__ for o in u_compound])) > 1


# Check compounds for containing same types only


# def is_solids_compound(topods_shape):
#     if isinstance(topods_shape, TopoDS_Compound):
#         e = get_solids(topods_shape)
#         return next(e, None) is not None
#     return False


# def is_faces_compound(topods_shape):
#     if isinstance(topods_shape, TopoDS_Compound):
#         e = get_faces(topods_shape)
#         return next(e, None) is not None
#     return False


# def is_wires_compound(topods_shape):
#     if isinstance(topods_shape, TopoDS_Compound):
#         e = get_wires(topods_shape)
#         return next(e, None) is not None
#     return False


# def is_edges_compound(topods_shape):
#     if isinstance(topods_shape, TopoDS_Compound):
#         e = get_edges(topods_shape)
#         return next(e, None) is not None
#     return False


# def is_vertices_compound(topods_shape):
#     if isinstance(topods_shape, TopoDS_Compound):
#         e = get_vertices(topods_shape)
#         return next(e, None) is not None
#     return False


def get_point(vertex):
    p = BRep_Tool.Pnt_s(vertex)
    return (p.X(), p.Y(), p.Z())


def get_tuple(obj):
    if hasattr(obj, "to_tuple"):
        return obj.to_tuple()
    elif hasattr(obj, "toTuple"):
        return obj.toTuple()
    else:
        raise RuntimeError(f"Cannot convert {type(obj)} to tuple")


def ocp_color(r, g, b, alpha=1.0):
    return Quantity_ColorRGBA(r, g, b, alpha)


def get_rgba(color, alpha=None, def_color=None):
    color = def_color if color is None else color

    if hasattr(color, "toTuple"):  # CadQery Color
        *rgb, a = color.toTuple()

    elif hasattr(color, "percentage"):  # Alg123d Color
        rgb, a = color.percentage, color.a

    elif hasattr(color, "to_tuple"):  # Build123d
        *rgb, a = color.to_tuple()

    elif isinstance(color, Quantity_ColorRGBA):  # OCP
        ocp_rgb = color.GetRGB()
        rgb = (ocp_rgb.Red(), ocp_rgb.Green(), ocp_rgb.Blue())
        a = color.Alpha()

    elif isinstance(color, str) or isinstance(color, (tuple, list)):
        col = Color(color)
        rgb, a = col.percentage, col.a
    else:
        raise ValueError(f"Unknown color input {color} ({type(color)}")

    if alpha is not None:
        a = alpha

    return (*rgb, a)


def vertex(obj):
    if isinstance(obj, gp_Vec):
        x, y, z = obj.X(), obj.Y(), obj.Z()
    else:
        x, y, z = obj

    return downcast(BRepBuilderAPI_MakeVertex(gp_Pnt(x, y, z)).Vertex())


def line(start, end):
    return downcast(BRepBuilderAPI_MakeEdge(gp_Pnt(*start), gp_Pnt(*end)).Edge())


def cross(v1, v2):
    x = gp_Vec(*v1).Normalized()
    z = gp_Vec(*v2).Normalized()
    y = x.Crossed(z).Normalized()
    return (y.X(), y.Y(), y.Z())


def tq_to_loc(t, q):
    T = gp_Trsf()
    Q = gp_Quaternion(*q)
    V = gp_Vec(*t)
    T.SetTransformation(Q, V)
    return TopLoc_Location(T)


def loc_to_tq(loc):
    if loc is None:
        return (None, None)

    T = loc.Transformation()
    t = T.TranslationPart()
    q = T.GetRotation()
    return ((t.X(), t.Y(), t.Z()), (q.X(), q.Y(), q.Z(), q.W()))


def identity_location():
    return TopLoc_Location(gp_Trsf())


# def get_location(obj, as_none=True):
#     if obj is None:
#         return None if as_none else identity_location()
#     elif hasattr(obj, "wrapped"):
#         return obj.wrapped
#     elif isinstance(obj, TopLoc_Location):
#         return obj
#     else:
#         raise TypeError(f"Unknown location typ {type(obj)}")


def get_location(obj, as_none=True):
    if obj is None:
        return None if as_none else identity_location()
    else:
        if hasattr(obj, "loc") and obj.loc is not None:
            loc = obj.loc
        elif hasattr(obj, "location"):
            loc = obj.location
        else:
            return None if as_none else identity_location()

    if hasattr(loc, "wrapped"):
        return loc.wrapped
    elif isinstance(loc, TopLoc_Location):
        return loc
    else:
        raise TypeError(f"Unknown location typ {type(loc)}")


def copy_shape(obj):
    cls = obj.__class__
    result = cls.__new__(cls)
    result.wrapped = downcast(BRepBuilderAPI_Copy(obj.wrapped).Shape())
    result.wrapped.TShape(obj.wrapped.TShape())
    return result


def get_tshape(obj):
    if hasattr(obj, "val"):
        return obj.val().wrapped.TShape()
    elif hasattr(obj, "wrapped"):
        return obj.wrapped.TShape()
    else:
        return obj.TShape()


def get_tlocation(obj):
    if hasattr(obj, "val"):
        return obj.val().wrapped.Location()
    elif hasattr(obj, "wrapped"):
        return obj.wrapped.Location()
    else:
        return obj.Location()
