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

import os
import sys

import numpy as np
from cachetools import LRUCache, cached
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepGProp import BRepGProp_Face
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.GCPnts import GCPnts_QuasiUniformAbscissa, GCPnts_QuasiUniformDeflection

# pylint: disable=no-name-in-module,import-error
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_Orientation, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location

from .ocp_utils import (
    get_edge_type,
    get_edges,
    get_face_type,
    get_faces,
    get_point,
    get_vertices,
    is_line,
    length,
    make_compound,
)
from .trace import Trace
from .utils import Timer, round_sig

try:
    from ocp_addons.tessellator import tessellate as tessellate_c

    def enable_native_tessellator():
        os.environ["NATIVE_TESSELLATOR"] = "1"

    def disable_native_tessellator():
        os.environ["NATIVE_TESSELLATOR"] = "0"

    def is_native_tessellator_enabled():
        return os.environ.get("NATIVE_TESSELLATOR") == "1"

    if os.environ.get("NATIVE_TESSELLATOR") is None:
        enable_native_tessellator()

    NATIVE = True

except ImportError:

    NATIVE = False

MAX_HASH_KEY = 2147483647
LOG_FILE = "ocp_tessellate.log"

#
# Caching helpers
#


def make_key(
    shape,
    cache_key,
    deviation,
    quality,
    angular_tolerance,
    compute_edges=True,
    compute_faces=True,
    debug=False,
    progress=None,
    shape_id=None,
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
    )

    if progress is not None and cache.get(key) is not None:
        progress.update("c")

    return key


def get_size(obj):
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum([get_size(v) + len(k) for k, v in obj.items()])
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


def face_mapper(shape, id):
    compound = make_compound(shape) if len(shape) > 1 else shape[0]
    return {
        "faces": get_faces(compound),
        "edges": get_edges(compound),
        "vertices": get_vertices(compound),
        "id": id,
    }


def edge_mapper(edges, id):
    vertices = []
    for e in edges:
        vertices.extend(get_vertices(e))

    return {
        "edges": edges,
        "vertices": vertices,
        "id": id,
    }


def vertex_mapper(vertices, id):
    return {
        "vertices": vertices,
        "id": id,
    }


