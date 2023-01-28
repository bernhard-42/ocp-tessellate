#
# Copyright 2023 Bernhard Walter
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from collections.abc import Iterable

from .cad_objects import (
    OCP_Edges,
    OCP_Faces,
    OCP_Part,
    OCP_PartGroup,
    OCP_Vertices,
    CoordSystem,
)
from .defaults import get_default, preset
from .mp_tessellator import get_mp_result, is_apply_result

from .ocp_utils import (
    BoundingBox,
    ocp_color,
    get_rgba,
    downcast,
    get_edges,
    get_downcasted_shape,
    get_tuple,
    is_cadquery,
    is_cadquery_assembly,
    is_cadquery_sketch,
    is_build123d,
    is_build123d_assembly,
    is_build123d_compound,
    is_build123d_shape,
    is_edge_list,
    is_face_list,
    is_solid_list,
    is_topods_compound,
    is_topods_shape,
    is_toploc_location,
    is_vertex_list,
    is_wire_list,
    is_wrapped,
    is_vector,
    np_bbox,
    identity_location,
    get_location,
    vertex,
    make_compound,
)
from .utils import Color, get_color

EDGE_COLOR = "Silver"
THICK_EDGE_COLOR = "MediumOrchid"
VERTEX_COLOR = "MediumOrchid"
FACE_COLOR = "Violet"

OBJECTS = {"objs": [], "names": [], "colors": [], "alphas": []}


def _debug(msg):
    # print("DEBUG:", msg)
    pass


def web_color(name):
    wc = Color(name)
    return ocp_color(*wc.percentage)


def tessellate_group(group, kwargs=None, progress=None, timeit=False):
    if kwargs is None:
        kwargs = {}

    shapes = group.collect_shapes(
        "",
        None,
        deviation=preset("deviation", kwargs.get("deviation")),
        angular_tolerance=preset("angular_tolerance", kwargs.get("angular_tolerance")),
        edge_accuracy=preset("edge_accuracy", kwargs.get("edge_accuracy")),
        render_edges=preset("render_edges", kwargs.get("render_edges")),
        parallel=kwargs.get("parallel"),
        progress=progress,
        timeit=timeit,
    )
    states = group.to_state()

    return shapes, states


def combined_bb(shapes):
    def c_bb(shapes, bb):
        for shape in shapes["parts"]:
            if shape.get("parts") is None:
                if bb is None:
                    if shape["bb"] is None:
                        bb = BoundingBox()
                    else:
                        bb = BoundingBox(shape["bb"])
                else:
                    if shape["bb"] is not None:
                        bb.update(shape["bb"])

                # after updating the global bounding box, remove the local
                del shape["bb"]
            else:
                bb = c_bb(shape, bb)
        return bb

    bb = c_bb(shapes, None)
    return bb


def mp_get_results(shapes, progress):
    def walk(shapes):
        for shape in shapes["parts"]:
            if shape.get("parts") is None:
                if shape.get("type") == "shapes":
                    if is_apply_result(shape["shape"].get("result")):
                        mesh = get_mp_result(shape["shape"]["result"])
                        t = shape["shape"]["t"]
                        q = shape["shape"]["q"]
                        shape["shape"] = mesh
                        shape["bb"] = np_bbox(mesh["vertices"], t, q)

                    if progress is not None:
                        progress.update()
            else:
                walk(shape)

    walk(shapes)
    return shapes


def get_accuracies(shapes):
    def _get_accuracies(shapes, lengths):
        if shapes.get("parts"):
            for shape in shapes["parts"]:
                _get_accuracies(shape, lengths)
        elif shapes.get("type") == "shapes":
            accuracies[shapes["id"]] = shapes["accuracy"]

    accuracies = {}
    _get_accuracies(shapes, accuracies)
    return accuracies


def get_normal_len(render_normals, shapes, deviation):
    if render_normals:
        accuracies = get_accuracies(shapes)
        normal_len = max(accuracies.values()) / deviation * 4
    else:
        normal_len = 0

    return normal_len


def conv_sketch(cad_obj):
    cad_objs = []
    if cad_obj._faces:
        if not isinstance(cad_obj._faces, Iterable):
            faces = [cad_obj._faces]
        else:
            faces = cad_obj._faces
        cad_objs.extend([f.moved(loc).wrapped for f in faces for loc in cad_obj.locs])

    if cad_obj._wires:
        cad_objs.extend(
            [w.moved(loc).wrapped for w in cad_obj._wires for loc in cad_obj.locs]
        )

    if cad_obj._edges:
        cad_objs.extend(
            [e.moved(loc).wrapped for e in cad_obj._edges for loc in cad_obj.locs]
        )

    if cad_obj._selection:
        if is_toploc_location(cad_obj._selection[0].wrapped):
            objs = [
                make_compound(
                    [vertex((0, 0, 0)).Moved(loc.wrapped) for loc in cad_obj._selection]
                )
            ]
        else:
            objs = [
                make_compound(
                    [
                        e.moved(loc).wrapped
                        for e in cad_obj._selection
                        for loc in cad_obj.locs
                    ]
                )
            ]
        cad_objs.extend(objs)

    return cad_objs


