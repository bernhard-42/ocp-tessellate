import unittest

import build123d as bd
import cadquery as cq
import pytest

from ocp_tessellate.ocp_utils import get_rgba
from ocp_tessellate.utils import Color


class TestColor(unittest.TestCase):

    def test_color_name(self):
        c = Color("aliceblue")
        self.assertEqual(c.web_color, "#f0f8ff")
        self.assertEqual(c.a, 1.0)

    def test_color_name_alpha(self):
        c = Color("aliceblue", 0.1)
        self.assertEqual(c.web_color, "#f0f8ff")
        self.assertAlmostEqual(c.a, 0.1, 6)

    def test_percentages(self):
        c = Color((0.2, 0.4, 0.8))
        self.assertEqual(c.web_color, "#3366cc")
        self.assertEqual(c.a, 1.0)

    def test_percentages_alpha(self):
        c = Color((0.2, 0.4, 0.8, 0.1))
        self.assertEqual(c.web_color, "#3366cc")
        self.assertAlmostEqual(c.a, 0.1, 6)

    def test_percentages_extra_alpha(self):
        c = Color((0.2, 0.4, 0.8, 0.1))
        self.assertEqual(c.web_color, "#3366cc")
        self.assertEqual(c.a, 0.1)

    def test_rgb(self):
        c = Color((160, 64, 16))
        self.assertEqual(c.web_color, "#a04010")
        self.assertEqual(c.a, 1.0)

    def test_rgb_alpha(self):
        c = Color((160, 64, 16, 128))
        self.assertEqual(c.web_color, "#a04010")
        self.assertAlmostEqual(c.a, 128 / 255, 6)

    def test_rgb_extra_alpha(self):
        c = Color((160, 64, 16), 0.5)
        self.assertEqual(c.web_color, "#a04010")
        self.assertEqual(c.a, 0.5)

    def test_color(self):
        c = Color(Color("red"))
        self.assertEqual(c.web_color, "#ff0000")
        self.assertEqual(c.a, 1.0)

    def test_color(self):
        c = Color(Color("red", 0.2))
        self.assertEqual(c.web_color, "#ff0000")
        self.assertAlmostEqual(c.a, 0.2, 6)

    def test_color_warn(self):
        with pytest.warns(RuntimeWarning):
            c = Color(Color("red", 1.2))
        self.assertEqual(c.web_color, "#ff0000")
        self.assertAlmostEqual(c.a, 1.0, 6)

    def test_color_fail(self):
        with pytest.raises(ValueError):
            c = Color(Color("redxgreenxblue", 1.2))


class TestGetRgba(unittest.TestCase):

    def test_color_name(self):
        c = get_rgba("aliceblue")
        self.assertEqual(c.web_color, "#f0f8ff")
        self.assertEqual(c.a, 1.0)

    def test_color_name_alpha(self):
        c = get_rgba("aliceblue", 0.1)
        self.assertEqual(c.web_color, "#f0f8ff")
        self.assertAlmostEqual(c.a, 0.1, 6)

    def test_percentages(self):
        c = get_rgba((0.2, 0.4, 0.8))
        self.assertEqual(c.web_color, "#3366cc")
        self.assertEqual(c.a, 1.0)

    def test_percentages_alpha(self):
        c = get_rgba((0.2, 0.4, 0.8, 0.1))
        self.assertEqual(c.web_color, "#3366cc")
        self.assertAlmostEqual(c.a, 0.1, 6)

    def test_percentages_extra_alpha(self):
        c = get_rgba((0.2, 0.4, 0.8, 0.1))
        self.assertEqual(c.web_color, "#3366cc")
        self.assertEqual(c.a, 0.1)

    def test_rgb(self):
        c = get_rgba((160, 64, 16))
        self.assertEqual(c.web_color, "#a04010")
        self.assertEqual(c.a, 1.0)

    def test_rgb_alpha(self):
        c = get_rgba((160, 64, 16, 128))
        self.assertEqual(c.web_color, "#a04010")
        self.assertAlmostEqual(c.a, 128 / 255, 6)

    def test_rgb_extra_alpha(self):
        c = get_rgba((160, 64, 16), 0.5)
        self.assertEqual(c.web_color, "#a04010")
        self.assertEqual(c.a, 0.5)

    def test_color(self):
        c = get_rgba(Color("red"))
        self.assertEqual(c.web_color, "#ff0000")
        self.assertEqual(c.a, 1.0)

    def test_color(self):
        c = get_rgba(Color("red", 0.2))
        self.assertEqual(c.web_color, "#ff0000")
        self.assertAlmostEqual(c.a, 0.2, 6)

    def test_color_warn(self):
        with pytest.warns(RuntimeWarning):
            c = get_rgba(Color("red", 1.2))
        self.assertEqual(c.web_color, "#ff0000")
        self.assertAlmostEqual(c.a, 1.0, 6)

    def test_color_fail(self):
        with pytest.raises(ValueError):
            c = get_rgba(Color("redxgreenxblue", 1.2))

    def test_bd_color(self):
        c = get_rgba(bd.Color("Orange"))
        self.assertEqual(c.web_color, "#ff5f00")
        self.assertAlmostEqual(c.a, 1.0, 6)

    def test_bd_color_alpha(self):
        c = get_rgba(bd.Color("Orange", 0.2))
        self.assertEqual(c.web_color, "#ff5f00")
        self.assertAlmostEqual(c.a, 0.2, 6)

    def test_bd_color_extra_alpha(self):
        c = get_rgba(bd.Color("Orange"), 0.2)
        self.assertEqual(c.web_color, "#ff5f00")
        self.assertAlmostEqual(c.a, 0.2, 6)

    def test_ocp_color(self):
        c = get_rgba(bd.Color("Orange").wrapped)
        self.assertEqual(c.web_color, "#ff5f00")
        self.assertAlmostEqual(c.a, 1.0, 6)

    def test_ocp_color_alpha(self):
        c = get_rgba(bd.Color("Orange", 0.2).wrapped)
        self.assertEqual(c.web_color, "#ff5f00")
        self.assertAlmostEqual(c.a, 0.2, 6)

    def test_bd_color_extra_alpha(self):
        c = get_rgba(bd.Color("Orange").wrapped, 0.2)
        self.assertEqual(c.web_color, "#ff5f00")
        self.assertAlmostEqual(c.a, 0.2, 6)

    def test_cq_color(self):
        c = get_rgba(cq.Color(0.2, 0.3, 0.4))
        self.assertEqual(c.web_color, "#334c66")
        self.assertAlmostEqual(c.a, 1.0, 6)

    def test_cq_color_alpha(self):
        c = get_rgba(cq.Color(0.2, 0.3, 0.4, 0.1))
        self.assertEqual(c.web_color, "#334c66")
        self.assertAlmostEqual(c.a, 0.1, 6)

    def test_cq_color_extra_alpha(self):
        c = get_rgba(cq.Color(0.2, 0.3, 0.4), 0.1)
        self.assertEqual(c.web_color, "#334c66")
        self.assertAlmostEqual(c.a, 0.1, 6)
