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
import os
import sys
import tempfile
from collections.abc import Iterable, Iterator
from typing import Literal, Protocol, TypeGuard, TypedDict, overload

# TypeIs is 3.13+ in typing; drop typing_extensions once the floor allows it
from typing_extensions import TypeIs

import numpy as np
import OCP
from cachetools import LRUCache, cached
from OCP.BinTools import BinTools, BinTools_FormatVersion_CURRENT
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import (
    BRepAdaptor_CompCurve,
    BRepAdaptor_Curve,
    BRepAdaptor_Surface,
)
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_Copy,
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeVertex,
    BRepBuilderAPI_FindPlane,
)
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.BRepTools import BRepTools
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.Geom import Geom_Plane
from OCP.GeomLib import GeomLib_IsPlanarSurface
from OCP.gp import (
    gp_Ax1,
    gp_Ax2,
    gp_Ax3,
    gp_Circ,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
    gp_Quaternion,
    gp_Trsf,
    gp_Vec,
    gp_Lin,
)
from OCP.GProp import GProp_GProps
from OCP.Quantity import Quantity_ColorRGBA, Quantity_TypeOfColor
from OCP.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_COMPSOLID,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
    TopAbs_WIRE,
    TopAbs_Orientation,
)

from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location

# Bounding Box
from OCP.TopoDS import (
    TopoDS,
    TopoDS_Builder,
    TopoDS_Compound,
    TopoDS_CompSolid,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Iterator,
    TopoDS_Shape,
    TopoDS_Shell,
    TopoDS_Solid,
    TopoDS_Vertex,
    TopoDS_Wire,
)
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)
from numpy.typing import ArrayLike

from .types import (
    Build123dBuilder,
    Build123dLineBuilder,
    Build123dPartBuilder,
    Build123dSketchBuilder,
    Build123dVector,
    Build123dLocationList,
    Build123dShape,
    Build123dShapeList,
    CadqueryAssembly,
    CadquerySketch,
    CadqueryWorkplane,
    Wrapped,
)
from .utils import Color, distance, type_name


class VectorLike(Protocol):
    def __iter__(self) -> Iterator[float]: ...


_Vertex = TopoDS.Vertex if hasattr(TopoDS, "Vertex") else TopoDS.Vertex_s
_Edge = TopoDS.Edge if hasattr(TopoDS, "Edge") else TopoDS.Edge_s
_Wire = TopoDS.Wire if hasattr(TopoDS, "Wire") else TopoDS.Wire_s
_Face = TopoDS.Face if hasattr(TopoDS, "Face") else TopoDS.Face_s
_Shell = TopoDS.Shell if hasattr(TopoDS, "Shell") else TopoDS.Shell_s
_Solid = TopoDS.Solid if hasattr(TopoDS, "Solid") else TopoDS.Solid_s
_CompSolid = TopoDS.CompSolid if hasattr(TopoDS, "CompSolid") else TopoDS.CompSolid_s
_Compound = TopoDS.Compound if hasattr(TopoDS, "Compound") else TopoDS.Compound_s
#
# %% Version


def occt_version() -> str:
    return OCP.__version__


#
# %% OCP Helpers
#

if OCP.__version__.startswith("7.7"):

    def hash_compat(obj):
        MAX_HASH_KEY = 2147483647
        return obj.HashCode(MAX_HASH_KEY)

else:
    hash_compat = hash


def ocp_hash(obj):
    if is_topods_solid(obj) or is_topods_face(obj) or is_topods_shell(obj):
        return hash_compat(obj)
    else:
        return ()


downcast_LUT = {
    TopAbs_VERTEX: _Vertex,
    TopAbs_EDGE: _Edge,
    TopAbs_WIRE: _Wire,
    TopAbs_FACE: _Face,
    TopAbs_SHELL: _Shell,
    TopAbs_SOLID: _Solid,
    TopAbs_COMPSOLID: _CompSolid,
    TopAbs_COMPOUND: _Compound,
}


def downcast(obj: TopoDS_Shape) -> TopoDS_Shape:
    d_func = downcast_LUT[obj.ShapeType()]
    return d_func(obj)


def make_compound(objs: Iterable[TopoDS_Shape]) -> TopoDS_Compound:
    comp = TopoDS_Compound()
    builder = TopoDS_Builder()
    builder.MakeCompound(comp)

    for obj in objs:
        builder.Add(comp, obj)

    return comp


def make_compsolid(objs):
    comp = TopoDS_CompSolid()
    builder = TopoDS_Builder()
    builder.MakeCompSolid(comp)

    for shape in objs:
        builder.Add(comp, shape)

    return comp


def copy_topods_shape(obj):
    result = downcast(BRepBuilderAPI_Copy(obj).Shape())
    return result


def copy_shape(obj):
    cls = obj.__class__
    result = cls.__new__(cls)
    result.wrapped = downcast(BRepBuilderAPI_Copy(obj.wrapped).Shape())
    return result


def get_tshape(obj):
    if hasattr(obj, "val"):
        return obj.val().wrapped.TShape()
    elif hasattr(obj, "wrapped"):
        return obj.wrapped.TShape()
    else:
        return obj.TShape()


def normalized(v):
    if not isinstance(v, gp_Vec):
        v = gp_Vec(*v)
    return v.Normalized()


