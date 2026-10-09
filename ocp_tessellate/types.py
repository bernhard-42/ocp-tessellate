from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import (
    TYPE_CHECKING,
    Protocol,
    TypeAlias,
    TypeVar,
)

import numpy as np
from numpy.typing import NDArray

# On Python 3.10, NotRequired only works with typing_extensions' TypedDict,
# so both must come from there until the floor is 3.11
from typing_extensions import NotRequired, TypedDict

from ocp_tessellate.utils import Color

if TYPE_CHECKING:
    # The OCCT types of annotations: the class of either binding. ocp_tessellate
    # does not export OCCT names; these exist for the type checker only, and the
    # other modules import them from here under TYPE_CHECKING, too.
    from nanocct.BRepAdaptor import (
        BRepAdaptor_Curve as _NC_BRepAdaptor_Curve,
        BRepAdaptor_Surface as _NC_BRepAdaptor_Surface,
    )
    from nanocct.BRepExtrema import (
        BRepExtrema_DistShapeShape as _NC_BRepExtrema_DistShapeShape,
    )
    from nanocct.Geom import (
        Geom_Plane as _NC_Geom_Plane,
    )
    from nanocct.gp import (
        gp_Ax1 as _NC_gp_Ax1,
        gp_Ax3 as _NC_gp_Ax3,
        gp_Dir as _NC_gp_Dir,
        gp_Lin as _NC_gp_Lin,
        gp_Pln as _NC_gp_Pln,
        gp_Pnt as _NC_gp_Pnt,
        gp_Vec as _NC_gp_Vec,
    )
    from nanocct.Quantity import (
        Quantity_ColorRGBA as _NC_Quantity_ColorRGBA,
    )
    from nanocct.TopLoc import (
        TopLoc_Location as _NC_TopLoc_Location,
    )
    from nanocct.TopoDS import (
        TopoDS_Compound as _NC_TopoDS_Compound,
        TopoDS_CompSolid as _NC_TopoDS_CompSolid,
        TopoDS_Edge as _NC_TopoDS_Edge,
        TopoDS_Face as _NC_TopoDS_Face,
        TopoDS_Shape as _NC_TopoDS_Shape,
        TopoDS_Shell as _NC_TopoDS_Shell,
        TopoDS_Solid as _NC_TopoDS_Solid,
        TopoDS_Vertex as _NC_TopoDS_Vertex,
        TopoDS_Wire as _NC_TopoDS_Wire,
    )
    from nanocct.XCAFDoc import (
        XCAFDoc_ColorTool as _NC_XCAFDoc_ColorTool,
        XCAFDoc_ShapeTool as _NC_XCAFDoc_ShapeTool,
        XCAFDoc_VisMaterial as _NC_XCAFDoc_VisMaterial,
        XCAFDoc_VisMaterialPBR as _NC_XCAFDoc_VisMaterialPBR,
    )
    from OCP.BRepAdaptor import (
        BRepAdaptor_Curve as _OCP_BRepAdaptor_Curve,
        BRepAdaptor_Surface as _OCP_BRepAdaptor_Surface,
    )
    from OCP.BRepExtrema import (
        BRepExtrema_DistShapeShape as _OCP_BRepExtrema_DistShapeShape,
    )
    from OCP.Geom import (
        Geom_Plane as _OCP_Geom_Plane,
    )
    from OCP.gp import (
        gp_Ax1 as _OCP_gp_Ax1,
        gp_Ax3 as _OCP_gp_Ax3,
        gp_Dir as _OCP_gp_Dir,
        gp_Lin as _OCP_gp_Lin,
        gp_Pln as _OCP_gp_Pln,
        gp_Pnt as _OCP_gp_Pnt,
        gp_Vec as _OCP_gp_Vec,
    )
    from OCP.Quantity import (
        Quantity_ColorRGBA as _OCP_Quantity_ColorRGBA,
    )
    from OCP.TopLoc import (
        TopLoc_Location as _OCP_TopLoc_Location,
    )
    from OCP.TopoDS import (
        TopoDS_Compound as _OCP_TopoDS_Compound,
        TopoDS_CompSolid as _OCP_TopoDS_CompSolid,
        TopoDS_Edge as _OCP_TopoDS_Edge,
        TopoDS_Face as _OCP_TopoDS_Face,
        TopoDS_Shape as _OCP_TopoDS_Shape,
        TopoDS_Shell as _OCP_TopoDS_Shell,
        TopoDS_Solid as _OCP_TopoDS_Solid,
        TopoDS_Vertex as _OCP_TopoDS_Vertex,
        TopoDS_Wire as _OCP_TopoDS_Wire,
    )
    from OCP.XCAFDoc import (
        XCAFDoc_ColorTool as _OCP_XCAFDoc_ColorTool,
        XCAFDoc_ShapeTool as _OCP_XCAFDoc_ShapeTool,
        XCAFDoc_VisMaterial as _OCP_XCAFDoc_VisMaterial,
        XCAFDoc_VisMaterialPBR as _OCP_XCAFDoc_VisMaterialPBR,
    )

    # the aliases carry OCCT's class names, gp_Pnt and so on, not CamelCase ones
    # ruff: noqa: PYI042
    BRepAdaptor_Curve: TypeAlias = _OCP_BRepAdaptor_Curve | _NC_BRepAdaptor_Curve
    BRepAdaptor_Surface: TypeAlias = _OCP_BRepAdaptor_Surface | _NC_BRepAdaptor_Surface
    BRepExtrema_DistShapeShape: TypeAlias = (
        _OCP_BRepExtrema_DistShapeShape | _NC_BRepExtrema_DistShapeShape
    )
    Geom_Plane: TypeAlias = _OCP_Geom_Plane | _NC_Geom_Plane
    Quantity_ColorRGBA: TypeAlias = _OCP_Quantity_ColorRGBA | _NC_Quantity_ColorRGBA
    TopLoc_Location: TypeAlias = _OCP_TopLoc_Location | _NC_TopLoc_Location
    TopoDS_CompSolid: TypeAlias = _OCP_TopoDS_CompSolid | _NC_TopoDS_CompSolid
    TopoDS_Compound: TypeAlias = _OCP_TopoDS_Compound | _NC_TopoDS_Compound
    TopoDS_Edge: TypeAlias = _OCP_TopoDS_Edge | _NC_TopoDS_Edge
    TopoDS_Face: TypeAlias = _OCP_TopoDS_Face | _NC_TopoDS_Face
    TopoDS_Shape: TypeAlias = _OCP_TopoDS_Shape | _NC_TopoDS_Shape
    TopoDS_Shell: TypeAlias = _OCP_TopoDS_Shell | _NC_TopoDS_Shell
    TopoDS_Solid: TypeAlias = _OCP_TopoDS_Solid | _NC_TopoDS_Solid
    TopoDS_Vertex: TypeAlias = _OCP_TopoDS_Vertex | _NC_TopoDS_Vertex
    TopoDS_Wire: TypeAlias = _OCP_TopoDS_Wire | _NC_TopoDS_Wire
    XCAFDoc_ColorTool: TypeAlias = _OCP_XCAFDoc_ColorTool | _NC_XCAFDoc_ColorTool
    XCAFDoc_ShapeTool: TypeAlias = _OCP_XCAFDoc_ShapeTool | _NC_XCAFDoc_ShapeTool
    XCAFDoc_VisMaterial: TypeAlias = _OCP_XCAFDoc_VisMaterial | _NC_XCAFDoc_VisMaterial
    XCAFDoc_VisMaterialPBR: TypeAlias = _OCP_XCAFDoc_VisMaterialPBR | _NC_XCAFDoc_VisMaterialPBR
    gp_Ax1: TypeAlias = _OCP_gp_Ax1 | _NC_gp_Ax1
    gp_Ax3: TypeAlias = _OCP_gp_Ax3 | _NC_gp_Ax3
    gp_Dir: TypeAlias = _OCP_gp_Dir | _NC_gp_Dir
    gp_Lin: TypeAlias = _OCP_gp_Lin | _NC_gp_Lin
    gp_Pln: TypeAlias = _OCP_gp_Pln | _NC_gp_Pln
    gp_Pnt: TypeAlias = _OCP_gp_Pnt | _NC_gp_Pnt
    gp_Vec: TypeAlias = _OCP_gp_Vec | _NC_gp_Vec

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


