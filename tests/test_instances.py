import copy
import unittest

from build123d import *

from ocp_tessellate.convert import OcpConverter, tessellate_group
from ocp_tessellate.ocp_utils import *


def reference(obj, label, loc=None):
    new_obj = copy.copy(obj)
    if label is not None:
        new_obj.label = label
    if loc is None:
        return new_obj
    else:
        return new_obj.move(loc)


class ProgressInstance:
    def __init__(self, runs, test):
        self.runs = runs
        self.run = 0
        self.test = test

    def update(self, mark):
        print(mark, end="", flush=True)
        if self.run == self.runs:
            self.test.assertTrue(mark in ["+", "*"])
        else:
            self.test.assertTrue(mark in ["-"])
        self.run += 1


class ProgressCache:
    def __init__(self, run, test):
        self.crun = run
        self.run = 0
        self.test = test

    def update(self, mark):
        print(mark, end="", flush=True)
        if self.run < self.crun:
            self.test.assertTrue(mark in ["+", "*"])
        else:
            self.test.assertTrue(mark in ["c"])
        self.run += 1


class ProgressSequence:
    """Assert the exact sequence of progress marks, e.g. ["c", "+", "c"]."""

    def __init__(self, expected, test):
        self.expected = expected
        self.marks = []
        self.test = test

    def update(self, mark):
        print(mark, end="", flush=True)
        self.marks.append(mark)
        self.test.assertEqual(self.marks, self.expected[: len(self.marks)])


class MyUnitTest(unittest.TestCase):
    def _assertTupleAlmostEquals(self, expected, actual, places, msg=None):
        for i, j in zip(actual, expected):
            self.assertAlmostEqual(i, j, places, msg=msg)


class TestInstances(MyUnitTest):
    def test_reference(self):
        locs = HexLocations(6, 10, 10).local_locations

        sphere = Solid.make_sphere(5)
        sphere_references = [reference(sphere, label="Sphere", loc=loc) for loc in locs]
        assembly = Compound(children=sphere_references)
        c = OcpConverter(progress=ProgressInstance(100, self))
        g = c.to_ocp(assembly, names=["Box"], colors=["red"])
        i = c.instances
        self.assertEqual(len(i), 1)
        _ = tessellate_group(g, i, progress=ProgressInstance(0, self))

    def test_reference_cache(self):
        s = Sphere(1)
        s2 = Sphere(1)  # cached
        b = Box(1, 2, 3)
        b1 = reference(b, label="b1", loc=Pos(X=3))  # instance
        b2 = reference(b, label="b2", loc=Pos(X=-3))  # instance
        c = OcpConverter(progress=ProgressInstance(2, self))
        g = c.to_ocp(
            s,
            b,
            b1,
            b2,
            s2,
        )
        i = c.instances
        self.assertEqual(len(i), 3)
        _ = tessellate_group(g, i, progress=ProgressCache(2, self))

        b2 = b2 - Pos(X=-3) * Box(5, 0.2, 0.2)
        c = OcpConverter(progress=ProgressInstance(1, self))
        g = c.to_ocp(
            s,
            b,
            b1,
            b2,
            s2,
        )
        i = c.instances
        self.assertEqual(len(i), 4)
        # Only the modified b2 is tessellated again; s, b and s2 come from the
        # cache, as tessellating them in the first round must not change their
        # cache ids
        progress = ProgressSequence(["c", "c", "+", "c"], self)
        _ = tessellate_group(g, i, progress=progress)
        self.assertEqual(progress.marks, ["c", "c", "+", "c"])

    def test_moved_copy_cache(self):
        # The mesh is computed at the shape's own origin and its location is
        # sent separately, so a moved or rotated copy reuses the cached mesh -
        # and must keep its own location
        b = Box(1, 2, 3) - Cylinder(0.3, 3)
        c = OcpConverter()
        g = c.to_ocp(b)
        _ = tessellate_group(g, c.instances, progress=ProgressSequence(["+"], self))

        moved = Rot(0, 0, 30) * Pos(10, 20, 30) * b
        c = OcpConverter()
        g = c.to_ocp(moved)
        progress = ProgressSequence(["c"], self)
        _ = tessellate_group(g, c.instances, progress=progress)
        self.assertEqual(progress.marks, ["c"])

        def leaf(group):
            while not hasattr(group, "ref"):
                group = group.objects[0]
            return group

        expected = moved.wrapped.Location().Transformation()
        actual = leaf(g).loc.Transformation()
        self._assertTupleAlmostEquals(
            expected.TranslationPart().Coord(), actual.TranslationPart().Coord(), 9
        )
        eq, aq = expected.GetRotation(), actual.GetRotation()
        self._assertTupleAlmostEquals(
            (eq.X(), eq.Y(), eq.Z(), eq.W()), (aq.X(), aq.Y(), aq.Z(), aq.W()), 9
        )
