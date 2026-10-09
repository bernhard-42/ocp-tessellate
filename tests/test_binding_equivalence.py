"""OCP and nanocct give the same tessellation of the same mesh.

The OCP kernel extracts a mesh with Python loops per node, the nanocct kernel
with numpy views and nanocct's C++ helpers. To compare the two, both get the
identical mesh: a shape is built and meshed with OCP, written with its
triangulation and read into nanocct (serialize / deserialize). The meshes have
to be transferred because BRepMesh itself does not mesh bit-identically in the
two builds (OCP 8.0.1.0 and nanocct 8.0.1.1, both OCCT 8.0.1: a torus gets the
same node and triangle counts but different nodes). The comparison is exact
for the integer arrays and to float32 rounding for the coordinates. Runs only
where both bindings are installed.
"""

import os
import tempfile

import numpy as np
import pytest
from occt_binding import INSTALLED, occt, root

from ocp_tessellate._kernel import binding_of, kernel_of
from ocp_tessellate.ocp_utils import (
    downcast,
    get_edges,
    get_faces,
    make_compound,
    to_nanocct,
)
from ocp_tessellate.tessellator import discretize_edge, tessellate

pytestmark = pytest.mark.skipif(
    INSTALLED != ["OCP", "nanocct"], reason="needs OCP and nanocct"
)

INT_ARRAYS = ("triangles", "triangles_per_face", "segments_per_edge", "face_types", "edge_types")
FLOAT_ARRAYS = ("vertices", "normals", "edges", "obj_vertices", "uvs")


def _fillet_box(b):
    box = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", b)(10, 20, 30).Shape()
    fillet = occt("BRepFilletAPI", "BRepFilletAPI_MakeFillet", b)(box)
    for edge in get_edges(box):
        fillet.Add(1.5, edge)
    return fillet.Shape()


def _moved(b, shape):
    trsf = occt("gp", "gp_Trsf", b)()
    axis = occt("gp", "gp_Ax1", b)(occt("gp", "gp_Pnt", b)(), occt("gp", "gp_Dir", b)(1, 1, 0))
    trsf.SetRotation(axis, 0.7)
    trsf.SetTranslationPart(occt("gp", "gp_Vec", b)(3, -4, 5))
    return shape.Moved(occt("TopLoc", "TopLoc_Location", b)(trsf))


def _mesh_only_face(b):
    """A face with a triangulation and no surface, as an STL import gives."""
    box = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", b)(1, 2, 3).Shape()
    occt("BRepMesh", "BRepMesh_IncrementalMesh", b)(box, 0.1)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "box.stl")
        occt("StlAPI", "StlAPI_Writer", b)().Write(box, path)
        poly = occt("RWStl", "RWStl", b).ReadFile_s(path)
    face = occt("TopoDS", "TopoDS_Face", b)()
    occt("BRep", "BRep_Builder", b)().MakeFace(face, poly)
    return face


SHAPES = {
    "box": lambda b: occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", b)(1, 2, 3).Shape(),
    "torus": lambda b: occt("BRepPrimAPI", "BRepPrimAPI_MakeTorus", b)(10, 3).Shape(),
    "sphere": lambda b: occt("BRepPrimAPI", "BRepPrimAPI_MakeSphere", b)(6.0).Shape(),
    "cylinder": lambda b: occt("BRepPrimAPI", "BRepPrimAPI_MakeCylinder", b)(2, 5).Shape(),
    "fillet_box": _fillet_box,
    "moved_torus": lambda b: _moved(b, occt("BRepPrimAPI", "BRepPrimAPI_MakeTorus", b)(4, 1).Shape()),
    "reversed_box": lambda b: downcast(occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", b)(2, 2, 2).Shape().Reversed()),
    "mesh_only_face": _mesh_only_face,
    # faces with and without UV nodes in one shape: the normals of the mesh-only
    # face are interpolated, the others read off the surface
    "mixed": lambda b: make_compound(
        [_mesh_only_face(b), occt("BRepPrimAPI", "BRepPrimAPI_MakeSphere", b)(2.0).Shape()]
    ),
}


QUALITY, ANGULAR_TOLERANCE = 0.05, 0.2


def _same_mesh_in_both(name):
    """The shape built and meshed with OCP, and the same shape and mesh in nanocct."""
    ocp_shape = SHAPES[name]("OCP")
    occt("BRepMesh", "BRepMesh_IncrementalMesh", "OCP")(
        ocp_shape, QUALITY, False, ANGULAR_TOLERANCE, True
    )
    # the mesh travels with the shape (BinTools, triangulations included)
    nanocct_shape = to_nanocct(ocp_shape)
    assert binding_of(nanocct_shape) is root("nanocct")
    return {"OCP": ocp_shape, "nanocct": nanocct_shape}


def _nodes(shape):
    """The triangulation nodes of all faces, to check that nothing re-meshes."""
    loc = kernel_of(shape).TopLoc.TopLoc_Location()
    result = []
    for face in get_faces(shape):
        poly = kernel_of(shape).BRep.BRep_Tool.Triangulation_s(face, loc)
        result.append([(p.X(), p.Y(), p.Z()) for p in (poly.Node(i) for i in range(1, poly.NbNodes() + 1))])
    return result


def _tessellate(shape, key, compute_uvs, normalize_uvs):
    return tessellate(
        shape,
        key,
        0.1,
        QUALITY,
        ANGULAR_TOLERANCE,
        compute_uvs=compute_uvs,
        normalize_uvs=normalize_uvs,
    )


@pytest.mark.parametrize("uvs", [(False, True), (True, True), (True, False)], ids=["no-uvs", "uvs", "raw-uvs"])
@pytest.mark.parametrize("name", SHAPES)
def test_tessellation_is_the_same(name, uvs):
    shapes = _same_mesh_in_both(name)
    before = _nodes(shapes["nanocct"])
    assert before == _nodes(shapes["OCP"])
    ocp, nanocct = (
        _tessellate(shapes[b], f"equivalence-{name}-{b}-{uvs}", *uvs) for b in INSTALLED
    )
    # tessellate() meshes with the same parameters, so the transferred mesh is kept
    assert _nodes(shapes["nanocct"]) == before
    assert ocp.keys() == nanocct.keys()
    for key in ocp:
        a, b = np.asarray(ocp[key]), np.asarray(nanocct[key])
        assert a.dtype == b.dtype, key
        assert a.shape == b.shape, key
        if key in INT_ARRAYS:
            np.testing.assert_array_equal(a, b, err_msg=key)
        else:
            assert key in FLOAT_ARRAYS, key
            np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-6, err_msg=key)


@pytest.mark.parametrize("name", ["box", "torus", "fillet_box", "moved_torus"])
def test_discretized_edges_are_the_same(name):
    shapes = _same_mesh_in_both(name)
    edges = {b: next(iter(get_edges(shapes[b]))) for b in INSTALLED}
    a, b = (np.asarray(discretize_edge(edges[x], 0.01)) for x in INSTALLED)
    assert a.shape == b.shape
    np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-6)