def cross(v1, v2):
    x = normalized(v1)
    z = normalized(v2)
    y = x.Crossed(z).Normalized()
    return y.Coord()


def _has(obj, attrs):
    return all([hasattr(obj, a) for a in attrs])


#
# %% Library identifiers
#


def is_cadquery(obj) -> TypeIs[CadqueryWorkplane]:
    return _has(obj, ["objects", "ctx", "val"])


def is_cadquery_shape(obj) -> TypeIs[Wrapped[TopoDS_Shape]]:
    return _has(obj, ["wrapped", "forConstruction"]) and is_topods_shape(obj.wrapped)


def is_cadquery_assembly(obj) -> TypeIs[CadqueryAssembly]:
    return _has(obj, ["obj", "loc", "name", "children"])


def is_cadquery_massembly(obj) -> TypeGuard[CadqueryAssembly]:
    return _has(obj, ["obj", "loc", "name", "children", "mates"])


def is_cadquery_sketch(obj) -> TypeIs[CadquerySketch]:
    return (
        hasattr(obj, "_faces") and hasattr(obj, "_edges") and hasattr(obj, "_selection")
    )


def is_cadquery_empty_workplane(obj) -> TypeGuard[CadqueryWorkplane]:
    return is_cadquery(obj) and len(obj.objects) == 0

    # (len(obj.objects) == 0 or (len(obj.objects) == 1 and is_vector(obj.objects[0])))


def is_vector(obj) -> TypeIs[Build123dVector]:
    return hasattr(obj, "wrapped") and isinstance(obj.wrapped, gp_Vec)


def is_massembly(obj) -> TypeGuard[CadqueryAssembly]:
    return _has(obj, ["obj", "loc", "name", "children", "mates"])


def is_wrapped(obj) -> TypeIs[Wrapped[object]]:
    return hasattr(obj, "wrapped")


def is_build123d(obj) -> TypeIs[Build123dBuilder]:
    return _has(obj, ["_obj", "_obj_name", "_tag"]) and not isinstance(obj, type)


def is_build123d_part(obj) -> TypeGuard[Build123dPartBuilder]:
    return is_build123d(obj) and obj._obj_name == "part"


def is_build123d_sketch(obj) -> TypeGuard[Build123dSketchBuilder]:
    return is_build123d(obj) and obj._obj_name == "sketch"


def is_build123d_line(obj) -> TypeGuard[Build123dLineBuilder]:
    return is_build123d(obj) and obj._obj_name == "line"


def is_build123d_shape(obj) -> TypeIs[Build123dShape]:
    return _has(obj, ["wrapped", "children"]) and is_topods_shape(obj.wrapped)


def is_build123d_shell(obj) -> TypeIs[Wrapped[TopoDS_Shell]]:
    return hasattr(obj, "wrapped") and is_topods_shell(obj.wrapped)


def is_build123d_compound(obj) -> TypeIs[Wrapped[TopoDS_Compound]]:
    return hasattr(obj, "wrapped") and is_topods_compound(obj.wrapped)


def is_build123d_assembly(obj) -> TypeGuard[Build123dShape]:
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


def is_build123d_shapelist(obj) -> TypeIs[Build123dShapeList]:
    return (
        isinstance(obj, Iterable)
        and hasattr(obj, "first")
        and hasattr(obj, "last")
        and hasattr(obj, "filter_by")
    )


def is_build123d_locationlist(obj) -> TypeIs[Build123dLocationList]:
    return (
        isinstance(obj, Iterable)
        and hasattr(obj, "locations")
        and hasattr(obj, "__enter__")
        and hasattr(obj, "__exit__")
    )


def is_build123d_plane(obj) -> TypeIs[Wrapped[gp_Pln]]:
    return is_wrapped(obj) and is_gp_plane(obj.wrapped)


def is_build123d_location(obj) -> TypeIs[Wrapped[TopLoc_Location]]:
    return is_wrapped(obj) and is_toploc_location(obj.wrapped)


def is_build123d_axis(obj) -> TypeIs[Wrapped[gp_Ax1]]:
    return is_wrapped(obj) and is_gp_axis(obj.wrapped)


#
# %% Shape identifiers on OCP level
#


def is_topods_shape(topods_shape) -> TypeIs[TopoDS_Shape]:
    return isinstance(topods_shape, TopoDS_Shape)


def is_topods_compound(topods_shape) -> TypeIs[TopoDS_Compound]:
    return isinstance(topods_shape, TopoDS_Compound)


def is_topods_compsolid(topods_shape) -> TypeIs[TopoDS_CompSolid]:
    return isinstance(topods_shape, TopoDS_CompSolid)


def is_topods_solid(topods_shape) -> TypeIs[TopoDS_Solid]:
    return isinstance(topods_shape, TopoDS_Solid)


def is_topods_shell(topods_shape) -> TypeIs[TopoDS_Shell]:
    return isinstance(topods_shape, TopoDS_Shell)


def is_topods_face(topods_shape) -> TypeIs[TopoDS_Face]:
    return isinstance(topods_shape, TopoDS_Face)


def is_topods_wire(topods_shape) -> TypeIs[TopoDS_Wire]:
    return isinstance(topods_shape, TopoDS_Wire)


def is_topods_edge(topods_shape) -> TypeIs[TopoDS_Edge]:
    return isinstance(topods_shape, TopoDS_Edge)