class Tessellator:
    def __init__(self, shape_id):
        self.shape_id = shape_id
        self.triangles = []
        self.triangles_per_face = []
        self.vertices = []  # triangle vertices
        self.normals = []
        self.edges = []
        self.segments_per_edge = []

        self.obj_vertices = []  # object vertices
        self.face_types = []
        self.edge_types = []

        self.shape = None

    def number_solids(self, shape):
        count = 0
        e = TopExp_Explorer(shape, TopAbs_SOLID)
        while e.More():
            count += 1
            e.Next()
        return count

    def compute(
        self,
        shape,
        quality,
        angular_tolerance,
        compute_faces=True,
        compute_edges=True,
        debug=False,
    ):
        self.shape = shape

        count = self.number_solids(shape)
        with Timer(
            debug,
            "",
            f"mesh incrementally",
            3,
            debug,
        ):
            # Remove previous mesh data
            # https://dev.opencascade.org/node/81262#comment-21130
            # BRepTools.Clean_s(shape)
            # print(quality, False, angular_tolerance, True)
            BRepMesh_IncrementalMesh(shape, quality, False, angular_tolerance, True)

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

    def tessellate(self, trace):
        # global buffers
        p_buf = gp_Pnt()
        n_buf = gp_Vec()
        loc_buf = TopLoc_Location()

        offset = -1

        # every line below is selected for performance. Do not introduce functions to "beautify" the code
        for ind, face in enumerate(get_faces(self.shape)):
            trace.face(f"{self.shape_id}/faces/faces_{ind}", face)
            if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
                i1, i2 = 2, 1
            else:
                i1, i2 = 1, 2

            internal = face.Orientation() == TopAbs_Orientation.TopAbs_INTERNAL

            self.face_types.append(get_face_type(face).value)

            poly = BRep_Tool.Triangulation_s(face, loc_buf)
            if poly is not None:
                Trsf = loc_buf.Transformation()

                # add vertices
                flat = []
                for i in range(1, poly.NbNodes() + 1):
                    flat.extend(poly.Node(i).Transformed(Trsf).Coord())
                self.vertices.extend(flat)

                # add triangles
                flat = []
                for i in range(1, poly.NbTriangles() + 1):
                    coord = poly.Triangle(i).Get()
                    flat.extend(
                        (coord[0] + offset, coord[i1] + offset, coord[i2] + offset)
                    )
                self.triangles.extend(flat)
                self.triangles_per_face.append(poly.NbTriangles())

                # add normals
                if poly.HasUVNodes():
                    prop = BRepGProp_Face(face)
                    flat = []
                    for i in range(1, poly.NbNodes() + 1):
                        u, v = poly.UVNode(i).Coord()
                        prop.Normal(u, v, p_buf, n_buf)
                        if n_buf.SquareMagnitude() > 0:
                            n_buf.Normalize()
                        flat.extend(
                            n_buf.Reverse().Coord() if internal else n_buf.Coord()
                        )
                    self.normals.extend(flat)

                offset += poly.NbNodes()

    def _compute_missing_normals(self):
        vertices = np.asarray(self.vertices).reshape(-1, 3)
        triangles = np.asarray(self.triangles).reshape(-1, 3)
        self.normals = np.zeros(len(self.vertices)).reshape(-1, 3)
        for triangle in triangles:
            c = vertices[triangle]
            v1 = c[2] - c[1]
            v2 = c[0] - c[1]
            n = np.cross(v1, v2)

            # extrpolate vertex normal by blending all face normals of a vertex
            for i in triangle:
                self.normals[i] += n

        # and normalize later
        for i in range(len(self.normals)):
            norm = np.linalg.norm(self.normals[i])
            self.normals[i] /= norm
        self.normals = self.normals.ravel()

    def _compute_missing_edges(self):
        vertices = np.asarray(self.vertices).reshape(-1, 3)
        triangles = np.asarray(self.triangles).reshape(-1, 3)
        for triangle in triangles:
            c = vertices[triangle]
            self.edges.extend([(c[0], c[1]), (c[1], c[2]), (c[2], c[0])])

    def compute_edges(self, trace):
        for ind, (edge, face) in enumerate(get_edges(self.shape, True)):
            trace.edge(f"{self.shape_id}/edges/edges_{ind}", edge)
            self.edge_types.append(get_edge_type(edge).value)

            edges = []
            loc = TopLoc_Location()
            triangle = BRep_Tool.Triangulation_s(face, loc)
            poly = BRep_Tool.PolygonOnTriangulation_s(edge, triangle, loc)

            if poly is None:
                continue

            if hasattr(poly, "Node"):  # OCCT > 7.5
                nrange = range(1, poly.NbNodes() + 1)
                index = poly.Node
            else:  # OCCT == 7.5
                indices = poly.Nodes()
                nrange = range(indices.Lower(), indices.Upper() + 1)
                index = indices.Value

            transf = loc.Transformation()
            v1 = None
            for j in nrange:
                v2 = triangle.Node(index(j)).Transformed(transf).Coord()
                if v1 is not None:
                    edges.extend((v1, v2))
                v1 = v2
            self.edges.extend(edges)
            self.segments_per_edge.append(len(edges) // 2)

        if len(self.edges) == 0:
            self._compute_missing_edges()

    def get_vertices(self):
        return np.asarray(self.vertices, dtype=np.float32)

    def get_triangles(self):
        return np.asarray(self.triangles, dtype=np.int32)

    def get_triangles_per_face(self):
        return np.asarray(self.triangles_per_face, dtype=np.int32)

    def get_face_types(self):
        return np.asarray(self.face_types, dtype=np.int32)

    def get_edge_types(self):
        return np.asarray(self.edge_types, dtype=np.int32)

    def get_normals(self):
        if len(self.normals) == 0:
            self._compute_missing_normals()
        return np.asarray(self.normals, dtype=np.float32)

    def get_edges(self):
        return np.asarray(self.edges, dtype=np.float32)

    def get_segments_per_edge(self):
        return np.asarray(self.segments_per_edge, dtype=np.int32)

    def get_obj_vertices(self):
        return np.asarray(self.obj_vertices, dtype=np.float32)


class NativeTessellator:
    def __init__(self, shape_id):
        self.shape_id = shape_id
        self.mesh = None

    def compute(
        self,
        shape,
        quality,
        angular_tolerance,
        compute_faces=True,
        compute_edges=True,
        debug=False,
    ):
        self.mesh = tessellate_c(
            shape,
            quality,
            angular_tolerance,
            compute_faces,
            compute_edges,
            True,
            0,
            debug,
        )

    def get_vertices(self):
        return self.mesh.vertices

    def get_triangles(self):
        return self.mesh.triangles

    def get_triangles_per_face(self):
        return self.mesh.triangles_per_face

    def get_face_types(self):
        return self.mesh.face_types

    def get_edge_types(self):
        return self.mesh.edge_types

    def get_normals(self):
        return self.mesh.normals

    def get_edges(self):
        return self.mesh.segments

    def get_segments_per_edge(self):
        return self.mesh.segments_per_edge

    def get_obj_vertices(self):
        return self.mesh.obj_vertices


def compute_quality(bb, deviation=0.1):
    # Since tessellation caching depends on quality, try to come up with stable a quality value
    quality = round_sig(
        (round_sig(bb.xsize, 3) + round_sig(bb.ysize, 3) + round_sig(bb.zsize, 3))
        / 300
        * deviation,
        3,
    )
    return quality


# cache key: (shape.hash, cache_key, deviaton, angular_tolerance, compute_edges, compute_faces)
@cached(cache, key=make_key)
def tessellate(
    shape,
    cache_key,
    # only provided for managing cache:
    deviation: float,  # pylint: disable=unused-argument
    quality: float,
    angular_tolerance: float,
    compute_faces=True,
    compute_edges=True,
    debug=False,
    progress=None,
    shape_id="",
):
    if isinstance(shape, (list, tuple)):
        if len(shape) == 1:
            shape = shape[0]
        else:
            raise RuntimeError("Only single shapes are supported")

    # compound = (
    #     make_compound(shapes) if len(shapes) > 1 else shapes[0]
    # )  # pylint: disable=protected-access

    if NATIVE and is_native_tessellator_enabled():
        if progress is not None:
            progress.update("*")
        tess = NativeTessellator(shape_id)
    else:
        if progress is not None:
            progress.update("+")
        tess = Tessellator(shape_id)

    tess.compute(shape, quality, angular_tolerance, compute_faces, compute_edges, debug)
    return {
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


def discretize_edge(edge, deflection=0.1, num=None):
    curve_adaptator = BRepAdaptor_Curve(edge)

    if num is not None and num > 1:
        discretizer = GCPnts_QuasiUniformAbscissa()
        discretizer.Initialize(curve_adaptator, num)
    else:
        discretizer = GCPnts_QuasiUniformDeflection()
        discretizer.Initialize(
            curve_adaptator,
            deflection,
            curve_adaptator.FirstParameter(),
            curve_adaptator.LastParameter(),
        )

    if not discretizer.IsDone():
        raise AssertionError("Discretizer not done.")

    points = [
        curve_adaptator.Value(discretizer.Parameter(i)).Coord()
        for i in range(1, discretizer.NbPoints() + 1)
    ]

    # return tuples representing the single lines of the egde
    edges = []
    for i in range(len(points) - 1):
        edges.append((points[i], points[i + 1]))

    return np.asarray(edges, dtype=np.float32)


def discretize_edges(edges, deflection=0.1, shape_id=""):
    d_edges = []
    segments_per_edge = []
    vertices = []
    edge_types = []

    trace = Trace(LOG_FILE)

    for ind, edge in enumerate(edges):
        trace.edge(f"{shape_id}/edges/edges_{ind}", edge)
        edge_types.append(get_edge_type(edge).value)

        d = discretize_edge(edge, deflection)
        if len(d) == 1 and not is_line(edge):
            num = int((length(edge) / 2000) / deflection)
            d = discretize_edge(edge, deflection=deflection, num=num)

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


def convert_vertices(vertices, shape_id=""):
    n_vertices = []

    trace = Trace(LOG_FILE)

    for ind, vertex in enumerate(vertices):
        trace.vertex(f"{shape_id}/vertices/vertex{ind}", vertex)
        n_vertices.extend(get_point(vertex))

    trace.close()

    return {"obj_vertices": np.asarray(n_vertices, dtype="float32")}


def bbox_edges(bb):
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
