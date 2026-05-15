import unittest

from build123d import *

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
