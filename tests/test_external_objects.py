"""Objects of another kernel: OcpExternalObject.

A solid, face or shell brings its own `tessellate` and `bounding_box` and is
meshed by them with the viewer's deviation and angular tolerance; an edge or
vertex brings `points`. None of them has an entry in the mapping, the
measurement backend's model, which holds OCCT shapes only. The OCCT objects of
the same scene are unchanged.
"""

import importlib

import numpy as np
import pytest
from occt_binding import DEFAULT_BINDING, occt

from ocp_tessellate.cad_objects import CoordAxis, CoordSystem, OcpGroup
from ocp_tessellate.convert import tessellate_group, to_ocpgroup
from ocp_tessellate.ocp_utils import BoundingBox
from ocp_tessellate.plugin import (
    CURVE_TYPES,
    SURFACE_TYPES,
    OcpExternalObject,
    external_coord_axis,
    external_coord_system,
    external_edges,
    external_scene,
    external_tessellate,
)
from ocp_tessellate.tessellator import compute_quality

BRepPrimAPI_MakeBox = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", DEFAULT_BINDING)


def bbox(lo, hi):
    return BoundingBox(
        {
            "xmin": lo[0],
            "xmax": hi[0],
            "ymin": lo[1],
            "ymax": hi[1],
            "zmin": lo[2],
            "zmax": hi[2],
        }
    )


# one triangle in the XY plane, laid out as the viewer wants it
TRIANGLE = {
    "vertices": np.array([0, 0, 0, 1, 0, 0, 0, 1, 0], dtype=np.float32),
    "triangles": np.array([0, 1, 2], dtype=np.int32),
    "normals": np.array([0, 0, 1] * 3, dtype=np.float32),
    "edges": np.array(
        [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0], dtype=np.float32
    ),
    "obj_vertices": np.array([0, 0, 0, 1, 0, 0, 0, 1, 0], dtype=np.float32),
    "face_types": np.array([0], dtype=np.int32),
    "edge_types": np.array([0, 0, 0], dtype=np.int32),
    "triangles_per_face": np.array([1], dtype=np.int32),
    "segments_per_edge": np.array([1, 1, 1], dtype=np.int32),
}


def sample_objects():
    calls = []

    def tessellate(**kwargs):
        calls.append(kwargs)
        return dict(TRIANGLE)

    def edges(**kwargs):
        calls.append(("edges", kwargs))
        return {
            "edges": np.array([0, 0, 1, 1, 0, 1], dtype=np.float32),
            "segments_per_edge": np.array([1], dtype=np.int32),
            "edge_types": np.array([0], dtype=np.int32),
            "obj_vertices": np.array([0, 0, 1, 1, 0, 1], dtype=np.float32),
        }, bbox((0, 0, 1), (1, 0, 1))

    def vertices():
        calls.append(("vertices",))
        return {"obj_vertices": np.array([2, 2, 2], dtype=np.float32)}, bbox(
            (2, 2, 2), (2, 2, 2)
        )

    group = OcpGroup(
        [
            OcpExternalObject(
                "face",
                "tri",
                tessellate=tessellate,
                bounding_box=bbox((0, 0, 0), (1, 1, 0)),
                cache_id="external",
                color="red",
            ),
            OcpExternalObject("edge", "line", discretize_edges=edges, color="blue"),
            OcpExternalObject("vertex", "point", points=[(2, 2, 2)], color="green"),
        ],
        name="external",
    )
    return group, calls


