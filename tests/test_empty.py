import unittest

from build123d import *
from OCP.gp import gp_Pnt
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
)
from OCP.TopoDS import TopoDS_Compound

from ocp_tessellate.convert import OcpConverter, tessellate_group
from ocp_tessellate.ocp_utils import *


def _degenerate_face():
    # Super-thin triangle: BRepMesh refuses to triangulate this and tessellate()
    # returns zero vertices. Models the degenerate-face case that build123d's
    # Text class can produce when a font encodes a straight segment as a Bezier
    # with a (0,0,0) start derivative.
    return Face(
        Wire([
            Line((0, 0, 0), (10, 0, 0)),
            Line((10, 0, 0), (5, 1e-9, 0)),
            Line((5, 1e-9, 0), (0, 0, 0)),
        ])
    )


def _collect_refs(parts, out):
    for part in parts:
        if "parts" in part:
            _collect_refs(part["parts"], out)
        elif (
            part.get("type") == "shapes"
            and isinstance(part.get("shape"), dict)
            and "ref" in part["shape"]
        ):
            out.append(part["shape"]["ref"])


class MyUnitTest(unittest.TestCase):
    def _assertTupleAlmostEquals(self, expected, actual, places, msg=None):
        for i, j in zip(actual, expected):
            self.assertAlmostEqual(i, j, places, msg=msg)


class TestsEmpty(MyUnitTest):
    """Tests for the OcpConverter class"""

    def test_empty_dict(self):
        """Test that an dict is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp({}, names=["z"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "z (empty)")
        self.assertEqual(o.kind, "vertex")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(is_topods_vertex(o.obj))
        self.assertEqual(o.color.a, 0.01)

    def test_empty_list(self):
        """Test that an empty list is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp([], names=["z"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "z (empty)")
        self.assertEqual(o.kind, "vertex")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(is_topods_vertex(o.obj))
        self.assertEqual(o.color.a, 0.01)

    def test_empty_compound(self):
        """Test that an empty Compound is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(Compound([]), names=["z"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "z (empty)")
        self.assertEqual(o.kind, "vertex")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(is_topods_vertex(o.obj))
        self.assertEqual(o.color.a, 0.01)


class TestsEmptyMesh(MyUnitTest):
    """Regression tests for instances that tessellate to zero vertices.

    Before the fix, a zero-vertex mesh was filtered out of meshed_instances
    without remapping the ref indices in the shape tree, causing
    `IndexError: list index out of range` in get_bb_max.
    """

    def test_degenerate_face_alone(self):
        """A single degenerate face must not crash tessellate_group."""
        c = OcpConverter()
        g = c.to_ocp(_degenerate_face(), names=["d"])
        instances = c.instances
        self.assertEqual(len(instances), 1)

        meshed, shapes, _ = tessellate_group(g, instances)

        # The empty mesh is dropped and the shape entry is removed from the tree
        # so no leftover ref can point at a non-existent mesh.
        self.assertEqual(len(meshed), 0)
        refs = []
        _collect_refs(shapes.get("parts", []), refs)
        self.assertEqual(refs, [])

    def test_degenerate_face_among_solids(self):
        """A degenerate instance must not shift the refs of later instances."""
        c = OcpConverter()
        g = c.to_ocp(
            Solid.make_sphere(1),
            _degenerate_face(),
            Solid.make_box(1, 1, 1),
            names=["s", "d", "b"],
        )
        instances = c.instances
        self.assertEqual(len(instances), 3)

        meshed, shapes, _ = tessellate_group(g, instances)

        # Only the two real shapes survive in meshed_instances.
        self.assertEqual(len(meshed), 2)
        self.assertTrue(all(len(m["vertices"]) > 0 for m in meshed))

        # Every ref left in the shape tree must point at a valid meshed entry.
        refs = []
        _collect_refs(shapes.get("parts", []), refs)
        self.assertEqual(sorted(refs), [0, 1])
        for r in refs:
            self.assertLess(r, len(meshed))


class TestsDegenerateArtifacts(MyUnitTest):
    """OCCT artifact objects (edges without geometry, zero-area faces) must be
    ignored with an info message instead of raising"""

    def _edge_without_geometry(self):
        # MakeEdge with two points closer than Precision::Confusion produces an
        # edge flagged Degenerated and carrying no 3D curve - BRepAdaptor_Curve
        # on it raises "No geometry"
        return BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(1e-12, 0, 0)).Edge()

    def _zero_area_face(self):
        # collinear closed polygon -> valid surface, zero area
        return BRepBuilderAPI_MakeFace(
            BRepBuilderAPI_MakePolygon(
                gp_Pnt(0, 0, 0), gp_Pnt(1, 0, 0), gp_Pnt(2, 0, 0), True
            ).Wire()
        ).Face()

    def _compound(self, shapes):
        builder = BRep_Builder()
        comp = TopoDS_Compound()
        builder.MakeCompound(comp)
        for s in shapes:
            builder.Add(comp, s)
        return comp

    def test_predicates(self):
        self.assertTrue(is_degenerated_edge(self._edge_without_geometry()))
        self.assertFalse(
            is_degenerated_edge(Edge.make_line((0, 0, 0), (1, 0, 0)).wrapped)
        )
        self.assertFalse(is_degenerated_face(self._zero_area_face()))
        self.assertFalse(is_degenerated_face(Face.make_rect(1, 1).wrapped))

    def test_degenerated_edge_alone(self):
        c = OcpConverter()
        g = c.to_ocp(self._edge_without_geometry(), names=["e"])
        meshed, shapes, _ = tessellate_group(g, c.instances)
        # dropped and replaced by the empty placeholder vertex
        self.assertEqual(len(shapes["parts"]), 1)
        self.assertEqual(shapes["parts"][0]["type"], "vertices")

    def test_degenerated_edge_in_compound(self):
        good1 = Edge.make_line((0, 0, 0), (1, 0, 0)).wrapped
        good2 = Edge.make_line((0, 0, 0), (0, 1, 0)).wrapped
        comp = self._compound([good1, self._edge_without_geometry(), good2])
        c = OcpConverter()
        g = c.to_ocp(comp, names=["edges"])
        meshed, shapes, _ = tessellate_group(g, c.instances)
        sh = shapes["parts"][0]["shape"]
        # only the two healthy edges survive, parallel arrays stay in sync
        self.assertEqual(len(sh["segments_per_edge"]), 2)
        self.assertEqual(len(sh["edge_types"]), 2)

    def test_zero_area_face_alone(self):
        c = OcpConverter()
        g = c.to_ocp(self._zero_area_face(), names=["f"])
        meshed, shapes, _ = tessellate_group(g, c.instances)
        # meshes to nothing and the part is dropped
        self.assertEqual(len(meshed), 0)
        self.assertEqual(len(shapes["parts"]), 0)

    def test_zero_area_face_in_compound(self):
        comp = self._compound([self._zero_area_face(), Face.make_rect(1, 1).wrapped])
        c = OcpConverter()
        g = c.to_ocp(comp, names=["faces"])
        meshed, shapes, _ = tessellate_group(g, c.instances)
        mesh = meshed[0]
        # the skipped face contributes to neither array
        self.assertEqual(len(mesh["face_types"]), len(mesh["triangles_per_face"]))
        self.assertEqual(len(mesh["face_types"]), 1)
        self.assertEqual(len(mesh["edge_types"]), len(mesh["segments_per_edge"]))
