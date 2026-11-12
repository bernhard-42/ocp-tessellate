"""Objects of another kernel go the way OCCT objects go.

A kernel's solid, face or shell is an instance, meshed by the kernel with the viewer's
deviation and angular tolerance and cached under its cache id; its edges and vertices are
leaves discretized by the kernel; a location or axis is the same CoordSystem or CoordAxis
OCCT objects get, drawn with the kernel's lines. Every leaf has an entry in the
measurement backend's model, tagged with the kernel. The OCCT objects of the same scene
are unchanged.
"""

import base64
import importlib
import os
import subprocess
import sys
import warnings

import numpy as np
import pytest
import toy_kernel
from occt_binding import DEFAULT_BINDING, occt
from toy_kernel import Bag, Point, Segment, ToyAxis, ToyLocation, Triangle

from ocp_tessellate._kernel import kernel
from ocp_tessellate._show_registry import _show_plugins
from ocp_tessellate.cad_objects import (
    CoordAxis,
    CoordSystem,
    OcpGroup,
    OcpInstancesGroup,
)
from ocp_tessellate.convert import tessellate_group, to_ocpgroup
from ocp_tessellate.kernels import (
    encode_kernel_shapes,
    is_external_object,
    show_of,
    tessellation_of,
)
from ocp_tessellate.ocp_utils import BoundingBox, nested_bounding_box
from ocp_tessellate.plugin import (
    CURVE_TYPES,
    SURFACE_TYPES,
    OcpObject,
    ShowProtocol,
    TessellationProtocol,
    register_show,
    validate_tessellation,
)
from ocp_tessellate.tessellator import OcctTessellation, compute_quality
from ocp_tessellate.utils import Color

BRepPrimAPI_MakeBox = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", DEFAULT_BINDING)


def bbox(lo, hi):
    return BoundingBox({"xmin": lo[0], "xmax": hi[0], "ymin": lo[1], "ymax": hi[1], "zmin": lo[2], "zmax": hi[2]})


def shown(*objs, **kwargs):
    converter_args = {k: kwargs.pop(k) for k in ("names", "colors", "alphas", "materials", "modes", "helper_scale") if k in kwargs}
    group, instances = to_ocpgroup(*objs, **converter_args)
    return tessellate_group(group, instances, kwargs)


def leaves(node):
    return [x for p in node["parts"] for x in (leaves(p) if "parts" in p else [p])]


def _leaf_kinds(group):
    kinds = []
    for obj in group.objects:
        kinds += _leaf_kinds(obj) if isinstance(obj, OcpGroup) else [obj.kind]
    return kinds


def _points(part):
    return {tuple(np.round(p, 6)) for p in np.asarray(part["shape"]["edges"]).reshape(-1, 3)}


# ------------------------------------------------------------------------- tessellation


def test_a_body_is_meshed_by_its_kernel_with_the_viewers_parameters():
    toy_kernel.TESSELLATION.calls.clear()
    meshed, shapes, _ = shown(Triangle(2.0, cached=False), names=["tri"], deviation=0.05, angular_tolerance=0.3)
    [call] = toy_kernel.TESSELLATION.calls
    assert call["deviation"] == 0.05 and call["angular_tolerance"] == 0.3
    assert call["quality"] == compute_quality(bbox((0, 0, 0), (2, 2, 0)), deviation=0.05)
    assert meshed[0]["triangles_per_face"].tolist() == [1]
    [part] = leaves(shapes)
    assert part["type"] == "shapes" and part["shape"] == {"ref": 0} and part["renderback"] is True
    # at the origin: an identity location, not None (the viewer applies it)
    assert part["loc"] == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def test_edges_and_vertices_are_leaves_of_the_kernel():
    _, shapes, _ = shown(Segment((0, 0, 1), (1, 0, 1)), Point(2, 2, 2), names=["line", "point"])
    line, point = leaves(shapes)
    assert line["type"] == "edges" and line["shape"]["segments_per_edge"].tolist() == [1] and line["width"] == 2
    assert point["type"] == "vertices" and point["shape"]["obj_vertices"].tolist() == [2, 2, 2] and point["size"] == 6
    assert shapes["bb"]["xmax"] == pytest.approx(2) and shapes["bb"]["zmax"] == pytest.approx(2)


def test_one_geometry_is_one_mesh_and_a_cache_hit_is_not_meshed_again():
    toy_kernel.TESSELLATION.calls.clear()
    meshed, shapes, _ = shown([Triangle(3.25), Triangle(3.25), Triangle(1.5)], names=["l"], deviation=0.123)
    assert len(meshed) == 2
    assert [p["shape"]["ref"] for p in leaves(shapes)] == [0, 0, 1]
    assert len(toy_kernel.TESSELLATION.calls) == 2
    shown(Triangle(3.25), names=["again"], deviation=0.123)
    assert len(toy_kernel.TESSELLATION.calls) == 2


def test_one_body_without_a_cache_id_is_one_mesh_and_meshed_at_every_show():
    toy_kernel.TESSELLATION.calls.clear()
    body = Triangle(2.5, cached=False)
    meshed, _, _ = shown([body, body], names=["l"])
    assert len(meshed) == 1
    shown(body, names=["again"])
    assert len(toy_kernel.TESSELLATION.calls) == 2


def test_two_bodies_without_a_cache_id_do_not_share_a_mesh():
    meshed, _, _ = shown([Triangle(1.0, cached=False), Triangle(7.0, cached=False)], names=["l"])
    assert [m["vertices"].max() for m in meshed] == [1.0, 7.0]


