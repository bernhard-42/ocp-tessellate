from typing import Iterable, Iterator, Protocol, Sequence, TypeVar

# On Python 3.10, NotRequired only works with typing_extensions' TypedDict,
# so both must come from there until the floor is 3.11
from typing_extensions import NotRequired, TypedDict

import numpy as np
from numpy.typing import NDArray
from OCP.gp import gp_Vec
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Edge, TopoDS_Face, TopoDS_Shape, TopoDS_Vertex

from ocp_tessellate.utils import Color

Coords = tuple[float, float, float]
TriangleIndices = tuple[int, int, int]

T_co = TypeVar("T_co", covariant=True)


# ocp_tessellate must not import build123d or CadQuery, so their objects are
# recognized by duck typing (the is_* predicates in ocp_utils) and described
# here as Protocols. Each Protocol lists the attributes the corresponding
# predicate tests plus the attributes ocp_tessellate accesses afterwards -
# it is the contract this library relies on, not the full external API.


class Wrapped(Protocol[T_co]):
    """A build123d or CadQuery wrapper around one OCP object."""

    @property
    def wrapped(self) -> T_co: ...


# everything Color() accepts
ColorLike = str | tuple[int | float, ...] | list[int | float] | Color | Wrapped[object]


class Build123dVector(Wrapped[gp_Vec], Protocol):
    """A build123d/CadQuery Vector: a wrapped gp_Vec with coordinate properties."""

    @property
    def X(self) -> float: ...
    @property
    def Y(self) -> float: ...
    @property
    def Z(self) -> float: ...


class Build123dShape(Wrapped[TopoDS_Shape], Protocol):
    """A build123d Shape: a wrapped TopoDS_Shape with assembly children."""

    @property
    def label(self) -> str: ...
    @property
    def color(self) -> "ColorLike | None": ...
    @property
    def children(self) -> "Sequence[Build123dShape]": ...
    def faces(self) -> "Iterable[Wrapped[TopoDS_Shape]]": ...
    def edges(self) -> "Iterable[Wrapped[TopoDS_Shape]]": ...


class Build123dBuilder(Protocol):
    """A build123d Builder (BuildPart, BuildSketch or BuildLine)."""

    @property
    def _obj(self) -> object: ...
    @property
    def _obj_name(self) -> str: ...
    @property
    def _tag(self) -> str: ...


class Build123dPartBuilder(Build123dBuilder, Protocol):
    """A build123d BuildPart. part_local exists only in newer build123d,
    access it with getattr."""

    @property
    def part(self) -> "Build123dShape | None": ...
    @property
    def part_local(self) -> "Build123dShape | None": ...


class Build123dSketchBuilder(Build123dBuilder, Protocol):
    """A build123d BuildSketch. sketch_local exists only in newer build123d,
    access it with getattr."""

    @property
    def sketch(self) -> "Build123dShape | None": ...
    @property
    def sketch_local(self) -> "Build123dShape | None": ...


class Build123dLineBuilder(Build123dBuilder, Protocol):
    """A build123d BuildLine. line_local exists only in newer build123d,
    access it with getattr."""

    @property
    def line(self) -> "Build123dShape | None": ...
    @property
    def line_local(self) -> "Build123dShape | None": ...


class Build123dShapeList(Protocol):
    """A build123d ShapeList. first/last/filter_by are only duck-test markers,
    ocp_tessellate never calls them - the elements go back into the to_ocp
    dispatcher, which accepts anything."""

    @property
    def first(self) -> object: ...
    @property
    def last(self) -> object: ...
    @property
    def filter_by(self) -> object: ...
    def __iter__(self) -> Iterator[object]: ...
    def __len__(self) -> int: ...


class Build123dLocationList(Protocol):
    """A build123d LocationList context manager."""

    @property
    def locations(self) -> "Sequence[Wrapped[TopLoc_Location]]": ...
    def __enter__(self) -> object: ...
    def __exit__(
        self, exc_type: object, exc_value: object, traceback: object, /
    ) -> object: ...
    def __iter__(self) -> "Iterator[Wrapped[TopLoc_Location]]": ...


class CadqueryPlane(Protocol):
    """A CadQuery Plane as reached through Workplane.plane."""

    @property
    def location(self) -> Wrapped[TopLoc_Location]: ...


class CadqueryWorkplane(Protocol):
    """A CadQuery Workplane: a context with a stack of objects."""

    @property
    def objects(self) -> "Sequence[object]": ...
    @property
    def ctx(self) -> object: ...
    @property
    def plane(self) -> CadqueryPlane: ...
    def val(self) -> object: ...
    def vals(self) -> "Sequence[object]": ...


class CadqueryAssembly(Protocol):
    """A CadQuery Assembly node."""

    @property
    def obj(self) -> object: ...
    @property
    def loc(self) -> object: ...
    @property
    def name(self) -> str: ...
    @property
    def color(self) -> "ColorLike | None": ...
    @property
    def parent(self) -> "CadqueryAssembly | None": ...
    @property
    def children(self) -> "Sequence[CadqueryAssembly]": ...


class CadquerySketch(Protocol):
    """A CadQuery Sketch: private face/edge/selection stores."""

    @property
    def _faces(self) -> object: ...
    @property
    def _edges(self) -> "Iterable[object]": ...
    @property
    def _selection(self) -> "Sequence[object] | None": ...
    @property
    def locs(self) -> "Sequence[Wrapped[TopLoc_Location]]": ...


class Instance(TypedDict):
    """
    One deduplicated shape registered by OcpConverter.get_instance:
    the shape relocated to the origin, its cache id, and the name of
    the first object that produced it.
    """

    obj: TopoDS_Shape
    cache_id: str
    name: str


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
        uvs: Parametric UV coordinates per vertex (only present when materials are used). Shape (V, 2)
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
    uvs: NotRequired[NDArray[np.float32]]


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
    def get_uvs(self) -> NDArray[np.float32]: ...
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
    ): ...
