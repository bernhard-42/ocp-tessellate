"""One numbering for viewer and backend: one tessellation entry per face and edge of the maps."""

import pytest
from occt_binding import INSTALLED, occt

from ocp_tessellate.ocp_utils import get_edges, get_faces
from ocp_tessellate.tessellator import Tessellator, discretize_edges

GEOMABS_PLANE = 0
GEOMABS_LINE = 0
GEOMABS_OTHERCURVE = 8

SQUARE = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
# self-intersecting quadrilateral, BRepMesh cannot mesh it
BOW_TIE = [(30, 0, 0), (40, 10, 0), (40, 0, 0), (30, 10, 0)]

# nanocct's EdgeSegments drops the edges that get a placeholder with OCP
EDGE_PLACEHOLDER_BINDINGS = [
    pytest.param(
        b,
        marks=pytest.mark.xfail(
            reason="nanocct's EdgeSegments drops edges without polygon", strict=False
        ),
    )
    if b == "nanocct"
    else b
    for b in INSTALLED
]


def _face(binding, points):
    gp_Pnt = occt("gp", "gp_Pnt", binding)
    polygon = occt("BRepBuilderAPI", "BRepBuilderAPI_MakePolygon", binding)()
    for p in points:
        polygon.Add(gp_Pnt(*p))
    polygon.Close()
    return occt("BRepBuilderAPI", "BRepBuilderAPI_MakeFace", binding)(
        polygon.Wire(), True
    ).Face()


def _line(binding, p1, p2):
    gp_Pnt = occt("gp", "gp_Pnt", binding)
    return occt("BRepBuilderAPI", "BRepBuilderAPI_MakeEdge", binding)(
        gp_Pnt(*p1), gp_Pnt(*p2)
    ).Edge()


def _no_geometry_edge(binding):
    edge = occt("TopoDS", "TopoDS_Edge", binding)()
    occt("BRep", "BRep_Builder", binding)().MakeEdge(edge)
    return edge


def _shell(binding, faces):
    builder = occt("BRep", "BRep_Builder", binding)()
    shell = occt("TopoDS", "TopoDS_Shell", binding)()
    builder.MakeShell(shell)
    for face in faces:
        builder.Add(shell, face)
    return shell


def _compound(binding, shapes):
    builder = occt("BRep", "BRep_Builder", binding)()
    compound = occt("TopoDS", "TopoDS_Compound", binding)()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _tessellate(shape):
    tess = Tessellator("shape")
    tess.compute(shape, 0.01, 0.2)
    return tess


def _distance(binding, point, edge):
    vertex = occt("BRepBuilderAPI", "BRepBuilderAPI_MakeVertex", binding)(
        occt("gp", "gp_Pnt", binding)(*(float(c) for c in point))
    ).Vertex()
    dist = occt("BRepExtrema", "BRepExtrema_DistShapeShape", binding)(vertex, edge)
    return dist.Value()


def _assert_kept_edges_on_map_edges(binding, shape, tess):
    edges = list(get_edges(shape))
    points = [tuple(p) for p in tess.get_edges().reshape(-1, 3)]
    start = 0
    for ind, n in enumerate(tess.segments_per_edge):
        for p in points[start : start + 2 * n]:
            assert _distance(binding, p, edges[ind]) < 1e-6, f"edges_{ind}"
        start += 2 * n
    assert start == len(points)


def _bow_tie_shell(binding, bow_tie_first):
    faces = [_face(binding, BOW_TIE), _face(binding, SQUARE)]
    if bow_tie_first is False:
        faces.reverse()
    return _shell(binding, faces)


@pytest.mark.parametrize("binding", INSTALLED)
@pytest.mark.parametrize("bow_tie_first", [True, False])
def test_unmeshable_face_keeps_its_index(binding, bow_tie_first):
    shape = _bow_tie_shell(binding, bow_tie_first)
    tess = _tessellate(shape)

    assert len(list(get_faces(shape))) == 2
    assert len(tess.face_types) == 2
    bow_tie = 0 if bow_tie_first is True else 1
    assert tess.triangles_per_face[bow_tie] == 0
    assert tess.triangles_per_face[1 - bow_tie] > 0
    assert list(tess.face_types) == [GEOMABS_PLANE, GEOMABS_PLANE]


@pytest.mark.parametrize("binding", EDGE_PLACEHOLDER_BINDINGS)
@pytest.mark.parametrize("bow_tie_first", [True, False])
def test_edges_of_unmeshable_face_keep_their_index(binding, bow_tie_first):
    shape = _bow_tie_shell(binding, bow_tie_first)
    tess = _tessellate(shape)

    assert len(list(get_edges(shape))) == 8
    assert len(tess.segments_per_edge) == 8
    assert list(tess.edge_types) == [GEOMABS_LINE] * 8
    bow_tie_edges = slice(0, 4) if bow_tie_first is True else slice(4, 8)
    assert list(tess.segments_per_edge[bow_tie_edges]) == [0, 0, 0, 0]
    _assert_kept_edges_on_map_edges(binding, shape, tess)


@pytest.mark.parametrize("binding", EDGE_PLACEHOLDER_BINDINGS)
def test_edge_without_face_keeps_its_index(binding):
    loose = _line(binding, (20, 0, 0), (20, 10, 0))
    shape = _compound(
        binding, [loose, _no_geometry_edge(binding), _face(binding, SQUARE)]
    )
    tess = _tessellate(shape)

    assert len(list(get_edges(shape))) == 6
    assert list(tess.segments_per_edge[:2]) == [0, 0]
    assert all(n > 0 for n in tess.segments_per_edge[2:])
    assert (
        list(tess.edge_types) == [GEOMABS_LINE, GEOMABS_OTHERCURVE] + [GEOMABS_LINE] * 4
    )
    _assert_kept_edges_on_map_edges(binding, shape, tess)


@pytest.mark.parametrize("binding", EDGE_PLACEHOLDER_BINDINGS)
def test_unmeshable_shape_has_placeholders_only(binding):
    shape = _shell(binding, [_face(binding, BOW_TIE)])
    tess = _tessellate(shape)

    assert list(tess.triangles_per_face) == [0]
    assert list(tess.segments_per_edge) == [0, 0, 0, 0]
    assert len(tess.get_edges()) == 0


@pytest.mark.parametrize("binding", INSTALLED)
def test_degenerated_edge_keeps_its_index_in_the_edges_only_path(binding):
    edges = [
        _line(binding, (0, 0, 0), (10, 0, 0)),
        _no_geometry_edge(binding),
        _line(binding, (10, 0, 0), (10, 10, 0)),
    ]
    result = discretize_edges(edges, 0.1)

    assert list(result["segments_per_edge"]) == [1, 0, 1]
    assert list(result["edge_types"]) == [
        GEOMABS_LINE,
        GEOMABS_OTHERCURVE,
        GEOMABS_LINE,
    ]
    assert len(result["edges"]) == 2 * 2 * 3


@pytest.mark.parametrize("binding", INSTALLED)
def test_what_was_ignored_is_said_on_stdout_for_it_is_no_error(binding, capsys):
    _tessellate(_shell(binding, [_face(binding, BOW_TIE), _face(binding, SQUARE)]))
    discretize_edges([_no_geometry_edge(binding)], 0.1)

    out, err = capsys.readouterr()
    assert "face 0 ignored" in out
    assert "edge 0 ignored" in out
    assert err == ""
