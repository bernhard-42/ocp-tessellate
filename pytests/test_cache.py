# %%
import unittest

import build123d as bd
import pytest
import webcolors
from build123d import *

from ocp_tessellate.convert import OcpConverter, tessellate_group, to_ocpgroup
from ocp_tessellate.ocp_utils import *
from ocp_tessellate.tessellator import cache


class MyUnitTest(unittest.TestCase):
    def _assertTupleAlmostEquals(self, expected, actual, places, msg=None):
        for i, j in zip(actual, expected):
            self.assertAlmostEqual(i, j, places, msg=msg)


b = Box(1, 2, 3)
b2 = Box(1, 1, 1) - Box(2, 2, 0.2)

with BuildPart() as bp:
    Box(1, 1, 1)

with BuildPart() as bp2:
    Box(1, 1, 1)
    Box(2, 2, 0.2, mode=Mode.SUBTRACT)

r = Rectangle(1, 2)
r2 = Rectangle(1, 2) - Rectangle(2, 0.2)

with BuildSketch(Plane.YZ) as bs:
    Rectangle(1, 1)

with BuildSketch(Plane.YZ) as bs2:
    Rectangle(1, 1)
    Rectangle(2, 0.2, mode=Mode.SUBTRACT)

l = Line((0, 0), (0, 1))
l2 = Line((0, 0), (0, 1)) - Line((0, 0.4), (0, 0.6))

with BuildLine() as bl:
    Line((0, 0), (0, 1))

with BuildLine() as bl2:
    Line((0, 0), (0, 1))
    Line((0, 0.4), (0, 0.6), mode=Mode.SUBTRACT)

# Create some objects to add to the compounds
s1 = Solid.make_box(1, 1, 1).move(Location((3, 3, 3)))
s1.label, s1.color = "box", "red"

s2 = Solid.make_cone(2, 1, 2).move(Location((-3, 3, 3)))
s2.label, s2.color = "cone", "green"

s3 = Solid.make_cylinder(1, 2).move(Location((-3, -3, 3)))
s3.label, s3.color = "cylinder", "blue"

s4 = Solid.make_sphere(2).move(Location((3, 3, -3)))
s4.label = "sphere"

s5 = Solid.make_torus(3, 1).move(Location((-3, 3, -3)))
s5.label, s5.color = "torus", "cyan"

c2 = Compound(label="c2", children=[s2, s3])
c3 = Compound(label="c3", children=[s4, s5])
c1 = Compound(label="c1", children=[s1, c2, c3])

c = Compound([Sphere(1.2), Circle(2).wire()])
mixed = Compound([Box(1, 2, 3), Circle(1), Line((0, 0), (1, 1)), c])

c1 = Compound([Box(1, 2, 3), Sphere(1)])
c2 = Compound([Cone(1, 2, 3), Box(1, 1, 1)])
unmixed = Compound([c1, c2])


class Progress:
    def __init__(self, run, test):
        self.run = run
        self.test = test

    def update(self, mark):
        print(mark, end="", flush=True)
        if self.run == 0:
            self.test.assertTrue(mark in ["+", "*"])
        elif self.run > 0:
            self.test.assertTrue(mark in ["c"])


# %%


class TestsConvertCache(MyUnitTest):
    """Tests for the caching of OcpConverter"""

    def test_buildpart(self):
        cache.clear()
        g, i = to_ocpgroup(bp)
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_buildsketch(self):
        cache.clear()
        g, i = to_ocpgroup(bs)
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_mixed(self):
        cache.clear()
        g1, i1 = to_ocpgroup(bp)
        g2, i2 = to_ocpgroup(bs)
        for run in range(5):
            result = tessellate_group(g1, i1, progress=Progress(run, self))
            result = tessellate_group(g2, i2, progress=Progress(run, self))

    def test_buildpart_part(self):
        cache.clear()
        g, i = to_ocpgroup(bp.part)
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_buildsketch_sketch(self):
        cache.clear()
        g, i = to_ocpgroup(bs.sketch)
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_build_shape_3d(self):
        cache.clear()
        g, i = to_ocpgroup(b2)
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_build_shape_2d(self):
        cache.clear()
        g, i = to_ocpgroup(s2)
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_build_shape_3d_wrapped(self):
        cache.clear()
        g1, i1 = to_ocpgroup(b2)
        g2, i2 = to_ocpgroup(b2.wrapped)
        result = tessellate_group(g1, i2, progress=Progress(0, self))
        result = tessellate_group(g2, i2, progress=Progress(1, self))

    def test_build_shape_2d_wrapped(self):
        cache.clear()
        g1, i1 = to_ocpgroup(s2)
        g2, i2 = to_ocpgroup(s2.wrapped)
        result = tessellate_group(g1, i2, progress=Progress(0, self))
        result = tessellate_group(g2, i2, progress=Progress(1, self))

    def test_build_shapelist_solid(self):
        cache.clear()
        g, i = to_ocpgroup(b2.solids())
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_build_shapelist_shell(self):
        cache.clear()
        g, i = to_ocpgroup(b2.shells())
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))

    def test_build_shapelist_face(self):
        cache.clear()
        g, i = to_ocpgroup(b2.faces())
        for run in range(5):
            result = tessellate_group(g, i, progress=Progress(run, self))
