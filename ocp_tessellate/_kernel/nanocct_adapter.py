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


"""The nanocct adapter: what differs in nanocct.

The counterpart of `ocp_adapter.py`, with the same names (tests/test_kernel.py). nanocct binds
OCCT 8 1:1, so the differences to OCP are calling conventions: OCCT's
namespace functions are module functions (`TopoDS.Face`), out-parameters are
returned (`BRep_Tool.Curve_s`), output streams are returned
(`BinTools.Write_s`, `ParOnEdgeS1`), `Coord()` returns a gp_XYZ, the
NCollection templates are generic classes, and the emissive factor of PBR
materials is an `NCollection_Vec3<float>`. The tessellation loops run on zero-copy numpy
views of the triangulation and on nanocct's C++ helpers (nanocct.AddOns).
"""

import importlib.metadata
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, cast

import numpy as np
from nanocct import AddOns, TopoDS
from nanocct.BinTools import BinTools, BinTools_FormatVersion_CURRENT
from nanocct.BRep import BRep_Tool
from nanocct.BRepTools import BRepTools
from nanocct.gp import gp_Pnt, gp_TrsfForm, gp_Vec
from nanocct.NCollection import (
    NCollection_IndexedDataMap,
    NCollection_IndexedMap,
    NCollection_List,
    NCollection_Sequence,
)
from nanocct.Quantity import NCollection_Vec3__float
from nanocct.TDF import TDF_Label
from nanocct.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_COMPSOLID,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_Orientation,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
    TopAbs_WIRE,
)
from nanocct.TopLoc import TopLoc_Location
from nanocct.TopoDS import TopoDS_Edge, TopoDS_Face, TopoDS_Shape
from nanocct.TopTools import TopTools_ShapeMapHasher
from numpy.typing import NDArray

if TYPE_CHECKING:
    from ..tessellator import Tessellator
    from ..trace import Trace

NAME = "nanocct"

TopTools_IndexedMapOfShape = NCollection_IndexedMap[TopoDS_Shape, TopTools_ShapeMapHasher]
TopTools_IndexedDataMapOfShapeListOfShape = NCollection_IndexedDataMap[
    TopoDS_Shape, NCollection_List[TopoDS_Shape], TopTools_ShapeMapHasher
]
TDF_LabelSequence = NCollection_Sequence[TDF_Label]


def version() -> str:
    """The nanocct version; nanocct does not expose OCCT's version itself."""
    return importlib.metadata.version("nanocct")


#
# TopoDS downcasts: functions of the TopoDS namespace, as in OCCT 8
#

downcast_vertex = TopoDS.Vertex
downcast_edge = TopoDS.Edge
downcast_wire = TopoDS.Wire
downcast_face = TopoDS.Face
downcast_shell = TopoDS.Shell
downcast_solid = TopoDS.Solid
downcast_compsolid = TopoDS.CompSolid
downcast_compound = TopoDS.Compound

downcast_LUT = {
    TopAbs_VERTEX: downcast_vertex,
    TopAbs_EDGE: downcast_edge,
    TopAbs_WIRE: downcast_wire,
    TopAbs_FACE: downcast_face,
    TopAbs_SHELL: downcast_shell,
    TopAbs_SOLID: downcast_solid,
    TopAbs_COMPSOLID: downcast_compsolid,
    TopAbs_COMPOUND: downcast_compound,
}

hash_compat = hash


#
# Calling conventions that differ from OCP
#


def coord(obj) -> tuple[float, float, float]:
    """The coordinates of a gp_Pnt, gp_Vec, gp_Dir or gp_XYZ as a tuple."""
    # Coord() returns a gp_XYZ here, not a tuple
    return (obj.X(), obj.Y(), obj.Z())


def curve_of(edge: TopoDS_Edge, loc: TopLoc_Location):
    """The 3D curve of an edge (None if it has none), BRep_Tool::Curve(E, L, First, Last)."""
    curve, _first, _last = BRep_Tool.Curve_s(edge, loc)
    return curve