def is_topods_vertex(topods_shape) -> TypeIs[TopoDS_Vertex]:
    return isinstance(topods_shape, TopoDS_Vertex)


def is_line(topods_shape):
    c = BRepAdaptor_Curve(topods_shape)
    return c.GetType() == GeomAbs_CurveType.GeomAbs_Line


def is_degenerated_edge(edge: TopoDS_Edge) -> bool:
    """
    Detect OCCT artifact edges: flagged degenerated or carrying no 3D curve.
    Both checks are O(1); constructing a BRepAdaptor_Curve on such an edge
    would raise "BRepAdaptor_Curve::No geometry".
    """
    if BRep_Tool.Degenerated_s(edge):
        return True
    loc = TopLoc_Location()
    return BRep_Tool.Curve_s(edge, loc, 0.0, 0.0) is None


def is_degenerated_face(face: TopoDS_Face) -> bool:
    """
    Detect OCCT artifact faces carrying no surface (O(1)). Zero-area faces
    with a valid surface are not caught here on purpose - computing the area
    is expensive, and the mesher drops them for free (no triangulation).
    """
    return BRep_Tool.Surface_s(face) is None


def is_toploc_location(obj) -> TypeIs[TopLoc_Location]:
    return isinstance(obj, TopLoc_Location)


def is_gp_plane(obj) -> TypeIs[gp_Pln]:
    return isinstance(obj, gp_Pln)


def is_gp_axis(obj) -> TypeIs[gp_Ax1]:
    return isinstance(obj, gp_Ax1)


def is_gp_vec(obj) -> TypeIs[gp_Vec]:
    return isinstance(obj, gp_Vec)


#
# %% Shape identifiers on build123d or CadQuery level
#


def is_shape(obj) -> TypeIs[Wrapped[TopoDS_Shape]]:
    return hasattr(obj, "wrapped") and is_topods_shape(obj.wrapped)


def is_compound(obj) -> TypeIs[Wrapped[TopoDS_Compound]]:
    return hasattr(obj, "wrapped") and is_topods_compound(obj.wrapped)


def is_compsolid(obj) -> TypeIs[Wrapped[TopoDS_CompSolid]]:
    return hasattr(obj, "wrapped") and is_topods_compsolid(obj.wrapped)


def is_solid(obj) -> TypeIs[Wrapped[TopoDS_Solid]]:
    return hasattr(obj, "wrapped") and is_topods_solid(obj.wrapped)


def is_shell(obj) -> TypeIs[Wrapped[TopoDS_Shell]]:
    return hasattr(obj, "wrapped") and is_topods_shell(obj.wrapped)


def is_face(obj) -> TypeIs[Wrapped[TopoDS_Face]]:
    return hasattr(obj, "wrapped") and is_topods_face(obj.wrapped)


def is_wire(obj) -> TypeIs[Wrapped[TopoDS_Wire]]:
    return hasattr(obj, "wrapped") and is_topods_wire(obj.wrapped)


def is_edge(obj) -> TypeIs[Wrapped[TopoDS_Edge]]:
    return hasattr(obj, "wrapped") and is_topods_edge(obj.wrapped)


def is_vertex(obj) -> TypeIs[Wrapped[TopoDS_Vertex]]:
    return hasattr(obj, "wrapped") and is_topods_vertex(obj.wrapped)


def is_ocp_color(obj) -> TypeIs[Wrapped[Quantity_ColorRGBA]]:
    # the guarded object is the wrapper, not the Quantity_ColorRGBA itself
    return hasattr(obj, "wrapped") and isinstance(obj.wrapped, Quantity_ColorRGBA)


def is_location(obj) -> TypeIs[Wrapped[TopLoc_Location]]:
    return hasattr(obj, "wrapped") and is_toploc_location(obj.wrapped)


def is_empty_compound(obj) -> bool:
    if is_wrapped(obj) and obj.wrapped is None:
        return True
    if is_compound(obj):
        if len(list(obj)) == 0:
            return True
        elif len(list(obj)) == 1:
            return is_empty_compound(list(obj)[0])
        else:
            return False
    else:
        return False


#
# %% OCP types and accessors
#


# change from occt 7.7 (Extent) to 7.8 (Size)
def extent_or_size(obj):
    if hasattr(obj, "Extent"):
        return obj.Extent()
    elif hasattr(obj, "Size"):
        return obj.Size()
    else:
        raise ValueError(f"Unknown type {type(obj)}")


def get_compounds(shape: TopoDS_Shape) -> Iterator[TopoDS_Compound]:
    compound_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_COMPOUND, compound_map)

    for i in range(1, extent_or_size(compound_map) + 1):
        yield _Compound(compound_map.FindKey(i))


def get_solids(shape: TopoDS_Shape) -> Iterator[TopoDS_Solid]:
    solid_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_SOLID, solid_map)

    for i in range(1, extent_or_size(solid_map) + 1):
        yield _Solid(solid_map.FindKey(i))


def get_faces(shape: TopoDS_Shape) -> Iterator[TopoDS_Face]:
    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)

    for i in range(1, extent_or_size(face_map) + 1):
        yield _Face(face_map.FindKey(i))