def test_tessellation_of_answers_for_every_kernel():
    box = BRepPrimAPI_MakeBox(1, 1, 1).Shape()
    assert isinstance(tessellation_of(box), OcctTessellation)
    assert tessellation_of(Triangle()) is toy_kernel.TESSELLATION
    assert tessellation_of([Segment((0, 0, 0), (1, 0, 0))]) is toy_kernel.TESSELLATION
    assert isinstance(tessellation_of([]), OcctTessellation)
    with pytest.raises(TypeError, match="unsupported kernel: int"):
        tessellation_of(1)


def test_a_flat_bounding_box_has_a_quality():
    # a planar face: one extent is exactly zero; round_sig used to raise on it,
    # which is why OCCT's boxes carry a 1e-7 gap and external ones had to copy it
    flat = bbox((0, 0, 0), (2, 1, 0))
    assert compute_quality(flat, deviation=0.1) == compute_quality(
        bbox((0, 0, 0), (2, 1, 1e-9)), deviation=0.1
    )
    assert abs(compute_quality(flat, deviation=0.1) - (2 + 1) / 300 * 0.1) < 1e-9


def test_the_type_tables_hold_every_geomabs_member_with_its_value():
    geomabs = importlib.import_module(f"{DEFAULT_BINDING}.GeomAbs")
    for table, enum in (
        (SURFACE_TYPES, geomabs.GeomAbs_SurfaceType),
        (CURVE_TYPES, geomabs.GeomAbs_CurveType),
    ):
        for name, value in table.items():
            member = getattr(enum, f"GeomAbs_{name}")
            assert (
                int(getattr(member, "value", member)) == value and type(value) is int
            ), name
    # the known codes, so a renamed or missing member would show
    assert (
        SURFACE_TYPES["Plane"] == 0
        and SURFACE_TYPES["OtherSurface"] == 10
        and len(SURFACE_TYPES) == 11
    )
    assert (
        CURVE_TYPES["Line"] == 0
        and CURVE_TYPES["OtherCurve"] == 8
        and len(CURVE_TYPES) == 9
    )


# ----------------------------------------------------------------------- the measuring side


def test_every_leaf_has_an_entry_tagged_with_its_kernel():
    body, line, point = Triangle(2.0), Segment((0, 0, 0), (1, 0, 0)), Point(1, 2, 3)
    _, _, mapping = shown(body, line, point, names=["tri", "line", "point"])
    entries = {e["id"].rsplit("/", 1)[1]: e for e in mapping["parts"]}
    assert entries["tri"]["shape"] == {"kernel": "toy", "obj": body}
    assert entries["line"]["shape"] == {"kernel": "toy", "obj": [line]}
    assert entries["point"]["shape"] == {"kernel": "toy", "obj": [point]}


def test_a_helper_has_an_entry_of_its_kernels_lines():
    _, _, mapping = shown(ToyLocation((1, 2, 3)), names=["frame"], helper_scale=2.0)
    [entry] = mapping["parts"]
    assert entry["shape"]["kernel"] == "toy"
    assert [type(s) for s in entry["shape"]["obj"]] == [Segment] * 3


def test_a_mixed_scene_keeps_the_occt_objects_in_the_model():
    box = BRepPrimAPI_MakeBox(1, 1, 1).Shape()
    meshed, shapes, mapping = shown(box, Triangle(2.0), names=["box", "tri"])
    assert len(meshed) == 2
    entries = {e["id"].rsplit("/", 1)[1]: e for e in mapping["parts"]}
    assert "kernel" not in entries["box"]["shape"]
    assert entries["box"]["shape"]["cache_id"] is not None
    assert entries["tri"]["shape"]["kernel"] == "toy"
    assert sorted(p["shape"]["ref"] for p in leaves(shapes)) == [0, 1]


def test_an_occt_edge_has_no_tag():
    edge = occt("BRepBuilderAPI", "BRepBuilderAPI_MakeEdge", DEFAULT_BINDING)(
        occt("gp", "gp_Pnt", DEFAULT_BINDING)(0, 0, 0), occt("gp", "gp_Pnt", DEFAULT_BINDING)(1, 0, 0)
    ).Edge()
    _, _, mapping = shown(edge, names=["edge"])
    assert isinstance(mapping["parts"][0]["shape"], list)


# ---------------------------------------------------------------- what convert gets and gives


def test_a_given_color_and_alpha_reach_the_object():
    _, shapes, _ = shown(Triangle(), names=["tri"], colors=["#ff0000"], alphas=[0.5])
    [part] = leaves(shapes)
    assert part["color"] == "#ff0000" and part["alpha"] == pytest.approx(0.5)


def test_a_bodys_own_color_is_used_unless_one_is_given():
    assert leaves(shown(Triangle(color="#00ff00"), names=["t"])[1])[0]["color"] == "#00ff00"
    assert leaves(shown(Triangle(color="#00ff00"), names=["t"], colors=["#ff0000"])[1])[0]["color"] == "#ff0000"


def test_objects_without_a_color_get_the_default_of_their_kind():
    _, shapes, _ = shown(Triangle(), Segment((0, 0, 0), (1, 0, 0)), Point(0, 0, 0), names=["t", "s", "p"])
    box_face = leaves(shown(occt("BRepBuilderAPI", "BRepBuilderAPI_MakeFace", DEFAULT_BINDING)(occt("gp", "gp_Pln", DEFAULT_BINDING)(), 0, 1, 0, 1).Face(), names=["f"])[1])[0]
    assert leaves(shapes)[0]["color"] == box_face["color"]
    assert leaves(shapes)[1]["color"] == "#ba55d3" and leaves(shapes)[2]["color"] == "#ba55d3"


def test_a_material_and_a_mode_reach_the_object():
    group, _ = to_ocpgroup(Triangle(), names=["t"], materials=["gold"], modes=[(0, 1)])
    [leaf] = group.objects
    assert leaf.material == "gold"
    assert (leaf.state_faces, leaf.state_edges) == (0, 1)


