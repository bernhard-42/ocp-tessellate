# %%
import pytest
import unittest

from build123d import *
from ocp_tessellate.convert2 import to_ocp
from ocp_tessellate.ocp_utils import *

# %%


b = Box(1, 2, 3)
b2 = Box(1, 1, 1) - Box(2, 2, 0.2)

with BuildPart() as bp:
    Box(1, 1, 1)

with BuildPart() as bp2:
    Box(1, 1, 1)
    Box(2, 2, 0.2, mode=Mode.SUBTRACT)

r = Rectangle(1, 2)
r2 = Rectangle(1, 2) - Rectangle(2, 0.2)

with BuildSketch() as bs:
    Rectangle(1, 1)

with BuildSketch() as bs2:
    Rectangle(1, 1)
    Rectangle(2, 0.2, mode=Mode.SUBTRACT)

l = Line((0, 0), (0, 1))
l2 = Line((0, 0), (0, 1)) - Line((0, 0.4), (0, 0.6))

with BuildLine() as bl:
    Line((0, 0), (0, 1))

with BuildLine() as bl2:
    Line((0, 0), (0, 1))
    Line((0, 0.4), (0, 0.6), mode=Mode.SUBTRACT)


class Tests(unittest.TestCase):

    def test_buildpart(self):
        o = to_ocp(bp)
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_solid(o.obj))

    def test_buildsketch(self):
        o = to_ocp(bs)
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_face(o.obj))

    def test_buildsketch_local(self):
        g = to_ocp(bs, sketch_local=True)
        self.assertEqual(g.length, 2)
        self.assertEqual(g.name, "Group")
        for o, n in zip(g.objs, ["Face", "Face_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(o.obj))

    def test_buildline(self):
        o = to_ocp(bl)
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj))

    def test_buildpart_name_color(self):
        o = to_ocp(bp, names=["bp"])
        self.assertEqual(o.name, "bp")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_solid(o.obj))

    def test_buildsketch_name_color(self):
        o = to_ocp(bs, names=["bs"])
        self.assertEqual(o.name, "bs")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_face(o.obj))

    def test_buildsketch_local_name_color(self):
        g = to_ocp(bs, names=["bs"], sketch_local=True)
        self.assertEqual(g.name, "bs")
        self.assertEqual(g.length, 2)
        for o, n in zip(g.objs, ["Face", "Face_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(o.obj))

    def test_buildline_name_color(self):
        o = to_ocp(bl, names=["bl"])
        self.assertEqual(o.name, "bl")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj))
