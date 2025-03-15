# %%
import unittest

import build123d as bd
import pytest
import webcolors
from build123d import *

from ocp_tessellate.convert import OcpConverter
from ocp_tessellate.ocp_utils import *


class MyUnitTest(unittest.TestCase):
    def _assertTupleAlmostEquals(self, expected, actual, places, msg=None):
        for i, j in zip(actual, expected):
            self.assertAlmostEqual(i, j, places, msg=msg)


# %%

colormap = list(webcolors._definitions._CSS3_NAMES_TO_HEX.items())

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

c = Compound([Sphere(1.2), Circle(2).wires()[0]])
mixed = Compound([Box(1, 2, 3), Circle(1), Line((0, 0), (1, 1)), c])

c1 = Compound([Box(1, 2, 3), Sphere(1)])
c2 = Compound([Cone(1, 2, 3), Box(1, 1, 1)])
unmixed = Compound([c1, c2])

# CompSolids

c1 = Cylinder(2, 1)
c2 = Pos(0, 0, -2) * c1
s = Pos(0, 0, -0.5) * Sphere(1.5)


s1 = (c2 - s).solid()
s2 = (c2 & s).solid()
t = s - c1 - c2
s3 = t.solids().sort_by(Axis.Z)[0]
s4 = ((s and c1) - s).solid()
s5 = (s & c1).solid()
s6 = t.solids().sort_by(Axis.Z)[1]

solids = [s1, s2, s3, s4, s5, s6]
ocp_solids = [x.wrapped for x in solids]

ocp_compsolid = make_compsolid(ocp_solids)
compsolid = Compound(ocp_compsolid)
compound1 = Compound(
    [
        (Pos(0, -3, -1) * Box(1, 1, 1)).shell(),
        Compound(ocp_compsolid),
        (Pos(0, 3, -1) * Cylinder(0.5, 1)).solid(),
    ]
)
ocp_compound = make_compound(
    [
        (Pos(0, -3, -1) * Box(1, 1, 1)).shell().wrapped,
        ocp_compsolid,
        (Pos(0, 3, -1) * Cylinder(0.5, 1)).solid().wrapped,
    ]
)