def test_a_bodys_own_name_is_used_unless_one_is_given():
    group, _ = to_ocpgroup([Triangle(name="plate")], names=["l"])
    assert group.objects[0].name == "plate"
    group, _ = to_ocpgroup(Triangle(name="plate"), names=["given"])
    assert group.objects[0].name == "given"


def test_an_object_without_a_name_is_named_by_its_type():
    group, _ = to_ocpgroup([Triangle(), Point(0, 0, 0)], names=["l"])
    assert [o.name for o in group.objects] == ["Triangle", "Point"]


def test_is_external_object_asks_the_registered_plugins():
    assert is_external_object(Triangle()) is True
    assert is_external_object(ToyLocation()) is True
    assert is_external_object(1) is False
    assert is_external_object(BRepPrimAPI_MakeBox(1, 1, 1).Shape()) is False
    assert show_of(1) is None


def test_a_plugin_whose_is_object_raises_answers_no():
    class Raises(toy_kernel.ToyShow):
        def is_object(self, obj):
            raise RuntimeError("the plugin's bug")

    register_show("raising", toy_kernel.ToyTessellation(), Raises(), api=1)
    assert is_external_object(Triangle()) is True
    assert is_external_object(1) is False


def test_a_registration_refuses_what_is_no_implementation():
    with pytest.raises(TypeError, match="TessellationProtocol"):
        register_show("wrong", object(), toy_kernel.ToyShow(), api=1)
    with pytest.raises(TypeError, match="ShowProtocol"):
        register_show("wrong", toy_kernel.ToyTessellation(), object(), api=1)


def test_a_forgotten_method_fails_when_the_plugin_creates_its_object():
    class Forgotten(TessellationProtocol):
        def tessellate(self, *args, **kwargs):
            return {}

    with pytest.raises(TypeError, match="abstract"):
        Forgotten()

    class NoLine(ShowProtocol):
        def is_object(self, obj):
            return False

        def convert(self, obj, name, color, alpha, helper_scale):
            return None

    with pytest.raises(TypeError, match="line"):
        NoLine()


# ------------------------------------------------------------------------------ the helpers


@pytest.mark.parametrize("direction", [(1, 2, 3), (0, 0, 1), (0, 0, -1), (1, 0, 0), (-2, 1, 0.3), (0.1, -0.1, -1)])
def test_a_kernels_axis_has_the_points_of_an_occt_axis(direction):
    _, mine, _ = shown(ToyAxis((1, 1, 0), direction), names=["axis"], helper_scale=2.0)
    _, theirs, _ = tessellate_group(*to_ocpgroup(CoordAxis("axis", (1, 1, 0), direction, size=2.0)), {})
    assert mine["parts"][0]["shape"]["segments_per_edge"].tolist() == [1] * 11
    assert _points(mine["parts"][0]) == _points(theirs["parts"][0])
    assert mine["parts"][0]["color"] == theirs["parts"][0]["color"] == "#000000"


def test_a_kernels_location_has_the_points_and_colors_of_an_occt_location():
    _, mine, _ = shown(ToyLocation((1, 2, 3), (0.6, 0.8, 0), (0, 0, 1)), names=["loc"], helper_scale=3.0)
    _, theirs, _ = tessellate_group(*to_ocpgroup(CoordSystem("loc", (1, 2, 3), (0.6, 0.8, 0), (0, 0, 1), size=3.0)), {})
    assert _points(mine["parts"][0]) == _points(theirs["parts"][0])
    assert mine["parts"][0]["color"] == theirs["parts"][0]["color"] == ["#ff0000", "#008000", "#0000ff"]
    assert mine["parts"][0]["width"] == theirs["parts"][0]["width"] == 2


def test_the_converters_helper_scale_reaches_the_helper():
    _, scaled, _ = shown(ToyLocation(), names=["loc"], helper_scale=5.0)
    seg = np.asarray(scaled["parts"][0]["shape"]["edges"]).reshape(-1, 2, 3)
    assert np.linalg.norm(seg[0, 1] - seg[0, 0]) == pytest.approx(5.0)


def test_like_without_a_plugin_stays_occt():
    helper = CoordSystem("loc", (0, 0, 0), (1, 0, 0), (0, 0, 1), size=1.0)
    assert not isinstance(helper.objs[0], Segment)
    helper = CoordSystem("loc", (0, 0, 0), (1, 0, 0), (0, 0, 1), size=1.0, like=ToyLocation())
    assert isinstance(helper.objs[0], Segment)


# ----------------------------------------------------------- the box of a relative helper_scale


@pytest.mark.parametrize(
    "objects",
    [
        [Point(3, 0, 0)],
        [[Point(3, 0, 0)]],
        [(Point(3, 0, 0),)],
        [{"a": Point(3, 0, 0)}],
        [Segment((0, 0, 0), (3, 0, 0))],
        [Triangle(3.0)],
        [Bag(Point(3, 0, 0))],
    ],
    ids=["vertex", "list", "tuple", "dict", "edge", "body", "container"],
)
def test_nested_bounding_box_measures_a_kernels_object_where_it_is(objects):
    assert nested_bounding_box(objects).xmax == pytest.approx(3)


def test_a_helper_adds_nothing_to_the_box_it_is_sized_from():
    assert nested_bounding_box([ToyLocation((5, 0, 0)), ToyAxis((5, 0, 0))]).max_dist_from_center() == 0


def test_nested_bounding_box_calls_no_convert():
    class Counting(toy_kernel.ToyShow):
        calls = 0

        def is_object(self, obj):
            return isinstance(obj, CountedPoint)

        def convert(self, obj, name, color, alpha, helper_scale):
            Counting.calls += 1
            return super().convert(obj, name, color, alpha, helper_scale)

    class CountedPoint(Point):
        pass

    register_show("counting", toy_kernel.ToyTessellation(), Counting(), api=1)
    assert nested_bounding_box([CountedPoint(9, 0, 0)]).xmax == pytest.approx(9)
    assert Counting.calls == 0