def conv(cad_obj, obj_id=1, obj_name=None, obj_color=None, obj_alpha=1.0):

    if isinstance(cad_obj, OCP_PartGroup):
        return cad_obj

    elif isinstance(cad_obj, (OCP_Faces, OCP_Edges, OCP_Vertices)):
        pg = OCP_PartGroup([cad_obj])
        return pg

    default_color = get_default("default_color")

    if obj_name is None and hasattr(cad_obj, "label") and cad_obj.label != "":
        obj_name = cad_obj.label

    cad_objs = []

    # BuildPart, BuildSketch, BuildLine
    if is_build123d(cad_obj):
        _debug(f"build123d Builder {obj_id}: {type(cad_obj)}")
        cad_obj = getattr(cad_obj, cad_obj._obj_name)  # convert to direct API

    if is_build123d_compound(cad_obj):
        # build123d assembly
        if is_build123d_assembly(cad_obj):
            _debug(f"build123d Assembly {obj_id}: {type(cad_obj)}")
            cad_objs = []
            raise NotImplemented("build123d assemblies not implemented yet")

        # build123d Compound
        else:
            _debug(f"build123d Compound {obj_id}: {type(cad_obj)}")
            cad_objs = [downcast(obj.wrapped) for obj in cad_obj]

    elif is_build123d_shape(cad_obj):
        _debug(f"build123d Shape {obj_id}: {type(cad_obj)}")
        cad_objs = [downcast(cad_obj.wrapped)]

    elif is_cadquery_sketch(cad_obj):
        cad_objs = conv_sketch(cad_obj)

    elif is_cadquery(cad_obj):
        cad_objs = []
        for v in cad_obj.vals():
            if is_cadquery_sketch(v):
                obj = conv_sketch(v)

            elif is_vector(v.wrapped):
                obj = [vertex(v.wrapped)]

            else:
                obj = get_downcasted_shape(v.wrapped)

            cad_objs.extend(obj)

    elif is_wrapped(cad_obj):
        if is_vector(cad_obj.wrapped):
            cad_objs = [vertex(cad_obj.wrapped)]
        else:
            cad_objs = [cad_obj.wrapped]

    elif isinstance(cad_obj, Iterable):
        objs = list(cad_obj)
        if len(objs) > 0 and is_wrapped(objs[0]):
            # ShapeList
            _debug(f"build123d ShapeList {obj_id}: {type(cad_obj)}")
            cad_objs = [downcast(obj.wrapped) for obj in objs]
        else:
            raise ValueError("Empty list cannot be tessellated")

    elif is_topods_compound(cad_obj):
        _debug(f"CAD Obj {obj_id}: TopoDS Compound")

        # Get the highest level shape
        cad_objs = get_downcasted_shape(cad_obj)

    elif is_topods_shape(cad_obj):
        _debug(f"CAD Obj {obj_id}: TopoDS Shape")
        cad_objs = [downcast(cad_obj)]

    # Convert to PartGroup

    if is_solid_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Solid'}_{obj_id}"
        return OCP_Part(
            cad_objs,
            name=name,
            color=get_rgba(obj_color, obj_alpha, Color(default_color)),
        )

    elif is_face_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Face'}_{obj_id}"
        return OCP_Faces(
            cad_objs, name=name, color=get_rgba(obj_color, obj_alpha, Color(FACE_COLOR))
        )

    elif is_wire_list(cad_objs):
        edges = []
        for wire in cad_objs:
            edges.extend(get_edges(wire))

        name = f"{obj_name if obj_name is not None else 'Wire'}_{obj_id}"
        return OCP_Edges(
            edges,
            name=name,
            color=get_rgba(obj_color, 1.0, Color(THICK_EDGE_COLOR)),
            width=2,
        )

    elif is_edge_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Edge'}_{obj_id}"
        return OCP_Edges(
            cad_objs,
            name=name,
            color=get_rgba(obj_color, 1.0, THICK_EDGE_COLOR),
            width=2,
        )

    elif is_vertex_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Vertex'}_{obj_id}"
        return OCP_Vertices(
            cad_objs,
            name=name,
            color=get_rgba(obj_color, 1.0, THICK_EDGE_COLOR),
            size=6,
        )

    else:
        # Mixed compound, analyse every obj separately

        name = f"{obj_name if obj_name is not None else 'Compound'}_{obj_id}"

        pg = OCP_PartGroup([], name=name)
        pg.loc = identity_location()

        ind = 0
        for cad_obj in cad_objs:
            if is_solid_list([cad_obj]):
                name = (
                    f"{cad_obj.label}_{ind}" if cad_obj.label != "" else f"Solid_{ind}"
                )
                part = OCP_Part(
                    cad_obj,
                    name=name,
                    color=get_rgba(obj_color, obj_alpha, Color(default_color)),
                )

            elif is_face_list([cad_obj]):
                part = OCP_Faces(
                    [cad_obj],
                    name=f"Face_{ind}",
                    color=get_rgba(obj_color, obj_alpha, Color(FACE_COLOR)),
                )

            elif is_edge_list([cad_obj]):
                part = OCP_Edges(
                    [cad_obj],
                    name=f"Edge_{ind}",
                    color=get_rgba(obj_color, 1.0, Color(THICK_EDGE_COLOR)),
                    width=2,
                )

            elif is_wire_list([cad_obj]):
                part = OCP_Edges(
                    get_edges(cad_obj),
                    name=f"Wire_{ind}",
                    color=get_rgba(obj_color, 1.0, Color(THICK_EDGE_COLOR)),
                    width=2,
                )

            elif is_vertex_list([cad_obj]):
                part = OCP_Vertices(
                    [cad_obj],
                    name=f"Vertex_{ind}",
                    color=get_rgba(obj_color, 1.0, Color(THICK_EDGE_COLOR)),
                    size=6,
                )

            elif is_topods_compound(cad_obj):
                part = conv(cad_obj, obj_id, "Compound")
                obj_id += 1

            else:
                part = OCP_Part(
                    cad_objs,
                    name=name,
                    color=get_rgba(obj_color, obj_alpha, Color(default_color)),
                )
            pg.add(part)
            ind += 1
        return pg