def bin_write(shape: TopoDS_Shape, triangles: bool, normals: bool) -> bytes:
    """The shape in OCCT's binary BRep format, written to memory."""
    return BinTools.Write_s(shape, triangles, normals, BinTools_FormatVersion_CURRENT)


def par_on_edge(extrema, solution: int, shape_index: int) -> float:
    """The edge parameter of an extrema solution, BRepExtrema_DistShapeShape::ParOnEdgeS1/S2(N, t)."""
    # the out-parameter t is returned as a float, not as a 1-tuple
    if shape_index == 1:
        return extrema.ParOnEdgeS1(solution)
    return extrema.ParOnEdgeS2(solution)


def emissive_of(pbr) -> tuple[float, float, float] | None:
    """XCAFDoc_VisMaterialPBR::EmissiveFactor as linear RGB."""
    factor = pbr.EmissiveFactor
    return (factor.r(), factor.g(), factor.b())


def set_emissive(pbr, rgb: tuple[float, float, float]) -> None:
    """Set XCAFDoc_VisMaterialPBR::EmissiveFactor (an NCollection_Vec3<float>)."""
    pbr.EmissiveFactor = NCollection_Vec3__float(*rgb)


#
# The tessellation loops of Tessellator, see tessellator.py
#


def tessellate_faces(
    tess: "Tessellator",
    faces: Iterable[TopoDS_Face],
    face_type: Callable[[TopoDS_Face], int],
    trace: "Trace",
) -> None:
    """Fill vertices, triangles, normals and UVs of `tess` from the faces of its shape.

    The nanocct part of Tessellator.tessellate: per face, numpy views of the
    triangulation's nodes, triangles and UV nodes instead of a loop per node,
    and the normals from nanocct.AddOns.Tessellator.NormalsFromSurface - the
    same clamped evaluation, normalisation and reversal for an INTERNAL face as
    the OCP loop. Same faces, same order, same outputs.
    """
    loc_buf = TopLoc_Location()
    vertices: list[np.ndarray] = []
    triangles: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    uvs: list[np.ndarray] = []
    # 0-based index of the next face's first vertex, and the triangles so far
    offset = len(tess.vertices) // 3
    n_triangles = len(tess.triangles) // 3

    for ind, face in enumerate(faces):
        trace.face(f"{tess.shape_id}/faces/faces_{ind}", face)
        orientation = face.Orientation()
        internal = orientation == TopAbs_Orientation.TopAbs_INTERNAL

        poly = BRep_Tool.Triangulation_s(face, loc_buf)
        if poly is not None:
            # face_types must only grow for faces that produced a
            # triangulation, or it desynchronizes from triangles_per_face
            tess.face_types.append(face_type(face))

            # vertices: one view, transformed only when the face is located
            nodes = np.asarray(poly.InternalNodes())
            trsf = loc_buf.Transformation()
            if trsf.Form() != gp_TrsfForm.gp_Identity:
                m = np.array(
                    [[trsf.Value(r, c) for c in range(1, 5)] for r in range(1, 4)]
                )
                nodes = nodes @ m[:, :3].T + m[:, 3]
            vertices.append(nodes.ravel())

            # triangles: OCCT's indices are 1-based, the flat buffer is 0-based
            tris = np.asarray(poly.InternalTriangles())
            if orientation == TopAbs_Orientation.TopAbs_REVERSED:
                tris = tris[:, [0, 2, 1]]
            triangles.append((tris + (offset - 1)).ravel())
            tess.triangles_per_face.append(poly.NbTriangles())

            # normals (and UVs if requested)
            if poly.HasUVNodes():
                uv = np.asarray(poly.InternalUVNodes())

                # Parametric bounds of the face. The tessellation can store a
                # node's UV one ULP outside these bounds at a parametric
                # singularity (e.g. a sphere pole), and the normal evaluated
                # just across the singularity is inward-flipped. Clamp the UV
                # used for the normal to the face domain.
                u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face)
                clamped = np.ascontiguousarray(
                    np.clip(uv, (u_min, v_min), (u_max, v_max))
                )
                normals.append(
                    AddOns.Tessellator.NormalsFromSurface(face, clamped, internal).ravel()
                )

                if tess.compute_uvs:
                    if tess.normalize_uvs:
                        # Physical scale per parameter unit at the face center, to
                        # preserve aspect ratio and a consistent tile size across
                        # faces; normalized against the shape's bounding box.
                        u_mid = (u_min + u_max) / 2
                        v_mid = (v_min + v_max) / 2
                        surf = BRep_Tool.Surface_s(face)
                        d1_p = gp_Pnt()
                        d1_u = gp_Vec()
                        d1_v = gp_Vec()
                        surf.D1(u_mid, v_mid, d1_p, d1_u, d1_v)
                        scale_u = d1_u.Magnitude()  # physical length per unit of u
                        scale_v = d1_v.Magnitude()  # physical length per unit of v
                        if scale_u > 1e-10:
                            us = (uv[:, 0] - u_min) * scale_u / tess.bbox_max_dim
                        else:
                            us = np.full(len(uv), 0.5)
                        if scale_v > 1e-10:
                            vs = (uv[:, 1] - v_min) * scale_v / tess.bbox_max_dim
                        else:
                            vs = np.full(len(uv), 0.5)
                    else:
                        # raw parametric UVs, matching OCCT's RWGltf_CafWriter;
                        # V is flipped (1-v) per glTF convention (top-left origin)
                        us = uv[:, 0]
                        vs = 1.0 - uv[:, 1]
                    uvs.append(np.column_stack((us, vs)).ravel())
            else:
                # No UV nodes (e.g. an STL import): pad so that normals stay
                # aligned with vertices, and interpolate the block later
                tess.faces_without_normals.append(
                    (offset, poly.NbNodes(), n_triangles, poly.NbTriangles())
                )
                normals.append(np.zeros(3 * poly.NbNodes()))

            offset += poly.NbNodes()
            n_triangles += poly.NbTriangles()
        else:
            print(f"face {ind} ignored")

    # the flat buffers the getters read (np.asarray(..., dtype=np.float32) etc.),
    # kept as float64 / int64 until then
    if len(vertices) > 0:
        tess.vertices = np.concatenate([np.asarray(tess.vertices, dtype=np.float64), *vertices])
        tess.triangles = np.concatenate([np.asarray(tess.triangles, dtype=np.int64), *triangles])
    if len(normals) > 0:
        tess.normals = np.concatenate([np.asarray(tess.normals, dtype=np.float64), *normals])
    if len(uvs) > 0:
        tess.uvs = np.concatenate([np.asarray(tess.uvs, dtype=np.float64), *uvs])