class TestsConvert(MyUnitTest):
    """Tests for the OcpConverter class"""

    def test_buildpart(self):
        """Test that a part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bp)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_buildsketch(self):
        """Test that a sketch is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bs)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_face(i[o.ref]["obj"]))

    def test_buildsketch_local(self):
        """Test that a sketch_local is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bs, sketch_local=True)
        i = c.instances
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(g.name, "Face")
        for o, n in zip(g.objects, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(i[o.ref]["obj"]))

    def test_buildline(self):
        """Test that a line is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bl)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertEqual(len(i), 0)
        self.assertTrue(is_topods_edge(o.obj))

    def test_buildpart_2(self):
        """Test that a part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bp2)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_buildsketch_2(self):
        """Test that a sketch is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bs2)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_buildsketch_local_2(self):
        """Test that a sketch_local is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bs2, sketch_local=True)
        i = c.instances
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(g.name, "Face")
        for o, n in zip(g.objects, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_buildline_2(self):
        """Test that a line is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bl2)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertEqual(len(i), 0)
        for i in range(2):
            self.assertTrue(is_topods_edge(o.obj[i]))

    def test_buildpart_name(self):
        """Test that the name is set correctly for a part"""
        c = OcpConverter()
        g = c.to_ocp(bp, names=["bp"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "bp")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_buildsketch_name(self):
        """Test that the name is set correctly for a sketch"""
        c = OcpConverter()
        g = c.to_ocp(bs, names=["bs"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "bs")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_face(i[o.ref]["obj"]))

    def test_buildsketch_local_name(self):
        """Test that the name is set correctly for a sketch_local"""
        c = OcpConverter()
        g = c.to_ocp(bs, names=["bs"], sketch_local=True)
        i = c.instances
        self.assertEqual(g.length, 2)
        self.assertEqual(g.name, "bs")
        for o, n in zip(g.objects, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertIsNotNone(o.ref)
            self.assertIsNone(o.obj)
            self.assertTrue(is_topods_face(i[o.ref]["obj"]))
            loc = loc_to_tq(o.loc)
            self._assertTupleAlmostEquals(loc[0], (0, 0, 0), 6)
            if n == "sketch":
                self._assertTupleAlmostEquals(loc[1], (0.5, 0.5, 0.5, 0.5), 6)
            else:
                self._assertTupleAlmostEquals(loc[1], (0, 0, 0, 1), 6)

    def test_buildsketch_local_color(self):
        """Test that the color is set correctly for a sketch_local"""
        c = OcpConverter()
        g = c.to_ocp(bs, sketch_local=True)
        i = c.instances
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(g.name, "Face")
        for o, n in zip(g.objects, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(i[o.ref]["obj"]))

    def test_buildline_name_color(self):
        """Test that the name and color are set correctly for a line"""
        c = OcpConverter()
        g = c.to_ocp(bl, names=["bl"])
        self.assertEqual(g.length, 1)
        i = c.instances
        o = g.objects[0]
        self.assertEqual(o.name, "bl")
        self.assertEqual(o.kind, "edge")
        self.assertEqual(len(i), 0)
        self.assertTrue(is_topods_edge(o.obj))

    def test_part_wrapped(self):
        """Test that a wrapped part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.wrapped)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_part_wrapped_2(self):
        """Test that a wrapped part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b2.wrapped)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_show_solid_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.solids()[0])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#e8b024")

    def test_show_solids_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.solids())
        o = g.objects[0]
        self.assertEqual(g.length, 1)
        self.assertEqual(o.color.web_color, "#e8b024")

    def test_show_solids_list_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(*b2.solids())
        self.assertEqual(g.length, 2)
        for o in g.objects:
            self.assertEqual(o.color.web_color, "#e8b024")

    def test_show_shell_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.shells()[0])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ee82ee")

    def test_show_shells_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.shells())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ee82ee")

    def test_show_shells_list_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(*b2.shells())
        self.assertEqual(g.length, 2)
        for o in g.objects:
            self.assertEqual(o.color.web_color, "#ee82ee")

    def test_show_face_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.faces()[0])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ee82ee")

    def test_show_faces_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.faces())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ee82ee")

    def test_show_faces_list_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(*b2.faces())
        self.assertEqual(g.length, 12)
        for o in g.objects:
            self.assertEqual(o.color.web_color, "#ee82ee")

    def test_show_wire_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.wires()[0])
        self.assertEqual(g.length, 1)
        for o in g.objects:
            self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_wires_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.wires())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_wires_list_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(*b2.wires())
        self.assertEqual(g.length, 12)
        for o in g.objects:
            self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_edge_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.edges()[0])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_edges_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.edges())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_edges_list_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(*b2.edges())
        self.assertEqual(g.length, 24)
        for o in g.objects:
            self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_vertex_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.vertices()[0])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_vertices_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(b2.vertices())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_show_vertices_list_default_colors(self):
        c = OcpConverter()
        g = c.to_ocp(*b2.vertices())
        self.assertEqual(g.length, 16)
        for o in g.objects:
            self.assertEqual(o.color.web_color, "#ba55d3")

    #

    def test_show_solid_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.solids()[0], names=["MySolid"], colors=[colormap[0][0]])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, colormap[0][1])
        self.assertEqual(o.name, "MySolid")

    def test_show_solids_colors_names(self):
        c = OcpConverter()
        names = ["MySolidShapeList"]
        colors = [bd.Color("Orange", 0.7)]
        g = c.to_ocp(b2.solids(), names=names, colors=colors)
        o = g.objects[0]
        self.assertEqual(g.length, 1)
        self.assertEqual(o.color.web_color, "#ff5f00")
        self.assertAlmostEqual(o.color.a, 0.7, 6)
        self.assertEqual(o.name, "MySolidShapeList")

    def test_show_solids_list_colors_names(self):
        c = OcpConverter()
        objs = b2.solids()
        names = [f"MySolid_{ind}" for ind in range(len(objs))]
        colors = [colormap[ind][0] for ind in range(len(objs))]
        g = c.to_ocp(*objs, names=names, colors=colors)
        self.assertEqual(g.length, 2)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.color.web_color, colormap[ind][1])
            self.assertEqual(o.name, f"MySolid_{ind}")

    def test_show_shell_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.shells()[0], colors=[colormap[0][0]])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, colormap[0][1])

    def test_show_shells_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.shells(), colors=[bd.Color("Orange", 0.7)])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ff5f00")

    def test_show_shells_list_colors_names(self):
        c = OcpConverter()
        objs = b2.shells()
        names = [f"MyShell_{ind}" for ind in range(len(objs))]
        colors = [colormap[ind][0] for ind in range(len(objs))]
        g = c.to_ocp(*objs, names=names, colors=colors)
        self.assertEqual(g.length, 2)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.color.web_color, colormap[ind][1])
            self.assertEqual(o.name, f"MyShell_{ind}")

    def test_show_face_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.faces()[0], colors=[colormap[0][0]])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, colormap[0][1])

    def test_show_faces_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.faces(), colors=[bd.Color("Orange", 0.7)])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ff5f00")

    def test_show_faces_list_colors_names(self):
        c = OcpConverter()
        objs = b2.faces()
        names = [f"MyFace_{ind}" for ind in range(len(objs))]
        colors = [colormap[ind][0] for ind in range(len(objs))]
        g = c.to_ocp(*objs, names=names, colors=colors)
        self.assertEqual(g.length, 12)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.color.web_color, colormap[ind][1])
            self.assertEqual(o.name, f"MyFace_{ind}")

    def test_show_wire_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.wires()[0], colors=[colormap[0][0]])
        self.assertEqual(g.length, 1)
        for o in g.objects:
            self.assertEqual(o.color.web_color, colormap[0][1])

    def test_show_wires_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.wires(), colors=[bd.Color("Orange", 1.0)])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ff5f00")

    def test_show_wires_list_colors_names(self):
        c = OcpConverter()
        objs = b2.wires()
        names = [f"MyWire_{ind}" for ind in range(len(objs))]
        colors = [colormap[ind][0] for ind in range(len(objs))]
        g = c.to_ocp(*objs, names=names, colors=colors)
        self.assertEqual(g.length, 12)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.color.web_color, colormap[ind][1])
            self.assertEqual(o.name, f"MyWire_{ind}")

    def test_show_edge_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.edges()[0], colors=[colormap[0][0]])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, colormap[0][1])

    def test_show_edges_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.edges(), colors=[bd.Color("Orange", 1.0)])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ff5f00")

    def test_show_edges_list_colors_names(self):
        c = OcpConverter()
        objs = b2.edges()
        names = [f"MyEdge_{ind}" for ind in range(len(objs))]
        colors = [colormap[ind][0] for ind in range(len(objs))]
        g = c.to_ocp(*objs, names=names, colors=colors)
        self.assertEqual(g.length, 24)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.color.web_color, colormap[ind][1])
            self.assertEqual(o.name, f"MyEdge_{ind}")

    def test_show_vertex_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.vertices()[0], colors=[colormap[0][0]])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, colormap[0][1])

    def test_show_vertices_colors_names(self):
        c = OcpConverter()
        g = c.to_ocp(b2.vertices(), colors=[bd.Color("Orange", 1.0)])
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.color.web_color, "#ff5f00")

    def test_show_vertices_list_colors_names(self):
        c = OcpConverter()
        objs = b2.vertices()
        names = [f"MyVertex_{ind}" for ind in range(len(objs))]
        colors = [colormap[ind][0] for ind in range(len(objs))]
        g = c.to_ocp(*objs, names=names, colors=colors)
        self.assertEqual(g.length, 16)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.color.web_color, colormap[ind][1])
            self.assertEqual(o.name, f"MyVertex_{ind}")

    #

    def test_show_mixed_builder_shape(self):
        c = OcpConverter()
        g = c.to_ocp(bl, Box(0.1, 0.1, 0.1))
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        o = g.objects[1]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")

    #

    def test_show_plane(self):
        c = OcpConverter()
        g = c.to_ocp(Plane.XZ)
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Plane")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj[0]))

    def test_show_Axis(self):
        c = OcpConverter()
        g = c.to_ocp(Axis.X)
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Axis")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj[0]))


