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

from collections import Iterable

from .cad_objects import Edges, Faces, Part, PartGroup, Vertices
from .convert import Edges, Faces, Part, PartGroup, Vertices
from .defaults import get_default, preset
from .mp_tessellator import get_mp_result, is_apply_result
from .ocp_utils import (
    BoundingBox,
    OcpColor,
    downcast,
    get_edges,
    get_faces,
    get_solids,
    get_vertices,
    get_wires,
    is_build123d,
    is_build123d_assembly,
    is_build123d_compound,
    is_build123d_shape,
    is_cadquery,
    is_edge_list,
    is_face_list,
    is_solid_list,
    is_topods_compound,
    is_topods_shape,
    is_vertex_list,
    is_wire_list,
    is_wrapped,
    make_compound,
    np_bbox,
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
    return OcpColor(*wc.percentage)


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


def conv(cad_obj, obj_id=1, obj_name=None, obj_color=None, obj_alpha=1.0):
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

    elif isinstance(cad_obj, Iterable):
        objs = list(cad_obj)
        if len(objs) > 0 and is_wrapped(objs[0]):
            # ShapeList
            _debug(f"build123d ShapeList {obj_id}: {type(cad_obj)}")
            cad_objs = [downcast(obj.wrapped) for obj in objs]
        else:
            raise ValueError("Empty list cannot be tessellated")

    elif is_cadquery(cad_obj):
        cad_objs = [downcast(v.wrapped) for v in cad_obj.vals()]

    elif is_topods_compound(cad_obj):
        _debug(f"CAD Obj {obj_id}: TopoDS Compound")

        # Get the highest level shape

        if next(get_solids(cad_obj), None) is not None:
            cad_objs = get_solids(cad_obj)

        elif next(get_faces(cad_obj), None) is not None:
            cad_objs = get_faces(cad_obj)

        elif next(get_wires(cad_obj), None) is not None:
            cad_objs = get_wires(cad_obj)

        elif next(get_edges(cad_obj), None) is not None:
            cad_objs = get_edges(cad_obj)

        elif next(get_vertices(cad_obj), None) is not None:
            cad_objs = get_vertices(cad_obj)

        else:
            raise NotImplementedError("Unknow TopoDS Compound")

        cad_objs = [downcast(obj) for obj in cad_objs]

    elif is_topods_shape(cad_obj):
        _debug(f"CAD Obj {obj_id}: TopoDS Shape")
        cad_objs = [downcast(cad_obj)]

    # Convert to PartGroup

    if is_solid_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Solid'}_{obj_id}"
        return Part(cad_objs, name=name, color=obj_color)

    elif is_face_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Face'}_{obj_id}"
        return Faces(cad_objs, name=name, color=obj_color)

    elif is_wire_list(cad_objs) or is_edge_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Edge'}_{obj_id}"
        if obj_color is None:
            obj_color = get_color(obj_color, THICK_EDGE_COLOR, 1.0)
        return Edges(cad_objs, name=name, color=obj_color, width=2)

    elif is_vertex_list(cad_objs):
        name = f"{obj_name if obj_name is not None else 'Vertex'}_{obj_id}"
        if obj_color is None:
            obj_color = get_color(obj_color, THICK_EDGE_COLOR, 1.0)
        return Vertices(cad_objs, name=name, color=obj_color, size=6)

    else:
        return Part([make_compound(cad_objs)], color=obj_color)


def to_assembly(
    *cad_objs,
    names=None,
    colors=None,
    alphas=None,
    name="Group",
    render_mates=None,
    mate_scale=1,
    default_color=None,
    show_parent=True,
):
    if names is None:
        names = [None] * len(cad_objs)

    if colors is None:
        colors = [None] * len(cad_objs)

    if alphas is None:
        alphas = [1.0] * len(cad_objs)

    default_color = (
        get_default("default_color") if default_color is None else default_color
    )

    pg = PartGroup([], name)
    obj_id = 0

    for obj_name, obj_color, obj_alpha, cad_obj in zip(names, colors, alphas, cad_objs):
        pg.add(
            conv(
                cad_obj,
                obj_id,
                obj_name,
            )
        )
        obj_id += 1

    if len(pg.objects) == 1 and isinstance(pg.objects[0], PartGroup):
        pg = pg.objects[0]

    return pg
