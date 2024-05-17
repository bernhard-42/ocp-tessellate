import unittest

import cadquery as cq
import pytest
import webcolors

from ocp_tessellate.convert import OcpConverter
from ocp_tessellate.ocp_utils import *


class MyUnitTest(unittest.TestCase):
    def _assertTupleAlmostEquals(self, expected, actual, places, msg=None):
        for i, j in zip(actual, expected):
            self.assertAlmostEqual(i, j, places, msg=msg)


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
        self.assertTrue(is_topods_compound(i[o.ref][0]))
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
        self.assertTrue(is_topods_compound(i[o.ref][0]))
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
        self.assertTrue(is_topods_compound(i[o.ref][0]))
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
