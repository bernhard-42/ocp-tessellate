"""The interface of a kernel plugin: what a kernel other than OCCT has to provide.

Two protocols here, for the viewer's side, and `BackendProtocol` in ocp_viewer_core for
the measurement backend (https://bernhard-42.github.io/ocp_viewer_docs/plugins/overview/).
A plugin subclasses them, so that a method it forgot fails when its object is created, and
hands the objects to `ocp_tessellate.plugin.register_show`. OCCT implements `TessellationProtocol` too
(`tessellator.OcctTessellation`), so `tessellation_of(obj)` answers alike for every
kernel; what `ShowProtocol` does for a plugin, `to_ocp`'s dispatch does for OCCT.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .cad_objects import CoordAxis, CoordSystem, OcpObject
    from .ocp_utils import BoundingBox
    from .ocp_utils.location import Placement
    from .types import (
        ColorLike,
        ConvertedVertices,
        DiscretizedEdges,
        KernelShape,
        Tessellation,
    )


# The type codes of faces and edges in a Tessellation, the values the viewer reads. They are
# OCCT's GeomAbs_SurfaceType and GeomAbs_CurveType (a test compares them with the binding).
SURFACE_TYPES: dict[str, int] = {
    "Plane": 0,
    "Cylinder": 1,
    "Cone": 2,
    "Sphere": 3,
    "Torus": 4,
    "BezierSurface": 5,
    "BSplineSurface": 6,
    "SurfaceOfRevolution": 7,
    "SurfaceOfExtrusion": 8,
    "OffsetSurface": 9,
    "OtherSurface": 10,
}
CURVE_TYPES: dict[str, int] = {
    "Line": 0,
    "Circle": 1,
    "Ellipse": 2,
    "Hyperbola": 3,
    "Parabola": 4,
    "BezierCurve": 5,
    "BSplineCurve": 6,
    "OffsetCurve": 7,
    "OtherCurve": 8,
}

# What a plugin's methods take, named when it subclasses a protocol, as in
# `TessellationProtocol[Body, Edge, Vertex]`, so a type checker checks it against them.
BodyT_contra = TypeVar("BodyT_contra", contravariant=True)
EdgeT_contra = TypeVar("EdgeT_contra", contravariant=True)
VertexT_contra = TypeVar("VertexT_contra", contravariant=True)
ObjectT_contra = TypeVar("ObjectT_contra", contravariant=True)


@runtime_checkable
class TessellationProtocol(Protocol[BodyT_contra, EdgeT_contra, VertexT_contra]):
    """What makes a kernel's shapes visible: the same functions OCCT's shapes go through."""

    @abstractmethod
    def tessellate(
        self,
        shape: BodyT_contra,
        deviation: float,
        quality: float,
        angular_tolerance: float,
        compute_edges: bool = True,
        compute_uvs: bool = False,
        normalize_uvs: bool = True,
        shape_id: str = "",
        debug: bool = False,
    ) -> Tessellation:
        """The mesh of a solid, face or shell. `compute_uvs` is true for an object with a
        material; a kernel without UVs leaves them out of the mesh."""

    @abstractmethod
    def discretize_edges(
        self, edges: Sequence[EdgeT_contra], deflection: float = 0.1, shape_id: str = ""
    ) -> DiscretizedEdges:
        """The segments of edges, chord deviation at most `deflection`."""

    @abstractmethod
    def convert_vertices(
        self, vertices: Sequence[VertexT_contra], shape_id: str = ""
    ) -> ConvertedVertices:
        """The coordinates of vertices."""

    @abstractmethod
    def bounding_box(self, shape: BodyT_contra | EdgeT_contra | VertexT_contra | Sequence[EdgeT_contra | VertexT_contra]) -> BoundingBox:
        """The box of a shape or a list of edges or vertices. An object without an
        extent, a location, plane or axis, raises or returns None: it adds nothing."""

    def cache_id(self, shape: BodyT_contra) -> str | None:
        """A string that identifies the shape's geometry, not its color or name: the
        mesh is cached and shared under it. None: it is meshed at every show."""
        return None


@runtime_checkable
class ShowProtocol(Protocol[ObjectT_contra]):
    """What makes the host's `show` and `show_all` take a kernel's objects."""

    @abstractmethod
    def is_object(self, obj: object) -> bool:
        """Whether one object is the kernel's, a container of the kernel included: test
        with `isinstance` on the kernel's own types, no duck typing, since this decides who
        owns an object. Cheap, since it is asked about every variable at a debug stop."""

    @abstractmethod
    def convert(
        self,
        obj: ObjectT_contra,
        name: str,
        color: ColorLike | None,
        alpha: float | None,
        helper_scale: float,
    ) -> OcpObject | CoordSystem | CoordAxis:
        """An atomic object as an OcpObject holding the kernel's shape; a location or
        plane as a CoordSystem and an axis as a CoordAxis with `like=obj`."""

    @abstractmethod
    def line(
        self, start: tuple[float, float, float], end: tuple[float, float, float]
    ) -> KernelShape:
        """The kernel's edge between two points: what `CoordSystem` and `CoordAxis`
        draw with, for an object of this kernel as `like`."""

    @abstractmethod
    def serialize(self, shape: ObjectT_contra | Sequence[ObjectT_contra]) -> bytes:
        """What a leaf of the model holds, a shape or a list of edges or vertices, as bytes
        for `BackendProtocol.deserialize`: every host runs the measurement backend in another
        process than the user's (VS Code's `python -m ocp_vscode --backend`, Jupyter CadQuery's
        server extension, ocp-viewer's server, build123d Studio's sidecar), and the model
        reaches it as JSON. Keep a format version in the bytes: the two processes can have
        different versions of the plugin."""

    def get_children(self, obj: ObjectT_contra) -> list[tuple[str | None, KernelShape, Placement | None]] | None:
        """A container's (name, child, relative placement) entries, None for an atomic
        object. A child can be anything `show` takes."""
        return None

    def get_location(self, obj: ObjectT_contra) -> Placement | None:
        """The object's own placement. A child is placed at
        `relative placement * get_location(child)`."""
        return None
