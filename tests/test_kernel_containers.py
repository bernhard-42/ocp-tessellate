"""A kernel plugin says what a container holds and where things are, with `get_children`
and `get_location`; `to_ocp` builds the tree with the walker it uses for lists and dicts.

The toy kernel below stores one assembly in two ways, and its plugin names no OcpGroup:

    top at x=100
      bar: at y=5 in top
      sub: at y=10 in top, rotated 90 degrees about z
        leg: at x=1 in sub
"""

import numpy as np
import pytest
from occt_binding import DEFAULT_BINDING, INSTALLED, occt

from ocp_tessellate import OcpGroup
from ocp_tessellate.convert import OcpConverter, tessellate_group, to_ocpgroup
from ocp_tessellate.kernels import is_external_object, show_of
from ocp_tessellate.ocp_utils import (
    BoundingBox,
    identity_location,
    loc_to_tq,
    mul_locations,
    mul_placements,
    nested_bounding_box,
    np_bbox,
    tq_to_loc,
)
from ocp_tessellate.plugin import (
    CoordSystem,
    OcpObject,
    Placement,
    ShowProtocol,
    TessellationProtocol,
    object_color,
    register_show,
)

Q0 = (0.0, 0.0, 0.0, 1.0)
QZ90 = (0.0, 0.0, 0.7071067811865476, 0.7071067811865476)

TOP = Placement((100.0, 0.0, 0.0), Q0)
BAR = Placement((0.0, 5.0, 0.0), Q0)
SUB = Placement((0.0, 10.0, 0.0), QZ90)
LEG = Placement((1.0, 0.0, 0.0), Q0)

# the triangle (0, 0), (1, 0), (0, 1), placed by these locations
WORLD_BAR = (100.0, 101.0, 5.0, 6.0)
WORLD_LEG = (99.0, 100.0, 11.0, 12.0)

TRIANGLE = {
    "vertices": np.array([0, 0, 0, 1, 0, 0, 0, 1, 0], dtype=np.float32),
    "triangles": np.array([0, 1, 2], dtype=np.int32),
    "normals": np.array([0, 0, 1] * 3, dtype=np.float32),
    "edges": np.array([0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0], dtype=np.float32),
    "obj_vertices": np.array([0, 0, 0, 1, 0, 0, 0, 1, 0], dtype=np.float32),
    "face_types": np.array([0], dtype=np.int32),
    "edge_types": np.array([0, 0, 0], dtype=np.int32),
    "triangles_per_face": np.array([1], dtype=np.int32),
    "segments_per_edge": np.array([1, 1, 1], dtype=np.int32),
}


class ToyBody:
    """An atomic object whose geometry is the triangle, wherever its kernel keeps it."""

    def __init__(self, name=None):
        self.name = name


class ToyPlaced(ToyBody):
    """An atomic object that carries a location of its own."""

    def __init__(self, name, location):
        super().__init__(name)
        self.location = location


class ToyFrame:
    """A location to draw, not one that places anything."""


class ToyLinked:
    """The parent holds its children with their locations: not iterable, no list."""

    def __init__(self, links, at=None):
        self.links, self.at = links, at


class ToyNode:
    """Every object carries its location relative to its parent."""

    def __init__(self, name, location, kids):
        self.name, self.location, self.kids = name, location, kids


class ToyBag:
    """An iterable that is not a list, with no locations at all."""

    def __init__(self, *items):
        self.items = items

    def __iter__(self):
        return iter(self.items)


