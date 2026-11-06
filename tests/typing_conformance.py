"""Typing-only conformance checks: real classes must satisfy the protocols."""

from collections.abc import Sequence

from build123d import (
    BuildLine,
    BuildPart,
    BuildSheet,
    BuildSketch,
    Compound,
    GroupBy,
    LocationList,
    ShapeList,
    Vector,
)
from cadquery import Assembly, Sketch, Workplane

from ocp_tessellate.ocp_utils import BoundingBox
from ocp_tessellate.plugin import OcpObject, ShowProtocol, TessellationProtocol
from ocp_tessellate.types import (
    Build123dGroupBy,
    Build123dLineBuilder,
    Build123dLocationList,
    Build123dPartBuilder,
    Build123dShape,
    Build123dShapeList,
    Build123dSheetBuilder,
    Build123dSketchBuilder,
    Build123dVector,
    CadqueryAssembly,
    CadquerySketch,
    CadqueryWorkplane,
)


def part_builder_conforms(x: BuildPart) -> Build123dPartBuilder:
    return x


def sheet_builder_conforms(x: BuildSheet) -> Build123dSheetBuilder:
    return x


def sketch_builder_conforms(x: BuildSketch) -> Build123dSketchBuilder:
    return x


def line_builder_conforms(x: BuildLine) -> Build123dLineBuilder:
    return x


def shape_conforms(x: Compound) -> Build123dShape:
    return x


def vector_conforms(x: Vector) -> Build123dVector:
    return x


def shapelist_conforms(x: ShapeList) -> Build123dShapeList:
    return x


def locationlist_conforms(x: LocationList) -> Build123dLocationList:
    return x


def groupby_conforms(x: GroupBy) -> Build123dGroupBy:
    return x


def workplane_conforms(x: Workplane) -> CadqueryWorkplane:
    return x


def assembly_conforms(x: Assembly) -> CadqueryAssembly:
    return x


def cq_sketch_conforms(x: Sketch) -> CadquerySketch:
    return x


# ---------------------------------------------------------------------------
# A kernel plugin names its types, and may then narrow what the protocols take
# ---------------------------------------------------------------------------


class _Body: ...


class _Edge: ...


class _Vertex: ...


class _Tessellation(TessellationProtocol[_Body, _Edge, _Vertex]):
    def tessellate(
        self,
        shape: _Body,
        deviation: float,
        quality: float,
        angular_tolerance: float,
        compute_edges: bool = True,
        compute_uvs: bool = False,
        normalize_uvs: bool = True,
        shape_id: str = "",
        debug: bool = False,
    ):
        raise NotImplementedError

    def discretize_edges(self, edges: Sequence[_Edge], deflection: float = 0.1, shape_id: str = ""):
        raise NotImplementedError

    def convert_vertices(self, vertices: Sequence[_Vertex], shape_id: str = ""):
        raise NotImplementedError

    def bounding_box(self, shape: _Body | _Edge | _Vertex | Sequence[_Edge | _Vertex]) -> BoundingBox:
        raise NotImplementedError

    def cache_id(self, shape: _Body) -> str:
        raise NotImplementedError


class _Show(ShowProtocol[_Body | _Edge]):
    def is_object(self, obj: object) -> bool:
        return isinstance(obj, (_Body, _Edge))

    def convert(self, obj: _Body | _Edge, name, color, alpha, helper_scale) -> OcpObject:
        raise NotImplementedError

    def line(self, start, end) -> _Edge:
        return _Edge()

    def serialize(self, shape) -> bytes:
        return b""
