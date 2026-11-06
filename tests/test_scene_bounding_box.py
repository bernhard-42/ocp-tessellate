"""The scene's bounding box holds every object where the viewer draws it: the viewer
places edges and vertices by the locations of the groups above them, as it does
solids, shells and faces."""

import pytest
from build123d import Box, Compound, Edge, Pos, Rot, Vertex
from toy_kernel import Point, Segment

from ocp_tessellate import OcpGroup
from ocp_tessellate.cad_objects import OcpObject
from ocp_tessellate.convert import tessellate_group, to_ocpgroup
from ocp_tessellate.ocp_utils import Placement


def scene_box(obj):
    group, instances = to_ocpgroup(obj)
    _, shapes, _ = tessellate_group(group, instances)
    return shapes["bb"]


def extent(box, axis):
    return box[f"{axis}min"], box[f"{axis}max"]


def near(low, high):
    """OCCT's bounding box of an edge is about 1e-7 larger than the edge."""
    return pytest.approx((low, high), abs=1e-5)


def line(label="line"):
    edge = Edge.make_line((0, 0, 0), (1, 0, 0))
    edge.label = label
    return edge


def point():
    vertex = Vertex(1, 2, 3)
    vertex.label = "point"
    return vertex


def assembly(*children, label="asm"):
    return Compound(label=label, children=list(children))


AT_100 = ((100.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def test_an_edge_in_a_located_assembly():
    box = scene_box(Pos(100, 0, 0) * assembly(line()))
    assert extent(box, "x") == near(100, 101)


def test_an_edge_moved_inside_a_located_assembly():
    box = scene_box(Pos(100, 0, 0) * assembly(Pos(0, 5, 0) * line()))
    assert extent(box, "x") == near(100, 101)
    assert extent(box, "y") == near(4.9, 5.1)


def test_a_vertex_in_a_located_assembly():
    box = scene_box(Pos(100, 0, 0) * assembly(point()))
    assert extent(box, "x") == near(100.9, 101.1)
    assert extent(box, "y") == near(1.9, 2.1)
    assert extent(box, "z") == near(2.9, 3.1)


def test_an_edge_in_a_rotated_assembly():
    box = scene_box(Pos(100, 0, 0) * Rot(0, 0, 90) * assembly(line()))
    assert extent(box, "x") == near(99.9, 100.1)
    assert extent(box, "y") == near(0, 1)


def test_an_edge_in_nested_assemblies():
    inner = Pos(0, 10, 0) * assembly(line(), label="sub")
    box = scene_box(Pos(100, 0, 0) * assembly(inner, label="top"))
    assert extent(box, "x") == near(100, 101)
    assert extent(box, "y") == near(9.9, 10.1)


def test_an_edge_beside_a_solid_in_a_located_assembly():
    box = scene_box(Pos(100, 0, 0) * assembly(line(), Box(2, 2, 2)))
    assert extent(box, "x") == near(99, 101)
    assert extent(box, "y") == near(-1, 1)


def test_an_edge_without_a_location_stays_where_it_is():
    box = scene_box(Pos(100, 0, 0) * line())
    assert extent(box, "x") == near(100, 101)


def test_an_external_edge_in_a_located_group():
    leaf = OcpObject("edge", [Segment((0, 0, 0), (1, 0, 0))], name="line", color="blue")
    box = scene_box(OcpGroup([leaf], name="asm", loc=Placement(*AT_100)))
    assert extent(box, "x") == near(100, 101)


def test_an_external_vertex_in_a_located_group():
    leaf = OcpObject("vertex", [Point(1, 0, 0)], name="point", color="blue")
    box = scene_box(OcpGroup([leaf], name="asm", loc=Placement(*AT_100)))
    assert extent(box, "x") == near(100.9, 101.1)


def test_the_backend_places_an_edge_where_the_viewer_draws_it():
    """`collect` gives an edge's entry every location above it, as a solid's."""
    group, instances = to_ocpgroup(Pos(100, 0, 0) * assembly(line(), Box(2, 2, 2)))
    _, _, mapping = tessellate_group(group, instances)
    entries = {e["id"]: e for e in mapping["parts"]}
    edge = next(e for path, e in entries.items() if path.endswith("/line"))
    assert edge["loc"] is not None
    assert edge["loc"][0] == near_point(100, 0, 0)


def near_point(x, y, z):
    return pytest.approx((x, y, z), abs=1e-6)