# ---------------------------------------------------------------------------- containers


class ListWithoutSelectors(list):
    """A kernel's own list type, without build123d's `first`, `last` and `filter_by`."""


class ListWithSelectors(list):
    """A kernel's own list type that looks like a build123d ShapeList."""

    def first(self):
        return self[0]

    def last(self):
        return self[-1]

    def filter_by(self, _):
        return self


@pytest.mark.parametrize("container", [list, tuple, ListWithoutSelectors, ListWithSelectors])
def test_a_kernels_container_needs_no_build123d_selectors(container):
    objects = container([Point(0, 0, 0), Point(1, 0, 0)])
    group, _ = to_ocpgroup(objects, names=["points"])
    assert _leaf_kinds(group) == ["vertex", "vertex"]


class Undeclared:
    def __iter__(self):
        return iter([Point(0, 0, 0)])


def test_a_container_the_kernel_declares_is_walked_by_to_ocp():
    bag = Bag(Point(3, 0, 0), Point(3, 0, 0))
    assert is_external_object(bag) is True
    group, _ = to_ocpgroup(bag, [bag], names=["bag", "bags"])
    assert _leaf_kinds(group) == ["vertex"] * 4


def test_an_iterable_no_plugin_declares_cannot_be_drawn(capsys):
    """Not a list, tuple or dict: nothing walks it, so it is an unknown object like any other."""
    assert is_external_object(Undeclared()) is False
    group, _ = to_ocpgroup(Undeclared(), names=["bag"])
    assert _leaf_kinds(group) == []
    assert capsys.readouterr().out == skipped("Undeclared")
    group, _ = to_ocpgroup([Undeclared()], names=["bags"])
    assert _leaf_kinds(group) == []
    assert capsys.readouterr().out == skipped("Undeclared")


class NotDrawable:
    """Nothing can draw it: no OCCT object, no build123d or CadQuery object, no plugin's."""


class AlsoNotDrawable:
    """A second type nothing can draw."""


def skipped(name):
    """The line a show prints for a type it left out."""
    return f"show: skipped test_external_objects.{name} (no kernel plugin installed?)\n"


def test_an_object_nothing_can_draw_is_left_out_with_one_line(capsys):
    group, _ = to_ocpgroup(NotDrawable(), names=["x"])
    assert _leaf_kinds(group) == []
    assert capsys.readouterr().out == skipped("NotDrawable")


def test_beside_an_object_that_can_be_drawn_that_one_is_drawn(capsys):
    group, _ = to_ocpgroup(Segment((0, 0, 0), (1, 0, 0)), NotDrawable(), names=["line", "x"])
    assert _leaf_kinds(group) == ["edge"]
    assert capsys.readouterr().out == skipped("NotDrawable")


@pytest.mark.parametrize(
    "container",
    [lambda item: [item], lambda item: (item,), lambda item: {"a": item}],
    ids=["list", "tuple", "dict"],
)
def test_inside_a_container_it_is_left_out_with_the_same_line(container, capsys):
    """`show_all` relies on the filtering: a container is drawable when anything in it is."""
    group, _ = to_ocpgroup(container(NotDrawable()), names=["c"])
    assert _leaf_kinds(group) == []
    assert capsys.readouterr().out == skipped("NotDrawable")
    group, _ = to_ocpgroup([Segment((0, 0, 0), (1, 0, 0)), container(NotDrawable())], names=["c"])
    assert _leaf_kinds(group) == ["edge"]
    assert capsys.readouterr().out == skipped("NotDrawable")


def test_one_line_per_type_however_many_objects(capsys):
    """In the order the types were met, passed directly or nested."""
    to_ocpgroup(NotDrawable(), [AlsoNotDrawable(), NotDrawable()], [NotDrawable()] * 100, names=["a", "b", "c"])
    assert capsys.readouterr().out == skipped("NotDrawable") + skipped("AlsoNotDrawable")


def test_every_conversion_reports_its_own(capsys):
    """Not once per session: a second show with the same type says it again."""
    to_ocpgroup(NotDrawable(), names=["x"])
    to_ocpgroup(NotDrawable(), names=["x"])
    assert capsys.readouterr().out == skipped("NotDrawable") * 2


@pytest.mark.parametrize("value", [5, 1.5, True, "text"])
def test_a_plain_value_stays_silent(value, capsys):
    group, _ = to_ocpgroup(value, names=["x"])
    assert _leaf_kinds(group) == []
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------- what a plugin gets wrong


class _Other:
    """An object of a kernel of its own."""

    size = 1.0


def _other_kernel(tag, *, convert=None, get_children=None, tessellate=None, cache_id=None):
    """A kernel of `_Other`-like objects, built for one test."""

    class Body(_Other):
        pass

    class Tessellation(toy_kernel.ToyTessellation):
        def tessellate(self, shape, deviation, quality, angular_tolerance, compute_edges=True, compute_uvs=False, normalize_uvs=True, shape_id="", debug=False):
            mesh = super().tessellate(shape, deviation, quality, angular_tolerance, compute_edges)
            return mesh if tessellate is None else tessellate(mesh)

        def bounding_box(self, shape):
            self.boxes = getattr(self, "boxes", 0) + 1
            return bbox((0, 0, 0), (1, 1, 0))

        def cache_id(self, shape):
            return cache_id

    class Show(toy_kernel.ToyShow):
        def is_object(self, obj):
            return isinstance(obj, Body)

        def convert(self, obj, name, color, alpha, helper_scale):
            return OcpObject("face", obj, name=name) if convert is None else convert(obj, name)

        def get_children(self, obj):
            return None if get_children is None else get_children(obj)

    tessellation = Tessellation()
    register_show(tag, tessellation, Show(), api=1)
    return Body, tessellation


