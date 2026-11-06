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
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING

from ._kernel import adapter, kernel_of
from ._show_registry import _set_occt_tessellation, tessellation_of

if TYPE_CHECKING:
    from .types import (
        KernelShape,
        TopoDS_Edge,
        TopoDS_Face,
        TopoDS_Shape,
        TopoDS_Vertex,
    )
import numpy as np
from cachetools import LRUCache, cached

# pylint: disable=no-name-in-module,import-error
from numpy.typing import NDArray

from . import trace as trace_module
from .ocp_utils import (
    bounding_box,
    extent_or_size as _extent_or_size,
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
from .protocols import CURVE_TYPES, SURFACE_TYPES, TessellationProtocol
from .trace import Trace
from .types import (
    ConvertedVertices,
    Coords,
    DiscretizedEdges,
    EdgeMapper,
    FaceMapper,
    Tessellation,
    TriangleIndices,  # noqa: F401 - public via tessellator (tests/api_surface.json)
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
            self,
            _edges_with_first_face(self.shape),
            get_edge_type,
            _faceless_edge_type,
            trace,
            trace_module.DEBUG,
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


def _edges_with_first_face(
    shape: TopoDS_Shape,
) -> Iterator[tuple[TopoDS_Edge, TopoDS_Face | None]]:
    """Every edge of the edge map with its first face, None for an edge without face."""
    k = kernel_of(shape)
    edge_map = adapter(k).TopTools_IndexedMapOfShape()
    k.TopExp.TopExp.MapShapes_s(shape, k.TopAbs.TopAbs_EDGE, edge_map)
    face_map = adapter(k).TopTools_IndexedDataMapOfShapeListOfShape()
    k.TopExp.TopExp.MapShapesAndAncestors_s(
        shape, k.TopAbs.TopAbs_EDGE, k.TopAbs.TopAbs_FACE, face_map
    )
    for i in range(1, _extent_or_size(edge_map) + 1):
        edge = adapter(k).downcast_edge(edge_map.FindKey(i))
        face = None
        if face_map.Contains(edge):
            face_list = face_map.FindFromKey(edge)
            if _extent_or_size(face_list) > 0:
                face = adapter(k).downcast_face(face_list.First())
        yield edge, face


def _faceless_edge_type(edge: TopoDS_Edge) -> int:
    """GeomAbs_CurveType of an edge without face, GeomAbs_OtherCurve without curve."""
    if is_degenerated_edge(edge):
        # BRepAdaptor_Curve raises on an edge without geometry
        t = kernel_of(edge).GeomAbs.GeomAbs_CurveType.GeomAbs_OtherCurve
        return t if isinstance(t, int) else t.value
    return get_edge_type(edge)


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
    shape: KernelShape | list[KernelShape] | tuple[KernelShape, ...],
    cache_key: str | None,
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
    if isinstance(shape, (list, tuple)):
        if len(shape) == 1:
            shape = shape[0]
        else:
            raise RuntimeError("Only single shapes are supported")

    if progress is not None:
        progress.update("+")
    # compute_faces is OCCT's alone, and no caller switches it off
    faces = {} if compute_faces is True else {"compute_faces": compute_faces}
    tessellation = tessellation_of(shape)
    mesh = tessellation.tessellate(
        shape=shape,
        deviation=deviation,
        quality=quality,
        angular_tolerance=angular_tolerance,
        compute_edges=compute_edges,
        compute_uvs=compute_uvs,
        normalize_uvs=normalize_uvs,
        shape_id=shape_id,
        debug=debug,
        **faces,
    )
    if not isinstance(tessellation, OcctTessellation):
        validate_tessellation(mesh)
    return mesh


def _occt_tessellate(
    shape: TopoDS_Shape,
    deviation: float,
    quality: float,
    angular_tolerance: float,
    compute_edges: bool = True,
    compute_uvs: bool = False,
    normalize_uvs: bool = True,
    shape_id: str = "",
    debug: bool = False,
    compute_faces: bool = True,
) -> Tessellation:
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
            # placeholder: keeps the edge numbering of get_edges
            edge_types.append(_faceless_edge_type(edge))
            segments_per_edge.append(0)
            continue

        d = discretize_edge(edge, deflection)
        if len(d) == 1 and not is_line(edge):
            # print("U", end="")
            # use another algoright with a higher accuracy to get similar result
            # Currently only happens for helix with pitch being a integer multiply of height
            d = discretize_edge(edge, deflection=deflection / 10, quasi=False)

        if len(d) == 0:
            print(f"edge {ind} ignored (could not be discretized)")
            # placeholder: keeps the edge numbering of get_edges
            edge_types.append(get_edge_type(edge))
            segments_per_edge.append(0)
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


def _check_arrays(values: Mapping[str, object], layout: dict[str, str]) -> None:
    """Every array of a kernel plugin's result is there, as the numpy array of its dtype that
    goes on the wire unchanged."""
    for key, dtype in layout.items():
        if key not in values:
            raise ValueError(f"a kernel plugin's result has no '{key}'")
        value = values[key]
        if not isinstance(value, np.ndarray) or value.dtype != dtype:
            found = getattr(value, "dtype", type(value).__name__)
            raise ValueError(f"'{key}' of a kernel plugin's result must be a {dtype} array, not {found}")


def _check_type_codes(values: Mapping[str, object], key: str, table: dict[str, int], name: str) -> None:
    """The viewer indexes a table of names with these codes."""
    codes = values[key]
    assert isinstance(codes, np.ndarray), "_check_arrays has looked"
    if len(codes) > 0 and (int(codes.min()) < 0 or int(codes.max()) >= len(table)):
        raise ValueError(f"a kernel plugin's '{key}' holds codes from {int(codes.min())} to {int(codes.max())}: the codes are those of {name}")


def _check_edge_arrays(values: Tessellation | DiscretizedEdges) -> None:
    _check_type_codes(values, "edge_types", CURVE_TYPES, "CURVE_TYPES")
    if len(values["edge_types"]) != len(values["segments_per_edge"]):
        raise ValueError("a kernel plugin's 'edge_types' and 'segments_per_edge' differ in length")
    # no edges were asked for, or there are the segments the counts say
    if len(values["edges"]) != 0 and int(values["segments_per_edge"].sum()) * 6 != len(values["edges"]):
        raise ValueError(
            f"a kernel plugin's 'segments_per_edge' count {int(values['segments_per_edge'].sum())} segments, "
            f"but 'edges' holds {len(values['edges']) / 6}"
        )


def validate_tessellation(mesh: Tessellation) -> None:
    """Check the `Tessellation` of a kernel plugin, what the viewer gets without a further
    look. The pipeline does for a plugin's mesh; a plugin's tests can call it too."""
    _check_arrays(
        mesh,
        {
            "vertices": "float32",
            "normals": "float32",
            "triangles": "int32",
            "triangles_per_face": "int32",
            "face_types": "int32",
            "edges": "float32",
            "segments_per_edge": "int32",
            "edge_types": "int32",
            "obj_vertices": "float32",
        },
    )
    if len(mesh["vertices"]) % 3 != 0 or len(mesh["normals"]) != len(mesh["vertices"]):
        raise ValueError(
            f"a kernel plugin's 'vertices' ({len(mesh['vertices'])}) must be points, "
            f"with one normal each ('normals': {len(mesh['normals'])})"
        )
    if int(mesh["triangles_per_face"].sum()) * 3 != len(mesh["triangles"]):
        raise ValueError(
            f"a kernel plugin's 'triangles_per_face' count {int(mesh['triangles_per_face'].sum())} triangles, "
            f"but 'triangles' holds {len(mesh['triangles']) / 3}"
        )
    _check_type_codes(mesh, "face_types", SURFACE_TYPES, "SURFACE_TYPES")
    if len(mesh["face_types"]) != len(mesh["triangles_per_face"]):
        raise ValueError("a kernel plugin's 'face_types' and 'triangles_per_face' differ in length")
    if len(mesh["triangles"]) > 0 and int(np.max(mesh["triangles"])) * 3 >= len(mesh["vertices"]):
        raise ValueError(f"a kernel plugin's 'triangles' point at vertex {int(np.max(mesh['triangles']))}, which it does not have")
    _check_edge_arrays(mesh)
    if "uvs" in mesh:
        _check_arrays(mesh, {"uvs": "float32"})
        if len(mesh["uvs"]) * 3 != len(mesh["vertices"]) * 2:
            raise ValueError("a kernel plugin's 'uvs' must hold one (u, v) per vertex")


def validate_edges(values: DiscretizedEdges) -> None:
    """Check the `DiscretizedEdges` of a kernel plugin."""
    _check_arrays(values, {"edges": "float32", "segments_per_edge": "int32", "edge_types": "int32", "obj_vertices": "float32"})
    _check_edge_arrays(values)


def validate_vertices(values: ConvertedVertices) -> None:
    """Check the `ConvertedVertices` of a kernel plugin."""
    _check_arrays(values, {"obj_vertices": "float32"})


class OcctTessellation(TessellationProtocol["TopoDS_Shape", "TopoDS_Edge", "TopoDS_Vertex"]):
    """OCCT's implementation of the protocol, for OCP and nanocct alike: what differs
    between the bindings lies below these functions, in `adapter(k)`. An OCCT instance
    gets its cache id in `OcpConverter.get_instance`."""

    def tessellate(
        self,
        shape,
        deviation,
        quality,
        angular_tolerance,
        compute_edges=True,
        compute_uvs=False,
        normalize_uvs=True,
        shape_id="",
        debug=False,
        compute_faces=True,
    ):
        return _occt_tessellate(
            shape,
            deviation,
            quality,
            angular_tolerance,
            compute_edges,
            compute_uvs,
            normalize_uvs,
            shape_id,
            debug,
            compute_faces,
        )

    def discretize_edges(self, edges, deflection=0.1, shape_id=""):
        return discretize_edges(edges, deflection, shape_id)

    def convert_vertices(self, vertices, shape_id=""):
        return convert_vertices(vertices, shape_id)

    def bounding_box(self, shape):
        return bounding_box(shape)


_set_occt_tessellation(OcctTessellation())


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
