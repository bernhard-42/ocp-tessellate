from typing import Iterable, Protocol, TypedDict

import numpy as np
from numpy.typing import NDArray
from OCP.TopoDS import TopoDS_Edge, TopoDS_Face, TopoDS_Shape, TopoDS_Vertex

Coords = tuple[float, float, float]
TriangleIndices = tuple[int, int, int]

class FaceMapper(TypedDict):
    faces: Iterable[TopoDS_Face]
    edges: Iterable[TopoDS_Edge]
    vertices: Iterable[TopoDS_Vertex]
    id: str


class EdgeMapper(TypedDict):
    edges: Iterable[TopoDS_Edge]
    vertices: Iterable[TopoDS_Vertex]
    id: str


class VertexMapper(TypedDict):
    vertices: Iterable[TopoDS_Vertex]
    id: str


class Tessellation(TypedDict):
    """
    Represents mesh tessellation data with vertices, triangles, and metadata.
    
    Attributes:
        vertices: Array of vertex positions. Shape (V, 3)
        triangles: Array of triangle indices. Shape (T, 3)
        normals: Array of normal vectors. Shape (N, 3)
        edges: List of pair of points representing the discretized edge. Shape (E, 2, 3)
        obj_vertices: Original object-space vertices. Shape (O, 3)
        face_types: Type identifier for each face. Shape (F,) See GeomAbs_Shape enum
        edge_types: Type identifier for each edge. Shape (E,) See GeomAbs_Shape enum
        triangles_per_face: Triangle count per face. Shape (F,)
        segments_per_edge: Segment count per edge. Shape (M,)
    """
    vertices: NDArray[np.float32]
    triangles: NDArray[np.int32]
    normals: NDArray[np.float32]
    edges: NDArray[np.float32]
    obj_vertices: NDArray[np.float32]
    face_types: NDArray[np.int32]
    edge_types: NDArray[np.int32]
    triangles_per_face: NDArray[np.int32]
    segments_per_edge: NDArray[np.int32]


class DiscretizedEdges(TypedDict):
    edges: NDArray[np.float32]
    segments_per_edge: NDArray[np.int32]
    edge_types: NDArray[np.int32]
    obj_vertices: NDArray[np.float32]


class ConvertedVertices(TypedDict):
    obj_vertices: NDArray[np.float32]


class TesselatorProtocol(Protocol):
    def get_vertices(self) -> NDArray[np.float32]: ...
    def get_triangles(self) -> NDArray[np.int32]: ...
    def get_normals(self) -> NDArray[np.float32]: ...
    def get_edges(self) -> NDArray[np.float32]: ...
    def get_obj_vertices(self) -> NDArray[np.float32]: ...
    def get_face_types(self) -> NDArray[np.int32]: ...
    def get_edge_types(self) -> NDArray[np.int32]: ...
    def get_triangles_per_face(self) -> NDArray[np.int32]: ...
    def get_segments_per_edge(self) -> NDArray[np.int32]: ...
    def compute(
        self,
        shape: TopoDS_Shape,
        quality: float,
        angular_tolerance: float,
        compute_faces: bool = True,
        compute_edges: bool = True,
        debug: bool = False,
    ): ...