def test_an_external_instance_is_meshed_by_its_own_tessellator_with_the_viewers_parameters():
    scene, calls = sample_objects()
    part_group, instances = to_ocpgroup(scene)
    assert len(instances) == 1 and instances[0]["cache_id"] == "external"
    meshed, shapes, _ = tessellate_group(
        part_group, instances, {"deviation": 0.05, "angular_tolerance": 0.3}
    )
    assert len(meshed) == 1 and meshed[0]["triangles_per_face"].tolist() == [1]
    tess_call = next(c for c in calls if isinstance(c, dict))
    assert tess_call["deviation"] == 0.05 and tess_call["angular_tolerance"] == 0.3
    assert tess_call["compute_edges"] is True and "quality" in tess_call
    edge_call = next(c for c in calls if isinstance(c, tuple) and c[0] == "edges")
    assert edge_call[1]["deviation"] == 0.05
    assert edge_call[1]["helper_scale"] == 1.0
    parts = {p["name"]: p for p in shapes["parts"]}
    assert parts["tri"]["type"] == "shapes" and parts["tri"]["shape"] == {"ref": 0}
    assert parts["tri"]["renderback"] is True
    # at the origin: an identity location, not None (the viewer applies it)
    assert parts["tri"]["loc"] == [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    assert parts["line"]["type"] == "edges" and parts["line"]["shape"][
        "segments_per_edge"
    ].tolist() == [1]
    assert parts["line"]["width"] == 2
    assert parts["point"]["type"] == "vertices" and parts["point"]["shape"][
        "obj_vertices"
    ].tolist() == [2, 2, 2]
    assert parts["point"]["size"] == 6
    # the group's bounding box spans the triangle, the edge and the point
    bb = shapes["bb"]
    assert (
        abs(bb["xmax"] - 2) < 1e-6
        and abs(bb["zmin"]) < 1e-6
        and abs(bb["zmax"] - 2) < 1e-6
    )


def test_external_objects_have_no_entry_in_the_backends_model():
    scene, _ = sample_objects()
    part_group, instances = to_ocpgroup(scene)
    _, _, mapping = tessellate_group(part_group, instances, {})
    assert mapping["parts"] == []


def test_a_mixed_scene_keeps_the_occt_objects_in_the_model():
    scene, _ = sample_objects()
    box = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
    part_group, instances = to_ocpgroup(scene, box, names=[None, "box"])
    meshed, shapes, mapping = tessellate_group(part_group, instances, {})
    assert len(meshed) == 2
    assert [p["name"] for p in shapes["parts"]] == ["external", "box"]
    box_part = shapes["parts"][1]
    assert box_part["shape"]["ref"] == 1 and len(meshed[1]["vertices"]) == 72

    # the box is the only measurable object (the external group keeps an entry
    # without parts, as the backend walks groups)
    def leaves(m):
        if "parts" in m:
            return [x for p in m["parts"] for x in leaves(p)]
        return [m["id"]]

    assert leaves(mapping) == ["/Group/box"]


def test_a_name_given_to_show_names_the_prebuilt_group():
    scene, _ = sample_objects()
    part_group, _ = to_ocpgroup(scene, names=["smlib"])
    assert part_group.name == "smlib"


def test_prebuilt_objects_without_a_color_get_the_default_of_their_kind():
    scene, _ = sample_objects()
    for obj in scene.objects:
        obj.color = None
    part_group, instances = to_ocpgroup(
        scene,
        default_facecolor="#112233",
        default_thickedgecolor="#445566",
        default_vertexcolor="#778899",
    )
    _, shapes, _ = tessellate_group(part_group, instances, {})
    colors = {p["name"]: p["color"] for p in shapes["parts"]}
    assert colors == {"tri": "#112233", "line": "#445566", "point": "#778899"}


def test_a_copy_keeps_the_callables_and_the_ref():
    scene, _ = sample_objects()
    to_ocpgroup(scene)
    face, leaf = scene.objects[0], scene.objects[1]
    assert face.copy().tessellate is face.tessellate and face.copy().ref == face.ref
    assert leaf.copy().discretize_edges is leaf.discretize_edges
    assert scene.objects[2].copy().points.tolist() == [[2, 2, 2]]


def test_an_external_object_needs_what_its_kind_is_meshed_with():
    with pytest.raises(ValueError):
        OcpExternalObject(
            "solid", "s", bounding_box=bbox((0, 0, 0), (1, 1, 1)), cache_id="s"
        )
    with pytest.raises(ValueError):
        OcpExternalObject(
            "face",
            "f",
            tessellate=lambda **k: None,
            bounding_box=bbox((0, 0, 0), (1, 1, 1)),
        )
    with pytest.raises(ValueError):
        OcpExternalObject("edge", "e")
    with pytest.raises(ValueError):
        OcpExternalObject("vertex", "v")
    with pytest.raises(ValueError):
        OcpExternalObject("compound", "c", points=[(0, 0, 0)])


def test_the_conversions_helper_scale_reaches_an_external_edge():
    scene, calls = sample_objects()
    part_group, instances = to_ocpgroup(scene, helper_scale=2.5)
    tessellate_group(part_group, instances, {})
    edge_call = next(c for c in calls if isinstance(c, tuple) and c[0] == "edges")
    assert edge_call[1]["helper_scale"] == 2.5


def test_a_prebuilt_group_has_a_nested_bounding_box():
    from ocp_tessellate.ocp_utils import nested_bounding_box

    scene, _ = sample_objects()
    bb = nested_bounding_box([scene])
    # the triangle's box; the leaves have none before they are discretized
    assert abs(bb.xmax - 1) < 1e-6 and abs(bb.ymax - 1) < 1e-6 and abs(bb.zmax) < 1e-6


def _points(part):
    return {
        tuple(np.round(p, 6)) for p in np.asarray(part["shape"]["edges"]).reshape(-1, 3)
    }


@pytest.mark.parametrize(
    "direction",
    [(1, 2, 3), (0, 0, 1), (0, 0, -1), (1, 0, 0), (-2, 1, 0.3), (0.1, -0.1, -1)],
)
def test_an_external_axis_arrow_has_the_points_of_coord_axis(direction):
    external = external_coord_axis("axis", (1, 1, 0), direction)
    _, mine, _ = tessellate_group(*to_ocpgroup(external, helper_scale=2.0), {})
    _, theirs, _ = tessellate_group(
        *to_ocpgroup(CoordAxis("axis", (1, 1, 0), direction, size=2.0)), {}
    )
    assert mine["parts"][0]["shape"]["segments_per_edge"].tolist() == [1] * 11
    assert _points(mine["parts"][0]) == _points(theirs["parts"][0])
    assert mine["parts"][0]["color"] == theirs["parts"][0]["color"] == "#000000"


def test_an_external_coord_system_has_the_points_and_colors_of_coord_system():
    external = external_coord_system("loc", (1, 2, 3), (0.6, 0.8, 0), (0, 0, 1))
    _, mine, _ = tessellate_group(*to_ocpgroup(external, helper_scale=3.0), {})
    _, theirs, _ = tessellate_group(
        *to_ocpgroup(CoordSystem("loc", (1, 2, 3), (0.6, 0.8, 0), (0, 0, 1), size=3.0)),
        {},
    )
    assert _points(mine["parts"][0]) == _points(theirs["parts"][0])
    assert (
        mine["parts"][0]["color"]
        == theirs["parts"][0]["color"]
        == ["#ff0000", "#008000", "#0000ff"]
    )
    # the helper scale set as a default reaches the external leaf too
    _, scaled, _ = tessellate_group(
        *to_ocpgroup(
            external_coord_system("loc", (0, 0, 0), (1, 0, 0), (0, 0, 1)),
            helper_scale=5.0,
        ),
        {},
    )
    seg = np.asarray(scaled["parts"][0]["shape"]["edges"]).reshape(-1, 2, 3)
    assert abs(np.linalg.norm(seg[0, 1] - seg[0, 0]) - 5.0) < 1e-6


class Body:
    """A body of a toy kernel, with its own color."""

    def __init__(self, color=None):
        self.color = color


def test_external_body_wraps_the_kernels_tessellator_in_the_cache():
    calls = []

    def tessellate(body, quality, angular_tolerance, compute_edges):
        calls.append((quality, angular_tolerance, compute_edges))
        return dict(TRIANGLE)

    marks = []

    class Progress:
        def update(self, mark):
            marks.append(mark)

    def scene():
        return OcpGroup(
            [
                external_tessellate(
                    "face",
                    "tri",
                    Body(),
                    tessellate,
                    bbox((0, 0, 0), (1, 1, 0)),
                    "toy-tri-7",
                )
            ],
            name="g",
        )

    part_group, instances = to_ocpgroup(scene())
    tessellate_group(
        part_group,
        instances,
        {"deviation": 0.1, "angular_tolerance": 0.2},
        progress=Progress(),
    )
    assert len(calls) == 1 and calls[0][2] is True and marks == ["+"]
    # the same geometry again (a new object, the same cache_id): a cache hit, no second call
    part_group, instances = to_ocpgroup(scene())
    tessellate_group(
        part_group,
        instances,
        {"deviation": 0.1, "angular_tolerance": 0.2},
        progress=Progress(),
    )
    assert len(calls) == 1 and marks == ["+", "c"]
    # another deviation: a new key
    part_group, instances = to_ocpgroup(scene())
    tessellate_group(
        part_group, instances, {"deviation": 0.05, "angular_tolerance": 0.2}
    )
    assert len(calls) == 2 and calls[1][0] < calls[0][0]


def test_external_body_takes_the_bodys_own_color_unless_one_is_given():
    def tessellate(body, quality, angular_tolerance, compute_edges):
        return dict(TRIANGLE)

    own = external_tessellate(
        "face", "a", Body("steelblue"), tessellate, bbox((0, 0, 0), (1, 1, 0)), "toy-a"
    )
    given = external_tessellate(
        "face",
        "b",
        Body("steelblue"),
        tessellate,
        bbox((0, 0, 0), (1, 1, 0)),
        "toy-b",
        color="red",
        alpha=0.5,
    )
    none = external_tessellate(
        "face", "c", Body(), tessellate, bbox((0, 0, 0), (1, 1, 0)), "toy-c"
    )
    assert (
        own.color.web_color == "#4682b4"
        and given.color.web_color == "#ff0000"
        and given.color.a == 0.5
    )
    assert none.color is None


def test_external_edges_wraps_the_kernels_discretizer_and_boxes_the_segments():
    seen = {}

    def discretize_edges(edges, deviation, edge_accuracy):
        seen.update(edges=edges, deviation=deviation, edge_accuracy=edge_accuracy)
        return {
            "edges": np.array([0, 0, 1, 3, 0, 1], dtype=np.float32),
            "segments_per_edge": np.array([1], dtype=np.int32),
            "edge_types": np.array([0], dtype=np.int32),
            "obj_vertices": np.array([0, 0, 1, 3, 0, 1], dtype=np.float32),
        }

    leaf = external_edges("line", ["an edge"], discretize_edges, color="blue")
    part_group, instances = to_ocpgroup(OcpGroup([leaf], name="g"))
    _, shapes, _ = tessellate_group(part_group, instances, {"deviation": 0.05})
    assert seen == {"edges": ["an edge"], "deviation": 0.05, "edge_accuracy": None}
    part = shapes["parts"][0]
    assert part["type"] == "edges" and part["color"] == "#0000ff"
    # the x extent is the segment's; the flat y and z extents get tessellate_group's
    # 0.1 padding for a camera box that is not degenerate
    assert abs(shapes["bb"]["xmax"] - 3) < 1e-6 and 0.85 < shapes["bb"]["zmin"] < 1


def test_external_body_without_a_cache_id_is_meshed_every_time():
    calls = []

    def tessellate(body, quality, angular_tolerance, compute_edges):
        calls.append(quality)
        return dict(TRIANGLE)

    marks = []

    class Progress:
        def update(self, mark):
            marks.append(mark)

    for _ in range(2):
        obj = external_tessellate(
            "face", "tri", Body(), tessellate, bbox((0, 0, 0), (1, 1, 0))
        )
        part_group, instances = to_ocpgroup(OcpGroup([obj], name="g"))
        tessellate_group(part_group, instances, {"deviation": 0.1}, progress=Progress())
    assert len(calls) == 2 and marks == ["+", "+"]


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


def test_external_scene_converts_with_the_kernels_convert_and_aligns_the_lists():
    seen = []

    def convert(obj, name, color, alpha):
        seen.append((obj, name, color, alpha))
        return OcpExternalObject("vertex", name, points=[(0, 0, 0)], color=color)

    scene, names, colors, alphas = external_scene(
        ["a", "b"], convert, names=["x", None], colors=[None, "red"]
    )
    assert [o.name for o in scene] == ["x", "shape1"]
    assert seen == [("a", "x", None, None), ("b", "shape1", "red", None)]
    assert names == ["x", None] and colors == [None, "red"] and alphas == [None, None]
    with pytest.raises(ValueError):
        external_scene(["a", "b"], convert, names=["only one"])


def test_external_scene_names_the_first_color_of_a_coordinate_system():
    def convert(obj, name, color, alpha):
        return external_coord_system(name, (0, 0, 0), (1, 0, 0), (0, 0, 1))

    scene, _, colors, _ = external_scene(["loc"], convert)
    assert colors[0].web_color == "#ff0000" and scene[0].color[1].web_color == "#008000"