def get_wires(shape: TopoDS_Shape) -> Iterator[TopoDS_Wire]:
    wire_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_WIRE, wire_map)

    for i in range(1, extent_or_size(wire_map) + 1):
        yield _Wire(wire_map.FindKey(i))


@overload
def get_edges(
    shape: TopoDS_Shape, with_face: Literal[False] = ...
) -> Iterator[TopoDS_Edge]: ...
@overload
def get_edges(
    shape: TopoDS_Shape, with_face: Literal[True]
) -> Iterator[tuple[TopoDS_Edge, TopoDS_Face]]: ...
def get_edges(
    shape: TopoDS_Shape, with_face: bool = False
) -> Iterator[TopoDS_Edge | tuple[TopoDS_Edge, TopoDS_Face]]:
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)

    if with_face:
        face_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, face_map)

    for i in range(1, extent_or_size(edge_map) + 1):
        edge = _Edge(edge_map.FindKey(i))

        if with_face:
            face_list = face_map.FindFromKey(edge)
            if extent_or_size(face_list) == 0:
                # print("no faces")
                continue

            yield edge, _Face(face_list.First())
        else:
            yield edge


def get_vertices(shape: TopoDS_Shape) -> Iterator[TopoDS_Vertex]:
    vertex_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_VERTEX, vertex_map)

    for i in range(1, extent_or_size(vertex_map) + 1):
        yield _Vertex(vertex_map.FindKey(i))


def get_downcasted_shape(shape: TopoDS_Shape) -> Iterable[TopoDS_Shape]:
    # if next(get_compounds(shape), None) is not None:
    #     objs = get_compounds(shape)

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
        return []

    return [downcast(obj) for obj in objs]


def get_point(vertex_or_pnt: TopoDS_Vertex | gp_Pnt) -> tuple[float, float, float]:
    if is_topods_vertex(vertex_or_pnt):
        p = BRep_Tool.Pnt_s(vertex_or_pnt)
    else:
        p = vertex_or_pnt
    return (p.X(), p.Y(), p.Z())


def get_tuple(obj) -> tuple:
    if hasattr(obj, "to_tuple"):
        return obj.to_tuple()
    elif hasattr(obj, "toTuple"):
        return obj.toTuple()
    else:
        raise RuntimeError(f"Cannot convert {type(obj)} to tuple")


def get_rgba(color, alpha=None, def_color=None) -> Color | None:
    if color is None:
        if def_color is None:
            return None
        color = def_color

    if isinstance(color, Color):
        return color

    if hasattr(color, "wrapped"):  # CadQery or build123d Color
        try:
            rgba = Color(tuple(color))  # build123d
        except Exception:
            rgba = Color(color.toTuple())  # CadQuery

        if alpha is not None:
            rgba.a = alpha

    elif isinstance(color, Quantity_ColorRGBA):  # OCP
        r, g, b = color.GetRGB().Values(Quantity_TypeOfColor.Quantity_TOC_sRGB)
        rgba = Color((
            int(round(r * 255)),
            int(round(g * 255)),
            int(round(b * 255)),
            color.Alpha() if alpha is None else alpha,
        ))

    elif isinstance(color, str) or isinstance(color, (tuple, list)):
        rgba = Color(color, 1.0 if alpha is None else alpha)

    else:
        raise ValueError(f"Unknown color input {color} ({type(color)}")

    return rgba


def list_topods_compound(
    compound: TopoDS_Compound | TopoDS_CompSolid,
) -> Iterable[TopoDS_Shape]:
    iterator = TopoDS_Iterator(compound)
    while iterator.More():
        yield downcast(iterator.Value())
        iterator.Next()


def unroll_compound(compound, typ=None):
    result = []
    for o in compound:
        if is_compound(o):
            unrolled, typ = unroll_compound(o, typ)
            if len(unrolled) == 1:
                result.append(unrolled[0])
            else:
                result.append(unrolled)
        else:
            result.append(downcast(o.wrapped))
            if typ is None:
                typ = type_name(o.wrapped)
            elif typ != type_name(o.wrapped):
                typ = "mixed"
    return result, typ


def unroll_topods_compound(compound, typ=None):
    result = []

    iterator = TopoDS_Iterator(compound)
    while iterator.More():
        obj = downcast(iterator.Value())

        if is_topods_compound(obj):
            unrolled, typ = unroll_topods_compound(obj, typ)
            if len(unrolled) == 1:
                result.append(unrolled[0])
            else:
                result.append(unrolled)
        else:
            result.append(downcast(obj))
            if typ is None:
                typ = type_name(obj)
            elif typ != type_name(obj) and not (
                typ in ["Edge", "Wire"] and type_name(obj) in ["Edge", "Wire"]
            ):
                typ = "mixed"
        iterator.Next()
    return result, typ


def is_mixed_compound(compound):
    return get_compound_type(compound) == "mixed"


def get_compound_type(compound):
    if is_topods_compound(compound):
        _, typ = unroll_topods_compound(compound)
    else:
        _, typ = unroll_compound(compound)

    return typ


def get_face_type(face: TopoDS_Face) -> int:
    """
    Get the type of the face as an integer using GeomAbs_SurfaceType
    """
    t = BRepAdaptor_Surface(face).GetType()
    if isinstance(t, int):
        return t
    else:
        return t.value


def get_surface(face: TopoDS_Face) -> BRepAdaptor_Surface:
    return BRepAdaptor_Surface(face)


