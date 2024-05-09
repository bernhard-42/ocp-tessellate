from ocp_tessellate.cad_objects import CoordAxis, CoordSystem, OcpGroup, OcpObject
from ocp_tessellate.defaults import get_default, preset
from ocp_tessellate.ocp_utils import *
from ocp_tessellate.tessellator import (
    compute_quality,
    convert_vertices,
    discretize_edges,
    tessellate,
)
from ocp_tessellate.utils import *

DEBUG = True
LINE_WIDTH = 2
POINT_SIZE = 4


def _debug(msg, name=None, prefix="debug:", eol="\n"):
    if name is None:
        print(f"{prefix} {msg}", end=eol)
    else:
        print(f"{prefix} {msg} ('{name}')", end=eol)


def get_name(obj, name, default):
    if name is None:
        if hasattr(obj, "name") and obj.name is not None and obj.name != "":
            name = obj.name
        elif hasattr(obj, "label") and obj.label is not None and obj.label != "":
            name = obj.label
        else:
            name = default
    return name


def get_kind(obj):
    kinds = {
        "TopoDS_Edge": "edge",
        "TopoDS_Face": "face",
        "TopoDS_Shell": "shell",
        "TopoDS_Solid": "solid",
        "TopoDS_Vertex": "vertex",
        "TopoDS_Wire": "wire",
    }
    return kinds.get(class_name(obj))


def unwrap(obj):
    if hasattr(obj, "wrapped"):
        return obj.wrapped
    elif isinstance(obj, (list, tuple)):
        return [(x.wrapped if hasattr(x, "wrapped") else x) for x in obj]
    return obj


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


def get_color_for_object(obj, color=None, alpha=None, kind=None):
    default_colors = {
        # ocp types
        "TopoDS_Edge": "MediumOrchid",
        "TopoDS_Face": "Violet",
        "TopoDS_Shell": "Violet",
        "TopoDS_Solid": (232, 176, 36),
        "TopoDS_Vertex": "MediumOrchid",
        "TopoDS_Wire": "MediumOrchid",
        # kind of objects
        "edge": "MediumOrchid",
        "face": "Violet",
        "solid": (232, 176, 36),
        "vertex": "MediumOrchid",
    }

    if color is not None:
        col_a = Color(color)

    elif hasattr(obj, "color") and obj.color is not None:
        col_a = Color(obj.color)

    # elif color is None and is_topods_compound(obj) and kind is not None:
    elif color is None and kind is not None:
        col_a = Color(default_colors[kind])

    # else return default color
    else:
        col_a = Color(default_colors.get(class_name(unwrap(obj))))

    if alpha is not None:
        col_a.a = alpha

    return col_a


# TODOs:
# - cache handling
# - ImageFace
# - render mates
# - render joints
# - render parent
# - render normals
#
# - CadQuery objects
# - CadQuery assemblies


