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


"""The OCP adapter: what differs in OCP (cadquery-ocp).

Everything that is the same in both bindings the code reaches through the
binding itself (`k.gp.gp_Pnt`, see `__init__.py`). This module holds only what
differs between OCP versions and between OCP and nanocct: the TopoDS downcasts,
the TopTools map and TDF label sequence classes, the shape hash, the
out-parameter and stream conventions, the emissive factor of PBR materials,
and the tessellation loops.
`nanocct_adapter.py` provides the same names (tests/test_kernel.py).
"""

import io
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import OCP
from OCP.BinTools import BinTools, BinTools_FormatVersion_CURRENT
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp_Face
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import (
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
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Edge, TopoDS_Face, TopoDS_Shape

# The collection classes, used as adapter(k).TopTools_IndexedMapOfShape and so on
# (ruff cannot see that, hence the noqa)
if OCP.__version__.startswith("7"):
    from OCP.TDF import TDF_LabelSequence
    from OCP.TopTools import (
        TopTools_IndexedDataMapOfShapeListOfShape,
        TopTools_IndexedMapOfShape,
    )
else:
    from OCP.collections import (  # noqa: F401
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape,
        IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape,
        Sequence_TDF_Label as TDF_LabelSequence,
    )

# the emissive factor of a PBR material: a gp_Vec3f in OCP 7.9, not bound in
# OCP 8 (neither gp_Vec3f nor XCAFDoc_VisMaterialPBR.EmissiveFactor)
try:
    # OCP's stubs do not list gp_Vec3f, OCP 7.9 binds it (probed at runtime here)
    from OCP.gp import gp_Vec3f  # ty: ignore[unresolved-import]
except ImportError:
    _HAS_EMISSIVE = False
else:
    _HAS_EMISSIVE = True

if TYPE_CHECKING:
    from ..tessellator import Tessellator
    from ..trace import Trace

NAME = "ocp"


def version() -> str:
    return OCP.__version__


#
# TopoDS downcasts: static methods (`TopoDS.Vertex_s`) on OCP 7, functions of
# the TopoDS namespace (`TopoDS.Vertex`) on OCP 8
#

downcast_vertex = TopoDS.Vertex if hasattr(TopoDS, "Vertex") else TopoDS.Vertex_s
downcast_edge = TopoDS.Edge if hasattr(TopoDS, "Edge") else TopoDS.Edge_s
downcast_wire = TopoDS.Wire if hasattr(TopoDS, "Wire") else TopoDS.Wire_s
downcast_face = TopoDS.Face if hasattr(TopoDS, "Face") else TopoDS.Face_s
downcast_shell = TopoDS.Shell if hasattr(TopoDS, "Shell") else TopoDS.Shell_s
downcast_solid = TopoDS.Solid if hasattr(TopoDS, "Solid") else TopoDS.Solid_s
downcast_compsolid = (
    TopoDS.CompSolid if hasattr(TopoDS, "CompSolid") else TopoDS.CompSolid_s
)
downcast_compound = (
    TopoDS.Compound if hasattr(TopoDS, "Compound") else TopoDS.Compound_s
)

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

#
# Shape hash: OCCT 7.7 has HashCode(upper bound), later versions __hash__
#

if OCP.__version__.startswith("7.7"):

    def hash_compat(obj):
        MAX_HASH_KEY = 2147483647
        return obj.HashCode(MAX_HASH_KEY)

else:
    hash_compat = hash


#
# Calling conventions that differ between the bindings
#


def coord(obj) -> tuple[float, float, float]:
    """The coordinates of a gp_Pnt, gp_Vec, gp_Dir or gp_XYZ as a tuple."""
    return obj.Coord()


def curve_of(edge: TopoDS_Edge, loc: TopLoc_Location):
    """The 3D curve of an edge (None if it has none), BRep_Tool::Curve(E, L, First, Last)."""
    return BRep_Tool.Curve_s(edge, loc, 0.0, 0.0)


def bin_write(shape: TopoDS_Shape, triangles: bool, normals: bool) -> bytes:
    """The shape in OCCT's binary BRep format, written to memory."""
    bio = io.BytesIO()
    BinTools.Write_s(shape, bio, triangles, normals, BinTools_FormatVersion_CURRENT)
    return bio.getvalue()


def par_on_edge(extrema, solution: int, shape_index: int) -> float:
    """The edge parameter of an extrema solution, BRepExtrema_DistShapeShape::ParOnEdgeS1/S2(N, t)."""
    if shape_index == 1:
        (t,) = extrema.ParOnEdgeS1(solution)
    else:
        (t,) = extrema.ParOnEdgeS2(solution)
    return t


def emissive_of(pbr) -> tuple[float, float, float] | None:
    """XCAFDoc_VisMaterialPBR::EmissiveFactor as linear RGB, None where OCP does not bind it."""
    if _HAS_EMISSIVE is False:
        return None
    factor = pbr.EmissiveFactor
    return (factor.r(), factor.g(), factor.b())


def set_emissive(pbr, rgb: tuple[float, float, float]) -> None:
    """Set XCAFDoc_VisMaterialPBR::EmissiveFactor; nothing is set where OCP does not bind it."""
    if _HAS_EMISSIVE is False:
        return
    pbr.EmissiveFactor = gp_Vec3f(*rgb)


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

    The OCP part of Tessellator.tessellate: one Python loop per face over its
    triangulation nodes and triangles, BRepGProp_Face.Normal per node.
    """
    # the OCP kernel fills the buffers as lists (the nanocct kernel as arrays)
    assert isinstance(tess.vertices, list) and isinstance(tess.triangles, list)
    assert isinstance(tess.normals, list) and isinstance(tess.uvs, list)
    # global buffers
    p_buf = gp_Pnt()
    n_buf = gp_Vec()
    loc_buf = TopLoc_Location()

    offset = -1

    # every line below is selected for performance. Do not introduce functions to "beautify" the code
    for ind, face in enumerate(faces):
        trace.face(f"{tess.shape_id}/faces/faces_{ind}", face)
        if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
            i1, i2 = 2, 1
        else:
            i1, i2 = 1, 2

        internal = face.Orientation() == TopAbs_Orientation.TopAbs_INTERNAL

        poly = BRep_Tool.Triangulation_s(face, loc_buf)
        if poly is not None:
            # face_types must only grow for faces that produced a
            # triangulation, or it desynchronizes from triangles_per_face
            tess.face_types.append(face_type(face))

            Trsf = loc_buf.Transformation()

            # add vertices
            flat: list[float] = []
            for i in range(1, poly.NbNodes() + 1):
                flat.extend(poly.Node(i).Transformed(Trsf).Coord())
            tess.vertices.extend(flat)

            # add triangles
            flat: list[int] = []
            for i in range(1, poly.NbTriangles() + 1):
                coord: tuple[int, int, int] = poly.Triangle(i).Get()
                flat.extend((
                    coord[0] + offset,
                    coord[i1] + offset,
                    coord[i2] + offset,
                ))
            tess.triangles.extend(flat)
            tess.triangles_per_face.append(poly.NbTriangles())

            # add normals (and UVs if requested)
            if poly.HasUVNodes():
                prop = BRepGProp_Face(face)
                normals_flat: list[float] = []

                # Parametric bounds of the face. The tessellation can store a
                # node's UV one ULP outside these bounds at a parametric
                # singularity (e.g. a sphere pole), and BRepGProp_Face.Normal
                # evaluated just across the singularity returns an inward-
                # flipped normal (visible as a dark spot at the pole for radii
                # like 3, 6, 12, 24 ...). Clamp the UV used for the normal to
                # the face domain to keep the evaluation on the correct side.
                u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face)

                if tess.compute_uvs:
                    uvs_flat: list[float] = []

                    if tess.normalize_uvs:
                        # Compute physical scale per parameter unit at face center
                        # to preserve aspect ratio and consistent tile size across faces.
                        # Normalize against shape bounding box so 1 UV unit = bbox_max_dim.
                        u_mid = (u_min + u_max) / 2
                        v_mid = (v_min + v_max) / 2
                        surf = BRep_Tool.Surface_s(face)
                        d1_p = gp_Pnt()
                        d1_u = gp_Vec()
                        d1_v = gp_Vec()
                        surf.D1(u_mid, v_mid, d1_p, d1_u, d1_v)
                        scale_u = d1_u.Magnitude()  # physical length per unit of u
                        scale_v = d1_v.Magnitude()  # physical length per unit of v

                        for i in range(1, poly.NbNodes() + 1):
                            u, v = poly.UVNode(i).Coord()
                            un = min(max(u, u_min), u_max)
                            vn = min(max(v, v_min), v_max)
                            prop.Normal(un, vn, p_buf, n_buf)
                            if n_buf.SquareMagnitude() > 0:
                                n_buf.Normalize()
                            normals_flat.extend(
                                n_buf.Reversed().Coord()
                                if internal
                                else n_buf.Coord()
                            )
                            uvs_flat.append(
                                (u - u_min) * scale_u / tess.bbox_max_dim
                                if scale_u > 1e-10
                                else 0.5
                            )
                            uvs_flat.append(
                                (v - v_min) * scale_v / tess.bbox_max_dim
                                if scale_v > 1e-10
                                else 0.5
                            )
                    else:
                        # Use raw parametric UVs, matching OCCT's RWGltf_CafWriter
                        # V is flipped (1-v) per glTF convention (top-left origin)
                        for i in range(1, poly.NbNodes() + 1):
                            u, v = poly.UVNode(i).Coord()
                            un = min(max(u, u_min), u_max)
                            vn = min(max(v, v_min), v_max)
                            prop.Normal(un, vn, p_buf, n_buf)
                            if n_buf.SquareMagnitude() > 0:
                                n_buf.Normalize()
                            normals_flat.extend(
                                n_buf.Reversed().Coord()
                                if internal
                                else n_buf.Coord()
                            )
                            uvs_flat.append(u)
                            uvs_flat.append(1.0 - v)
                    tess.uvs.extend(uvs_flat)
                else:
                    for i in range(1, poly.NbNodes() + 1):
                        u, v = poly.UVNode(i).Coord()
                        un = min(max(u, u_min), u_max)
                        vn = min(max(v, v_min), v_max)
                        prop.Normal(un, vn, p_buf, n_buf)
                        if n_buf.SquareMagnitude() > 0:
                            n_buf.Normalize()
                        normals_flat.extend(
                            n_buf.Reversed().Coord() if internal else n_buf.Coord()
                        )

                tess.normals.extend(normals_flat)
            else:
                # No UV nodes (e.g. an STL import): pad so that normals stay
                # aligned with vertices, and interpolate the block later
                tess.faces_without_normals.append((
                    offset + 1,
                    poly.NbNodes(),
                    len(tess.triangles) // 3 - poly.NbTriangles(),
                    poly.NbTriangles(),
                ))
                tess.normals.extend([0.0] * (3 * poly.NbNodes()))

            offset += poly.NbNodes()
        else:
            print(f"face {ind} ignored")


def compute_edges(
    tess: "Tessellator",
    edges_with_faces: Iterable[tuple[TopoDS_Edge, TopoDS_Face]],
    edge_type: Callable[[TopoDS_Edge], int],
    trace: "Trace",
    debug: bool,
) -> None:
    """Fill the edge segments of `tess` from the polygons on triangulation of its edges.

    The OCP part of Tessellator.compute_edges: one Python loop per edge over
    the nodes of its polygon on the triangulation of its first face. Every
    edge is traced, so `debug` is not needed.
    """
    # the OCP kernel fills the buffers as lists (the nanocct kernel as arrays)
    assert isinstance(tess.edges, list)
    for ind, (edge, face) in enumerate(edges_with_faces):
        trace.edge(f"{tess.shape_id}/edges/edges_{ind}", edge)

        edges: list[tuple[float, float, float]] = []  # point pairs, flattened
        loc = TopLoc_Location()
        triangle = BRep_Tool.Triangulation_s(face, loc)
        poly = BRep_Tool.PolygonOnTriangulation_s(edge, triangle, loc)

        if poly is None:
            continue

        # edge_types must only grow for edges that produced a polygon,
        # or it desynchronizes from segments_per_edge
        tess.edge_types.append(edge_type(edge))

        if hasattr(poly, "Node"):  # OCCT > 7.5
            nrange = range(1, poly.NbNodes() + 1)
            index = poly.Node
        else:  # OCCT == 7.5
            indices = poly.Nodes()
            nrange = range(indices.Lower(), indices.Upper() + 1)
            index = indices.Value

        transf = loc.Transformation()
        v1: tuple[float, float, float] | None = None
        for j in nrange:
            v2: tuple[float, float, float] = triangle.Node(index(j)).Transformed(transf).Coord()
            if v1 is not None:
                edges.extend((v1, v2))
            v1 = v2
        tess.edges.extend(edges)
        tess.segments_per_edge.append(len(edges) // 2)
