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


"""Measure shapes: mass properties, distances, lengths, tangents."""

from .._kernel import ANY, kernel_of
from .._kernel.default import (
    gp_Dir,
    gp_Pnt,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Shape,
    TopoDS_Wire,
)

from .predicates import is_forward, is_topods_face


def center_of_mass(obj: TopoDS_Shape) -> tuple[float, float, float]:
    k = kernel_of(obj)
    if is_topods_face(obj):
        properties = k.GProp_GProps()
        k.BRepGProp.SurfaceProperties_s(obj, properties)
        center = properties.CentreOfMass()
    else:
        Properties = k.GProp_GProps()
        k.BRepGProp.VolumeProperties_s(obj, Properties)
        center = Properties.CentreOfMass()
    return (center.X(), center.Y(), center.Z())


def center_of_geometry(obj: TopoDS_Face) -> tuple[float, float, float]:
    k = kernel_of(obj)
    u0, u1, v0, v1 = k.BRepTools.UVBounds_s(obj)
    u = 0.5 * (u0 + u1)
    v = 0.5 * (v0 + v1)
    center = k.gp_Pnt()
    normal = k.gp_Vec()

    k.BRepGProp_Face(obj).Normal(u, v, center, normal)
    return (center.X(), center.Y(), center.Z())


def dist_shapes(obj1: TopoDS_Shape, obj2: TopoDS_Shape) -> tuple[float, gp_Pnt, gp_Pnt]:
    k = kernel_of(obj1)
    distCalc = k.BRepExtrema_DistShapeShape(obj1, obj2)
    distCalc.Perform()

    if distCalc.IsDone():
        # Get the minimum distance value
        distance = distCalc.Value()

        # Get points on each shape for the first solution
        point_on_shape1 = distCalc.PointOnShape1(1)
        point_on_shape2 = distCalc.PointOnShape2(1)
    return distance, point_on_shape1, point_on_shape2


def area(obj: TopoDS_Face) -> float:
    k = kernel_of(obj)
    properties = k.GProp_GProps()
    k.BRepGProp.SurfaceProperties_s(obj, properties)
    return properties.Mass()


def volume(obj: TopoDS_Shape) -> float:
    k = kernel_of(obj)
    properties = k.GProp_GProps()
    k.BRepGProp.VolumeProperties_s(obj, properties)
    return properties.Mass()


def end_points(
    obj: TopoDS_Edge,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    k = kernel_of(obj)
    curve = k.BRepAdaptor_Curve(obj)
    umin = curve.FirstParameter()
    umax = curve.LastParameter()
    e1, e2 = curve.Value(umin), curve.Value(umax)
    return (e1.X(), e1.Y(), e1.Z()), (e2.X(), e2.Y(), e2.Z())


def length(edge_or_wire: TopoDS_Edge | TopoDS_Wire) -> float:
    k = kernel_of(edge_or_wire)
    if isinstance(edge_or_wire, ANY.TopoDS_Edge):
        curve = k.BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = k.BRepAdaptor_CompCurve(edge_or_wire)
    return k.GCPnts_AbscissaPoint.Length_s(curve)


def position_at(edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float) -> gp_Pnt:
    k = kernel_of(edge_or_wire)
    if isinstance(edge_or_wire, ANY.TopoDS_Edge):
        curve = k.BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = k.BRepAdaptor_CompCurve(edge_or_wire)
    length = k.GCPnts_AbscissaPoint.Length_s(curve)
    parameter = k.GCPnts_AbscissaPoint(
        curve, length * distance, curve.FirstParameter()
    ).Parameter()
    return curve.Value(parameter)


def tangent_at(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float
) -> tuple[gp_Pnt, gp_Dir]:
    k = kernel_of(edge_or_wire)
    if isinstance(edge_or_wire, ANY.TopoDS_Edge):
        curve = k.BRepAdaptor_Curve(edge_or_wire)
    else:
        curve = k.BRepAdaptor_CompCurve(edge_or_wire)

    length = k.GCPnts_AbscissaPoint.Length_s(curve)
    parameter = k.GCPnts_AbscissaPoint(
        curve, length * distance, curve.FirstParameter()
    ).Parameter()

    pnt = k.gp_Pnt()
    vec = k.gp_Vec()
    curve.D1(parameter, pnt, vec)

    if is_forward(edge_or_wire):
        vec = vec.Reversed()
    return (pnt, k.gp_Dir(vec))