class OcpConverter:
    def __init__(self):
        self.instances = []
        self.ocp = None

    def get_instance(self, obj, kind, name, color, cache_id, progress=None):
        is_instance = False
        ocp_obj = None

        obj, loc = relocate(obj)

        # check if the same instance is already available
        for i, instance in enumerate(self.instances):
            if instance[0] == get_tshape(obj):
                # create a referential OcpObject
                ocp_obj = OcpObject(
                    kind,
                    ref=i,
                    name=name,
                    loc=loc,
                    color=color,
                    cache_id=cache_id,
                )
                # and stop the loop
                is_instance = True

                if progress is not None:
                    progress.update("-")

                break

        if not is_instance:
            ref = len(self.instances)
            # append the new instance
            self.instances.append((get_tshape(obj), obj))
            # and create a referential OcpObject
            ocp_obj = OcpObject(
                kind,
                ref=ref,
                name=name,
                loc=loc,
                color=color,
                cache_id=cache_id,
            )

        return ocp_obj

    def unify(self, objs, kind, name, color, alpha=1.0, cache_id=None):
        if cache_id is None:
            cache_id = ()

        if len(objs) == 1:  # needs to be the first condition
            ocp_obj = objs[0]
        elif kind == "edge" or kind == "vertex":
            ocp_obj = objs
        else:
            ocp_obj = make_compound(objs)

        color = get_color_for_object(ocp_obj, color, kind=kind)
        if alpha < 1.0:
            color.a = alpha

        if kind in ("solid", "face"):
            return self.get_instance(
                ocp_obj,
                kind,
                name,
                color,
                (*cache_id, id(ocp_obj)),
            )
        else:
            return OcpObject(
                kind,
                obj=ocp_obj,
                name=name,
                color=color,
                width=LINE_WIDTH if kind == "edge" else POINT_SIZE,
            )

    def to_ocp(
        self,
        *cad_objs,
        names=None,
        colors=None,
        alphas=None,
        loc=None,
        render_mates=None,
        render_joints=None,
        helper_scale=1,
        default_color=None,
        show_parent=False,
        sketch_local=False,
        instances=None,
        top_level=True,
    ):
        if loc is None:
            loc = identity_location()
        group = OcpGroup(loc=loc)

        # ============================= Validate parameters ============================= #

        if names is None:
            names = [None] * len(cad_objs)
        else:
            if len(names) != len(cad_objs):
                raise ValueError("Length of names does not match the number of objects")
            names = make_unique(names)

        if alphas is None:
            alphas = [None] * len(cad_objs)

        if len(alphas) != len(cad_objs):
            raise ValueError("Length of alphas does not match the number of objects")

        if colors is None:
            colors = [None] * len(cad_objs)
        else:
            if len(colors) != len(cad_objs):
                raise ValueError(
                    "Length of colors does not match the number of objects"
                )
            colors = [get_rgba(c, a) for c, a in zip(colors, alphas)]

        if default_color is None:
            default_color = get_default("default_color")

        if instances is None:
            instances = []

        for cad_obj, obj_name, rgba_color in zip(cad_objs, names, colors):

            # ================================= Prepare ================================= #

            # Get object color
            if rgba_color is not None and not isinstance(rgba_color, Color):
                rgba_color = get_rgba(rgba_color)

            elif hasattr(cad_obj, "color") and cad_obj.color is not None:
                rgba_color = get_rgba(cad_obj.color)

            # ================================== Loops ================================== #

            # TODO mixed topods compound
            # Generic iterables (tuple, list) or mixed type compounds (but not ShapeList)
            if (
                isinstance(cad_obj, (list, tuple))
                and not is_build123d_shapelist(cad_obj)
            ) or (is_compound(cad_obj) and is_mixed_compound(cad_obj)):
                name = (
                    "List" if isinstance(cad_obj, (list, tuple)) else "Mixed Compound"
                )
                if DEBUG:
                    _debug(name, obj_name)

                name = get_name(cad_obj, obj_name, name.rsplit(" ", maxsplit=1)[-1])
                ocp_obj = OcpGroup(name=name)
                for i, el in enumerate(cad_obj):
                    result = self.to_ocp(
                        el,
                        names=[f"{name}[{i}]"],
                        colors=[rgba_color],
                        sketch_local=sketch_local,
                        instances=instances,
                        top_level=False,
                    )
                    ocp_obj.add(result)

                if ocp_obj.length > 1:
                    ocp_obj.make_unique_names()

            # Dicts
            elif isinstance(cad_obj, dict):
                if DEBUG:
                    _debug("dict", obj_name)

                ocp_obj = OcpGroup(name=obj_name)
                for name, el in cad_obj.items():
                    result = self.to_ocp(
                        el,
                        names=[name],
                        colors=[rgba_color],
                        sketch_local=sketch_local,
                        instances=instances,
                        top_level=False,
                    )
                    ocp_obj.add(result)

            # =============================== Assemblies ================================ #

            elif is_build123d_assembly(cad_obj):
                # TODO: Fix global location
                if DEBUG:
                    _debug("build123d Assembly", obj_name)

                name = get_name(cad_obj, obj_name, "Assembly")
                ocp_obj = OcpGroup(name=name, loc=get_location(cad_obj, as_none=False))

                for child in cad_obj.children:
                    sub_obj = self.to_ocp(
                        child,
                        names=[child.label],
                        helper_scale=helper_scale,
                        instances=instances,
                        top_level=False,
                    )
                    if isinstance(sub_obj, OcpGroup) and sub_obj.length == 1:
                        if sub_obj.objects[0].loc is None:
                            sub_obj.objects[0].loc = sub_obj.loc
                        else:
                            sub_obj.objects[0].loc = (
                                sub_obj.loc * sub_obj.objects[0].loc
                            )
                        sub_obj = sub_obj.objects[0]

                    ocp_obj.add(sub_obj)

            # =============================== Conversions =============================== #

            # build123d ShapeList
            elif is_build123d_shapelist(cad_obj):
                if DEBUG:
                    _debug("build123d ShapeList", obj_name)

                # convert wires to edges
                if len(cad_obj) > 0 and is_topods_wire(cad_obj[0].wrapped):
                    objs = flatten([[e.wrapped for e in o.edges()] for o in cad_obj])
                    kind, wkind = "edge", "wire"

                # convert shells to faces
                elif len(cad_obj) > 0 and is_topods_shell(cad_obj[0].wrapped):
                    objs = flatten([[f.wrapped for f in o.faces()] for o in cad_obj])
                    kind, wkind = "face", "shell"

                # unwrap everything else
                else:
                    objs = unwrap(cad_obj)
                    kind = wkind = get_kind(objs[0])

                if kind in ("solid", "face"):
                    ocp_obj = self.unify(
                        objs,
                        kind=kind,
                        name=get_name(cad_obj, obj_name, f"ShapeList({wkind})"),
                        color=get_color_for_object(objs[0], rgba_color),
                        cache_id=tuple(id(o) for o in objs),
                    )
                else:
                    # keep the array of wrapped edges or vertices
                    ocp_obj = OcpObject(
                        kind,
                        obj=objs,
                        name=get_name(cad_obj, obj_name, f"ShapeList({wkind})"),
                        color=get_color_for_object(objs[0], rgba_color),
                        width=LINE_WIDTH if kind == "edge" else POINT_SIZE,
                        cache_id=tuple(id(o) for o in objs),
                    )

            # build123d BuildPart, BuildSketch, BuildLine
            elif is_build123d(cad_obj):
                if DEBUG:
                    _debug(f"build123d {cad_obj._obj_name}", obj_name)

                # bild123d BuildPart().part
                if is_build123d_part(cad_obj):
                    name, objs = "Solid", unwrap(cad_obj.part.solids())

                # build123d BuildSketch().sketch
                elif is_build123d_sketch(cad_obj):
                    name, objs = "Face", unwrap(cad_obj.sketch.faces())

                # build123d BuildLine().line
                elif is_build123d_line(cad_obj):
                    name, objs = "Edge", unwrap(cad_obj.line.edges())

                else:
                    raise ValueError(f"Unknown build123d object: {cad_obj}")

                name = get_name(cad_obj, obj_name, name)
                ocp_obj = self.unify(
                    objs,
                    kind=get_kind(objs[0]),
                    name=name,
                    color=rgba_color,
                    cache_id=tuple(id(o) for o in objs),
                )

                if sketch_local and hasattr(cad_obj, "sketch_local"):
                    ocp_obj.name = "sketch"
                    ocp_obj = OcpGroup([ocp_obj], name=name)
                    objs = unwrap(cad_obj.sketch_local.faces())
                    ocp_obj.add(
                        self.unify(
                            objs,
                            kind="face",
                            name="sketch_local",
                            color=rgba_color,
                            alpha=0.2,
                            cache_id=tuple(id(o) for o in objs),
                        )
                    )

            # build123d Wire, treat as shapelist of edges
            elif is_wrapped(cad_obj) and is_topods_wire(cad_obj.wrapped):
                if DEBUG:
                    _debug("build123d Wire", obj_name)

                name = get_name(cad_obj, obj_name, type_name(cad_obj.wrapped))
                ocp_obj = self.to_ocp(
                    cad_obj.edges(), names=[name], colors=[rgba_color]
                ).objects[0]

            # build123d Shape, Compound, Edge, Face, Shell, Solid, Vertex
            # elif is_build123d_shape(obj):
            #     if DEBUG:
            #         _debug(f"build123d Shape({class_name(obj)})", obj_name, eol="")

            #     objs = get_downcasted_shape(obj.wrapped)
            #     name = get_name(obj, obj_name, type_name(objs[0]))
            #     ocp_obj = self.unify(
            #         objs, name, rgba_color, cache_id=tuple(id(o) for o in objs)
            #     )
            #     if DEBUG:
            #         _debug(class_name(ocp_obj.obj), prefix="")

            # TopoDS_Shape, TopoDS_Compound, TopoDS_Edge, TopoDS_Face, TopoDS_Shell,
            # TopoDS_Solid, TopoDS_Vertex, TopoDS_Wire,
            # build123d Shape, Compound, Edge, Face, Shell, Solid, Vertex
            elif is_topods_shape(cad_obj) or is_build123d_shape(cad_obj):
                if DEBUG:
                    cl = (
                        "TopoDS_Shape"
                        if is_topods_shape(cad_obj)
                        else "build123d Shape"
                    )
                    _debug(f"{cl} ({class_name(cad_obj)})", obj_name)

                if is_build123d_shape(cad_obj):
                    cad_obj = cad_obj.wrapped

                if is_topods_wire(cad_obj):
                    objs = list(get_edges(cad_obj))
                else:
                    objs = get_downcasted_shape(cad_obj)

                if is_topods_shell(cad_obj):
                    name = get_name(cad_obj, obj_name, "Shell")
                else:
                    name = get_name(cad_obj, obj_name, type_name(objs[0]))

                ocp_obj = self.unify(
                    objs,
                    kind=get_kind(objs[0]),
                    name=name,
                    color=rgba_color,
                    cache_id=tuple(id(o) for o in objs),
                )

            # build123d Location or TopLoc_Location
            elif (is_build123d_location(cad_obj) or is_toploc_location(cad_obj)) or (
                is_build123d_plane(cad_obj) and hasattr(cad_obj, "location")
            ):
                if DEBUG:
                    _debug("build123d Location or TopLoc_Location or Plane", obj_name)

                if is_build123d_plane(cad_obj) and hasattr(cad_obj, "location"):
                    cad_obj = cad_obj.location
                    def_name = "Plane"
                else:
                    def_name = "Location"

                coord = get_location_coord(
                    cad_obj.wrapped if is_build123d_location(cad_obj) else cad_obj
                )
                name = get_name(cad_obj, obj_name, def_name)
                ocp_obj = CoordSystem(
                    name,
                    coord["origin"],
                    coord["x_dir"],
                    coord["z_dir"],
                    size=helper_scale,
                )

            # build123d Axis
            elif is_build123d_axis(cad_obj):
                if DEBUG:
                    _debug("build123d Axis", obj_name)

                coord = get_axis_coord(cad_obj.wrapped)
                name = get_name(cad_obj, obj_name, "Axis")
                ocp_obj = CoordAxis(
                    name,
                    coord["origin"],
                    coord["z_dir"],
                    size=helper_scale,
                )

            else:
                raise ValueError(f"Unknown object type: {cad_obj}")

            if DEBUG:
                print(ocp_obj)

            group.add(ocp_obj)

        if top_level and group.length == 1 and isinstance(group.objects[0], OcpGroup):
            group = group.objects[0]

        group.make_unique_names()
        return group