class Build123dVector(Wrapped["gp_Vec"], Protocol):
    """A build123d/CadQuery Vector: a wrapped gp_Vec with coordinate properties."""

    @property
    def X(self) -> float: ...
    @property
    def Y(self) -> float: ...
    @property
    def Z(self) -> float: ...


class Build123dShape(Wrapped["TopoDS_Shape"], Protocol):
    """A build123d Shape: a wrapped TopoDS_Shape with assembly children."""

    @property
    def label(self) -> str: ...
    @property
    def color(self) -> ColorLike | None: ...
    @property
    def children(self) -> Sequence[Build123dShape]: ...
    def faces(self) -> Iterable[Wrapped[TopoDS_Shape]]: ...
    def edges(self) -> Iterable[Wrapped[TopoDS_Shape]]: ...


class Build123dBuilder(Protocol):
    """A build123d Builder (BuildPart, BuildSheet, BuildSketch or BuildLine)."""

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
    def part(self) -> Build123dShape | None: ...
    @property
    def part_local(self) -> Build123dShape | None: ...


class Build123dSheetBuilder(Build123dBuilder, Protocol):
    """A build123d BuildSheet. sheet is the placed reference Shell (a Compound
    of Shells for several placements), sheet_local the Shell in construction
    coordinates. sheet asserts before anything has been built; sheet_local is
    always readable, so test emptiness on it first."""

    @property
    def sheet(self) -> Build123dShape | None: ...
    @property
    def sheet_local(self) -> Build123dShape: ...


