import unittest

import cadquery as cq
import pytest
import webcolors

from ocp_tessellate.convert import OcpConverter, tessellate_group, to_ocpgroup
from ocp_tessellate.ocp_utils import *


class MyUnitTest(unittest.TestCase):
    def _assertTupleAlmostEquals(self, expected, actual, places, msg=None):
        for i, j in zip(actual, expected):
            self.assertAlmostEqual(i, j, places, msg=msg)


colormap = list(webcolors._definitions._CSS3_NAMES_TO_HEX.items())


class TestWorkplane(MyUnitTest):
    def test_box(self):
        result = cq.Workplane().box(1, 1, 1)
        c = OcpConverter()
        g = c.to_ocp(result, names=["Box"], colors=["red"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Box")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_solid(i[o.ref]["obj"]))
        self.assertEqual(o.color.web_color, "#ff0000")

    def test_boxes_compound(self):
        result = cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2))
        c = OcpConverter()
        g = c.to_ocp(result, names=["Box"], colors=["red"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Box")
        self.assertEqual(o.kind, "solid")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))
        self.assertEqual(o.color.web_color, "#ff0000")

    def test_boxes(self):
        result = cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2))
        c = OcpConverter()
        g = c.to_ocp(*result.val(), names=["Box0", "Box1"], colors=["red", "green"])
        i = c.instances
        self.assertEqual(g.length, 2)
        cols = ["#ff0000", "#008000"]
        for ind in range(2):
            o = g.objects[ind]
            self.assertEqual(o.name, f"Box{ind}")
            self.assertEqual(o.kind, "solid")
            self.assertIsNotNone(o.ref)
            self.assertIsNone(o.obj)
            self.assertTrue(is_topods_solid(i[o.ref]["obj"]))
            self.assertEqual(o.color.web_color, cols[ind])

    def test_faces_compound(self):
        result = cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2)).faces()
        c = OcpConverter()
        g = c.to_ocp(result, names=["Faces"], colors=["cyan"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Faces")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))
        self.assertEqual(o.color.web_color, "#00ffff")

    def test_wires_compound(self):
        result = cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2)).wires()
        c = OcpConverter()
        g = c.to_ocp(result, names=["Wires"], colors=["cyan"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Wires")
        self.assertEqual(o.kind, "edge")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertEqual(len(o.obj), 48)
        self.assertTrue(is_topods_edge(o.obj[0]))
        self.assertEqual(o.color.web_color, "#00ffff")

    def test_edges_compound(self):
        result = cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2)).edges()
        c = OcpConverter()
        g = c.to_ocp(result, names=["Edges"], colors=["cyan"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Edges")
        self.assertEqual(o.kind, "edge")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertEqual(len(o.obj), 24)
        self.assertTrue(is_topods_edge(o.obj[0]))
        self.assertEqual(o.color.web_color, "#00ffff")

    def test_vertices_compound(self):
        result = (
            cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2)).vertices()
        )
        c = OcpConverter()
        g = c.to_ocp(result, names=["Vertex"], colors=["cyan"])
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertEqual(len(o.obj), 16)
        self.assertTrue(is_topods_vertex(o.obj[0]))
        self.assertEqual(o.color.web_color, "#00ffff")

    def test_faces(self):
        result = cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2)).faces()
        c = OcpConverter()
        g = c.to_ocp(
            *result.vals(),
            names=[f"face{i}" for i in range(12)],
            colors=[c[0] for c in colormap[:12]],
        )
        i = c.instances
        self.assertEqual(g.length, 12)
        for ind in range(12):
            o = g.objects[ind]
            self.assertEqual(o.name, f"face{ind}")
            self.assertEqual(o.kind, "face")
            self.assertIsNotNone(o.ref)
            self.assertIsNone(o.obj)
            self.assertTrue(is_topods_face(i[o.ref]["obj"]))
            self.assertEqual(o.color.web_color, colormap[ind][1])

    def test_edges(self):
        result = cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2)).edges()
        c = OcpConverter()
        g = c.to_ocp(
            *result.vals(),
            names=[f"edge{i}" for i in range(24)],
            colors=[c[0] for c in colormap[:24]],
        )
        i = c.instances
        self.assertEqual(g.length, 24)
        for ind in range(12):
            o = g.objects[ind]
            self.assertEqual(o.name, f"edge{ind}")
            self.assertEqual(o.kind, "edge")
            self.assertIsNone(o.ref)
            self.assertIsNotNone(o.obj)
            self.assertTrue(is_topods_edge(o.obj))
            self.assertEqual(o.color.web_color, colormap[ind][1])

    def test_vertices(self):
        result = (
            cq.Workplane().box(1, 1, 1).cut(cq.Workplane().box(2, 2, 0.2)).vertices()
        )
        c = OcpConverter()
        g = c.to_ocp(
            *result.vals(),
            names=[f"vertex{i}" for i in range(16)],
            colors=[c[0] for c in colormap[:16]],
        )
        i = c.instances
        self.assertEqual(g.length, 16)
        for ind in range(12):
            o = g.objects[ind]
            self.assertEqual(o.name, f"vertex{ind}")
            self.assertEqual(o.kind, "vertex")
            self.assertIsNone(o.ref)
            self.assertIsNotNone(o.obj)
            self.assertTrue(is_topods_vertex(o.obj))
            self.assertEqual(o.color.web_color, colormap[ind][1])


