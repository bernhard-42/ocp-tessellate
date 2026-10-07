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


"""Measure shapes: mass properties, distances, lengths, tangents, normals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._kernel import adapter, kernel_of, kernel_of_all
if TYPE_CHECKING:
    from types import ModuleType

    from ..types import (
        BRepExtrema_DistShapeShape,
        gp_Dir,
        gp_Pnt,
        TopoDS_Edge,
        TopoDS_Face,
        TopoDS_Shape,
        TopoDS_Shell,
        TopoDS_Wire,
    )

from .predicates import (
    is_forward,
    is_topods_edge,
    is_topods_face,
)


def center_of_mass(obj: TopoDS_Shape) -> tuple[float, float, float]:
    """The center of mass of a shape, by its highest dimension: of the volume
    of its solids, else of the area of its faces, else of the length of its
    edges, else the mean of its vertices. (A compound of solids and loose faces
    or edges is measured by volume, which OCCT computes over all its faces.)
    """
    k = kernel_of(obj)
    properties = k.GProp.GProp_GProps()
    if _contains(k, obj, k.TopAbs.TopAbs_SOLID):
        k.BRepGProp.BRepGProp.VolumeProperties_s(obj, properties)
    elif _contains(k, obj, k.TopAbs.TopAbs_FACE):
        k.BRepGProp.BRepGProp.SurfaceProperties_s(obj, properties)
    elif _contains(k, obj, k.TopAbs.TopAbs_EDGE):
        k.BRepGProp.BRepGProp.LinearProperties_s(obj, properties)
    elif _contains(k, obj, k.TopAbs.TopAbs_VERTEX):
        return _mean_of_vertices(k, obj)
    else:
        # an empty shape: no mass, CentreOfMass gives the origin
        k.BRepGProp.BRepGProp.VolumeProperties_s(obj, properties)
    center = properties.CentreOfMass()
    return (center.X(), center.Y(), center.Z())


def _contains(k: ModuleType, obj: TopoDS_Shape, shape_type) -> bool:
    """Whether obj is or contains a sub-shape of shape_type."""
    return k.TopExp.TopExp_Explorer(obj, shape_type).More()


def _mean_of_vertices(k: ModuleType, obj: TopoDS_Shape) -> tuple[float, float, float]:
    explorer = k.TopExp.TopExp_Explorer(obj, k.TopAbs.TopAbs_VERTEX)
    x = y = z = 0.0
    n = 0
    while explorer.More():
        p = k.BRep.BRep_Tool.Pnt_s(adapter(k).downcast_vertex(explorer.Current()))
        x, y, z, n = x + p.X(), y + p.Y(), z + p.Z(), n + 1
        explorer.Next()
    return (x / n, y / n, z / n)


def center_of_geometry(obj: TopoDS_Face) -> tuple[float, float, float]:
    k = kernel_of(obj)
    u0, u1, v0, v1 = k.BRepTools.BRepTools.UVBounds_s(obj)
    u = 0.5 * (u0 + u1)
    v = 0.5 * (v0 + v1)
    center = k.gp.gp_Pnt()
    normal = k.gp.gp_Vec()

    k.BRepGProp.BRepGProp_Face(obj).Normal(u, v, center, normal)
    return (center.X(), center.Y(), center.Z())


def dist_shapes(obj1: TopoDS_Shape, obj2: TopoDS_Shape) -> tuple[float, gp_Pnt, gp_Pnt]:
    k = kernel_of(obj1)
    distCalc = k.BRepExtrema.BRepExtrema_DistShapeShape(obj1, obj2)
    distCalc.Perform()

    if distCalc.IsDone():
        # Get the minimum distance value
        distance = distCalc.Value()

        # Get points on each shape for the first solution
        point_on_shape1 = distCalc.PointOnShape1(1)
        point_on_shape2 = distCalc.PointOnShape2(1)
    return distance, point_on_shape1, point_on_shape2


def area(obj: TopoDS_Face | TopoDS_Shell) -> float:
    k = kernel_of(obj)
    properties = k.GProp.GProp_GProps()
    k.BRepGProp.BRepGProp.SurfaceProperties_s(obj, properties)
    return properties.Mass()


def volume(obj: TopoDS_Shape) -> float:
    k = kernel_of(obj)
    properties = k.GProp.GProp_GProps()
    k.BRepGProp.BRepGProp.VolumeProperties_s(obj, properties)
    return properties.Mass()


def end_points(
    obj: TopoDS_Edge,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    k = kernel_of(obj)
    curve = k.BRepAdaptor.BRepAdaptor_Curve(obj)
    umin = curve.FirstParameter()
    umax = curve.LastParameter()
    e1, e2 = curve.Value(umin), curve.Value(umax)
    return (e1.X(), e1.Y(), e1.Z()), (e2.X(), e2.Y(), e2.Z())


def length(edge_or_wire: TopoDS_Edge | TopoDS_Wire) -> float:
    k = kernel_of(edge_or_wire)
    if is_topods_edge(edge_or_wire):
        curve = k.BRepAdaptor.BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = k.BRepAdaptor.BRepAdaptor_CompCurve(edge_or_wire)
    return k.GCPnts.GCPnts_AbscissaPoint.Length_s(curve)


def position_at(edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float) -> gp_Pnt:
    k = kernel_of(edge_or_wire)
    if is_topods_edge(edge_or_wire):
        curve = k.BRepAdaptor.BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = k.BRepAdaptor.BRepAdaptor_CompCurve(edge_or_wire)
    length = k.GCPnts.GCPnts_AbscissaPoint.Length_s(curve)
    parameter = k.GCPnts.GCPnts_AbscissaPoint(
        curve, length * distance, curve.FirstParameter()
    ).Parameter()
    return curve.Value(parameter)


def tangent_at(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float
) -> tuple[gp_Pnt, gp_Dir]:
    k = kernel_of(edge_or_wire)
    if is_topods_edge(edge_or_wire):
        curve = k.BRepAdaptor.BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = k.BRepAdaptor.BRepAdaptor_CompCurve(edge_or_wire)

    length = k.GCPnts.GCPnts_AbscissaPoint.Length_s(curve)
    parameter = k.GCPnts.GCPnts_AbscissaPoint(
        curve, length * distance, curve.FirstParameter()
    ).Parameter()

    pnt = k.gp.gp_Pnt()
    vec = k.gp.gp_Vec()
    curve.D1(parameter, pnt, vec)

    if is_forward(edge_or_wire):
        vec = vec.Reversed()
    return (pnt, k.gp.gp_Dir(vec))


def face_normal(face: TopoDS_Face) -> gp_Dir | None:
    """The normal of a face at the center of its UV bounds (BRepGProp_Face::Normal,
    so it follows the face orientation), None where it vanishes."""
    k = kernel_of(face)
    u0, u1, v0, v1 = k.BRepTools.BRepTools.UVBounds_s(face)
    pnt = k.gp.gp_Pnt()
    normal = k.gp.gp_Vec()
    k.BRepGProp.BRepGProp_Face(face).Normal((u0 + u1) / 2, (v0 + v1) / 2, pnt, normal)
    if normal.Magnitude() > 1e-10:
        return k.gp.gp_Dir(normal)
    return None


def closest_directions(
    shape1: TopoDS_Edge | TopoDS_Face, shape2: TopoDS_Edge | TopoDS_Face
) -> tuple[gp_Dir, gp_Dir] | None:
    """The directions of two edges or faces at their closest points: the tangent
    of an edge, the normal of a face (at the first BRepExtrema solution).

    None if BRepExtrema finds no solution or a direction is undefined there: a
    tangent or normal that vanishes, or an edge whose closest point is neither on
    the edge nor one of its vertices. A TypeError for other shapes.
    """
    for shape in (shape1, shape2):
        if not (is_topods_edge(shape) or is_topods_face(shape)):
            raise TypeError(f"closest_directions takes edges and faces, not {type(shape).__name__}")
    k = kernel_of_all((shape1, shape2))
    extrema = k.BRepExtrema.BRepExtrema_DistShapeShape(shape1, shape2)
    if not extrema.IsDone() or extrema.NbSolution() == 0:
        return None
    direction1 = _direction_at(k, shape1, extrema, 1)
    direction2 = _direction_at(k, shape2, extrema, 2)
    if direction1 is None or direction2 is None:
        return None
    return (direction1, direction2)


def _direction_at(
    k: ModuleType, shape: TopoDS_Edge | TopoDS_Face, extrema: BRepExtrema_DistShapeShape, index: int
) -> gp_Dir | None:
    if is_topods_edge(shape):
        return _edge_tangent_at(k, shape, extrema, index)
    return _face_normal_at(k, shape, extrema, index)


def _edge_tangent_at(
    k: ModuleType, edge: TopoDS_Edge, extrema: BRepExtrema_DistShapeShape, index: int
) -> gp_Dir | None:
    """The tangent of an edge at the extrema solution point of shape `index`."""
    support_types = k.BRepExtrema.BRepExtrema_SupportType
    if index == 1:
        support_type = extrema.SupportTypeShape1(1)
    else:
        support_type = extrema.SupportTypeShape2(1)

    curve = k.BRepAdaptor.BRepAdaptor_Curve(edge)

    if support_type == support_types.BRepExtrema_IsOnEdge:
        param = adapter(k).par_on_edge(extrema, 1, index)
    elif support_type == support_types.BRepExtrema_IsVertex:
        # the endpoint of the edge closest to the solution point
        if index == 1:
            pt = extrema.PointOnShape1(1)
        else:
            pt = extrema.PointOnShape2(1)
        d_first = pt.Distance(curve.Value(curve.FirstParameter()))
        d_last = pt.Distance(curve.Value(curve.LastParameter()))
        if d_first <= d_last:
            param = curve.FirstParameter()
        else:
            param = curve.LastParameter()
    else:
        return None

    pnt = k.gp.gp_Pnt()
    vec = k.gp.gp_Vec()
    curve.D1(param, pnt, vec)
    if vec.Magnitude() < 1e-10:
        return None
    return k.gp.gp_Dir(vec)


def _face_normal_at(
    k: ModuleType, face: TopoDS_Face, extrema: BRepExtrema_DistShapeShape, index: int
) -> gp_Dir | None:
    """The normal of a face at the extrema solution point of shape `index`."""
    if index == 1:
        support_type = extrema.SupportTypeShape1(1)
    else:
        support_type = extrema.SupportTypeShape2(1)

    if support_type == k.BRepExtrema.BRepExtrema_SupportType.BRepExtrema_IsInFace:
        if index == 1:
            u, v = extrema.ParOnFaceS1(1)
        else:
            u, v = extrema.ParOnFaceS2(1)
    else:
        # the solution point is on an edge or vertex of the face: project it
        if index == 1:
            pt = extrema.PointOnShape1(1)
        else:
            pt = extrema.PointOnShape2(1)
        surface = k.BRep.BRep_Tool.Surface_s(face)
        projection = k.GeomAPI.GeomAPI_ProjectPointOnSurf(pt, surface)
        if projection.NbPoints() == 0:
            return None
        u, v = projection.Parameters(1)

    pnt = k.gp.gp_Pnt()
    normal = k.gp.gp_Vec()
    k.BRepGProp.BRepGProp_Face(face).Normal(u, v, pnt, normal)
    if normal.Magnitude() < 1e-10:
        return None
    return k.gp.gp_Dir(normal)
