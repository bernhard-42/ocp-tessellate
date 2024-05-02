# %%
import pytest
import unittest

from build123d import *
from ocp_tessellate.convert2 import OcpConverter
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


class Tests_convert(unittest.TestCase):

    def test_buildpart(self):
        c = OcpConverter()
        o = c.to_ocp(bp)
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref][1]))

    def test_buildsketch(self):
        c = OcpConverter()
        o = c.to_ocp(bs)
        i = c.instances
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_face(i[o.ref][1]))

    def test_buildsketch_local(self):
        c = OcpConverter()
        g = c.to_ocp(bs, sketch_local=True)
        i = c.instances
        self.assertEqual(g.length, 2)
        self.assertEqual(g.name, "Face")
        for o, n in zip(g.objs, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(i[o.ref][1]))

    def test_buildline(self):
        c = OcpConverter()
        o = c.to_ocp(bl)
        i = c.instances
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertEqual(len(i), 0)
        self.assertTrue(is_topods_edge(o.obj))

    def test_buildpart_name_color(self):
        c = OcpConverter()
        o = c.to_ocp(bp, names=["bp"])
        i = c.instances
        self.assertEqual(o.name, "bp")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref][1]))

    def test_buildsketch_name_color(self):
        c = OcpConverter()
        o = c.to_ocp(bs, names=["bs"])
        i = c.instances
        self.assertEqual(o.name, "bs")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_face(i[o.ref][1]))

    def test_buildsketch_local_name_color(self):
        c = OcpConverter()
        g = c.to_ocp(bs, names=["bs"], sketch_local=True)
        i = c.instances
        self.assertEqual(g.name, "bs")
        self.assertEqual(g.length, 2)
        for o, n in zip(g.objs, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertIsNotNone(o.ref)
            self.assertIsNone(o.obj)
            self.assertTrue(is_topods_face(i[o.ref][1]))

    def test_buildsketch_local_color(self):
        c = OcpConverter()
        g = c.to_ocp(bs, sketch_local=True)
        i = c.instances
        self.assertEqual(g.name, "Face")
        self.assertEqual(g.length, 2)
        for o, n in zip(g.objs, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(i[o.ref][1]))

    def test_buildline_name_color(self):
        c = OcpConverter()
        o = c.to_ocp(bl, names=["bl"])
        i = c.instances
        self.assertEqual(o.name, "bl")
        self.assertEqual(o.kind, "edge")
        self.assertEqual(len(i), 0)
        self.assertTrue(is_topods_edge(o.obj))

    def test_part_wrapped(self):
        c = OcpConverter()
        o = c.to_ocp(b.wrapped)
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref][1]))


class Tests_convert_moved(unittest.TestCase):

    def test_part_wrapped_moved(self):
        c = OcpConverter()
        o = c.to_ocp(b.wrapped.Moved(Location((2, 0, 0)).wrapped))
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref][1]))

    def test_part_algebra_moved(self):
        c = OcpConverter()
        o = c.to_ocp(Pos(4, 0, 0) * b)
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref][1]))

    def test_part_wrapped_algebra_moved(self):
        c = OcpConverter()
        o = c.to_ocp(Pos(6, 0, 0) * Part(b.wrapped))
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref][1]))

    def test_compoud_algebra_moved(self):
        c = OcpConverter()
        o = c.to_ocp(Pos(8, 0, 0) * Compound(b.wrapped))
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref][1]))