def compute_edges(
    tess: "Tessellator",
    edges_with_faces: Iterable[tuple[TopoDS_Edge, TopoDS_Face]],
    edge_type: Callable[[TopoDS_Edge], int],
    trace: "Trace",
    debug: bool,
) -> None:
    """Fill the edge segments of `tess` from the polygons on triangulation of its edges.

    The nanocct part of Tessellator.compute_edges: one C++ call for the whole
    shape (nanocct.AddOns.Tessellator.EdgeSegments) with the same edge map, the
    same first ancestor face and the same skips (no face, no triangulation, no
    polygon on it) as the OCP loop, so the point pairs, the segment counts and
    the GeomAbs_CurveType of each kept edge line up as there. `edges_with_faces`
    is walked only for the trace, and `edge_type` is not needed.
    """
    assert tess.shape is not None, "compute() sets the shape"
    if debug is True:
        for ind, (edge, _face) in enumerate(edges_with_faces):
            trace.edge(f"{tess.shape_id}/edges/edges_{ind}", edge)

    # the stub types the result as object; its docstring says what it is
    segments, per_edge, types = cast(
        "tuple[NDArray[np.float64], NDArray[np.int32], NDArray[np.int32]]",
        AddOns.Tessellator.EdgeSegments(tess.shape),
    )
    if len(segments) > 0:
        tess.edges = segments  # (2 * segments, 3) point pairs
    tess.segments_per_edge.extend(per_edge.tolist())
    tess.edge_types.extend(types.tolist())