def test_two_plugins_with_one_cache_id_do_not_share_a_mesh():
    body_a, tess_a = _other_kernel("clash a", cache_id="same id")
    body_b, tess_b = _other_kernel("clash b", cache_id="same id")
    group, instances = to_ocpgroup(body_a(), body_b(), names=["a", "b"])
    assert len(instances) == 2
    _, _, mapping = tessellate_group(group, instances)
    assert len(tess_a.calls) == 1 and len(tess_b.calls) == 1
    assert [part["shape"]["kernel"] for part in mapping["parts"]] == ["clash a", "clash b"]
    # across shows too: the mesh cache knows the kernel
    tess_b.calls.clear()
    group, instances = to_ocpgroup(body_b(), names=["b"])
    meshed, _, _ = tessellate_group(group, instances)
    assert len(meshed) == 1 and len(tess_b.calls) == 0


def test_a_plugins_box_is_asked_once_per_cache_id_and_at_every_show_without_one():
    cached, tess = _other_kernel("boxed", cache_id="boxed id")
    for _ in range(3):
        tessellate_group(*to_ocpgroup(cached(), names=["b"]))
    assert tess.boxes == 1
    uncached, tess = _other_kernel("not boxed")
    for _ in range(3):
        tessellate_group(*to_ocpgroup(uncached(), names=["b"]))
    assert tess.boxes == 3


def test_a_plugin_is_called_by_keyword():
    class KeywordOnly(toy_kernel.ToyTessellation):
        def tessellate(self, *, shape, deviation, quality, angular_tolerance, compute_edges, compute_uvs, normalize_uvs, shape_id, debug):
            return super().tessellate(shape, deviation, quality, angular_tolerance, compute_edges)

        def bounding_box(self, *, shape):
            return bbox((0, 0, 0), (1, 1, 0))

        def cache_id(self, *, shape):
            return None

    class Body(_Other):
        pass

    class Show(toy_kernel.ToyShow):
        def is_object(self, *, obj):
            return isinstance(obj, Body)

        def convert(self, *, obj, name, color, alpha, helper_scale):
            return OcpObject("face", obj, name=name)

        def get_children(self, *, obj):
            return None

        def get_location(self, *, obj):
            return None

    register_show("keywords", KeywordOnly(), Show(), api=1)
    meshed, _, _ = tessellate_group(*to_ocpgroup(Body(), names=["b"]))
    assert len(meshed) == 1


@pytest.mark.parametrize("api", [0, 2, 99])
def test_a_plugin_written_for_another_interface_is_refused(api):
    with pytest.raises(ValueError, match="plugin interface"):
        register_show("from the future", toy_kernel.ToyTessellation(), toy_kernel.ToyShow(), api=api)


def test_a_plugin_has_to_state_its_interface():
    with pytest.raises(TypeError, match="api"):
        register_show("no api", toy_kernel.ToyTessellation(), toy_kernel.ToyShow())


def test_registering_goes_to_stdout_and_says_when_it_replaces(capsys):
    register_show("twice", toy_kernel.ToyTessellation(), toy_kernel.ToyShow(), api=1)
    register_show("twice", toy_kernel.ToyTessellation(), toy_kernel.ToyShow(), api=1)
    out, err = capsys.readouterr()
    assert err == ""
    assert "Kernel plugin 'twice' registered for drawing" in out
    assert "Kernel plugin 'twice' re-registered for drawing" in out


@pytest.mark.parametrize("wrong", [None, "text", OcpGroup([], name="a group")], ids=["None", "str", "OcpGroup"])
def test_convert_must_return_an_object_of_the_tree(wrong):
    body, _ = _other_kernel("wrong convert", convert=lambda obj, name: wrong)
    with pytest.raises(TypeError, match=r"convert must return an OcpObject, CoordSystem or CoordAxis, not"):
        to_ocpgroup(body(), names=["b"])


@pytest.mark.parametrize("entries", [[("only name",)], ["text"], [("a", "b")]])
def test_get_children_must_return_its_three_part_entries(entries):
    body, _ = _other_kernel("wrong children", get_children=lambda obj: entries)
    with pytest.raises(TypeError, match=r"get_children must return \(name, child, relative placement\) entries"):
        to_ocpgroup(body(), names=["b"])


def test_a_plugin_whose_is_object_raises_is_reported_once():
    class Raising(toy_kernel.ToyShow):
        def is_object(self, obj):
            raise RuntimeError("is_object broke")

    register_show("reported", toy_kernel.ToyTessellation(), Raising(), api=1)
    try:
        with pytest.warns(UserWarning, match="is_object of kernel plugin 'reported' raised: .*is_object broke"):
            assert is_external_object(object()) is False
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert is_external_object(object()) is False
    finally:
        _show_plugins.pop("reported")


@pytest.mark.parametrize(
    "objects",
    [lambda: (None,), lambda: ([Segment((0, 0, 0), (1, 0, 0)), None],), lambda: ({"a": object()},)],
    ids=["None", "None in a list", "object() in a dict"],
)
def test_an_object_of_a_builtin_type_is_left_out_quietly(objects, capsys):
    """No plugin draws a builtin type, so there is nothing to suggest - `[box, None]` stays
    as quiet as numbers and strings."""
    to_ocpgroup(*objects(), names=["x"])
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------- validating a mesh


def _good_mesh():
    return toy_kernel.ToyTessellation().tessellate(Triangle(), 0.1, 0.01, 0.2)