class TestsConvert2(MyUnitTest):

    def test_buildpart(self):
        """Test that a part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bp2)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_buildsketch(self):
        """Test that a sketch is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bs2)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_buildsketch_local(self):
        """Test that a sketch_local is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bs2, sketch_local=True)
        i = c.instances
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(g.name, "Face")
        for o, n in zip(g.objects, ["sketch", "sketch_local"]):
            self.assertEqual(o.name, n)
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_buildline(self):
        """Test that a line is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(bl2)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertEqual(len(i), 0)
        for i in range(2):
            self.assertTrue(is_topods_edge(o.obj[i]))


class TestsShapeLists(MyUnitTest):
    """Tests for the OcpConverter class with shape lists"""

    def test_shapelist_solids(self):
        """Test that a shapelist of solids is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.solids())
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Solid)")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_shapelist_shells(self):
        """Test that a shapelist of shells is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.shells())
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Shell)")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_shell(i[o.ref]["obj"]))

    def test_shapelist_face(self):
        """Test that a shapelist of faces is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.faces())
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Face)")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_shapelist_edge(self):
        """Test that a shapelist of edges is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.edges())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Edge)")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(isinstance(o.obj, list))
        self.assertTrue(all(is_topods_edge(e) for e in o.obj))

    def test_shapelist_wire(self):
        """Test that a shapelist of wires is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.wires())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Wire)")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(isinstance(o.obj, list))
        self.assertTrue(all(is_topods_edge(e) for e in o.obj))

    def test_shapelist_vertex(self):
        """Test that a shapelist of vertices is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.vertices())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Vertex)")
        self.assertEqual(o.kind, "vertex")
        self.assertTrue(isinstance(o.obj, list))
        self.assertTrue(all(is_topods_vertex(e) for e in o.obj))

    def test_shapelist_solids_2(self):
        """Test that a shapelist of solids is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b2.solids())
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Solid)")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_shapelist_shells_2(self):
        """Test that a shapelist of shells is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b2.shells())
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Shell)")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_shapelist_face_2(self):
        """Test that a shapelist of faces is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b2.faces())
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Face)")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_shapelist_edge_2(self):
        """Test that a shapelist of edges is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b2.edges())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Edge)")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(isinstance(o.obj, list))
        self.assertTrue(all(is_topods_edge(e) for e in o.obj))

    def test_shapelist_wire_2(self):
        """Test that a shapelist of wires is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b2.wires())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Wire)")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(isinstance(o.obj, list))
        self.assertTrue(all(is_topods_edge(e) for e in o.obj))

    def test_shapelist_vertex_2(self):
        """Test that a shapelist of vertices is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b2.vertices())
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Vertex)")
        self.assertEqual(o.kind, "vertex")
        self.assertTrue(isinstance(o.obj, list))
        self.assertTrue(all(is_topods_vertex(e) for e in o.obj))

    def test_shapelist_solids_2_list(self):
        """Test that a shapelist of solids is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(*b2.solids())
        i = c.instances
        self.assertEqual(g.length, 2)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.name, "Solid" if ind == 0 else f"Solid({ind+1})")
            self.assertEqual(o.kind, "solid")
            self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_shapelist_shells_2_list(self):
        """Test that a shapelist of shells is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(*b2.shells())
        i = c.instances
        self.assertEqual(g.length, 2)
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.name, "Shell" if ind == 0 else f"Shell({ind+1})")
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_shell(i[o.ref]["obj"]))

    def test_shapelist_face_2_list(self):
        """Test that a shapelist of faces is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(*b2.faces())
        i = c.instances
        self.assertEqual(g.length, 12)
        o = g.objects[0]
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.name, "Face" if ind == 0 else f"Face({ind+1})")
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(i[o.ref]["obj"]))

    def test_shapelist_edge_2_list(self):
        """Test that a shapelist of edges is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(*b2.edges())
        self.assertEqual(g.length, 24)
        o = g.objects[0]
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.name, "Edge" if ind == 0 else f"Edge({ind+1})")
            self.assertEqual(o.kind, "edge")
            self.assertTrue(is_topods_edge(o.obj))

    def test_shapelist_wire_2_list(self):
        """Test that a shapelist of wires is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(*b2.wires())
        self.assertEqual(g.length, 12)
        o = g.objects[0]
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.name, "Wire" if ind == 0 else f"Wire({ind+1})")
            self.assertEqual(o.kind, "edge")
            self.assertTrue(all(is_topods_edge(e) for e in o.obj))

    def test_shapelist_vertex_2_list(self):
        """Test that a shapelist of vertices is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(*b2.vertices())
        self.assertEqual(g.length, 16)
        o = g.objects[0]
        for ind, o in enumerate(g.objects):
            self.assertEqual(o.name, "Vertex" if ind == 0 else f"Vertex({ind+1})")
            self.assertEqual(o.kind, "vertex")
            self.assertTrue(is_topods_vertex(o.obj))

    def test_shapelist_vector(self):
        """Test that a shapelist of vertices is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(ShapeList([Vector(0, 1, 2), Vector(3, 4, 5)]))
        o = g.objects[0]
        self.assertEqual(g.length, 1)
        self.assertEqual(o.name, "ShapeList(Vertex)")
        self.assertEqual(o.kind, "vertex")
        self.assertTrue(is_topods_vertex(o.obj[0]))
        self.assertTrue(is_topods_vertex(o.obj[1]))

    def test_shapeList_compound(self):
        """Test that a shapelist of a compound is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(ShapeList([r]))
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "ShapeList(Face)")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_face(i[o.ref]["obj"]))

    def test_shapeList_compounds(self):
        """Test that a shapelist of compounds is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(
            [
                r,
                Pos(
                    1,
                    1,
                )
                * r,
            ]
        )
        i = c.instances
        self.assertEqual(g.length, 2)
        for n, o in enumerate(g.objects):
            self.assertEqual(o.name, "Face" if n == 0 else f"Face({n+1})")
            self.assertEqual(o.kind, "face")
            self.assertTrue(is_topods_face(i[o.ref]["obj"]))


class TestsConvertMoved(MyUnitTest):
    """Tests for the OcpConverter class with moved objects"""

    def test_part_wrapped_moved(self):
        """Test that a moved wrapped part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(b.wrapped.Moved(Location((2, 0, 0)).wrapped))
        o = g.objects[0]
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_part_algebra_moved(self):
        """Test that a moved algebra part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(Pos(4, 0, 0) * b)
        o = g.objects[0]
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_part_wrapped_algebra_moved(self):
        """Test that a moved algebra wrapped part is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(Pos(6, 0, 0) * Part(b.wrapped))
        o = g.objects[0]
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_compoud_algebra_moved(self):
        """Test that a moved algebra compound is converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(Pos(8, 0, 0) * Compound(b.wrapped))
        o = g.objects[0]
        i = c.instances
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))


class TestConvertMixedCompounds(MyUnitTest):

    def test_mixed_compound(self):
        c = OcpConverter()
        g = c.to_ocp(mixed)
        self.assertEqual(g.length, 4)
        i = c.instances
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))
        o = g.objects[1]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_face(i[o.ref]["obj"]))
        o = g.objects[2]
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj))
        g = g.objects[3]
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))
        o = g.objects[1]
        self.assertEqual(o.name, "Wire")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj))

    def test_mixed_topods_compound(self):
        c = OcpConverter()
        g = c.to_ocp(mixed.wrapped)
        self.assertEqual(g.length, 4)
        i = c.instances
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))
        o = g.objects[1]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertTrue(is_topods_face(i[o.ref]["obj"]))
        o = g.objects[2]
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj))
        g = g.objects[3]
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))
        o = g.objects[1]
        self.assertEqual(o.name, "Wire")
        self.assertEqual(o.kind, "edge")
        self.assertTrue(is_topods_edge(o.obj))

    def test_unmixed(self):
        c = OcpConverter()
        g = c.to_ocp(unmixed)
        self.assertEqual(g.length, 1)
        i = c.instances
        o = g.objects[0]
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))
        self.assertEqual(o.name, f"Solid")
        self.assertEqual(o.kind, "solid")


class TestCompund(MyUnitTest):

    def test_compound_solid(self):
        c = OcpConverter()
        g = c.to_ocp(Compound(b2.solids()))
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_compound_shell(self):
        c = OcpConverter()
        g = c.to_ocp(Compound(b2.shells()))
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Shell")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_compound_face(self):
        c = OcpConverter()
        g = c.to_ocp(Compound(b2.faces()))
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))

    def test_compound_wire(self):
        c = OcpConverter()
        g = c.to_ocp(Compound(b2.wires()))
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Wire")
        self.assertEqual(o.kind, "edge")
        self.assertIsNotNone(o.obj)
        self.assertTrue(isinstance(o.obj, list))
        self.assertEqual(len(o.obj), 24)
        self.assertTrue(is_topods_edge(o.obj[0]))

    def test_compound_edge(self):
        c = OcpConverter()
        g = c.to_ocp(Compound(b2.edges()))
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Edge")
        self.assertEqual(o.kind, "edge")
        self.assertIsNotNone(o.obj)
        self.assertTrue(isinstance(o.obj, list))
        self.assertEqual(len(o.obj), 24)
        self.assertTrue(is_topods_edge(o.obj[0]))

    def test_compound_solid(self):
        c = OcpConverter()
        g = c.to_ocp(Compound(b2.vertices()))
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")
        print(o.obj)
        self.assertIsNotNone(o.obj)
        self.assertTrue(isinstance(o.obj, list))
        self.assertEqual(len(o.obj), 16)
        self.assertTrue(is_topods_vertex(o.obj[0]))


class TestVector(MyUnitTest):
    def test_vector(self):
        c = OcpConverter()
        g = c.to_ocp(Vector(1, 1, 1))
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")

    def test_vectors(self):
        c = OcpConverter()
        g = c.to_ocp(Vector(1, 1, 1), Vector(2, 2, 2))
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")
        o = g.objects[1]
        self.assertEqual(o.name, "Vertex(2)")
        self.assertEqual(o.kind, "vertex")

    def test_vector_list(self):
        c = OcpConverter()
        g = c.to_ocp((Vector(1, 1, 1), Vector(2, 2, 2)))
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")
        o = g.objects[1]
        self.assertEqual(o.name, "Vertex(2)")
        self.assertEqual(o.kind, "vertex")

    def test_vector_wrapped(self):
        c = OcpConverter()
        g = c.to_ocp(Vector(1, 1, 1).wrapped, Vector(2, 2, 2).wrapped)
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")
        o = g.objects[1]
        self.assertEqual(o.name, "Vertex(2)")
        self.assertEqual(o.kind, "vertex")


class TestMultipleObjects(MyUnitTest):
    def test_multiple_objects(self):
        s = bd.Sphere(1)
        b = bd.Box(1, 2, 3)
        b1 = bd.Pos(X=3) * b
        b2 = bd.Pos(X=-3) * b

        c = OcpConverter()
        g = c.to_ocp(
            s,
            b1,
            b2,
            names=["s", "b1", "b2"],
            colors=["red", "green", "blue"],
            alphas=[0.8, 0.6, 0.4],
        )
        self.assertEqual(g.length, 3)
        o = g.objects[0]
        self.assertEqual(o.name, "s")
        self.assertEqual(o.color.web_color, "#ff0000")
        self.assertEqual(o.color.a, 0.8)
        o = g.objects[1]
        self.assertEqual(o.name, "b1")
        self.assertEqual(o.color.web_color, "#008000")
        self.assertEqual(o.color.a, 0.6)
        o = g.objects[2]
        self.assertEqual(o.name, "b2")
        self.assertEqual(o.color.web_color, "#0000ff")
        self.assertEqual(o.color.a, 0.4)


class TestComSolid(MyUnitTest):

    def test_compsolid_ocp(self):
        c = OcpConverter()
        g = c.to_ocp(ocp_compsolid)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "CompSolid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compsolid(i[o.ref]["obj"]))

    def test_compsolid(self):
        c = OcpConverter()
        g = c.to_ocp(compsolid)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "CompSolid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compsolid(i[o.ref]["obj"]))

    def test_compsolid_mixed_compound(self):
        c = OcpConverter()
        g = c.to_ocp(compound1)
        i = c.instances
        self.assertEqual(g.length, 3)

        o = g.objects[0]
        self.assertEqual(o.name, "Shell")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_shell(i[o.ref]["obj"]))

        o = g.objects[1]
        self.assertEqual(o.name, "CompSolid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compsolid(i[o.ref]["obj"]))

        o = g.objects[2]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))

    def test_compsolid_mixed_ocp_compound(self):
        c = OcpConverter()
        g = c.to_ocp(ocp_compound)
        i = c.instances
        self.assertEqual(g.length, 3)

        o = g.objects[0]
        self.assertEqual(o.name, "Shell")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_shell(i[o.ref]["obj"]))

        o = g.objects[1]
        self.assertEqual(o.name, "CompSolid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compsolid(i[o.ref]["obj"]))

        o = g.objects[2]
        self.assertEqual(o.name, "Solid")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))
