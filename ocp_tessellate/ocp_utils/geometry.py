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

from .._kernel import ANY, kernel, kernel_of
from .._kernel.default import (
    Geom_Plane,
    gp_Ax1,
    gp_Ax3,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
    gp_Vec,
    gp_Lin,
    TopLoc_Location,
    TopoDS_Edge,
    TopoDS_Face,
    TopoDS_Vertex,
    TopoDS_Wire,
)

from .predicates import (
    is_toploc_location,
    is_topods_edge,
    is_topods_face,
    is_topods_vertex,
)
from .measure import area, length, tangent_at


def normalized(v):
    k = kernel_of(v)
    if not isinstance(v, ANY.gp_Vec):
        v = k.gp_Vec(*v)
    return v.Normalized()


def cross(v1, v2):
    x = normalized(v1)
    z = normalized(v2)
    y = x.Crossed(z).Normalized()
    return kernel_of(y).coord(y)


def get_point(vertex_or_pnt: TopoDS_Vertex | gp_Pnt) -> tuple[float, float, float]:
    k = kernel_of(vertex_or_pnt)
    if is_topods_vertex(vertex_or_pnt):
        p = k.BRep_Tool.Pnt_s(vertex_or_pnt)
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
        finder = k.BRepBuilderAPI_FindPlane(obj)
        if finder.Found():
            plane = finder.Plane()
            if isinstance(plane, ANY.Geom_Plane):
                return plane.Pln()

    elif is_topods_face(obj):
        surface = k.BRep_Tool.Surface_s(obj)
        check = k.GeomLib_IsPlanarSurface(surface, 1e-6)
        if check.IsPlanar() and isinstance(surface, ANY.Geom_Plane):
            # in case 1e-6 is not sufficient e.g. spline surfaces
            return surface.Pln()

    return None


def axis_to_line(axis: gp_Ax1) -> gp_Lin:
    k = kernel_of(axis)
    return k.gp_Lin(axis.Location(), axis.Direction())


def vertex(obj: gp_Vec | gp_Pnt | gp_Dir | tuple[float, float, float]) -> TopoDS_Vertex:
    k = kernel_of(obj)
    if isinstance(obj, (ANY.gp_Vec, ANY.gp_Pnt, ANY.gp_Dir)):
        x, y, z = obj.X(), obj.Y(), obj.Z()
    else:
        x, y, z = obj

    return k.BRepBuilderAPI_MakeVertex(k.gp_Pnt(x, y, z)).Vertex()


def vector(xyz: tuple[float, float, float]) -> gp_Vec:
    k = kernel()
    return k.gp_Vec(*xyz)


def axis(origin, z_dir):
    k = kernel()
    return k.gp_Ax1(k.gp_Pnt(*origin), k.gp_Dir(*z_dir))


def rect(width: float, height: float, ax3: gp_Ax3 | None = None) -> TopoDS_Face:
    k = kernel_of(ax3)
    if ax3 is None:
        ax3 = k.gp_Ax3(k.gp_Pnt(0, 0, 0), k.gp_Dir(0, 0, 1), k.gp_Dir(1, 0, 0))
    return k.BRepBuilderAPI_MakeFace(
        k.gp_Pln(ax3),
        -width * 0.5,
        width * 0.5,
        -height * 0.5,
        height * 0.5,
    ).Face()


def line(
    start: gp_Pnt | gp_Vec | tuple[float, float, float],
    end: gp_Pnt | gp_Vec | tuple[float, float, float],
) -> TopoDS_Edge:
    k = kernel_of(start)
    if isinstance(start, (list, tuple)):
        start = k.gp_Pnt(*start)
    if isinstance(end, (list, tuple)):
        end = k.gp_Pnt(*end)
    return k.BRepBuilderAPI_MakeEdge(k.gp_Pnt(*k.coord(start)), k.gp_Pnt(*k.coord(end))).Edge()