class TestCadQuerySketch(MyUnitTest):
    def test_trapezoid_vertices(self):
        result = (
            cq.Sketch()
            .trapezoid(4, 3, 90)
            .vertices()
            .circle(0.5, mode="s")
            .reset()
            .vertices()
        )
        c = OcpConverter()
        g = c.to_ocp(result)
        i = c.instances
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))
        self.assertEqual(g.objects[0].color.web_color, "#ee82ee")
        o = g.objects[1]
        self.assertEqual(o.name, "Selection")
        self.assertEqual(o.kind, "vertex")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(isinstance(o.obj, list))
        self.assertEqual(len(o.obj), 8)
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_trapezoid_rarray(self):
        result = (
            cq.Sketch()
            .trapezoid(4, 3, 90)
            .vertices()
            .circle(0.5, mode="s")
            .reset()
            .vertices()
            .fillet(0.25)
            .reset()
            .rarray(0.6, 1, 5, 1)
        )
        c = OcpConverter()
        g = c.to_ocp(result)
        i = c.instances
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))
        self.assertEqual(g.objects[0].color.web_color, "#ee82ee")
        g2 = g.objects[1]
        self.assertEqual(g2.length, 5)
        for ind, loc in enumerate(g2.objects):
            self.assertEqual(loc.kind, "edge")
            self.assertEqual(loc.name, "Location" if ind == 0 else f"Location({ind+1})")
            self.assertIsNone(loc.ref)
            self.assertIsNotNone(loc.obj)
            self.assertTrue(isinstance(loc.obj, list))
            self.assertTrue(len(loc.obj), 3)

    def test_trapezoid_reset(self):
        result = (
            cq.Sketch()
            .trapezoid(4, 3, 90)
            .vertices()
            .circle(0.5, mode="s")
            .reset()
            .vertices()
            .fillet(0.25)
            .reset()
            .rarray(0.6, 1, 5, 1)
            .reset()
        )
        c = OcpConverter()
        g = c.to_ocp(result)
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertEqual(o.kind, "face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_compound(i[o.ref]["obj"]))
        self.assertEqual(g.objects[0].color.web_color, "#ee82ee")

    def test_multi_segment(self):
        locs = [cq.Location((2 * x, 2 * y, 0)) for x in range(2) for y in range(2)]
        result = cq.Sketch(locs=locs).segment((0.0, 0.0), (0.0, 1.0)).segment((1.0, 0))
        c = OcpConverter()
        g = c.to_ocp(result)
        self.assertTrue(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Edge")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(isinstance(o.obj, list))
        self.assertEqual(len(o.obj), 8)
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_multi_segment_vertices(self):
        locs = [cq.Location((2 * x, 2 * y, 0)) for x in range(2) for y in range(2)]
        result = (
            cq.Sketch(locs=locs)
            .segment((0.0, 0.0), (0.0, 1.0))
            .segment((1.0, 0))
            .vertices()
        )
        c = OcpConverter()
        g = c.to_ocp(result)
        self.assertTrue(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Edge")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(isinstance(o.obj, list))
        self.assertEqual(len(o.obj), 8)
        self.assertEqual(o.color.web_color, "#ba55d3")
        o = g.objects[1]
        self.assertEqual(o.name, "Selection")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(isinstance(o.obj, list))
        self.assertEqual(len(o.obj), 16)
        self.assertEqual(o.color.web_color, "#ba55d3")

    def test_multi_workplane_sketch(self):

        result = (
            cq.Workplane()
            .transformed((0, 90, 90), (2, 0, 0))
            .sketch()
            .trapezoid(4, 3, 90)
            .vertices()
            .circle(0.5, mode="s")
            .reset()
            .vertices()
            .fillet(0.25)
            .reset()
            .rarray(0.6, 1, 5, 1)
            .slot(01.5, 0.4, mode="s", angle=90)
            .reset()
            .finalize()
        )
        c = OcpConverter()
        g = c.to_ocp(result)
        self.assertTrue(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Face")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)


class TestVector(MyUnitTest):

    def test_vector(self):
        c = OcpConverter()
        g = c.to_ocp(cq.Vector(1, 1, 1))
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")

    def test_vectors(self):
        c = OcpConverter()
        g = c.to_ocp(cq.Vector(1, 1, 1), cq.Vector(2, 2, 2))
        self.assertEqual(g.length, 2)
        o = g.objects[0]
        self.assertEqual(o.name, "Vertex")
        self.assertEqual(o.kind, "vertex")
        o = g.objects[1]
        self.assertEqual(o.name, "Vertex(2)")
        self.assertEqual(o.kind, "vertex")


class TestTessellator(MyUnitTest):
    def test_wires_1(self):
        result = (
            cq.Workplane("ZY")
            .workplane(offset=50)
            .circle(5)
            .circle(4)
            .consolidateWires()
        )
        g, i = to_ocpgroup(result)
        r = tessellate_group(g, i)
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.kind, "edge")
        self.assertIsNone(o.ref)
        self.assertIsNotNone(o.obj)
        self.assertTrue(is_topods_edge(o.obj[0]))
        self.assertTrue(is_topods_edge(o.obj[1]))
