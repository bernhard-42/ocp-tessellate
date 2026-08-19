"""Typing-only conformance checks: real classes must satisfy the protocols."""

from build123d import BuildLine, BuildPart, BuildSketch, Compound, Vector
from build123d import ShapeList, LocationList
from cadquery import Assembly, Sketch, Workplane

from ocp_tessellate.types import (
    Build123dBuilder,
    Build123dLineBuilder,
    Build123dLocationList,
    Build123dPartBuilder,
    Build123dShape,
    Build123dShapeList,
    Build123dSketchBuilder,
    Build123dVector,
    CadqueryAssembly,
    CadquerySketch,
    CadqueryWorkplane,
)


def part_builder_conforms(x: BuildPart) -> Build123dPartBuilder:
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


def workplane_conforms(x: Workplane) -> CadqueryWorkplane:
    return x


def assembly_conforms(x: Assembly) -> CadqueryAssembly:
    return x


def cq_sketch_conforms(x: Sketch) -> CadquerySketch:
    return x