def test_a_good_mesh_passes():
    validate_tessellation(_good_mesh())
    validate_tessellation({**_good_mesh(), "uvs": np.zeros(6, dtype=np.float32)})


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("vertices", np.zeros(9, dtype=np.float64), "'vertices' .* must be a float32 array, not float64"),
        ("triangles", np.array([0, 1, 2], dtype=np.int64), "'triangles' .* must be a int32 array, not int64"),
        ("vertices", [0.0] * 9, "'vertices' .* must be a float32 array, not list"),
        ("normals", np.zeros(3, dtype=np.float32), "one normal each"),
        ("triangles_per_face", np.array([5], dtype=np.int32), "count 5 triangles"),
        ("triangles", np.array([0, 1, 9], dtype=np.int32), "point at vertex 9"),
        ("face_types", np.array([0, 0], dtype=np.int32), "'face_types' and 'triangles_per_face'"),
        ("segments_per_edge", np.array([1, 1, 2], dtype=np.int32), "'segments_per_edge' count 4 segments"),
        ("edge_types", np.array([0], dtype=np.int32), "'edge_types' and 'segments_per_edge'"),
        ("face_types", np.array([99], dtype=np.int32), "'face_types' holds codes from 99 to 99: .* SURFACE_TYPES"),
        ("edge_types", np.array([0, 0, 9], dtype=np.int32), "'edge_types' holds codes from 0 to 9: .* CURVE_TYPES"),
        ("edge_types", np.array([-1, 0, 0], dtype=np.int32), "'edge_types' holds codes from -1 to 0"),
        ("uvs", np.zeros(4, dtype=np.float32), "one .u, v. per vertex"),
    ],
)
def test_a_wrong_mesh_is_refused(key, value, message):
    with pytest.raises(ValueError, match=message):
        validate_tessellation({**_good_mesh(), key: value})


def test_a_mesh_without_a_key_is_refused():
    mesh = _good_mesh()
    del mesh["normals"]
    with pytest.raises(ValueError, match="has no 'normals'"):
        validate_tessellation(mesh)


def test_the_pipeline_refuses_a_plugins_wrong_mesh():
    def wrong(mesh):
        return {**mesh, "vertices": mesh["vertices"].astype(np.float64)}

    body, _ = _other_kernel("wrong mesh", tessellate=wrong)
    with pytest.raises(ValueError, match="must be a float32 array, not float64"):
        tessellate_group(*to_ocpgroup(body(), names=["b"]))


def test_the_pipeline_refuses_a_plugins_wrong_edges():
    class WrongEdges(toy_kernel.ToyTessellation):
        def discretize_edges(self, edges, deflection=0.1, shape_id=""):
            values = super().discretize_edges(edges, deflection, shape_id)
            return {**values, "edges": values["edges"].astype(np.float64)}

    class Line:
        start, end = (0, 0, 0), (1, 0, 0)

    class Show(toy_kernel.ToyShow):
        def is_object(self, obj):
            return isinstance(obj, Line)

        def convert(self, obj, name, color, alpha, helper_scale):
            return OcpObject("edge", [obj], name=name, color="red")

    class Box(WrongEdges):
        def bounding_box(self, shape):
            return bbox((0, 0, 0), (1, 0, 0))

    register_show("wrong edges", Box(), Show(), api=1)
    with pytest.raises(ValueError, match="must be a float32 array, not float64"):
        tessellate_group(*to_ocpgroup(Line(), names=["l"]))


# ---------------------------------------------------------------------------- the type tables


def test_the_type_tables_are_the_bindings_values():
    surfaces, curves = kernel().GeomAbs.GeomAbs_SurfaceType, kernel().GeomAbs.GeomAbs_CurveType
    for name, value in SURFACE_TYPES.items():
        member = getattr(surfaces, f"GeomAbs_{name}")
        assert int(getattr(member, "value", member)) == value
    for name, value in CURVE_TYPES.items():
        member = getattr(curves, f"GeomAbs_{name}")
        assert int(getattr(member, "value", member)) == value


# ---------------------------------------------------------------------------- instance sharing


def test_one_shape_moved_is_one_instance_and_shapes_of_a_merged_group_are_found():
    from build123d import Box as BdBox, Pos as BdPos

    box = BdBox(1, 1, 1)
    group, instances = to_ocpgroup(box, BdPos(5, 0, 0) * box, BdPos(9, 0, 0) * box, names=["a", "b", "c"])
    assert len(instances) == 1
    assert [o.ref for o in group.objects] == [0, 0, 0]
    # what came in as a finished group is shared with what follows it
    merged = OcpInstancesGroup(instances, group)
    _, instances2 = to_ocpgroup(merged, BdPos(1, 2, 3) * box, names=["merged", "more"])
    assert len(instances2) == 1


# ---------------------------------------------------------------------------- generic protocols


def test_a_plugin_may_name_its_types_or_not():
    class Named(toy_kernel.ToyTessellation, TessellationProtocol[Triangle, Segment, Point]):
        pass

    class NamedShow(toy_kernel.ToyShow, ShowProtocol[Triangle | Segment | Point]):
        pass

    assert isinstance(Named(), TessellationProtocol)
    assert isinstance(NamedShow(), ShowProtocol)
    assert isinstance(toy_kernel.ToyTessellation(), TessellationProtocol)
    assert toy_kernel.ToyTessellation.__bases__ == (TessellationProtocol,)


def test_a_method_forgotten_by_a_plugin_that_names_its_types_still_fails():
    class Forgetful(TessellationProtocol[Triangle, Segment, Point]):
        def tessellate(self, *args, **kwargs): ...

    with pytest.raises(TypeError, match="abstract"):
        Forgetful()


@pytest.mark.parametrize("color", ["red", "#ff0000", (1.0, 0.0, 0.0), Color("red")])
def test_a_helper_takes_the_color_convert_is_given(color):
    """`convert` gets a color as the user wrote it, and hands it on to CoordAxis."""
    axis = CoordAxis("axis", (0, 0, 0), (0, 0, 1), color)
    assert isinstance(axis.color, Color)
    assert axis.color.web_color == "#ff0000"


