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


"""Explore, downcast, build and copy topology."""

from collections.abc import Iterable, Iterator
from typing import Literal, overload

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
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
from OCP.TopExp import TopExp
from OCP.TopoDS import (
    TopoDS_Builder,
    TopoDS_Compound,
    TopoDS_CompSolid,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Iterator,
    TopoDS_Shape,
    TopoDS_Solid,
    TopoDS_Vertex,
    TopoDS_Wire,
)

from ..utils import type_name
from .compat import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
    _CompSolid,
    _Compound,
    _Edge,
    _Face,
    _Shell,
    _Solid,
    _Vertex,
    _Wire,
)
from .predicates import is_compound, is_topods_compound


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
