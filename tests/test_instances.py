import copy
import unittest

import build123d as bd
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
        _ = tessellate_group(g, i, progress=ProgressCache(3, self))
