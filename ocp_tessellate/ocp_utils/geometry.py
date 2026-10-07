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


"""Create OCP geometry and edges, and plane helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._kernel import adapter, kernel, kernel_of, kernel_of_all
if TYPE_CHECKING:
    from ..types import (
        Geom_Plane,
        gp_Ax1,
        gp_Ax3,
        gp_Dir,
        gp_Lin,
        gp_Pln,
        gp_Pnt,
        gp_Vec,
        TopLoc_Location,
        TopoDS_Edge,
        TopoDS_Face,
        TopoDS_Vertex,
        TopoDS_Wire,
    )

from .predicates import (
    is_gp_plane,
    is_gp_vec,
    is_toploc_location,
    is_topods_edge,
    is_topods_face,
    is_topods_vertex,
    _is_geom_plane,
    _is_gp_dir,
    _is_gp_pnt,
)
from .measure import area, length, tangent_at


def normalized(v):
    k = kernel_of(v)
    if not is_gp_vec(v):
        v = k.gp.gp_Vec(*v)
    return v.Normalized()


def cross(v1, v2):
    # one kernel for both, also when only one of them is an OCCT vector
    k = kernel_of_all((v1, v2))
    x = (v1 if is_gp_vec(v1) else k.gp.gp_Vec(*v1)).Normalized()
    z = (v2 if is_gp_vec(v2) else k.gp.gp_Vec(*v2)).Normalized()
    y = x.Crossed(z).Normalized()
    return adapter(k).coord(y)


def get_point(vertex_or_pnt: TopoDS_Vertex | gp_Pnt) -> tuple[float, float, float]:
    k = kernel_of(vertex_or_pnt)
    if is_topods_vertex(vertex_or_pnt):
        p = k.BRep.BRep_Tool.Pnt_s(vertex_or_pnt)
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


def get_plane(obj: object) -> gp_Pln | None:
    k = kernel_of(obj)
    if is_topods_edge(obj):
        finder = k.BRepBuilderAPI.BRepBuilderAPI_FindPlane(obj)
        if finder.Found():
            plane = finder.Plane()
            if _is_geom_plane(plane):
                return plane.Pln()

    elif is_topods_face(obj):
        surface = k.BRep.BRep_Tool.Surface_s(obj)
        check = k.GeomLib.GeomLib_IsPlanarSurface(surface, 1e-6)
        if check.IsPlanar() and _is_geom_plane(surface):
            # in case 1e-6 is not sufficient e.g. spline surfaces
            return surface.Pln()

    return None


def axis_to_line(axis: gp_Ax1) -> gp_Lin:
    k = kernel_of(axis)
    return k.gp.gp_Lin(axis.Location(), axis.Direction())


def vertex(obj: gp_Vec | gp_Pnt | gp_Dir | tuple[float, float, float]) -> TopoDS_Vertex:
    k = kernel_of(obj)
    if (is_gp_vec(obj) or _is_gp_pnt(obj) or _is_gp_dir(obj)):
        x, y, z = obj.X(), obj.Y(), obj.Z()
    else:
        x, y, z = obj

    return k.BRepBuilderAPI.BRepBuilderAPI_MakeVertex(k.gp.gp_Pnt(x, y, z)).Vertex()


def vector(xyz: tuple[float, float, float]) -> gp_Vec:
    k = kernel()
    return k.gp.gp_Vec(*xyz)


def axis(origin, z_dir):
    k = kernel()
    return k.gp.gp_Ax1(k.gp.gp_Pnt(*origin), k.gp.gp_Dir(*z_dir))


def rect(width: float, height: float, ax3: gp_Ax3 | None = None) -> TopoDS_Face:
    k = kernel_of(ax3)
    if ax3 is None:
        ax3 = k.gp.gp_Ax3(k.gp.gp_Pnt(0, 0, 0), k.gp.gp_Dir(0, 0, 1), k.gp.gp_Dir(1, 0, 0))
    return k.BRepBuilderAPI.BRepBuilderAPI_MakeFace(
        k.gp.gp_Pln(ax3),
        -width * 0.5,
        width * 0.5,
        -height * 0.5,
        height * 0.5,
    ).Face()


def line(
    start: gp_Pnt | gp_Vec | tuple[float, float, float],
    end: gp_Pnt | gp_Vec | tuple[float, float, float],
) -> TopoDS_Edge:
    k = kernel_of_all((start, end))
    if isinstance(start, (list, tuple)):
        start = k.gp.gp_Pnt(*start)
    if isinstance(end, (list, tuple)):
        end = k.gp.gp_Pnt(*end)
    return k.BRepBuilderAPI.BRepBuilderAPI_MakeEdge(k.gp.gp_Pnt(*adapter(k).coord(start)), k.gp.gp_Pnt(*adapter(k).coord(end))).Edge()


def circle(
    origin: gp_Pnt | tuple[float, float, float],
    z_dir: gp_Dir | tuple[float, float, float],
    radius: float,
) -> TopoDS_Edge:
    k = kernel_of_all((origin, z_dir))
    o = origin if _is_gp_pnt(origin) else k.gp.gp_Pnt(*origin)
    d = z_dir if _is_gp_dir(z_dir) else k.gp.gp_Dir(*z_dir)
    ax = k.gp.gp_Ax2(o, d)
    circle_gp = k.gp.gp_Circ(ax, radius)
    return k.BRepBuilderAPI.BRepBuilderAPI_MakeEdge(circle_gp).Edge()


def point(obj: TopoDS_Vertex | gp_Pnt) -> tuple[float, float, float]:
    k = kernel_of(obj)
    p = obj if _is_gp_pnt(obj) else k.BRep.BRep_Tool.Pnt_s(obj)
    return (p.X(), p.Y(), p.Z())


def face_center_location(face: TopoDS_Face) -> tuple[gp_Pnt, gp_Vec, gp_Vec]:
    k = kernel_of(face)
    surf = k.BRep.BRep_Tool.Surface_s(face)
    umin, umax, vmin, vmax = k.BRepTools.BRepTools.UVBounds_s(face)
    u = (umin + umax) / 2
    v = (vmin + vmax) / 2

    pnt = k.gp.gp_Pnt()
    d1u = k.gp.gp_Vec()
    d1v = k.gp.gp_Vec()
    surf.D1(u, v, pnt, d1u, d1v)

    xdir = d1u.Normalized()
    zdir = (d1u.Crossed(d1v)).Normalized()
    return pnt, xdir, zdir


def _as_plane(plane: TopoDS_Face | TopLoc_Location | gp_Pln) -> gp_Pln | Geom_Plane:
    k = kernel_of(plane)
    if is_gp_plane(plane):
        return plane
    if is_topods_face(plane):
        surface = k.BRep.BRep_Tool.Surface_s(plane)
        if not _is_geom_plane(surface):
            raise ValueError(f"Face is not planar: {plane}")
        return surface
    if is_toploc_location(plane):
        a = k.gp.gp_Ax3()
        a.Transform(plane.Transformation())
        return k.gp.gp_Pln(a)
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
    k = kernel_of(obj)
    return is_same_plane(
        obj, k.gp.gp_Pln(k.gp.gp_Ax3(k.gp.gp_Pnt(0, 0, 0), k.gp.gp_Dir(0, 0, 1), k.gp.gp_Dir(1, 0, 0)))
    )


def tangent_edge_at(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float
) -> TopoDS_Edge:
    k = kernel_of(edge_or_wire)
    pnt, dir = tangent_at(edge_or_wire, distance)
    vec = k.gp.gp_Vec(k.gp.gp_Pnt(0, 0, 0), pnt)
    vec.Add(k.gp.gp_Vec(dir))
    pnt2 = k.gp.gp_Pnt(vec.XYZ())
    return line(pnt, pnt2)


def trim_infinite_edge(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, scale: float
) -> TopoDS_Edge | TopoDS_Wire:
    k = kernel_of(edge_or_wire)
    if length(edge_or_wire) > 1e90:
        pnt, dir = tangent_at(edge_or_wire, 0.5)
        start = k.gp.gp_Vec(k.gp.gp_Pnt(0, 0, 0), pnt)
        start.Add(k.gp.gp_Vec(dir).Multiplied(-scale))
        end = k.gp.gp_Vec(k.gp.gp_Pnt(0, 0, 0), pnt)
        end.Add(k.gp.gp_Vec(dir).Multiplied(scale))
        return line(start, end)
    return edge_or_wire


def trim_infinite_face(face: TopoDS_Face, scale: float) -> TopoDS_Face:
    k = kernel_of(face)
    if area(face) > 1e90:
        pnt, xdir, zdir = face_center_location(face)
        ax3 = k.gp.gp_Ax3(pnt, k.gp.gp_Dir(zdir), k.gp.gp_Dir(xdir))
        return rect(scale, scale, ax3)
    return face
