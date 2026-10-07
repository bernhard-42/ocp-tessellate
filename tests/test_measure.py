"""face_normal, closest_directions, angle_between and center_of_mass, once per installed binding."""

import math

import pytest

from ocp_tessellate.ocp_utils import (
    angle_between,
    center_of_mass,
    closest_directions,
    downcast,
    face_normal,
    get_faces,
)
from ocp_tessellate._kernel import binding_of

from occt_binding import INSTALLED, occt, root


def _pnt(b, *xyz):
    return occt("gp", "gp_Pnt", b)(*xyz)


def _line(b, p1, p2):
    return occt("BRepBuilderAPI", "BRepBuilderAPI_MakeEdge", b)(_pnt(b, *p1), _pnt(b, *p2)).Edge()


def _box(b, *size):
    return occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", b)(*size).Shape()


def _top_face(b, shape):
    """The face of a box whose normal points up."""
    for face in get_faces(shape):
        normal = face_normal(face)
        if normal is not None and normal.Z() > 0.5:
            return face
    raise AssertionError("no upward face")


def _xyz(d):
    return (d.X(), d.Y(), d.Z())


def _rotated_square(b):
    """A 4 x 4 square at z = 25, rotated by 30 degrees about the x axis."""
    trsf = occt("gp", "gp_Trsf", b)()
    trsf.SetRotation(occt("gp", "gp_Ax1", b)(_pnt(b, 0, 0, 25), occt("gp", "gp_Dir", b)(1, 0, 0)), math.radians(30))
    plane = occt("gp", "gp_Pln", b)(_pnt(b, 0, 0, 25), occt("gp", "gp_Dir", b)(0, 0, 1))
    face = occt("BRepBuilderAPI", "BRepBuilderAPI_MakeFace", b)(plane, -2, 2, -2, 2).Face()
    return downcast(occt("BRepBuilderAPI", "BRepBuilderAPI_Transform", b)(face, trsf).Shape())


@pytest.mark.parametrize("binding", INSTALLED)
def test_face_normal_follows_the_orientation(binding):
    box = _box(binding, 10, 20, 30)
    normals = sorted(tuple(round(c, 12) + 0.0 for c in _xyz(face_normal(f))) for f in get_faces(box))
    assert normals == sorted([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)])
    top = _top_face(binding, box)
    assert binding_of(face_normal(top)) is root(binding)
    reversed_top = downcast(top.Reversed())
    assert _xyz(face_normal(reversed_top)) == pytest.approx((0, 0, -1))


@pytest.mark.parametrize("binding", INSTALLED)
def test_closest_directions_of_two_edges(binding):
    e1 = _line(binding, (0, 0, 0), (10, 0, 0))
    e2 = _line(binding, (0, 5, 3), (10, 8, 3))
    d1, d2 = closest_directions(e1, e2)
    assert binding_of(d1) is root(binding)
    assert _xyz(d1) == pytest.approx((1, 0, 0))
    assert _xyz(d2) == pytest.approx((10 / math.hypot(10, 3), 3 / math.hypot(10, 3), 0))


@pytest.mark.parametrize("binding", INSTALLED)
def test_closest_directions_at_vertices(binding):
    """Closest points at vertices: the tangent at the nearer end of each edge."""
    e1 = _line(binding, (0, 0, 0), (10, 0, 0))
    e2 = _line(binding, (12, 1, 0), (15, 5, 0))
    d1, d2 = closest_directions(e1, e2)
    assert _xyz(d1) == pytest.approx((1, 0, 0))
    assert _xyz(d2) == pytest.approx((0.6, 0.8, 0))


@pytest.mark.parametrize("binding", INSTALLED)
def test_closest_directions_of_edge_and_face(binding):
    top = _top_face(binding, _box(binding, 10, 20, 30))
    edge = _line(binding, (0, 0, 40), (5, 5, 45))
    d1, d2 = closest_directions(edge, top)
    assert _xyz(d1) == pytest.approx((1 / math.sqrt(3),) * 3)
    assert _xyz(d2) == pytest.approx((0, 0, 1))
    # the other way round
    d2, d1 = closest_directions(top, edge)
    assert _xyz(d2) == pytest.approx((0, 0, 1))


@pytest.mark.parametrize("binding", INSTALLED)
def test_closest_directions_of_two_faces(binding):
    top = _top_face(binding, _box(binding, 10, 20, 30))
    d1, d2 = closest_directions(top, _rotated_square(binding))
    assert _xyz(d1) == pytest.approx((0, 0, 1))
    assert math.degrees(angle_between(d1, d2)) == pytest.approx(30)


@pytest.mark.parametrize("binding", INSTALLED)
def test_closest_directions_takes_edges_and_faces(binding):
    edge = _line(binding, (0, 0, 0), (1, 0, 0))
    vertex = occt("BRepBuilderAPI", "BRepBuilderAPI_MakeVertex", binding)(_pnt(binding, 0, 0, 5)).Vertex()
    with pytest.raises(TypeError, match="edges and faces"):
        closest_directions(edge, vertex)
    with pytest.raises(TypeError, match="edges and faces"):
        closest_directions(downcast(_box(binding, 1, 1, 1)), edge)