# ---------------------------------------------------------------------------- UVs


class UvBody:
    """A body of a kernel of its own, which may or may not know its UVs."""

    size = 1.0

    def __init__(self, with_uvs):
        self.with_uvs = with_uvs


class UvTessellation(toy_kernel.ToyTessellation):
    def __init__(self):
        super().__init__()
        self.asked = []

    def tessellate(self, shape, deviation, quality, angular_tolerance, compute_edges=True,
                   compute_uvs=False, normalize_uvs=True, shape_id="", debug=False):
        self.asked.append((compute_uvs, normalize_uvs))
        mesh = dict(super().tessellate(shape, deviation, quality, angular_tolerance, compute_edges))
        if compute_uvs and shape.with_uvs is True:
            mesh["uvs"] = np.array([0, 0, 1, 0, 0, 1], dtype=np.float32)
        return mesh

    def bounding_box(self, shape):
        return bbox((0, 0, 0), (1, 1, 0))

    def cache_id(self, shape):
        return None


class UvShow(toy_kernel.ToyShow):
    def is_object(self, obj):
        return isinstance(obj, UvBody)

    def convert(self, obj, name, color, alpha, helper_scale):
        return OcpObject("face", obj, name=name)


UV_TESSELLATION = UvTessellation()
register_show("uv test", UV_TESSELLATION, UvShow(), api=1)


@pytest.mark.parametrize(
    ("with_uvs", "material", "asked", "in_mesh"),
    [
        (True, None, False, False),
        (True, "a material", True, True),
        (False, "a material", True, False),
    ],
    ids=["no material", "a plugin with uvs", "a plugin without uvs"],
)
def test_uvs_are_asked_for_with_a_material_and_are_the_plugins_to_give(with_uvs, material, asked, in_mesh):
    """A kernel gains UVs by changing its plugin alone: the interface already carries them."""
    UV_TESSELLATION.asked.clear()
    group, instances = to_ocpgroup(UvBody(with_uvs), names=["b"], materials=[material])
    meshed, _, _ = tessellate_group(group, instances)
    assert UV_TESSELLATION.asked == [(asked, True)]
    assert ("uvs" in meshed[0]) is in_mesh


# ---------------------------------------------------------------------------- the entry point


def _kernel_package(tmp_path, plugin_source):
    """A kernel and its plugin as installed packages: `toykernel` knows nothing of
    the viewer, `toyplugin` is found through its entry point alone."""
    (tmp_path / "toykernel").mkdir()
    (tmp_path / "toykernel" / "__init__.py").write_text("class Body:\n    pass\n")
    (tmp_path / "toyplugin.py").write_text(plugin_source)
    info = tmp_path / "toyplugin-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: toyplugin\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text("[ocp_viewer.kernels.show]\ntoykernel = toyplugin\n")
    return tmp_path


TOY_PLUGIN = """
from ocp_tessellate.plugin import OcpObject, ShowProtocol, TessellationProtocol, register_show
from toykernel import Body

print("plugin imported")

class Tessellation(TessellationProtocol):
    def tessellate(self, *args, **kwargs): ...
    def discretize_edges(self, *args, **kwargs): ...
    def convert_vertices(self, *args, **kwargs): ...
    def bounding_box(self, shape): ...

class Show(ShowProtocol):
    def is_object(self, obj):
        return isinstance(obj, Body)
    def convert(self, obj, name, color, alpha, helper_scale):
        return OcpObject("vertex", [obj], name=name)
    def line(self, start, end): ...
    def serialize(self, shape): ...

register_show("toykernel", Tessellation(), Show(), api=1)
"""


def _in_fresh_process(path, script):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(path), *sys.path]))
    return subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_script_that_imports_only_the_kernel_finds_the_plugin(tmp_path):
    result = _in_fresh_process(
        _kernel_package(tmp_path, TOY_PLUGIN),
        "from toykernel import Body\n"
        "from ocp_tessellate.kernels import is_external_object\n"
        "print('before', flush=True)\n"
        "assert is_external_object(1) is False\n"
        "print('number asked', flush=True)\n"
        "assert is_external_object(Body()) is True\n"
        "assert is_external_object(Body()) is True\n",
    )
    assert result.returncode == 0, result.stderr
    # imported on the first question about any object, and only once
    lines = result.stdout.split("\n")
    assert lines.index("before") < lines.index("plugin imported") < lines.index("number asked")
    assert "Kernel plugin 'toykernel' registered for drawing (toyplugin)" in lines
    assert result.stdout.count("plugin imported") == 1
    assert "Kernel plugin" not in result.stderr


def test_a_subclass_of_a_kernel_type_is_found_when_it_is_seen_first(tmp_path):
    result = _in_fresh_process(
        _kernel_package(tmp_path, TOY_PLUGIN),
        "from toykernel import Body\n"
        "from ocp_tessellate.kernels import is_external_object\n"
        "class Mine(Body):\n"
        "    pass\n"
        "assert is_external_object(Mine()) is True\n",
    )
    assert result.returncode == 0, result.stderr


def test_a_plugin_that_registers_nothing_says_so(tmp_path):
    result = _in_fresh_process(
        _kernel_package(tmp_path, "x = 1\n"),
        "from toykernel import Body\n"
        "from ocp_tessellate.kernels import is_external_object\n"
        "assert is_external_object(Body()) is False\n",
    )
    assert result.returncode == 0, result.stderr
    assert "did not register its kernel tag 'toykernel'" in result.stderr