def get_edge_type(edge: TopoDS_Edge) -> int:
    """
    Get the type of the edge as an integer using GeomAbs_CurveType
    """
    t = BRepAdaptor_Curve(edge).GetType()
    if isinstance(t, int):
        return t
    else:
        return t.value


def get_curve(edge: TopoDS_Edge) -> BRepAdaptor_Curve:
    return BRepAdaptor_Curve(edge)


def get_plane(obj: object) -> gp_Pln | None:
    if is_topods_edge(obj):
        finder = BRepBuilderAPI_FindPlane(obj)
        if finder.Found():
            plane = finder.Plane()
            if isinstance(plane, Geom_Plane):
                return plane.Pln()

    elif is_topods_face(obj):
        surface = BRep_Tool.Surface_s(obj)
        check = GeomLib_IsPlanarSurface(surface, 1e-6)
        if check.IsPlanar() and isinstance(surface, Geom_Plane):
            # in case 1e-6 is not sufficient e.g. spline surfaces
            return surface.Pln()

    return None


def axis_to_line(axis: gp_Ax1) -> gp_Lin:
    return gp_Lin(axis.Location(), axis.Direction())


#
# %% OCP object creation
#


def ocp_color(r: float, g: float, b: float, alpha: float = 1.0) -> Quantity_ColorRGBA:
    return Quantity_ColorRGBA(r, g, b, alpha)


def vertex(obj: gp_Vec | gp_Pnt | gp_Dir | tuple[float, float, float]) -> TopoDS_Vertex:
    if isinstance(obj, (gp_Vec, gp_Pnt, gp_Dir)):
        x, y, z = obj.X(), obj.Y(), obj.Z()
    else:
        x, y, z = obj

    return BRepBuilderAPI_MakeVertex(gp_Pnt(x, y, z)).Vertex()


def vector(xyz: tuple[float, float, float]) -> gp_Vec:
    return gp_Vec(*xyz)


def axis(origin, z_dir):
    return gp_Ax1(gp_Pnt(*origin), gp_Dir(*z_dir))


def rect(width: float, height: float, ax3: gp_Ax3 | None = None) -> TopoDS_Face:
    if ax3 is None:
        ax3 = gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
    return BRepBuilderAPI_MakeFace(
        gp_Pln(ax3),
        -width * 0.5,
        width * 0.5,
        -height * 0.5,
        height * 0.5,
    ).Face()


def line(
    start: gp_Pnt | gp_Vec | tuple[float, float, float],
    end: gp_Pnt | gp_Vec | tuple[float, float, float],
) -> TopoDS_Edge:
    if isinstance(start, (list, tuple)):
        start = gp_Pnt(*start)
    if isinstance(end, (list, tuple)):
        end = gp_Pnt(*end)
    return BRepBuilderAPI_MakeEdge(gp_Pnt(*start.Coord()), gp_Pnt(*end.Coord())).Edge()


def circle(
    origin: gp_Pnt | tuple[float, float, float],
    z_dir: gp_Dir | tuple[float, float, float],
    radius: float,
) -> TopoDS_Edge:
    o = origin if isinstance(origin, gp_Pnt) else gp_Pnt(*origin)
    d = z_dir if isinstance(z_dir, gp_Dir) else gp_Dir(*z_dir)
    ax = gp_Ax2(o, d)
    circle_gp = gp_Circ(ax, radius)
    return BRepBuilderAPI_MakeEdge(circle_gp).Edge()


def center_of_mass(obj: TopoDS_Shape) -> tuple[float, float, float]:
    if is_topods_face(obj):
        properties = GProp_GProps()
        BRepGProp.SurfaceProperties_s(obj, properties)
        center = properties.CentreOfMass()
    else:
        Properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(obj, Properties)
        center = Properties.CentreOfMass()
    return (center.X(), center.Y(), center.Z())


def center_of_geometry(obj: TopoDS_Face) -> tuple[float, float, float]:
    u0, u1, v0, v1 = BRepTools.UVBounds_s(obj)
    u = 0.5 * (u0 + u1)
    v = 0.5 * (v0 + v1)
    center = gp_Pnt()
    normal = gp_Vec()

    BRepGProp_Face(obj).Normal(u, v, center, normal)
    return (center.X(), center.Y(), center.Z())


def dist_shapes(obj1: TopoDS_Shape, obj2: TopoDS_Shape) -> tuple[float, gp_Pnt, gp_Pnt]:
    distCalc = BRepExtrema_DistShapeShape(obj1, obj2)
    distCalc.Perform()

    if distCalc.IsDone():
        # Get the minimum distance value
        distance = distCalc.Value()

        # Get points on each shape for the first solution
        point_on_shape1 = distCalc.PointOnShape1(1)
        point_on_shape2 = distCalc.PointOnShape2(1)
    return distance, point_on_shape1, point_on_shape2


def area(obj: TopoDS_Face) -> float:
    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(obj, properties)
    return properties.Mass()


def volume(obj: TopoDS_Shape) -> float:
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(obj, properties)
    return properties.Mass()