@pytest.mark.parametrize("binding", INSTALLED)
def test_angle_between(binding):
    vec = occt("gp", "gp_Vec", binding)(0, 3, 0)
    direction = occt("gp", "gp_Dir", binding)(0, 0, 1)
    assert angle_between((1, 0, 0), (0, 0, 1)) == pytest.approx(math.pi / 2)
    assert angle_between(vec, direction) == pytest.approx(math.pi / 2)
    assert angle_between(direction, (0, 0, -1)) == pytest.approx(math.pi)
    assert angle_between((1, 1, 0), vec) == pytest.approx(math.pi / 4)


@pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
def test_two_bindings_do_not_combine():
    with pytest.raises(TypeError, match="objects of two bindings"):
        angle_between(occt("gp", "gp_Dir", "OCP")(1, 0, 0), occt("gp", "gp_Dir", "nanocct")(0, 1, 0))
    with pytest.raises(TypeError, match="objects of two bindings"):
        closest_directions(_line("OCP", (0, 0, 0), (1, 0, 0)), _line("nanocct", (0, 1, 0), (1, 1, 0)))


@pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
@pytest.mark.parametrize(
    "case",
    ["edge-edge", "edge-vertex", "edge-face", "face-face"],
)
def test_both_bindings_give_the_same_directions(case):
    def shapes(b):
        top = _top_face(b, _box(b, 10, 20, 30))
        return {
            "edge-edge": (_line(b, (0, 0, 0), (10, 0, 0)), _line(b, (0, 5, 3), (10, 8, 3))),
            "edge-vertex": (_line(b, (0, 0, 0), (10, 0, 0)), _line(b, (12, 1, 0), (15, 5, 0))),
            "edge-face": (_line(b, (0, 0, 40), (5, 5, 45)), top),
            "face-face": (top, _rotated_square(b)),
        }[case]

    ocp, nanocct = (closest_directions(*shapes(b)) for b in INSTALLED)
    assert [_xyz(d) for d in ocp] == [_xyz(d) for d in nanocct]


#
# center_of_mass by the highest dimension of a shape
#


def _compound(b, shapes):
    comp = occt("TopoDS", "TopoDS_Compound", b)()
    builder = occt("BRep", "BRep_Builder", b)()
    builder.MakeCompound(comp)
    for s in shapes:
        builder.Add(comp, s)
    return comp


def _square(b, x, y):
    """A 2 x 2 face in the XY plane centered at (x, y, 0)."""
    plane = occt("gp", "gp_Pln", b)(_pnt(b, x, y, 0), occt("gp", "gp_Dir", b)(0, 0, 1))
    return occt("BRepBuilderAPI", "BRepBuilderAPI_MakeFace", b)(plane, -1, 1, -1, 1).Face()


@pytest.mark.parametrize("binding", INSTALLED)
def test_center_of_mass_by_dimension(binding):
    b = binding
    vertex = occt("BRepBuilderAPI", "BRepBuilderAPI_MakeVertex", b)(_pnt(b, 1, 2, 3)).Vertex()
    cases = {
        "vertex": (vertex, (1, 2, 3)),
        "edge": (_line(b, (1, 2, 3), (5, 6, 7)), (3, 4, 5)),
        "face": (_square(b, 3, 4), (3, 4, 0)),
        "solid": (downcast(_box(b, 2, 4, 6)), (1, 2, 3)),
        "compound of solids": (_compound(b, [_box(b, 2, 2, 2), occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", b)(_pnt(b, 4, 0, 0), 2, 2, 2).Shape()]), (3, 1, 1)),
        "compound of faces": (_compound(b, [_square(b, 5, 0), _square(b, 9, 0)]), (7, 0, 0)),
        "compound of edges": (_compound(b, [_line(b, (0, 0, 0), (2, 0, 0)), _line(b, (0, 4, 0), (2, 4, 0))]), (1, 2, 0)),
        "compound of vertices": (_compound(b, [vertex, occt("BRepBuilderAPI", "BRepBuilderAPI_MakeVertex", b)(_pnt(b, 3, 0, 1)).Vertex()]), (2, 1, 2)),
    }
    for name, (shape, expected) in cases.items():
        assert center_of_mass(shape) == pytest.approx(expected, abs=1e-12), name


@pytest.mark.parametrize("binding", INSTALLED)
def test_center_of_mass_of_an_arc(binding):
    """The centroid of a circular arc: r (sin b - sin a, cos a - cos b) / (b - a)."""
    r, a, b = 4.0, math.radians(10), math.radians(200)
    circ = occt("gp", "gp_Circ", binding)(occt("gp", "gp_Ax2", binding)(), r)
    arc = occt("BRepBuilderAPI", "BRepBuilderAPI_MakeEdge", binding)(circ, a, b).Edge()
    expected = (r * (math.sin(b) - math.sin(a)) / (b - a), r * (math.cos(a) - math.cos(b)) / (b - a), 0)
    assert center_of_mass(arc) == pytest.approx(expected, abs=1e-9)