def test_the_kernels_module_answers_for_occt_in_a_fresh_process(tmp_path):
    result = _in_fresh_process(
        tmp_path,
        "from build123d import Box\n"
        "from ocp_tessellate.kernels import tessellation_of\n"
        "print(type(tessellation_of(Box(1, 1, 1).wrapped)).__name__)\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("OcctTessellation")


def test_a_plugin_that_fails_to_load_warns_once_and_breaks_nothing(tmp_path):
    result = _in_fresh_process(
        _kernel_package(tmp_path, "raise RuntimeError('broken plugin')\n"),
        "from toykernel import Body\n"
        "from ocp_tessellate.kernels import is_external_object\n"
        "assert is_external_object(Body()) is False\n"
        "assert is_external_object(Body()) is False\n",
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr.count("broken plugin") == 1


# ---------------------------------------------------------------------------- the second review


def test_an_alpha_without_a_color_goes_on_the_default_of_the_kind():
    _, shapes, _ = shown(Triangle(), Segment((0, 0, 0), (1, 0, 0)), names=["tri", "edge"], alphas=[0.3, 0.4])
    tri, edge = leaves(shapes)
    assert tri["alpha"] == pytest.approx(0.3)
    # the wire has no alpha for an edge, for OCCT's neither: the default color is still there
    assert edge["color"] == leaves(shown(Segment((0, 0, 0), (1, 0, 0)), names=["edge"])[1])[0]["color"]


@pytest.mark.parametrize("tag", ["OCCT", ""])
def test_a_tag_that_names_no_plugin_is_refused(tag):
    with pytest.raises(ValueError, match="no kernel tag"):
        register_show(tag, toy_kernel.ToyTessellation(), toy_kernel.ToyShow(), api=1)
    assert tag not in _show_plugins


@pytest.mark.parametrize("api", [True, "1", None, 1.0])
def test_the_interface_version_has_to_be_an_int(api):
    with pytest.raises(TypeError, match="api must be an int"):
        register_show("no int", toy_kernel.ToyTessellation(), toy_kernel.ToyShow(), api=api)
    assert "no int" not in _show_plugins


def test_a_prebuilt_occt_object_is_an_instance_like_any_occt_shape():
    box = BRepPrimAPI_MakeBox(1, 1, 1).Shape()
    group, instances = to_ocpgroup(OcpObject("solid", box, name="prebuilt"), box, names=["prebuilt", "plain"])
    assert len(instances) == 1
    assert instances[0]["cache_id"] is not None
    assert [o.ref for o in group.objects] == [0, 0]
    assert group.objects[0].cache_id == instances[0]["cache_id"]


def test_a_plugins_list_where_one_body_belongs_is_named():
    body, _ = _other_kernel("list of bodies", convert=lambda obj, name: OcpObject("solid", [obj, obj], name=name))
    with pytest.raises(TypeError, match="Show.convert must return a solid holding one shape, not a list"):
        to_ocpgroup(body(), names=["b"])


def test_a_plugins_body_without_a_box_is_named():
    class NoBox(toy_kernel.ToyTessellation):
        def bounding_box(self, shape):
            return None

        def cache_id(self, shape):
            return None

    class Body:
        pass

    class Show(toy_kernel.ToyShow):
        def is_object(self, obj):
            return isinstance(obj, Body)

        def convert(self, obj, name, color, alpha, helper_scale):
            return OcpObject("face", obj, name=name, color="red")

    register_show("no box", NoBox(), Show(), api=1)
    try:
        with pytest.raises(TypeError, match="NoBox.bounding_box returned None for a body"):
            tessellate_group(*to_ocpgroup(Body(), names=["b"]))
    finally:
        _show_plugins.pop("no box")


def test_an_occt_shape_is_never_a_plugins():
    class Duck(toy_kernel.ToyShow):
        def is_object(self, obj):
            return hasattr(obj, "ShapeType")

    register_show("duck", toy_kernel.ToyTessellation(), Duck(), api=1)
    try:
        box = BRepPrimAPI_MakeBox(1, 1, 1).Shape()
        assert show_of(box) is None
        assert is_external_object(box) is False
        assert isinstance(tessellation_of(box), OcctTessellation)
    finally:
        _show_plugins.pop("duck")


def test_a_kernels_leaf_travels_as_base64_of_its_show_protocols_bytes():
    triangle = Triangle()
    mapping = {
        "id": "/Group",
        "parts": [
            {"id": "/Group/tri", "shape": {"kernel": toy_kernel.KERNEL, "obj": triangle}, "loc": None},
            {"id": "/Group/sub", "parts": [{"id": "/Group/sub/edge", "shape": {"kernel": toy_kernel.KERNEL, "obj": [Segment((0, 0, 0), (1, 0, 0))]}, "loc": None}]},
            {"id": "/Group/occt", "shape": ["left to the codec"], "loc": None},
        ],
    }
    encoded = encode_kernel_shapes(mapping)
    entry = encoded["parts"][0]["shape"]
    assert entry["kernel"] == toy_kernel.KERNEL
    assert base64.b64decode(entry["obj"]) == toy_kernel.ToyShow().serialize(triangle)
    assert isinstance(encoded["parts"][1]["parts"][0]["shape"]["obj"], str)
    assert encoded["parts"][2]["shape"] == ["left to the codec"]
    # the mapping given is not changed
    assert mapping["parts"][0]["shape"]["obj"] is triangle


def test_serialize_is_called_by_keyword():
    class KeywordOnly(toy_kernel.ToyShow):
        def serialize(self, *, shape):
            return b"written"

    register_show("keyword serialize", toy_kernel.ToyTessellation(), KeywordOnly(), api=1)
    try:
        leaf = {"id": "/t", "shape": {"kernel": "keyword serialize", "obj": Triangle()}, "loc": None}
        encoded = encode_kernel_shapes({"parts": [leaf]})
        assert base64.b64decode(encoded["parts"][0]["shape"]["obj"]) == b"written"
    finally:
        _show_plugins.pop("keyword serialize")
