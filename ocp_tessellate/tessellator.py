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

"""Tessellator class"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Iterable, Sequence

from ._kernel import adapter, kernel_of
if TYPE_CHECKING:
    from .types import (
        TopoDS_Edge,
        TopoDS_Shape,
        TopoDS_Vertex,
    )
import numpy as np
from cachetools import LRUCache, cached

# pylint: disable=no-name-in-module,import-error
from numpy.typing import NDArray

from .ocp_utils import (
    get_edge_type,
    get_edges,
    get_face_type,
    get_faces,
    get_point,
    get_vertices,
    is_degenerated_edge,
    is_line,
    make_compound,
)
from .ocp_utils import is_topods_shape as _is_topods_shape
from . import trace as trace_module
from .trace import Trace
from .types import (
    ConvertedVertices,
    DiscretizedEdges,
    EdgeMapper,
    FaceMapper,
    Coords,
    Tessellation,
    TriangleIndices,
    VertexMapper,
)
from .utils import Timer, round_sig

LOG_FILE = "ocp_tessellate.log"

#
# Caching helpers
#


def make_key(
    shape,
    cache_key,
    deviation: float,
    quality,
    angular_tolerance,
    compute_edges=True,
    compute_faces=True,
    debug=False,
    progress=None,
    shape_id=None,
    compute_uvs=False,
    normalize_uvs=True,
):  # pylint: disable=unused-argument
    # quality is a measure of bounding box and deviation, hence can be ignored (and should due to accuracy issues
    # shape_id is also ignored
    # of non optimal bounding boxes. debug and progress are also irrelevant for tessellation results)
    if not isinstance(shape, (tuple, list)):
        shape = [shape]

    key = (
        # tuple((cache_key, tuple(s.HashCode(MAX_HASH_KEY) for s in shape))),
        cache_key,
        deviation,
        angular_tolerance,
        compute_edges,
        compute_faces,
        compute_uvs,
        normalize_uvs,
    )

    if progress is not None and cache.get(key) is not None:
        progress.update("c")

    return key


def get_size(obj: object) -> int:
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum([
            get_size(v) + (len(k) if isinstance(k, str) else 0) for k, v in obj.items()
        ])
    elif isinstance(obj, np.ndarray):
        size += obj.size * obj.dtype.itemsize
    elif isinstance(obj, (tuple, list)):
        size += sum([get_size(i) for i in obj])
    return size


cache_size = os.environ.get("OCP_CACHE_SIZE_MB")
if cache_size is None:
    cache_size = 256 * 1024 * 1024
else:
    cache_size = int(cache_size) * 1024 * 1024
cache = LRUCache(maxsize=cache_size, getsizeof=get_size)


def face_mapper(shape: Sequence[TopoDS_Shape], id: str) -> FaceMapper:
    compound = make_compound(shape) if len(shape) > 1 else shape[0]
    return {
        "faces": get_faces(compound),
        "edges": get_edges(compound),
        "vertices": get_vertices(compound),
        "id": id,
    }


def edge_mapper(edges: Iterable[TopoDS_Edge], id: str) -> EdgeMapper:
    vertices: list[TopoDS_Vertex] = []
    for e in edges:
        vertices.extend(get_vertices(e))

    return {
        "edges": edges,
        "vertices": vertices,
        "id": id,
    }


def vertex_mapper(vertices: Iterable[TopoDS_Vertex], id: str) -> VertexMapper:
    return {
        "vertices": vertices,
        "id": id,
    }


class Tessellator:
    def __init__(self, shape_id: str):
        self.shape_id = shape_id
        # flat buffers: lists filled by the OCP kernel, numpy arrays by the
        # nanocct kernel; the getters convert either
        self.triangles: list[int] | NDArray[np.int64] = []  # flat triangle indices
        self.triangles_per_face: list[int] = []
        self.vertices: list[float] | NDArray[np.float64] = []  # flat triangle vertex coordinates
        self.normals: list[float] | NDArray[np.float64] = []  # flat normal coordinates
        self.uvs: list[float] | NDArray[np.float64] = []
        # point pairs, flattened by compute_edges and paired by
        # _compute_missing_edges - get_edges ravels both to the same flat array
        self.edges: (
            list[Coords | tuple[NDArray[np.float32], NDArray[np.float32]]]
            | NDArray[np.float64]
        ) = []
        self.segments_per_edge: list[int] = []

        self.obj_vertices: list[float] = []  # flat object vertex coordinates
        self.face_types: list[int] = []
        self.edge_types: list[int] = []
        # (vertex offset, vertex count, triangle offset, triangle count) of every
        # face whose triangulation has no UV nodes, so its normals cannot be read
        # off the surface and have to be interpolated from its triangles
        self.faces_without_normals: list[tuple[int, int, int, int]] = []

        self.shape: TopoDS_Shape | None = None

    def number_solids(self, shape: TopoDS_Shape) -> int:
        k = kernel_of(shape)
        count = 0
        e = k.TopExp.TopExp_Explorer(shape, k.TopAbs.TopAbs_SOLID)
        while e.More():
            count += 1
            e.Next()
        return count

    def compute(
        self,
        shape: TopoDS_Shape,
        quality: float,
        angular_tolerance: float,
        compute_faces: bool = True,
        compute_edges: bool = True,
        debug: bool = False,
        deviation: float = 0.1,
        compute_uvs: bool = False,
        normalize_uvs: bool = True,
    ):
        k = kernel_of(shape)
        self.shape = shape
        self.compute_uvs = compute_uvs
        self.normalize_uvs = normalize_uvs
        if compute_uvs and normalize_uvs:
            # Recover average dimension from quality and deviation for UV normalization.
            # quality ≈ (xsize + ysize + zsize) / 300 * deviation, so quality * 100 / deviation ≈ (x+y+z)/3
            self.bbox_max_dim = (
                max(quality * 100 / deviation, 1e-10) if deviation > 0 else 1.0
            )

        # count = self.number_solids(shape)
        with Timer(
            debug,
            "",
            "mesh incrementally",
            3,
            debug,
        ):
            # Remove previous mesh data
            # https://dev.opencascade.org/node/81262#comment-21130
            # BRepTools.Clean_s(shape)
            # print(quality, False, angular_tolerance, True)
            k.BRepMesh.BRepMesh_IncrementalMesh(shape, quality, False, angular_tolerance, True)

        trace = Trace(LOG_FILE)

        if compute_faces:
            with Timer(debug, "", "get nodes, triangles and normals", 3):
                self.tessellate(trace)

        if compute_edges:
            with Timer(debug, "", "get edges", 3):
                self.compute_edges(trace)

        for ind, v in enumerate(get_vertices(shape)):
            trace.vertex(f"{self.shape_id}/vertices/vertex{ind}", v)
            self.obj_vertices.extend(get_point(v))

        trace.close()

        # Remove mesh data again
        # BRepTools.Clean_s(shape)

    def tessellate(self, trace: Trace):
        assert self.shape is not None, "compute() sets the shape"
        # the per-face loops are binding-specific and live in the kernel
        adapter(kernel_of(self.shape)).tessellate_faces(
            self, get_faces(self.shape), get_face_type, trace
        )

    def _compute_missing_normals(self) -> NDArray[np.float32]:
        """
        Interpolate the normals of every face that has no UV nodes from its own
        triangles, leaving the faces that do have them untouched. A face owns a
        contiguous block of vertices and no triangle spans two faces, so doing
        this per face gives the same result as doing it for the whole shape when
        no face has UV nodes - and the right one when only some do.
        """
        vertices = np.asarray(self.vertices).reshape(-1, 3)
        triangles = np.asarray(self.triangles).reshape(-1, 3)
        normals = np.asarray(self.normals, dtype=np.float32).reshape(-1, 3)

        for v_offset, v_count, t_offset, t_count in self.faces_without_normals:
            block = slice(v_offset, v_offset + v_count)
            normals[block] = 0.0

            for triangle in triangles[t_offset : t_offset + t_count]:
                c = vertices[triangle]
                v1 = c[2] - c[1]
                v2 = c[0] - c[1]
                n = np.cross(v1, v2)

                # extrpolate vertex normal by blending all face normals of a vertex
                for i in triangle:
                    normals[i] += n

            # and normalize later
            for i in range(v_offset, v_offset + v_count):
                norm = np.linalg.norm(normals[i])
                normals[i] /= norm

        return normals.ravel()

    def _compute_missing_edges(self):
        # only called when no edge was found, so edges is still the empty list
        assert isinstance(self.edges, list)
        vertices = np.asarray(self.vertices).reshape(-1, 3)
        triangles = np.asarray(self.triangles).reshape(-1, 3)
        for triangle in triangles:
            c = vertices[triangle]
            self.edges.extend([(c[0], c[1]), (c[1], c[2]), (c[2], c[0])])

    def compute_edges(self, trace: Trace):
        assert self.shape is not None, "compute() sets the shape"
        # the per-edge loops are binding-specific and live in the kernel
        adapter(kernel_of(self.shape)).compute_edges(
            self, get_edges(self.shape, True), get_edge_type, trace, trace_module.DEBUG
        )

        if len(self.edges) == 0:
            self._compute_missing_edges()

    def get_vertices(self) -> NDArray[np.float32]:
        return np.asarray(self.vertices, dtype=np.float32)

    def get_triangles(self) -> NDArray[np.int32]:
        return np.asarray(self.triangles, dtype=np.int32)

    def get_triangles_per_face(self) -> NDArray[np.int32]:
        return np.asarray(self.triangles_per_face, dtype=np.int32)

    def get_face_types(self) -> NDArray[np.int32]:
        return np.asarray(self.face_types, dtype=np.int32)

    def get_edge_types(self) -> NDArray[np.int32]:
        return np.asarray(self.edge_types, dtype=np.int32)

    def get_uvs(self) -> NDArray[np.float32]:
        return np.asarray(self.uvs, dtype=np.float32)

    def get_normals(self) -> NDArray[np.float32]:
        if len(self.faces_without_normals) > 0:
            return self._compute_missing_normals()
        return np.asarray(self.normals, dtype=np.float32)

    def get_edges(self) -> NDArray[np.float32]:
        # compute_edges collects single points and _compute_missing_edges point
        # pairs, so np.asarray yields (N, 3) for the one and (N, 2, 3) for the
        # other. Ravel to the flat array every other producer of edge segments
        # returns - discretize_edges and bbox_edges
        return np.asarray(self.edges, dtype=np.float32).ravel()

    def get_segments_per_edge(self) -> NDArray[np.int32]:
        return np.asarray(self.segments_per_edge, dtype=np.int32)

    def get_obj_vertices(self) -> NDArray[np.float32]:
        return np.asarray(self.obj_vertices, dtype=np.float32)


def compute_quality(bb, deviation: float = 0.1) -> float:
    # Since tessellation caching depends on quality, try to come up with stable a quality value
    quality = round_sig(
        (round_sig(bb.xsize, 3) + round_sig(bb.ysize, 3) + round_sig(bb.zsize, 3))
        / 300
        * deviation,
        3,
    )
    return quality


# cache key: (cache_key, deviation, angular_tolerance, compute_edges, compute_faces, compute_uvs)
@cached(cache, key=make_key)
def tessellate(
    shape: TopoDS_Shape | list[TopoDS_Shape] | tuple[TopoDS_Shape, ...],
    cache_key: str,
    # only provided for managing cache:
    deviation: float,  # pylint: disable=unused-argument
    quality: float,
    angular_tolerance: float,
    compute_faces: bool = True,
    compute_edges: bool = True,
    debug: bool = False,
    progress=None,
    shape_id: str = "",
    compute_uvs: bool = False,
    normalize_uvs: bool = True,
) -> Tessellation:
    if not _is_topods_shape(shape):
        if len(shape) == 1:
            shape = shape[0]
        else:
            raise RuntimeError("Only single shapes are supported")

    if progress is not None:
        progress.update("+")
    tess = Tessellator(shape_id)
    tess.compute(
        shape,
        quality,
        angular_tolerance,
        compute_faces,
        compute_edges,
        debug,
        deviation=deviation,
        compute_uvs=compute_uvs,
        normalize_uvs=normalize_uvs,
    )

    result: Tessellation = {
        "vertices": tess.get_vertices(),
        "triangles": tess.get_triangles(),
        "normals": tess.get_normals(),
        "edges": tess.get_edges(),
        # added for version 2
        "obj_vertices": tess.get_obj_vertices(),
        "face_types": tess.get_face_types(),
        "edge_types": tess.get_edge_types(),
        # added for version 3 (optional)
        "triangles_per_face": tess.get_triangles_per_face(),
        "segments_per_edge": tess.get_segments_per_edge(),
    }
    # added for version 4 (parametric UVs, only when materials are present)
    if compute_uvs:
        result["uvs"] = tess.get_uvs()
    return result


def discretize_edge(
    edge: TopoDS_Edge, deflection: float = 0.1, quasi: bool = True
) -> NDArray[np.float32]:
    """
    Discretize an edge into a list of points.
    Args:
        edge: The edge to discretize.
        deflection: The deflection of the discretization.
        quasi: Whether to use a quasi-uniform discretization.
    Returns:
        A list of pairs of points representing the discretized edge. Shape (N, 2, 3)
    """
    k = kernel_of(edge)
    curve_adaptator = k.BRepAdaptor.BRepAdaptor_Curve(edge)

    if quasi:
        discretizer = k.GCPnts.GCPnts_QuasiUniformDeflection()
    else:
        discretizer = k.GCPnts.GCPnts_UniformDeflection()
    discretizer.Initialize(
        curve_adaptator,
        deflection,
        curve_adaptator.FirstParameter(),
        curve_adaptator.LastParameter(),
    )

    if not discretizer.IsDone():
        # e.g. a degenerate artifact edge that cannot be discretized -
        # report no segments instead of raising, callers skip empty results
        return np.empty((0, 2, 3), dtype=np.float32)

    points: list[Coords] = [
        adapter(k).coord(curve_adaptator.Value(discretizer.Parameter(i)))
        for i in range(1, discretizer.NbPoints() + 1)
    ]

    # return tuples representing the single lines of the egde
    edges: list[tuple[Coords, Coords]] = []
    for i in range(len(points) - 1):
        edges.append((points[i], points[i + 1]))

    return np.asarray(edges, dtype=np.float32)


def discretize_edges(
    edges: Iterable[TopoDS_Edge], deflection: float = 0.1, shape_id: str = ""
) -> DiscretizedEdges:
    d_edges = []
    segments_per_edge = []
    vertices = []
    edge_types = []

    trace = Trace(LOG_FILE)

    for ind, edge in enumerate(edges):
        trace.edge(f"{shape_id}/edges/edges_{ind}", edge)
        if is_degenerated_edge(edge):
            # get_edge_type and discretize_edge would raise on an edge
            # without geometry
            print(f"edge {ind} ignored (degenerated)")
            continue

        d = discretize_edge(edge, deflection)
        if len(d) == 1 and not is_line(edge):
            # print("U", end="")
            # use another algoright with a higher accuracy to get similar result
            # Currently only happens for helix with pitch being a integer multiply of height
            d = discretize_edge(edge, deflection=deflection / 10, quasi=False)

        if len(d) == 0:
            print(f"edge {ind} ignored (could not be discretized)")
            continue

        edge_types.append(get_edge_type(edge))
        d_edges.extend(d.flatten())
        segments_per_edge.append(len(d))

        for v in get_vertices(edge):
            if v not in vertices:  # ignore duplicates
                vertices.append(v)

    d_vertices = []
    for ind, v in enumerate(vertices):
        trace.vertex(f"{shape_id}/vertices/vertex{ind}", v)
        d_vertices.extend(get_point(v))

    trace.close()
    return {
        "edges": np.asarray(d_edges, dtype="float32"),
        "segments_per_edge": np.asarray(segments_per_edge, dtype="int32"),
        "edge_types": np.asarray(edge_types, dtype="int32"),
        "obj_vertices": np.asarray(d_vertices, dtype="float32"),
    }


def convert_vertices(
    vertices: Iterable[TopoDS_Vertex], shape_id: str = ""
) -> ConvertedVertices:
    n_vertices = []

    trace = Trace(LOG_FILE)

    for ind, vertex in enumerate(vertices):
        trace.vertex(f"{shape_id}/vertices/vertex{ind}", vertex)
        n_vertices.extend(get_point(vertex))

    trace.close()

    return {"obj_vertices": np.asarray(n_vertices, dtype="float32")}


def bbox_edges(bb) -> NDArray[np.float32]:
    return np.asarray(
        [
            bb["xmax"],
            bb["ymax"],
            bb["zmin"],
            bb["xmax"],
            bb["ymax"],
            bb["zmax"],
            bb["xmax"],
            bb["ymin"],
            bb["zmax"],
            bb["xmax"],
            bb["ymax"],
            bb["zmax"],
            bb["xmax"],
            bb["ymin"],
            bb["zmin"],
            bb["xmax"],
            bb["ymax"],
            bb["zmin"],
            bb["xmax"],
            bb["ymin"],
            bb["zmin"],
            bb["xmax"],
            bb["ymin"],
            bb["zmax"],
            bb["xmin"],
            bb["ymax"],
            bb["zmax"],
            bb["xmax"],
            bb["ymax"],
            bb["zmax"],
            bb["xmin"],
            bb["ymax"],
            bb["zmin"],
            bb["xmax"],
            bb["ymax"],
            bb["zmin"],
            bb["xmin"],
            bb["ymax"],
            bb["zmin"],
            bb["xmin"],
            bb["ymax"],
            bb["zmax"],
            bb["xmin"],
            bb["ymin"],
            bb["zmax"],
            bb["xmax"],
            bb["ymin"],
            bb["zmax"],
            bb["xmin"],
            bb["ymin"],
            bb["zmax"],
            bb["xmin"],
            bb["ymax"],
            bb["zmax"],
            bb["xmin"],
            bb["ymin"],
            bb["zmin"],
            bb["xmax"],
            bb["ymin"],
            bb["zmin"],
            bb["xmin"],
            bb["ymin"],
            bb["zmin"],
            bb["xmin"],
            bb["ymax"],
            bb["zmin"],
            bb["xmin"],
            bb["ymin"],
            bb["zmin"],
            bb["xmin"],
            bb["ymin"],
            bb["zmax"],
        ],
        dtype="float32",
    )