class ContainerTessellation(TessellationProtocol):
    def tessellate(self, shape, deviation, quality, angular_tolerance, compute_edges=True, compute_uvs=False, normalize_uvs=True, shape_id="", debug=False):
        return dict(TRIANGLE)

    def discretize_edges(self, edges, deflection=0.1, shape_id=""):
        return {}

    def convert_vertices(self, vertices, shape_id=""):
        return {}

    def bounding_box(self, shape):
        if isinstance(shape, ToyFrame):
            raise TypeError("a location has no extent")
        return BoundingBox({"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1, "zmin": 0, "zmax": 0})


class ContainerShow(ShowProtocol):
    def is_object(self, obj):
        return isinstance(obj, (ToyBody, ToyFrame, ToyLinked, ToyNode, ToyBag))

    def line(self, start, end):
        return ("line", start, end)

    def serialize(self, shape):
        return repr(shape).encode("utf-8")

    def convert(self, obj, name, color, alpha, helper_scale):
        if isinstance(obj, ToyFrame):
            return CoordSystem(name, (0, 0, 0), (1, 0, 0), (0, 0, 1), size=helper_scale)
        return OcpObject("face", obj, name=name, color=object_color(obj, color, alpha))

    def get_children(self, obj):
        if isinstance(obj, ToyLinked):
            return obj.links
        if isinstance(obj, ToyNode):
            return [(k.name, k, None) for k in obj.kids]
        if isinstance(obj, ToyBag):
            return [(None, item, None) for item in obj]
        return None

    def get_location(self, obj):
        if isinstance(obj, ToyLinked):
            return obj.at
        if isinstance(obj, (ToyNode, ToyPlaced)):
            return obj.location
        return None


CONTAINERS = ContainerShow()
register_show("toy containers", ContainerTessellation(), CONTAINERS, api=1)


def linked():
    sub = ToyLinked([("leg", ToyBody(), LEG)])
    return ToyLinked([("bar", ToyBody(), BAR), ("sub", sub, SUB)], at=TOP)


def noded():
    sub = ToyNode("sub", SUB, [ToyPlaced("leg", LEG)])
    return ToyNode("top", TOP, [ToyPlaced("bar", BAR), sub])


def converted(obj, name="top", **kwargs):
    converter_args = {k: kwargs.pop(k) for k in ("python_enumeration",) if k in kwargs}
    group, instances = to_ocpgroup(obj, names=[name], **converter_args, **kwargs)
    return tessellate_group(group, instances)


def walk(node, loc, meshed, out):
    """The world box (x, y) of every shape, accumulating locations as the viewer does."""
    for part in node["parts"]:
        placed = loc if part.get("loc") is None else mul_locations(loc, tq_to_loc(*part["loc"]))
        if "parts" in part:
            walk(part, placed, meshed, out)
        elif part["type"] == "shapes":
            vertices = np.asarray(meshed[part["shape"]["ref"]]["vertices"])
            box = np_bbox(vertices, *loc_to_tq(placed))
            out[part["id"]] = tuple(round(float(box[k]), 3) for k in ("xmin", "xmax", "ymin", "ymax"))
        else:
            out[part["id"]] = part["type"]
    return out


def world(obj, name="top", **kwargs):
    meshed, shapes, _ = converted(obj, name, **kwargs)
    top = identity_location() if shapes.get("loc") is None else tq_to_loc(*shapes["loc"])
    return walk(shapes, top, meshed, {})


def part_named(shapes, path):
    if shapes["id"] == path:
        return shapes
    for part in shapes.get("parts", []):
        found = part_named(part, path)
        if found is not None:
            return found
    return None


# ------------------------------------------------------------------ the tree and its places


@pytest.mark.parametrize("build", [linked, noded], ids=["parent holds locations", "objects hold locations"])
def test_a_kernels_assembly_lands_where_its_locations_say(build):
    assert world(build()) == {"/top/bar": WORLD_BAR, "/top/sub/leg": WORLD_LEG}


@pytest.mark.parametrize("build", [linked, noded], ids=["parent holds locations", "objects hold locations"])
def test_the_tree_holds_relative_locations_as_animation_needs(build):
    _, shapes, _ = converted(build())
    assert shapes["loc"][0] == pytest.approx(TOP[0])
    sub = part_named(shapes, "/top/sub")
    assert sub["loc"][0] == pytest.approx(SUB[0]) and sub["loc"][1] == pytest.approx(QZ90)
    assert part_named(shapes, "/top/sub/leg")["loc"][0] == pytest.approx(LEG[0])


def test_the_scene_box_holds_the_assembly():
    _, shapes, _ = converted(linked())
    assert (shapes["bb"]["xmin"], shapes["bb"]["xmax"]) == pytest.approx((99, 101))
    assert (shapes["bb"]["ymin"], shapes["bb"]["ymax"]) == pytest.approx((5, 12))


def test_the_plugin_needs_no_group_of_its_own():
    assert show_of(linked()) is CONTAINERS
    group, _ = to_ocpgroup(linked(), names=["top"])
    assert isinstance(group, OcpGroup) and group.name == "top"


def test_a_container_without_locations_is_a_group():
    assert world(ToyLinked([("a", ToyBody(), None), ("b", ToyBody(), None)])) == {
        "/top/a": (0.0, 1.0, 0.0, 1.0),
        "/top/b": (0.0, 1.0, 0.0, 1.0),
    }


def test_an_iterable_that_is_no_list_is_walked_through_get_children():
    assert world(ToyBag(ToyBody(), ToyBody())) == {
        "/top/ToyBody": (0.0, 1.0, 0.0, 1.0),
        "/top/ToyBody(2)": (0.0, 1.0, 0.0, 1.0),
    }


def test_an_object_with_children_none_is_atomic():
    assert world(ToyBody(), name="body") == {"/Group/body": (0.0, 1.0, 0.0, 1.0)}


def test_an_atomic_object_is_placed_by_its_own_location():
    assert world(ToyPlaced("p", BAR), name="p") == {"/Group/p": (0.0, 1.0, 5.0, 6.0)}


def test_a_childs_relative_location_goes_on_top_of_its_own():
    parent = ToyLinked([("p", ToyPlaced("p", LEG), TOP)])
    assert world(parent) == {"/top/p": (101.0, 102.0, 0.0, 1.0)}


# ------------------------------------------------- what the walker brings along without code


@pytest.mark.parametrize(
    ("enumerate_names", "expected"),
    [(False, {"/top/p", "/top/p(2)"}), (True, {"/top/p(0)", "/top/p(1)"})],
)
def test_children_of_one_name_are_numbered_as_the_host_asks(enumerate_names, expected):
    parent = ToyLinked([("p", ToyBody(), None), ("p", ToyBody(), BAR)])
    assert set(world(parent, python_enumeration=enumerate_names)) == expected


def test_a_child_without_a_name_is_named_by_its_type():
    assert set(world(ToyLinked([(None, ToyBody(), None)]))) == {"/top/ToyBody"}


def test_a_container_given_no_name_is_named_by_its_type():
    converter = OcpConverter()
    group = converter.to_ocp(ToyLinked([("a", ToyBody(), None), ("b", ToyBody(), None)]))
    assert group.name == "ToyLinked"


def test_a_color_given_to_the_container_reaches_its_children():
    group, instances = to_ocpgroup(linked(), names=["top"], colors=["#ff0000"], alphas=[0.5])
    _, shapes, _ = tessellate_group(group, instances)
    for path in ("/top/bar", "/top/sub/leg"):
        part = part_named(shapes, path)
        assert part["color"] == "#ff0000" and part["alpha"] == pytest.approx(0.5)


def test_lists_and_dicts_are_children_like_any_other():
    parent = ToyLinked([("l", [ToyBody(), ToyBody()], BAR), ("d", {"x": ToyBody()}, None)], at=TOP)
    assert world(parent) == {
        "/top/l/ToyBody": WORLD_BAR,
        "/top/l/ToyBody(2)": WORLD_BAR,
        "/top/d/x": (100.0, 101.0, 0.0, 1.0),
    }


def test_a_container_inside_a_list_or_dict():
    assert set(world([linked()], name="l")) == {"/l/ToyLinked/bar", "/l/ToyLinked/sub/leg"}
    assert set(world({"a": linked()}, name="d")) == {"/d/a/bar", "/d/a/sub/leg"}


def test_a_drawn_location_is_a_child_like_any_other():
    assert world(ToyLinked([("frame", ToyFrame(), BAR), ("b", ToyBody(), None)])) == {
        "/top/frame": "edges",
        "/top/b": (0.0, 1.0, 0.0, 1.0),
    }


def test_an_empty_container_shows_like_an_empty_list():
    shown = world(ToyLinked([("empty", ToyLinked([]), BAR), ("list", [], None)]))
    assert set(shown) == {"/top/empty (empty)", "/top/list (empty)"}


def test_an_occt_child_in_a_located_assembly():
    box = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", DEFAULT_BINDING)(1, 1, 1).Shape()
    parent = ToyLinked([("bar", ToyBody(), BAR), ("occt", box, Placement((0.0, 20.0, 0.0), Q0))], at=TOP)
    shown = world(parent)
    assert shown["/top/bar"] == WORLD_BAR
    assert shown["/top/occt"] == (100.0, 101.0, 20.0, 21.0)


@pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
def test_occt_children_of_two_bindings_in_a_located_assembly():
    def box(binding):
        return occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", binding)(1, 1, 1).Shape()

    parent = ToyLinked(
        [("a", box("OCP"), BAR), ("b", box("nanocct"), Placement((0.0, 20.0, 0.0), Q0)), ("t", ToyBody(), None)],
        at=TOP,
    )
    assert world(parent) == {
        "/top/a": (100.0, 101.0, 5.0, 6.0),
        "/top/b": (100.0, 101.0, 20.0, 21.0),
        "/top/t": (100.0, 101.0, 0.0, 1.0),
    }


@pytest.mark.parametrize("binding", INSTALLED)
def test_an_occt_child_of_any_binding_gets_the_location_in_its_binding(binding):
    box = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", binding)(1, 1, 1).Shape()
    assert world(ToyLinked([("occt", box, BAR)], at=TOP)) == {"/top/occt": (100.0, 101.0, 5.0, 6.0)}


# ------------------------------------------------------------------- measuring and helpers


def test_the_backends_entry_is_placed_by_every_location_above_it():
    _, _, mapping = converted(linked())

    def entries(node):
        for part in node["parts"]:
            if "parts" in part:
                yield from entries(part)
            else:
                yield part

    by_id = {e["id"]: e for e in entries(mapping)}
    assert by_id["/top/bar"]["shape"]["kernel"] == "toy containers"
    assert by_id["/top/bar"]["loc"][0] == pytest.approx((100, 5, 0))
    translation, rotation = by_id["/top/sub/leg"]["loc"]
    assert translation == pytest.approx((100, 11, 0))
    assert rotation == pytest.approx(QZ90)


@pytest.mark.parametrize("build", [linked, noded], ids=["parent holds locations", "objects hold locations"])
def test_nested_bounding_box_walks_the_container_before_it_is_converted(build):
    box = nested_bounding_box([build()])
    assert (box.xmax, box.ymax) == pytest.approx((101, 12))


def test_nested_bounding_box_places_an_atomic_object_by_its_own_location():
    box = nested_bounding_box([ToyPlaced("p", BAR)])
    assert box.ymax == pytest.approx(6)


def test_nested_bounding_box_rotates_with_the_location():
    box = nested_bounding_box([ToyLinked([("leg", ToyBody(), Placement((0.0, 0.0, 0.0), QZ90))])])
    assert (box.xmin, box.ymax) == pytest.approx((-1, 1))


# ------------------------------------------------------------------- the host's entry points


def test_a_container_is_the_kernels_object():
    assert is_external_object(linked()) is True
    assert is_external_object(ToyBag()) is True


@pytest.mark.parametrize(
    "build",
    [
        lambda plain: ToyLinked([("bar", ToyBody(), None)], at=plain),
        lambda plain: ToyLinked([("bar", ToyBody(), plain)]),
        lambda plain: ToyPlaced("bar", plain),
    ],
)
def test_a_plugin_returns_a_placement_not_a_plain_tuple(build):
    with pytest.raises(TypeError, match="must be a Placement or None, not tuple"):
        to_ocpgroup(build(((1.0, 0.0, 0.0), Q0)), names=["top"])


@pytest.mark.parametrize(
    "build",
    [
        lambda bad: ToyLinked([("bar", ToyBody(), None)], at=bad),
        lambda bad: ToyLinked([("bar", ToyBody(), bad)]),
        lambda bad: ToyPlaced("bar", bad),
    ],
)
@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (Placement((1.0, 0.0), Q0), "origin of 3"),
        (Placement((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), "quaternion of 4"),
        (Placement((1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 2.0)), "unit quaternion"),
    ],
)
def test_a_plugin_returns_a_placement_the_viewer_can_use(build, bad, message):
    with pytest.raises(ValueError, match=message):
        to_ocpgroup(build(bad), names=["top"])
    with pytest.raises(ValueError, match=message):
        nested_bounding_box(build(bad))


def test_a_container_is_named_by_its_own_name_like_any_object():
    class Named(ToyLinked):
        name = "my_asm"

    register_show("toy named", ContainerTessellation(), type("NamedShow", (ContainerShow,), {"is_object": lambda self, obj: isinstance(obj, Named)})(), api=1)
    group, _ = to_ocpgroup([Named([("bar", ToyBody(), None)])], names=["list"])
    assert group.objects[0].name == "my_asm"


def _leaf_x_range(part, parent=None):
    """The world x range of the first shape below `part`, accumulating locations."""
    placement = mul_placements(parent, None if part.get("loc") is None else Placement(*part["loc"]))
    if "parts" in part:
        return _leaf_x_range(part["parts"][0], placement)
    points = np.asarray(part["shape"]["edges"], dtype=np.float64).reshape(-1, 3)
    box = np_bbox(points, *placement)
    return (box["xmin"], box["xmax"])


def test_the_joints_of_a_part_move_with_the_part_in_a_placed_container():
    import build123d as bd

    if not hasattr(bd, "RigidJoint"):
        pytest.skip("this build123d has no joints")
    part = bd.Box(1, 1, 1)
    bd.RigidJoint("j", part, bd.Location((0.5, 0, 0)))
    holder = ToyLinked([("part", part, Placement((100.0, 0.0, 0.0), Q0))])
    group, instances = to_ocpgroup(holder, names=["top"], render_joints=True)
    _, shapes, _ = tessellate_group(group, instances)
    joints = part_named(shapes, "/top/part.joints")
    assert joints is not None, "the joints are in the tree"
    xmin, xmax = _leaf_x_range(joints)
    assert 100 < xmin < xmax < 101


def test_a_plugins_error_in_get_children_is_not_hidden():
    class Broken:
        pass

    def raises(obj):
        raise ValueError("the plugin's bug")

    class BrokenShow(ContainerShow):
        def is_object(self, obj):
            return isinstance(obj, Broken)

        def get_children(self, obj):
            return raises(obj)

    register_show("toy broken", ContainerTessellation(), BrokenShow(), api=1)
    with pytest.raises(ValueError, match="the plugin's bug"):
        to_ocpgroup(Broken())
