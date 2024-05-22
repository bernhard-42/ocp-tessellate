import unittest

import pytest
import webcolors
from build123d import *

from ocp_tessellate.convert import OcpConverter
from ocp_tessellate.ocp_utils import *


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