def to_assembly(
    *cad_objs,
    names=None,
    colors=None,
    alphas=None,
    name="Group",
    render_mates=None,
    mate_scale=1,
    default_color=None,
    show_parent=False,
    loc=None,
    grp_id=0,
    mates=None,
):
    if names is None:
        names = [None] * len(cad_objs)

    if colors is None:
        colors = [None] * len(cad_objs)

    if alphas is None:
        alphas = [None] * len(cad_objs)

    if default_color is None:
        default_color = (
            get_default("default_color") if default_color is None else default_color
        )

    pg = OCP_PartGroup([], f"{name}_{grp_id}")

    obj_id = 0

    for obj_name, obj_color, obj_alpha, cad_obj in zip(names, colors, alphas, cad_objs):

        if is_cadquery_assembly(cad_obj):
            pg.name = cad_obj.name

            loc = get_location(cad_obj.loc, as_none=False)
            pg.loc = loc

            if cad_obj.color is None:
                *rgb, a = get_rgba(obj_color, obj_alpha, Color(default_color))

            else:
                *rgb, a = get_rgba(cad_obj.color, obj_alpha, Color(default_color))

            if cad_obj.obj is not None:
                pg.add(
                    conv(
                        cad_obj.obj,
                        obj_id,
                        pg.name,
                        rgb,
                        a,
                    ),
                )

            top_level_mates = None
            if render_mates and hasattr(cad_obj, "mates") and cad_obj.mates is not None:
                top_level_mates = cad_obj.mates if mates is None else mates
                pg2 = OCP_PartGroup(
                    [
                        CoordSystem(
                            name,
                            get_tuple(mate_def.mate.origin),
                            get_tuple(mate_def.mate.x_dir),
                            get_tuple(mate_def.mate.y_dir),
                            get_tuple(mate_def.mate.z_dir),
                            mate_scale,
                        )
                        for name, mate_def in top_level_mates.items()
                        if mate_def.assembly == cad_obj
                    ],
                    name="mates",
                    loc=identity_location(),  # mates inherit the parent location, so actually add a no-op
                )
                if pg2.objects:
                    pg.add(pg2)

            for child in cad_obj.children:
                grp_id += 1
                pg.add(
                    to_assembly(
                        child,
                        loc=loc,
                        grp_id=grp_id,
                        default_color=default_color,
                        mates=top_level_mates,
                        render_mates=render_mates,
                        mate_scale=mate_scale,
                    ),
                )

        elif is_build123d_assembly(cad_obj):
            pg.name = cad_obj.label

            loc = get_location(cad_obj.location, as_none=False)
            pg.loc = loc

            for child in cad_obj.children:
                grp_id += 1
                pg.add(
                    to_assembly(
                        child,
                        loc=loc,
                        grp_id=grp_id,
                        default_color=default_color,
                        render_mates=render_mates,
                        mate_scale=mate_scale,
                    )
                )

        else:
            if show_parent and hasattr(cad_obj, "parent"):
                pg.add(conv(cad_obj.parent, obj_id, "parent", None, None))
                pg.objects[0].state_faces = 0

            if hasattr(cad_obj, "color") and cad_obj.color is not None:
                *color, alpha = get_rgba(cad_obj.color, obj_alpha, Color(default_color))
                pg.add(conv(cad_obj, obj_id, obj_name, color, alpha))
            else:
                pg.add(conv(cad_obj, obj_id, obj_name, obj_color, obj_alpha))

        if pg.loc is None:
            pg.loc = identity_location()

        obj_id += 1

    if len(pg.objects) == 1 and isinstance(pg.objects[0], OCP_PartGroup):
        pg = pg.objects[0]

    return pg