def circle(
    origin: gp_Pnt | tuple[float, float, float],
    z_dir: gp_Dir | tuple[float, float, float],
    radius: float,
) -> TopoDS_Edge:
    k = kernel_of(origin)
    o = origin if isinstance(origin, ANY.gp_Pnt) else k.gp_Pnt(*origin)
    d = z_dir if isinstance(z_dir, ANY.gp_Dir) else k.gp_Dir(*z_dir)
    ax = k.gp_Ax2(o, d)
    circle_gp = k.gp_Circ(ax, radius)
    return k.BRepBuilderAPI_MakeEdge(circle_gp).Edge()


def point(obj: TopoDS_Vertex | gp_Pnt) -> tuple[float, float, float]:
    k = kernel_of(obj)
    p = obj if isinstance(obj, ANY.gp_Pnt) else k.BRep_Tool.Pnt_s(obj)
    return (p.X(), p.Y(), p.Z())


def face_center_location(face: TopoDS_Face) -> tuple[gp_Pnt, gp_Vec, gp_Vec]:
    k = kernel_of(face)
    surf = k.BRep_Tool.Surface_s(face)
    umin, umax, vmin, vmax = k.BRepTools.UVBounds_s(face)
    u = (umin + umax) / 2
    v = (vmin + vmax) / 2

    pnt = k.gp_Pnt()
    d1u = k.gp_Vec()
    d1v = k.gp_Vec()
    surf.D1(u, v, pnt, d1u, d1v)

    xdir = d1u.Normalized()
    zdir = (d1u.Crossed(d1v)).Normalized()
    return pnt, xdir, zdir


def _as_plane(plane: TopoDS_Face | TopLoc_Location | gp_Pln) -> gp_Pln | Geom_Plane:
    k = kernel_of(plane)
    if isinstance(plane, ANY.gp_Pln):
        return plane
    if is_topods_face(plane):
        surface = k.BRep_Tool.Surface_s(plane)
        if not isinstance(surface, ANY.Geom_Plane):
            raise ValueError(f"Face is not planar: {plane}")
        return surface
    if is_toploc_location(plane):
        a = k.gp_Ax3()
        a.Transform(plane.Transformation())
        return k.gp_Pln(a)
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
        obj, k.gp_Pln(k.gp_Ax3(k.gp_Pnt(0, 0, 0), k.gp_Dir(0, 0, 1), k.gp_Dir(1, 0, 0)))
    )


def tangent_edge_at(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, distance: float
) -> TopoDS_Edge:
    k = kernel_of(edge_or_wire)
    pnt, dir = tangent_at(edge_or_wire, distance)
    vec = k.gp_Vec(k.gp_Pnt(0, 0, 0), pnt)
    vec.Add(k.gp_Vec(dir))
    pnt2 = k.gp_Pnt(vec.XYZ())
    return line(pnt, pnt2)


def trim_infinite_edge(
    edge_or_wire: TopoDS_Edge | TopoDS_Wire, scale: float
) -> TopoDS_Edge | TopoDS_Wire:
    k = kernel_of(edge_or_wire)
    if length(edge_or_wire) > 1e90:
        pnt, dir = tangent_at(edge_or_wire, 0.5)
        start = k.gp_Vec(k.gp_Pnt(0, 0, 0), pnt)
        start.Add(k.gp_Vec(dir).Multiplied(-scale))
        end = k.gp_Vec(k.gp_Pnt(0, 0, 0), pnt)
        end.Add(k.gp_Vec(dir).Multiplied(scale))
        return line(start, end)
    return edge_or_wire


def trim_infinite_face(face: TopoDS_Face, scale: float) -> TopoDS_Face:
    k = kernel_of(face)
    if area(face) > 1e90:
        pnt, xdir, zdir = face_center_location(face)
        ax3 = k.gp_Ax3(pnt, k.gp_Dir(zdir), k.gp_Dir(xdir))
        return rect(scale, scale, ax3)
    return face