def to_assembly(
    *cad_objs,
    names=None,
    colors=None,
    alphas=None,
    render_mates=None,
    render_joints=None,
    helper_scale=1,
    default_color=None,
    show_parent=False,
    show_sketch_local=True,
    loc=None,
    mates=None,
    instances=None,
    progress=None,
):
    converter = OcpConverter()
    ocp_group = converter.to_ocp(
        *cad_objs,
        names=names,
        colors=colors,
        alphas=alphas,
        loc=loc,
        render_mates=render_mates,
        render_joints=render_joints,
        helper_scale=helper_scale,
        default_color=default_color,
        show_parent=show_parent,
        sketch_local=show_sketch_local,
        instances=instances,
    )
    instances = [i[1] for i in converter.instances]

    return ocp_group, instances


def tessellate_group(group, instances, kwargs=None, progress=None, timeit=False):
    def _add_bb(shapes):
        for shape in shapes["parts"]:
            if shape.get("parts") is None:
                if shape["type"] == "shapes":
                    ind = shape["shape"]["ref"]
                    with Timer(
                        timeit,
                        f"instance({ind})",
                        "create bounding boxes:     ",
                        2,
                    ) as t:
                        shape["bb"] = np_bbox(
                            meshed_instances[ind]["vertices"],
                            *shape["loc"],
                        )
            else:
                _add_bb(shape)

    def _discretize_edges(obj, name, id_):
        with Timer(timeit, name, "bounding box:", 2) as t:
            deviation = preset("deviation", kwargs.get("deviation"))
            edge_accuracy = preset("edge_accuracy", kwargs.get("edge_accuracy"))

            bb = bounding_box(obj)
            quality = compute_quality(bb, deviation=deviation)
            deflection = quality / 100 if edge_accuracy is None else edge_accuracy
            t.info = str(bb)

        with Timer(timeit, name, "discretize:  ", 2) as t:
            t.info = f"quality: {quality}, deflection: {deflection}"
            disc_edges = discretize_edges(obj, deflection, id_)

        return disc_edges, bb

    def _convert_vertices(obj, _name, id_):
        bb = bounding_box(obj)
        vertices = convert_vertices(obj, id_)

        return vertices, bb

    if kwargs is None:
        kwargs = {}

    mapping, shapes = group.collect(
        "", instances, None, _discretize_edges, _convert_vertices
    )

    states = group.to_state()

    meshed_instances = []

    deviation = preset("deviation", kwargs.get("deviation"))
    angular_tolerance = preset("angular_tolerance", kwargs.get("angular_tolerance"))

    render_edges = preset("render_edges", kwargs.get("render_edges"))

    for i, instance in enumerate(instances):
        with Timer(timeit, f"instance({i})", "compute quality:", 2) as t:
            shape = instance
            # A first rough estimate of the bounding box.
            # Will be too large, but is sufficient for computing the quality
            # location is not relevant here
            bb = bounding_box(shape, loc=None, optimal=False)
            quality = compute_quality(bb, deviation=deviation)
            t.info = str(bb)

        with Timer(timeit, f"instance({i})", "tessellate:     ", 2) as t:
            mesh = tessellate(
                shape,
                id(shape),
                deviation=deviation,
                quality=quality,
                angular_tolerance=angular_tolerance,
                debug=timeit,
                compute_edges=render_edges,
                progress=progress,
                shape_id="n/a",
            )
            meshed_instances.append(mesh)
            t.info = (
                f"{{quality:{quality:.4f}, angular_tolerance:{angular_tolerance:.2f}}}"
            )
    _add_bb(shapes)

    return meshed_instances, shapes, states, mapping


#
# Interface functions
#


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


def conv():
    raise NotImplementedError("conv is not implemented any more")