def end_points(
    obj: TopoDS_Edge,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    curve = BRepAdaptor_Curve(obj)
    umin = curve.FirstParameter()
    umax = curve.LastParameter()
    e1, e2 = curve.Value(umin), curve.Value(umax)
    return (e1.X(), e1.Y(), e1.Z()), (e2.X(), e2.Y(), e2.Z())


def point(obj: TopoDS_Vertex | gp_Pnt) -> tuple[float, float, float]:
    p = obj if isinstance(obj, gp_Pnt) else BRep_Tool.Pnt_s(obj)
    return (p.X(), p.Y(), p.Z())


def is_closed(obj: TopoDS_Shape) -> bool:
    return BRep_Tool.IsClosed_s(obj)


#
# %% Location helpers
#


def tq_to_loc(
    t: tuple[float, float, float], q: tuple[float, float, float, float]
) -> TopLoc_Location:
    T = gp_Trsf()
    Q = gp_Quaternion(*q)
    V = gp_Vec(*t)
    T.SetTransformation(Q, V)
    return TopLoc_Location(T)


def loc_to_tq(
    loc: TopLoc_Location | None,
) -> (
    tuple[tuple[float, float, float], tuple[float, float, float, float]]
    | tuple[None, None]
):
    if loc is None:
        return (None, None)

    T = loc.Transformation()
    t = T.TranslationPart()
    q = T.GetRotation()
    return ((t.X(), t.Y(), t.Z()), (q.X(), q.Y(), q.Z(), q.W()))


def identity_location() -> TopLoc_Location:
    loc = TopLoc_Location()
    TopLoc_Location.Identity(loc)
    return loc


def is_identity(loc: TopLoc_Location | None) -> bool:
    # a missing location acts as identity everywhere (see OcpObject.collect)
    if loc is None:
        return True
    return loc.IsIdentity()


def relocate(obj: TopoDS_Shape) -> tuple[TopoDS_Shape, TopLoc_Location]:
    loc = get_location(obj)

    if loc is None:
        return obj, identity_location()

    obj2 = copy_topods_shape(obj)

    tshape = get_tshape(obj2)
    obj2.Move(loc.Inverted())
    obj2.TShape(tshape)

    return obj2, loc


def _call_if_callable(value: object) -> object:
    """cadquery exposes some locations as zero-argument methods."""
    if callable(value):
        # duck-typed zero-argument call, ty cannot know the signature
        return value()  # ty: ignore[call-top-callable]
    return value


@overload
def get_location(obj: object, as_none: Literal[True] = ...) -> TopLoc_Location | None: ...
@overload
def get_location(obj: object, as_none: Literal[False]) -> TopLoc_Location: ...
def get_location(obj: object, as_none: bool = True) -> TopLoc_Location | None:
    if obj is None:
        return None if as_none else identity_location()

    loc: object
    if getattr(obj, "loc", None) is not None:
        loc = getattr(obj, "loc")

    elif hasattr(obj, "location"):
        loc = _call_if_callable(getattr(obj, "location"))

    elif hasattr(obj, "to_location"):
        loc = _call_if_callable(getattr(obj, "to_location"))

    elif is_wrapped(obj) and hasattr(obj.wrapped, "Location"):
        loc = _call_if_callable(getattr(obj.wrapped, "Location"))

    elif isinstance(obj, TopLoc_Location):
        return obj

    elif is_topods_shape(obj):
        loc = obj.Location()

    else:
        return None if as_none else identity_location()

    if is_wrapped(loc):
        loc = loc.wrapped
    if isinstance(loc, TopLoc_Location):
        return loc
    raise TypeError(f"Unknown location typ {type(loc)}")


def mul_locations(
    loc1: TopLoc_Location | None, loc2: TopLoc_Location | None
) -> TopLoc_Location | None:
    if loc1 is None:
        return loc2
    if loc2 is None:
        return loc1
    return loc1 * loc2


def copy_location(loc: TopLoc_Location | None) -> TopLoc_Location | None:
    if loc is None:
        return None
    return TopLoc_Location(loc.Transformation())


class AxisCoord(TypedDict):
    origin: tuple[float, float, float]
    z_dir: tuple[float, float, float]


def get_axis_coord(axis: gp_Ax1) -> AxisCoord:
    return {
        "origin": axis.Location().Coord(),
        "z_dir": axis.Direction().Coord(),
    }


class LocationCoord(TypedDict):
    origin: tuple[float, float, float]
    x_dir: tuple[float, float, float]
    y_dir: tuple[float, float, float]
    z_dir: tuple[float, float, float]


def get_location_coord(loc: TopLoc_Location) -> LocationCoord:
    trsf = loc.Transformation()

    origin = trsf.TranslationPart()
    q = trsf.GetRotation()

    x_dir = q * gp_Vec(1, 0, 0)
    y_dir = q * gp_Vec(0, 1, 0)
    z_dir = q * gp_Vec(0, 0, 1)

    return {
        "origin": origin.Coord(),
        "x_dir": x_dir.Coord(),
        "y_dir": y_dir.Coord(),
        "z_dir": z_dir.Coord(),
    }


def loc_to_vecs(
    origin: VectorLike, x_dir: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    ax3 = gp_Ax3(gp_Pnt(*origin), gp_Dir(*z_dir), gp_Dir(*x_dir))
    o = gp_Vec(ax3.Location().XYZ())
    x = gp_Vec(ax3.XDirection().XYZ())
    y = gp_Vec(ax3.YDirection().XYZ())
    z = gp_Vec(ax3.Direction().XYZ())
    return (o, x, y, z)


def loc_from_gp_pln(pln: gp_Pln) -> TopLoc_Location:
    o = pln.Location()
    x = pln.XAxis().Direction()
    z = pln.Axis().Direction()

    ax3 = gp_Ax3(o, z, x)
    trsf = gp_Trsf()
    trsf.SetTransformation(ax3)
    trsf.Invert()
    return TopLoc_Location(trsf)


def face_center_location(face: TopoDS_Face) -> tuple[gp_Pnt, gp_Vec, gp_Vec]:
    surf = BRep_Tool.Surface_s(face)
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    u = (umin + umax) / 2
    v = (vmin + vmax) / 2

    pnt = gp_Pnt()
    d1u = gp_Vec()
    d1v = gp_Vec()
    surf.D1(u, v, pnt, d1u, d1v)

    xdir = d1u.Normalized()
    zdir = (d1u.Crossed(d1v)).Normalized()
    return pnt, xdir, zdir


#
# %% Axis helpers
#


def axis_to_vecs(
    origin: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    ax3 = gp_Ax3(gp_Pnt(*origin), gp_Dir(*z_dir))
    o = gp_Vec(ax3.Location().XYZ())
    x = gp_Vec(ax3.XDirection().XYZ())
    y = gp_Vec(ax3.YDirection().XYZ())
    z = gp_Vec(ax3.Direction().XYZ())
    return (o, x, y, z)


#
# %% Plane helpers
#


def _as_plane(plane: TopoDS_Face | TopLoc_Location | gp_Pln) -> gp_Pln | Geom_Plane:
    if isinstance(plane, gp_Pln):
        return plane
    if is_topods_face(plane):
        surface = BRep_Tool.Surface_s(plane)
        if not isinstance(surface, Geom_Plane):
            raise ValueError(f"Face is not planar: {plane}")
        return surface
    if is_toploc_location(plane):
        a = gp_Ax3()
        a.Transform(plane.Transformation())
        return gp_Pln(a)
    raise ValueError(f"Unknown plane type: {type(plane)}")


def is_same_plane(
    plane1: TopoDS_Face | TopLoc_Location | gp_Pln,
    plane2: TopoDS_Face | TopLoc_Location | gp_Pln,
) -> bool:
    first_plane = _as_plane(plane1)
    second_plane = _as_plane(plane2)

    coordSystem1 = first_plane.Position()
    coordSystem2 = second_plane.Position()

    return (
        coordSystem1.Location().IsEqual(coordSystem2.Location(), 1e-6)
        and coordSystem1.XDirection().IsEqual(coordSystem2.XDirection(), 1e-6)
        and coordSystem1.YDirection().IsEqual(coordSystem2.YDirection(), 1e-6)
        and coordSystem1.Direction().IsEqual(coordSystem2.Direction(), 1e-6)
    )


def is_plane_xy(obj: TopoDS_Face | TopLoc_Location) -> bool:
    return is_same_plane(
        obj, gp_Pln(gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)))
    )


#
# %% Bounding Box
#


# Caching helpers for bounding box


def make_key(
    objs: TopoDS_Shape | Iterable[TopoDS_Shape],
    loc: TopLoc_Location | None = None,
    optimal: bool = False,
) -> tuple[
    tuple[tuple[int, int], ...],
    tuple[tuple[float, float, float], tuple[float, float, float, float]]
    | tuple[None, None],
]:  # pylint: disable=unused-argument
    # optimal is not used and as such ignored
    if isinstance(objs, TopoDS_Shape):
        objs = [objs]

    key = (tuple(((hash_compat(s), id(s)) for s in objs)), loc_to_tq(loc))
    return key


def get_size(obj: object) -> int:
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum([get_size(v) + (len(k) if isinstance(k, str) else 0) for k, v in obj.items()])
    elif isinstance(obj, (tuple, list)):
        size += sum([get_size(i) for i in obj])
    return size


cache = LRUCache(maxsize=16 * 1024 * 1024, getsizeof=get_size)


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
        return center_of_mass(obj)

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
        self.max = max([
            abs(x)
            for x in (
                self.xmin,
                self.xmax,
                self.ymin,
                self.ymax,
                self.zmin,
                self.zmax,
            )
        ])

    def is_empty(self):
        return (
            (abs(self.xmax - self.xmin) < 0.01)
            and (abs(self.ymax - self.ymin) < 0.01)
            and (abs(self.zmax - self.zmin) < 0.01)
        )

    def max_dist_from_center(self):
        return max([
            distance(self.center, v)
            for v in itertools.product(
                (self.xmin, self.xmax),
                (self.ymin, self.ymax),
                (self.zmin, self.zmax),
            )
        ])

    def max_dist_from_origin(self):
        return max([
            np.linalg.norm(v)
            for v in itertools.product(
                (self.xmin, self.xmax),
                (self.ymin, self.ymax),
                (self.zmin, self.zmax),
            )
        ])

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
            raise ValueError("Wrong bounding box param")

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


def nested_bounding_box(objs):
    def bb(objs, total=None):
        if total is None:
            total = BoundingBox()

        if isinstance(objs, (list, tuple)):
            for obj in objs:
                total.update(bb(obj, total))
        elif isinstance(objs, dict):
            for obj in objs.values():
                total.update(bb(obj, total))
        else:
            try:
                new_bb = bounding_box(objs.wrapped)
                total.update(new_bb)
            except Exception:
                pass
        return total

    return bb(objs)


#
# %% Numpy bounding box
#


def rotate(q: tuple[float, float, float, float], v: ArrayLike) -> np.ndarray:
    x, y, z, w = q
    x2 = 2 * x * x
    y2 = 2 * y * y
    z2 = 2 * z * z
    xy = 2 * x * y
    xz = 2 * x * z
    yz = 2 * y * z
    xw = 2 * x * w
    yw = 2 * y * w
    zw = 2 * z * w

    R = np.array([
        [1 - y2 - z2, xy - zw, xz + yw],
        [xy + zw, 1 - x2 - z2, yz - xw],
        [xz - yw, yz + xw, 1 - x2 - y2],
    ])
    return np.dot(v, R.T)


class NumpyBBox(TypedDict):
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float


def np_bbox(
    p: np.ndarray,
    t: tuple[float, float, float] | np.ndarray | None = None,
    q: tuple[float, float, float, float] | None = None,
) -> NumpyBBox | None:
    if p.size == 0:
        return None

    n_p = p.reshape(-1, 3)
    if t is None or q is None:
        v = n_p
    else:
        n_t = np.asarray(t)
        v = rotate(q, n_p) + n_t

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


def is_forward(obj: TopoDS_Edge | TopoDS_Wire) -> bool:
    return obj.Orientation() == TopAbs_Orientation.TopAbs_FORWARD


def length(edge_or_wire: TopoDS_Edge | TopoDS_Wire) -> float:
    if isinstance(edge_or_wire, TopoDS_Edge):
        curve = BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = BRepAdaptor_CompCurve(edge_or_wire)
    return GCPnts_AbscissaPoint.Length_s(curve)


def position_at(edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float) -> gp_Pnt:
    if isinstance(edge_or_wire, TopoDS_Edge):
        curve = BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = BRepAdaptor_CompCurve(edge_or_wire)
    length = GCPnts_AbscissaPoint.Length_s(curve)
    parameter = GCPnts_AbscissaPoint(
        curve, length * distance, curve.FirstParameter()
    ).Parameter()
    return curve.Value(parameter)


def tangent_at(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float
) -> tuple[gp_Pnt, gp_Dir]:
    if isinstance(edge_or_wire, TopoDS_Edge):
        curve = BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = BRepAdaptor_CompCurve(edge_or_wire)

    length = GCPnts_AbscissaPoint.Length_s(curve)
    parameter = GCPnts_AbscissaPoint(
        curve, length * distance, curve.FirstParameter()
    ).Parameter()

    pnt = gp_Pnt()
    vec = gp_Vec()
    curve.D1(parameter, pnt, vec)

    if is_forward(edge_or_wire):
        vec = vec.Reversed()
    return (pnt, gp_Dir(vec))


def tangent_edge_at(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float
) -> TopoDS_Edge:
    pnt, dir = tangent_at(edge_or_wire, distance)
    vec = gp_Vec(gp_Pnt(0, 0, 0), pnt)
    vec.Add(gp_Vec(dir))
    pnt2 = gp_Pnt(vec.XYZ())
    return line(pnt, pnt2)


def trim_infinite_edge(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, scale: float
) -> TopoDS_Edge | TopoDS_Wire:
    if length(edge_or_wire) > 1e90:
        pnt, dir = tangent_at(edge_or_wire, 0.5)
        start = gp_Vec(gp_Pnt(0, 0, 0), pnt)
        start.Add(gp_Vec(dir).Multiplied(-scale))
        end = gp_Vec(gp_Pnt(0, 0, 0), pnt)
        end.Add(gp_Vec(dir).Multiplied(scale))
        return line(start, end)
    return edge_or_wire


def trim_infinite_face(face: TopoDS_Face, scale: float) -> TopoDS_Face:
    if area(face) > 1e90:
        pnt, xdir, zdir = face_center_location(face)
        ax3 = gp_Ax3(pnt, gp_Dir(zdir), gp_Dir(xdir))
        return rect(scale, scale, ax3)
    return face


# %% OCP serialisation

# TODO replace with https://github.com/MatthiasJ1/ocp_serializer when published


def serialize(
    shape: TopoDS_Shape | None, triangles: bool = False, normals: bool = False
) -> bytes | None:
    if shape is None:
        return None

    try:
        bio = io.BytesIO()
        BinTools.Write_s(shape, bio, triangles, normals, BinTools_FormatVersion_CURRENT)
        buffer = bio.getvalue()
    except Exception:
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "shape.brep")
            BinTools.Write_s(
                shape, filename, False, False, BinTools_FormatVersion_CURRENT
            )
            with open(filename, "rb") as fd:
                buffer = fd.read()
    return buffer


def deserialize(buffer: bytes | None) -> TopoDS_Shape | None:
    if buffer is None:
        return None

    shape = TopoDS_Shape()
    try:
        bio = io.BytesIO(buffer)
        BinTools.Read_s(shape, bio)
    except Exception:
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "shape.brep")
            with open(filename, "wb") as fd:
                fd.write(buffer)
            BinTools.Read_s(shape, filename)
    return shape
