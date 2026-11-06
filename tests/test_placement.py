"""The tree's locations as plain numbers: the same results as OCCT's TopLoc_Location."""

import math

import numpy as np
import pytest
from occt_binding import DEFAULT_BINDING, occt

from ocp_tessellate import OcpGroup
from ocp_tessellate.cad_objects import OcpObject
from ocp_tessellate.ocp_utils import (
    IDENTITY_PLACEMENT,
    Placement,
    loc_to_tq,
    mul_placements,
    tq_to_loc,
)
from ocp_tessellate.ocp_utils.location import rotate


def rotation(axis, degrees):
    half = math.radians(degrees) / 2
    x, y, z = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    return (x * math.sin(half), y * math.sin(half), z * math.sin(half), math.cos(half))


CASES = [
    Placement((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)),
    Placement((0.0, 0.0, 0.0), rotation((0, 0, 1), 90)),
    Placement((5.0, -2.0, 1.0), rotation((1, 2, 3), 37)),
    Placement((-4.0, 8.0, 0.5), rotation((-1, 0.5, 2), 211)),
]


def same(a, b):
    """Two placements of one motion: a quaternion and its negation are one rotation."""
    assert a.origin == pytest.approx(b.origin, abs=1e-9)
    sign = 1 if np.dot(a.quaternion, b.quaternion) >= 0 else -1
    assert a.quaternion == pytest.approx(tuple(sign * c for c in b.quaternion), abs=1e-9)


@pytest.mark.parametrize("a", CASES)
@pytest.mark.parametrize("b", CASES)
def test_a_product_is_the_product_of_the_locations(a, b):
    expected = tq_to_loc(*a) * tq_to_loc(*b)
    same(a.mul(b), Placement(*loc_to_tq(expected)))
    same(mul_placements(a, b), a.mul(b))


@pytest.mark.parametrize("a", CASES)
def test_an_inverse_is_the_inverse_of_the_location(a):
    same(a.inverted(), Placement(*loc_to_tq(tq_to_loc(*a).Inverted())))


def test_a_missing_placement_acts_as_identity():
    assert mul_placements(None, CASES[0]) == CASES[0]
    assert mul_placements(CASES[0], None) == CASES[0]
    assert mul_placements(None, None) is None
    assert CASES[0].mul(None) == CASES[0]


def test_is_identity():
    assert IDENTITY_PLACEMENT.is_identity() is True
    assert CASES[0].is_identity() is False


def test_from_occt_takes_a_location():
    loc = tq_to_loc((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))
    assert Placement.from_occt(loc) == CASES[0]
    assert Placement.from_occt(occt("TopLoc", "TopLoc_Location", DEFAULT_BINDING)()) == IDENTITY_PLACEMENT


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (None, TypeError),
        (CASES[0], AttributeError),
        (((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)), AttributeError),
    ],
)
def test_from_occt_takes_nothing_else(value, error):
    with pytest.raises(error):
        Placement.from_occt(value)


NOT_PLACEMENTS = [
    pytest.param(lambda: tq_to_loc((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)), id="location"),
    pytest.param(lambda: ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)), id="tuple"),
]


def _tree_objects(**kwargs):
    return [OcpGroup([], name="group", **kwargs), OcpObject("edge", [], name="object", **kwargs)]


@pytest.mark.parametrize("value", NOT_PLACEMENTS)
def test_the_tree_refuses_what_is_no_placement_when_created(value):
    with pytest.raises(TypeError, match="loc must be a Placement or None"):
        OcpGroup([], name="group", loc=value())
    with pytest.raises(TypeError, match="loc must be a Placement or None"):
        OcpObject("edge", [], name="object", loc=value())


@pytest.mark.parametrize("value", NOT_PLACEMENTS)
def test_the_tree_refuses_what_is_no_placement_when_assigned(value):
    for item in _tree_objects():
        with pytest.raises(TypeError, match="loc must be a Placement or None"):
            item.loc = value()
        assert item.loc is None


def test_the_tree_gives_back_what_it_was_given():
    for item in _tree_objects(loc=CASES[0]):
        assert item.loc is CASES[0]
        item.loc = CASES[1]
        assert item.loc is CASES[1]
        item.loc = None
        assert item.loc is None


@pytest.mark.parametrize("placement", CASES)
def test_matrix_is_the_motion_of_the_location(placement):
    trsf = tq_to_loc(*placement).Transformation()
    expected = [[trsf.Value(row, col) for col in range(1, 5)] for row in range(1, 4)]
    assert np.allclose(placement.matrix()[:3], expected, atol=1e-12)
    assert placement.matrix()[3].tolist() == [0.0, 0.0, 0.0, 1.0]


def test_a_placement_unpacks_as_tq_to_loc_takes_it():
    same(Placement(*loc_to_tq(tq_to_loc(*CASES[2]))), CASES[2])


def directions_of(placement):
    """The x and z directions a placement's quaternion turns the unit axes into."""
    return (
        rotate(placement.quaternion, np.array([[1.0, 0.0, 0.0]]))[0],
        rotate(placement.quaternion, np.array([[0.0, 0.0, 1.0]]))[0],
    )


@pytest.mark.parametrize(
    ("x_dir", "z_dir"),
    [
        ((1, 0, 0), (0, 0, 1)),
        ((1, 0, 0), (0, 0, -1)),  # 180 degrees about x
        ((-1, 0, 0), (0, 0, -1)),  # 180 degrees about y
        ((-1, 0, 0), (0, 0, 1)),  # 180 degrees about z
        ((0, 1, 0), (0, 0, 1)),  # 90 degrees about z
        ((0, 0, 1), (1, 0, 0)),
        ((0.6, 0.8, 0), (0, 0, 1)),
    ],
)
def test_from_axes_gives_the_rotation_of_the_directions(x_dir, z_dir):
    placement = Placement.from_axes((1.0, 2.0, 3.0), x_dir, z_dir)
    assert placement.origin == (1.0, 2.0, 3.0)
    x, z = directions_of(placement)
    assert x == pytest.approx(x_dir, abs=1e-12)
    assert z == pytest.approx(z_dir, abs=1e-12)
    assert np.linalg.norm(placement.quaternion) == pytest.approx(1)


def test_from_axes_of_random_rotations_matches_the_location():
    rng = np.random.default_rng(42)
    for _ in range(500):
        expected = Placement(tuple(rng.uniform(-50, 50, 3)), rotation(rng.normal(size=3), rng.uniform(-180, 180)))
        x, z = directions_of(expected)
        same(Placement.from_axes(expected.origin, tuple(x), tuple(z)), expected)


def test_from_axes_normalizes_and_keeps_z_when_the_directions_are_not_orthogonal():
    x, z = directions_of(Placement.from_axes((0.0, 0.0, 0.0), (2, 0, 1), (0, 0, 5)))
    assert x == pytest.approx((1, 0, 0), abs=1e-12)
    assert z == pytest.approx((0, 0, 1), abs=1e-12)


def test_from_axes_refuses_directions_without_a_frame():
    with pytest.raises(ValueError, match="z_dir"):
        Placement.from_axes((0.0, 0.0, 0.0), (1, 0, 0), (0, 0, 0))
    with pytest.raises(ValueError, match="parallel"):
        Placement.from_axes((0.0, 0.0, 0.0), (0, 0, 1), (0, 0, 1))


def test_from_axes_is_a_placement_the_tree_takes():
    placement = Placement.from_axes((1, 2, 3), (1, 0, 0), (0, 0, 1))
    assert OcpGroup(loc=placement).loc is placement
    assert placement.origin == (1.0, 2.0, 3.0) and isinstance(placement.origin[0], float)
