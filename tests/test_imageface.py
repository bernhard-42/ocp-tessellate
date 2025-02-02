import unittest

import pytest
from build123d import *

from ocp_tessellate.cad_objects import ImageFace
from ocp_tessellate.convert import OcpConverter
from ocp_tessellate.ocp_utils import *


class MyUnitTest(unittest.TestCase):
    def _assertTupleAlmostEquals(self, expected, actual, places, msg=None):
        for i, j in zip(actual, expected):
            self.assertAlmostEqual(i, j, places, msg=msg)


class TestsImageFace(MyUnitTest):
    """Tests for the ImageFace class"""

    def test_image_face(self):
        """Test that an ImageFace gets converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(
            ImageFace("tests/object-160x160mm.png", 600 / 912, name="imageplane")
        )
        i = c.instances
        self.assertEqual(g.length, 1)
        o = g.objects[0]
        self.assertEqual(o.name, "imageplane")
        self.assertEqual(o.kind, "imageface")
        self.assertIsNotNone(o.ref)
        self.assertIsNone(o.obj)
        self.assertTrue(is_topods_face(i[o.ref]["obj"]))
        self.assertEqual(o.color.a, 1.0)

    def test_image_faces(self):
        """Test that an two ImageFace gets converted correctly"""
        c = OcpConverter()
        g = c.to_ocp(
            ImageFace(
                "tests/object-160x160mm.png",
                600 / 912,
                name="face0",
                location=Location((100, 0, 0), (90, 0, 0)),
            ),
            ImageFace(
                "tests/object-160x160mm.png",
                600 / 912,
                (912 / 2, 914 / 2),
                name="face1",
                location=Location((0, -100, 0)),
            ),
        )
        i = c.instances
        self.assertEqual(g.length, 2)
        for ind in range(2):
            o = g.objects[ind]
            self.assertEqual(o.name, f"face{ind}")
            self.assertEqual(o.kind, "imageface")
            self.assertIsNotNone(o.ref)
            self.assertIsNone(o.obj)
            self.assertTrue(is_topods_face(i[o.ref]["obj"]))
            self.assertEqual(o.color.a, 1.0)
            if ind == 0:
                self._assertTupleAlmostEquals(
                    (400.0, -6.672440377997191e-14, -300.65789473684214),
                    loc_to_tq(o.loc)[0],
                    5,
                )
                self._assertTupleAlmostEquals(
                    (0.7071067811865475, 0.0, 0.0, 0.7071067811865476),
                    loc_to_tq(o.loc)[1],
                    5,
                )
            else:
                self._assertTupleAlmostEquals((0.0, -100, 0.0), loc_to_tq(o.loc)[0], 5)
                self._assertTupleAlmostEquals(
                    (0.0, 0.0, 0.0, 1.0),
                    loc_to_tq(o.loc)[1],
                    5,
                )