class Build123dSketchBuilder(Build123dBuilder, Protocol):
    """A build123d BuildSketch. sketch_local exists only in newer build123d,
    access it with getattr."""

    @property
    def sketch(self) -> Build123dShape | None: ...
    @property
    def sketch_local(self) -> Build123dShape | None: ...


class Build123dLineBuilder(Build123dBuilder, Protocol):
    """A build123d BuildLine. line_local exists only in newer build123d,
    access it with getattr."""

    @property
    def line(self) -> Build123dShape | None: ...
    @property
    def line_local(self) -> Build123dShape | None: ...


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


class Build123dGroupBy(Protocol):
    """The result of build123d's ShapeList.group_by: an iterable of ShapeLists.
    groups/group_for are only duck-test markers, ocp_tessellate never calls them -
    iterating yields the ShapeLists, which go back into the to_ocp dispatcher."""

    @property
    def groups(self) -> Sequence[Build123dShapeList]: ...
    @property
    def group_for(self) -> object: ...
    def __iter__(self) -> Iterator[Build123dShapeList]: ...
    def __len__(self) -> int: ...


class Build123dLocationList(Protocol):
    """A build123d LocationList context manager."""

    @property
    def locations(self) -> Sequence[Wrapped[TopLoc_Location]]: ...
    def __enter__(self) -> object: ...
    def __exit__(
        self, exc_type: object, exc_value: object, traceback: object, /
    ) -> object: ...
    def __iter__(self) -> Iterator[Wrapped[TopLoc_Location]]: ...


class CadqueryPlane(Protocol):
    """A CadQuery Plane as reached through Workplane.plane."""

    @property
    def location(self) -> Wrapped[TopLoc_Location]: ...


class CadqueryWorkplane(Protocol):
    """A CadQuery Workplane: a context with a stack of objects."""

    @property
    def objects(self) -> Sequence[object]: ...
    @property
    def ctx(self) -> object: ...
    @property
    def plane(self) -> CadqueryPlane: ...
    def val(self) -> object: ...
    def vals(self) -> Sequence[object]: ...


class CadqueryAssembly(Protocol):
    """A CadQuery Assembly node."""

    @property
    def obj(self) -> object: ...
    @property
    def loc(self) -> object: ...
    @property
    def name(self) -> str: ...
    @property
    def color(self) -> ColorLike | None: ...
    @property
    def parent(self) -> CadqueryAssembly | None: ...
    @property
    def children(self) -> Sequence[CadqueryAssembly]: ...


class CadquerySketch(Protocol):
    """A CadQuery Sketch: private face/edge/selection stores."""

    @property
    def _faces(self) -> object: ...
    @property
    def _edges(self) -> Iterable[object]: ...
    @property
    def _selection(self) -> Sequence[object] | None: ...
    @property
    def locs(self) -> Sequence[Wrapped[TopLoc_Location]]: ...


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

    Every array is flat: the wire format transports them as typed buffers, so
    the components of a vertex, a triangle or a segment follow each other
    instead of forming a second dimension. V is the vertex count, T the
    triangle count, F the face count, E the edge count, S the segment count
    and O the object vertex count.

    Attributes:
        vertices: Vertex positions, x, y, z per vertex. Shape (V * 3,)
        triangles: Triangle indices, three per triangle. Shape (T * 3,)
        normals: Normal vectors, x, y, z per vertex. Shape (V * 3,)
        edges: Discretized edges, start and end point per segment. Shape (S * 6,)
        obj_vertices: Original object-space vertices, x, y, z each. Shape (O * 3,)
        face_types: Type identifier for each face. Shape (F,) See GeomAbs_Shape enum
        edge_types: Type identifier for each edge. Shape (E,) See GeomAbs_Shape enum
        triangles_per_face: Triangle count per face. Shape (F,)
        segments_per_edge: Segment count per edge. Shape (E,)
        uvs: Parametric UV coordinates, u and v per vertex, only present when
            materials are used. Shape (V * 2,)
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
    """
    Discretized edges, flat like Tessellation. `edges` holds the start and end
    point of every segment, shape (S * 6,); `obj_vertices` holds x, y, z per
    vertex, shape (O * 3,).
    """

    edges: NDArray[np.float32]
    segments_per_edge: NDArray[np.int32]
    edge_types: NDArray[np.int32]
    obj_vertices: NDArray[np.float32]


class ConvertedVertices(TypedDict):
    obj_vertices: NDArray[np.float32]

