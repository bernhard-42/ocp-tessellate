"""A build123d builder takes the color and alpha it is given, like any other object.

build123d's builders have a `color` attribute that is None until it is set. It
used to stand in for the given color - `getattr(builder, "color", color)` finds
the attribute - so `show(builder, colors=[...], alphas=[...])` drew the builder
in its default color, alpha included, since alpha travels in the color. And the
`alpha` argument itself was not read for builders at all. Lines take the
color only: edges are drawn without alpha.
"""

import pytest
import build123d as bd
from build123d import BuildLine, BuildPart, BuildSheet, BuildSketch, Box, Circle, Line, Plane, Rectangle

from ocp_tessellate import OcpGroup
from ocp_tessellate.convert import to_ocpgroup
from ocp_tessellate.utils import Color

GREEN = Color("green").web_color


def sketch():
    with BuildSketch() as builder:
        Circle(1)
    return builder


def part():
    with BuildPart() as builder:
        Box(1, 2, 3)
    return builder


def line():
    with BuildLine() as builder:
        Line((0, 0), (1, 1))
    return builder


def sheet():
    with BuildSheet(Plane.YZ, thickness=0.1) as builder, BuildSketch():
        Rectangle(1, 2)
    return builder


BUILDERS = [sketch, part, line, sheet]
# Edges are drawn without alpha: ocp-tessellate sends no alpha for them and
# three-cad-viewer's edge material takes none, so a line's alpha shows nowhere.
WITH_ALPHA = [sketch, part, sheet]


def leaves(node):
    if isinstance(node, OcpGroup):
        for child in node.objects:
            yield from leaves(child)
    else:
        yield node


def built(builder, **kwargs):
    """The leaf that holds what the builder built (not its `*_local` shapes)."""
    group, _ = to_ocpgroup(builder, names=["b"], **kwargs)
    found = [leaf for leaf in leaves(group) if not leaf.name.endswith("_local")]
    assert len(found) == 1, [leaf.name for leaf in leaves(group)]
    return found[0]


@pytest.mark.parametrize("make", BUILDERS, ids=lambda f: f.__name__)
def test_a_given_color_is_used(make):
    leaf = built(make(), colors=[Color("green")])
    assert leaf.color.web_color == GREEN


@pytest.mark.parametrize("make", WITH_ALPHA, ids=lambda f: f.__name__)
def test_the_alpha_of_a_given_color_is_used(make):
    leaf = built(make(), colors=[Color("green", 0.5)])
    assert (leaf.color.web_color, leaf.color.a) == (GREEN, 0.5)


@pytest.mark.parametrize("make", WITH_ALPHA, ids=lambda f: f.__name__)
def test_a_given_alpha_overwrites_the_colors(make):
    """As for every other object (`get_color_for_object`)."""
    leaf = built(make(), colors=[Color("green", 0.7)], alphas=[0.5])
    assert (leaf.color.web_color, leaf.color.a) == (GREEN, 0.5)


@pytest.mark.parametrize("make", WITH_ALPHA, ids=lambda f: f.__name__)
def test_a_given_alpha_without_a_color(make):
    leaf = built(make(), alphas=[0.5])
    assert leaf.color.a == 0.5


@pytest.mark.parametrize("make", BUILDERS, ids=lambda f: f.__name__)
def test_the_builders_own_color_wins(make):
    """A color set on the builder is the object's own, as `show` keeps it too."""
    builder = make()
    builder.color = bd.Color("blue")
    leaf = built(builder, colors=[Color("green")])
    assert leaf.color.web_color == Color("blue").web_color


def test_the_local_shapes_stay_faint():
    group, _ = to_ocpgroup(sketch(), names=["b"], colors=[Color("green")], alphas=[0.5])
    local = [leaf for leaf in leaves(group) if leaf.name.endswith("_local")]
    assert [(leaf.color.web_color, leaf.color.a) for leaf in local] == [(GREEN, 0.2)]
