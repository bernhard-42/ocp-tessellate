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


"""Type predicates for OCP objects and for the wrappers around them."""

from typing_extensions import TypeIs

from .._kernel import ANY, kernel_of
from .._kernel.default import (
    gp_Ax1,
    gp_Pln,
    gp_Vec,
    TopLoc_Location,
    TopoDS_Compound,
    TopoDS_CompSolid,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Shape,
    TopoDS_Shell,
    TopoDS_Solid,
    TopoDS_Vertex,
    TopoDS_Wire,
)

from ..types import Wrapped


def is_wrapped(obj) -> TypeIs[Wrapped[object]]:
    return hasattr(obj, "wrapped")


def is_topods_shape(topods_shape) -> TypeIs[TopoDS_Shape]:
    return isinstance(topods_shape, ANY.TopoDS_Shape)


def is_topods_compound(topods_shape) -> TypeIs[TopoDS_Compound]:
    return isinstance(topods_shape, ANY.TopoDS_Compound)


def is_topods_compsolid(topods_shape) -> TypeIs[TopoDS_CompSolid]:
    return isinstance(topods_shape, ANY.TopoDS_CompSolid)


def is_topods_solid(topods_shape) -> TypeIs[TopoDS_Solid]:
    return isinstance(topods_shape, ANY.TopoDS_Solid)


def is_topods_shell(topods_shape) -> TypeIs[TopoDS_Shell]:
    return isinstance(topods_shape, ANY.TopoDS_Shell)


def is_topods_face(topods_shape) -> TypeIs[TopoDS_Face]:
    return isinstance(topods_shape, ANY.TopoDS_Face)


def is_topods_wire(topods_shape) -> TypeIs[TopoDS_Wire]:
    return isinstance(topods_shape, ANY.TopoDS_Wire)


def is_topods_edge(topods_shape) -> TypeIs[TopoDS_Edge]:
    return isinstance(topods_shape, ANY.TopoDS_Edge)


def is_topods_vertex(topods_shape) -> TypeIs[TopoDS_Vertex]:
    return isinstance(topods_shape, ANY.TopoDS_Vertex)


def is_line(topods_shape):
    k = kernel_of(topods_shape)
    c = k.BRepAdaptor_Curve(topods_shape)
    return c.GetType() == k.GeomAbs_CurveType.GeomAbs_Line


def is_degenerated_edge(edge: TopoDS_Edge) -> bool:
    """
    Detect OCCT artifact edges: flagged degenerated or carrying no 3D curve.
    Both checks are O(1); constructing a BRepAdaptor_Curve on such an edge
    would raise "BRepAdaptor_Curve::No geometry".
    """
    k = kernel_of(edge)
    if k.BRep_Tool.Degenerated_s(edge):
        return True
    loc = k.TopLoc_Location()
    return k.curve_of(edge, loc) is None


def is_degenerated_face(face: TopoDS_Face) -> bool:
    """
    Detect OCCT artifact faces carrying no geometry at all (O(1)): neither a
    surface nor a triangulation. A mesh-only face, e.g. from `import_stl`, has
    no surface by construction and carries its geometry as a triangulation, so
    the surface alone does not decide. Zero-area faces with a valid surface are
    not caught here on purpose - computing the area is expensive, and the
    mesher drops them for free (no triangulation).
    """
    k = kernel_of(face)
    return (
        k.BRep_Tool.Surface_s(face) is None
        and k.BRep_Tool.Triangulation_s(face, k.TopLoc_Location()) is None
    )


def is_toploc_location(obj) -> TypeIs[TopLoc_Location]:
    return isinstance(obj, ANY.TopLoc_Location)


def is_gp_plane(obj) -> TypeIs[gp_Pln]:
    return isinstance(obj, ANY.gp_Pln)


def is_gp_axis(obj) -> TypeIs[gp_Ax1]:
    return isinstance(obj, ANY.gp_Ax1)


def is_gp_vec(obj) -> TypeIs[gp_Vec]:
    return isinstance(obj, ANY.gp_Vec)


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


def is_closed(obj: TopoDS_Shape) -> bool:
    k = kernel_of(obj)
    return k.BRep_Tool.IsClosed_s(obj)


def is_forward(obj: TopoDS_Edge | TopoDS_Wire) -> bool:
    k = kernel_of(obj)
    return obj.Orientation() == k.TopAbs_Orientation.TopAbs_FORWARD
