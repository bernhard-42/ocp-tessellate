import enum
from hashlib import sha256

from ocp_tessellate.cad_objects import (
    CoordAxis,
    CoordSystem,
    ImageFace,
    OcpGroup,
    OcpObject,
)
from ocp_tessellate.defaults import get_default, preset
from ocp_tessellate.ocp_utils import *
from ocp_tessellate.tessellator import (
    compute_quality,
    convert_vertices,
    discretize_edges,
    tessellate,
)
from ocp_tessellate.utils import *

LINE_WIDTH = 2
POINT_SIZE = 6

EDGE_COLOR = "Silver"
THICK_EDGE_COLOR = "MediumOrchid"
VERTEX_COLOR = "MediumOrchid"
FACE_COLOR = "Violet"

DEBUG = True


def _debug(level, msg, name=None, prefix="debug:", end="\n"):
    if DEBUG:
        prefix = "  " * level + prefix
        suffix = f" ('{name}')" if name is not None else ""
        print(f"{prefix} {msg} {suffix}", end=end, flush=True)


def get_name(obj, name, default):
    if name is None:
        if hasattr(obj, "name") and obj.name is not None and obj.name != "":
            name = obj.name
        elif hasattr(obj, "label") and obj.label is not None and obj.label != "":
            name = obj.label
        else:
            name = default
    return name


def get_type(obj):
    kinds = {
        "TopoDS_Edge": "Edge",
        "TopoDS_Face": "Face",
        "TopoDS_Shell": "Shell",
        "TopoDS_Solid": "Solid",
        "TopoDS_Vertex": "Vertex",
        "TopoDS_Wire": "Wire",
    }
    typ = kinds.get(class_name(obj))
    if typ is None:
        raise ValueError(f"Unknown type: {type(obj)}")
    return typ


def get_kind(typ):
    kinds = {
        "Edge": "edge",
        "Face": "face",
        "Shell": "face",
        "Solid": "solid",
        "Vertex": "vertex",
        "Wire": "edge",
    }
    kind = kinds.get(typ)
    if kind is None:
        raise ValueError(f"Unknown type: {typ}")
    return kind


def unwrap(obj):
    if hasattr(obj, "wrapped"):
        return obj.wrapped
    elif isinstance(obj, (list, tuple)):
        return [(x.wrapped if hasattr(x, "wrapped") else x) for x in obj]
    return obj


def create_cache_id(obj):
    sha = sha256()
    objs = [obj] if not isinstance(obj, (tuple, list)) else obj
    for o in objs:
        sha.update(serialize(o.wrapped if is_wrapped(o) else o))

    return sha.hexdigest()


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
    def __init__(self, progress=None):
        self.instances = []
        self.ocp = None
        self.progress = progress
        self.default_color = get_default("default_color")

    # ============================== Create instances =============================== #

    def get_instance(self, obj, cache_id, name):
        ref = None

        # Create the relocated object as a copy
        loc = obj.Location()  # Get location
        obj2 = downcast(obj.Moved(loc.Inverted()))

        # check if the same instance is already available
        for i, instance in enumerate(self.instances):
            if instance["obj"] == obj2:
                ref = i

                if self.progress is not None:
                    self.progress.update("-")

                break

        if ref is None:
            # append the new instance
            ref = len(self.instances)
            self.instances.append({"obj": obj2, "cache_id": cache_id, "name": name})

        return ref, loc

    def unify(self, objs, kind, name, color, alpha=1.0):
        # Try to downcast to one TopoDS_Shape
        if len(objs) == 1:
            ocp_obj = objs[0]
            # unroll TopoDS_Compound
            if is_topods_compound(ocp_obj):
                ocp_objs = list(list_topods_compound(ocp_obj))
                if len(ocp_objs) == 1:
                    ocp_obj = downcast(ocp_objs[0])
                elif kind in ["edge", "vertex"]:
                    ocp_obj = ocp_objs

        # else make a TopoDS_Compound
        elif kind in ["solid", "face", "shell"]:
            ocp_obj = make_compound(objs)

        # and for vertices and edges, keep the list
        else:
            ocp_obj = objs

        color = self.get_color_for_object(
            ocp_obj[0] if isinstance(ocp_obj, list) else ocp_obj,
            color,
            kind=kind,
        )
        if alpha < 1.0:
            color.a = alpha

        if kind in ("solid", "face", "shell"):
            cache_id = create_cache_id(objs)
            ref, loc = self.get_instance(ocp_obj, cache_id, name)
            return OcpObject(
                kind,
                ref=ref,
                name=name,
                loc=loc,
                color=color,
                cache_id=cache_id,
            )
        else:
            return OcpObject(
                kind,
                obj=ocp_obj,
                name=name,
                color=color,
                width=LINE_WIDTH if kind == "edge" else POINT_SIZE,
            )

    def get_color_for_object(self, obj, color=None, alpha=None, kind=None):
        default_colors = {
            # ocp types
            "TopoDS_Edge": THICK_EDGE_COLOR,
            "TopoDS_Face": FACE_COLOR,
            "TopoDS_Shell": FACE_COLOR,
            "TopoDS_Solid": self.default_color,
            "TopoDS_Vertex": VERTEX_COLOR,
            "TopoDS_Wire": THICK_EDGE_COLOR,
            # kind of objects
            "edge": THICK_EDGE_COLOR,
            "wire": THICK_EDGE_COLOR,
            "face": FACE_COLOR,
            "shell": FACE_COLOR,
            "solid": self.default_color,
            "vertex": VERTEX_COLOR,
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

    # ============================= Iterate Containers ============================== #

    def _unroll_iterable(
        self, objs, obj_name, rgba_color, sketch_local, helper_scale, level
    ):
        ocp_obj = OcpGroup(name=obj_name)
        for name, obj in objs:
            name = get_name(objs, name, None)

            result = self.to_ocp(
                obj,
                names=[name],
                colors=[rgba_color],
                sketch_local=sketch_local,
                helper_scale=helper_scale,
                top_level=False,
                level=level + 1,
            )
            if result.length > 0:
                ocp_obj.add(result.cleanup())

        return ocp_obj.make_unique_names().cleanup()

    def handle_list_tuple(
        self, cad_obj, obj_name, rgba_color, sketch_local, helper_scale, level
    ):
        _debug(level, "handle_list_tuple", obj_name)
        return self._unroll_iterable(
            zip([None] * len(cad_obj), cad_obj),
            get_name(cad_obj, obj_name, "List"),
            rgba_color,
            sketch_local,
            helper_scale,
            level,
        )

    def handle_dict(
        self, cad_obj, obj_name, rgba_color, sketch_local, helper_scale, level
    ):
        _debug(level, "handle_dict", obj_name)

        return self._unroll_iterable(
            cad_obj.items(),
            get_name(cad_obj, obj_name, "Dict"),
            rgba_color,
            sketch_local,
            helper_scale,
            level,
        )

    def handle_compound(
        self, cad_obj, obj_name, rgba_color, sketch_local, helper_scale, level
    ):
        _debug(level, f"handle_compound", obj_name)

        if is_compound(cad_obj):
            cad_obj = list(cad_obj)
        elif is_topods_compound(cad_obj):
            cad_obj = list(list_topods_compound(cad_obj))

        return self._unroll_iterable(
            zip([None] * len(cad_obj), cad_obj),
            get_name(cad_obj, obj_name, "Compound"),
            rgba_color,
            sketch_local,
            helper_scale,
            level,
        )
            ocp_obj.add(result.cleanup())

    # ================================= Assemblies ================================== #

    def handle_build123d_assembly(
        self, cad_obj, obj_name, rgba_color, render_joints, helper_scale, level
    ):
        _debug(level, "handle_build123d_assembly", obj_name)

        name = get_name(cad_obj, obj_name, "Assembly")
        ocp_obj = OcpGroup(name=name, loc=get_location(cad_obj, as_none=False))

        for child in cad_obj.children:
            sub_obj = self.to_ocp(
                child,
                names=[child.label],
                colors=[rgba_color],
                helper_scale=helper_scale,
                render_joints=render_joints,
                top_level=False,
                level=level + 1,
            )
            if sub_obj.length == 1 and len(child.children) == 0:
                ocp_obj.add(sub_obj.objects[0])
            else:
                ocp_obj.add(sub_obj)

        return ocp_obj

    # ================================= Conversions ================================= #

    def handle_parent(self, cad_obj, obj_name, rgba_color, level):
        parent = None
        if hasattr(cad_obj, "parent"):
            parent = cad_obj.parent
            topo = False
        elif hasattr(cad_obj, "topo_parent"):
            parent = cad_obj.topo_parent
            topo = True
        elif (
            isinstance(cad_obj, Iterable)
            and len(cad_obj) > 0
            and hasattr(cad_obj[0], "topo_parent")
        ):
            parent = cad_obj[0].topo_parent
            topo = True

        ind = 0
        parents = []
        while parent is not None:
            pname = "parent" if ind == 0 else f"parent({ind})"
            p = self.to_ocp(parent, names=[pname], colors=None, level=level + 1)
            p = p.objects[0]
            if p.kind == "solid":
                p.state_faces = 0
            elif p.kind == "face":
                p.state_edges = 0
            parents.insert(0, p)
            parent = parent.topo_parent if topo else None
            ind -= 1

        return parents

    def handle_shape_list(
        self,
        cad_obj,
        obj_name,
        rgba_color,
        show_parent,
        level,
    ):
        parent_obj = cad_obj

        if is_build123d_shapelist(cad_obj):
            _debug(level, "handle_shapelist (build123d ShapeList)", obj_name)
            name = "ShapeList"
        else:
            _debug(level, "handle_shapelist (cadquery Workplane)", obj_name)
            name = "Workplane"

            # Resolve cadquery Workplane
            cad_obj = cad_obj.vals()
            if len(cad_obj) > 0:
                if is_compound(cad_obj[0]):
                    cad_obj = flatten([list(obj) for obj in cad_obj])
                elif is_cadquery_sketch(cad_obj[0]):
                    return self.to_ocp(cad_obj).cleanup()

        # convert wires to edges
        if len(cad_obj) > 0 and is_wire(cad_obj[0]):
            objs = [e.wrapped for o in cad_obj for e in o.edges()]
            typ = "Wire"

        # unwrap everything else
        else:
            objs = unwrap(cad_obj)
            typ = get_type(objs[0])

        kind = get_kind(typ)

        ocp_obj = self.unify(
            objs,
            kind=kind,
            name=get_name(cad_obj, obj_name, f"{name}({typ})"),
            color=self.get_color_for_object(objs[0], rgba_color),
        )

        if show_parent:
            parents = self.handle_parent(parent_obj, obj_name, rgba_color, level)
            return OcpGroup(parents + [ocp_obj], name=ocp_obj.name)
        else:
            return ocp_obj

    def handle_shapes(self, cad_obj, obj_name, render_joints, rgba_color, level):

        if is_topods_shape(cad_obj):
            t, obj = "TopoDS_Shape", downcast(cad_obj)
        elif is_build123d_shape(cad_obj):
            t, obj = "build123d Shape", cad_obj.wrapped
        elif is_cadquery_shape(cad_obj):
            t, obj = "cadquery Shape", cad_obj.wrapped
        else:
            raise ValueError(f"Unknown shape type: {cad_obj}")

        _debug(level, f"handle_shapes ({t}) ({class_name(obj)})", obj_name)

        edges = None
        if is_topods_wire(obj):
            typ, edges = "Wire", list(get_edges(obj))
        elif is_topods_compound(obj):
            typ = get_compound_type(obj)
            if typ == "Wire":
                obj = list(get_edges(obj))
        else:
            typ = type_name(obj)

        name = get_name(cad_obj, obj_name, typ)

        ocp_obj = self.unify(
            [obj] if edges is None else edges,
            kind=get_kind(typ),
            name=name,
            color=rgba_color,
        )

        if render_joints and hasattr(cad_obj, "joints") and len(cad_obj.joints) > 0:
            joints = self.to_ocp(
                *[j.symbol for j in cad_obj.joints.values()],
                names=list(cad_obj.joints.keys()),
                level=level + 1,
            )
            joints.name = "joints"
            ocp_obj = OcpGroup([ocp_obj, joints], name=name)

        return ocp_obj

    def handle_build123d_builder(
        self, cad_obj, obj_name, rgba_color, sketch_local, render_joints, level
    ):
        _debug(level, f"handle_build123d_builder {cad_obj._obj_name}", obj_name)

        # bild123d BuildPart().part
        if is_build123d_part(cad_obj):
            obj = cad_obj.part
            obj_name = get_name(cad_obj, obj_name, "Solid")

        # build123d BuildSketch().sketch
        elif is_build123d_sketch(cad_obj):
            obj = cad_obj.sketch.faces()
            obj_name = get_name(cad_obj, obj_name, "Face")

        # build123d BuildLine().line
        elif is_build123d_line(cad_obj):
            obj = cad_obj.edges()
            obj_name = get_name(cad_obj, obj_name, "Edge")

        ocp_obj = self.to_ocp(
            obj,
            names=[obj_name],
            colors=[rgba_color],
            render_joints=render_joints,
            level=level + 1,
        )

        if sketch_local and hasattr(cad_obj, "sketch_local"):
            obj = cad_obj.sketch_local.faces()
            ocp_obj.name = ocp_obj.objects[0].name
            ocp_obj.objects[0].name = "sketch"
            ocp_obj_local = self.to_ocp(
                obj,
                names=["sketch_local"],
                colors=[rgba_color],
                render_joints=render_joints,
                level=level + 1,
            ).objects[0]
            ocp_obj_local.color.a = 0.2
            ocp_obj.add(ocp_obj_local)

        return ocp_obj.cleanup()

    def handle_cadquery_sketch(self, cad_obj, obj_name, rgba_color, level):
        _debug(level, "cadquery Sketch", obj_name)

        if not list(cad_obj._faces):  # empty compound
            cad_obj._faces = []

        if not isinstance(cad_obj._faces, (list, tuple)):
            cad_obj._faces = [cad_obj._faces]

        cad_objs = []
        names = []
        for typ, objs, calc_bb in [
            ("Face", list(cad_obj._faces), False),
            ("Edge", list(cad_obj._edges), False),
            ("Wire", list(cad_obj._wires), True),
            ("Selection", list(cad_obj._selection), False),
        ]:
            if objs:
                if is_location(objs[0]):
                    compound = [
                        loc.wrapped * obj.wrapped
                        for obj in cad_obj._selection
                        for loc in cad_obj.locs
                    ]
                else:
                    compound = make_compound(
                        [
                            downcast(obj.wrapped.Moved(loc.wrapped))
                            for obj in objs
                            for loc in cad_obj.locs
                        ]
                    )
                cad_objs.append(compound)
                names.append(typ)

            if calc_bb:
                bb = BoundingBox()
                for obj in cad_objs:
                    bb.update(BoundingBox(obj))
                size = max(bb.xsize, bb.ysize, bb.zsize)

        name = get_name(cad_obj, obj_name, "Sketch")
        result = self.to_ocp(
            *cad_objs,
            names=names,
            colors=[rgba_color] * len(cad_objs),
            level=level,
            helper_scale=size / 20,
        )
        result.name = name
        return result

    # ================================ Empty objects ================================ #

    def handle_empty_iterables(self, obj_name, level):
        _debug(level, "Empty object")
        name = "Object" if obj_name is None else obj_name
        return OcpObject(
            "vertex",
            obj=vertex((0, 0, 0)),
            name=f"{name} (empty)",
            color=Color((0, 0, 0, 0.01)),
            width=0.1,
        )

    # ============================ OcpObj's and OcpGroup ============================ #

    def handle_locations_planes(
        self, cad_obj, obj_name, rgba_color, helper_scale, sketch_local, level
    ):
        if is_build123d_location(cad_obj) or is_toploc_location(cad_obj):
            _debug(level, "build123d Location or TopLoc_Location", obj_name)

        elif (
            is_build123d_plane(cad_obj)
            and hasattr(cad_obj, "location")
            or is_gp_plane(cad_obj)
        ):
            _debug(level, "build123d Plane or gp_Pln", obj_name)

        elif is_cadquery_empty_workplane(cad_obj):
            _debug(level, "cadquery Workplane", obj_name)

        if is_build123d_plane(cad_obj) and hasattr(cad_obj, "location"):
            cad_obj = cad_obj.location
            def_name = "Plane"

        elif is_gp_plane(cad_obj):
            def_name = "Plane"
            cad_obj = loc_from_gp_pln(cad_obj)

        elif is_cadquery_empty_workplane(cad_obj):
            def_name = "Workplane"
            cad_obj = cad_obj.plane.location

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
        return ocp_obj

    def handle_axis(
        self, cad_obj, obj_name, rgba_color, helper_scale, sketch_local, level
    ):
        _debug(level, "build123d Axis", obj_name)

        if is_wrapped(cad_obj):
            cad_obj = cad_obj.wrapped
        coord = get_axis_coord(cad_obj)
        name = get_name(cad_obj, obj_name, "Axis")
        ocp_obj = CoordAxis(
            name,
            coord["origin"],
            coord["z_dir"],
            size=helper_scale,
        )
        return ocp_obj

    def handle_ocp_group(self, cad_obj, obj_name):
        name = get_name(cad_obj, obj_name, "Group")
        cad_obj.name = name
        return cad_obj

    def handle_ocp_obj(self, cad_obj, obj_name):
        name = get_name(cad_obj, obj_name, "Object")
        ref, loc = self.get_instance(cad_obj.obj, create_cache_id(cad_obj.obj), name)
        ocp_obj = cad_obj.copy()
        ocp_obj.ref = name
        ocp_obj.ref = ref
        ocp_obj.loc = cad_obj.loc * loc
        ocp_obj.obj = None
        return ocp_obj

        cad_obj.name = name
        return cad_obj

    # ======================== Iterate and identify objects ========================= #

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
        unroll_compounds=False,
        cache_id=None,
        top_level=True,
        level=0,
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

        if default_color is not None:
            self.default_color = default_color

        # =========================== Loop over all objects ========================== #

        for cad_obj, obj_name, rgba_color in zip(cad_objs, names, colors):

            # =================== Silently skip enums and known types =================== #
            if (
                isinstance(cad_obj, enum.Enum)
                or is_ocp_color(cad_obj)
                or isinstance(cad_obj, (int, float, bool, str, np.number, np.ndarray))
            ):
                continue

            # ============================== Prepare color ============================== #

            # Get object color
            if rgba_color is not None:
                if not isinstance(rgba_color, Color):
                    rgba_color = get_rgba(rgba_color)

            elif hasattr(cad_obj, "color") and cad_obj.color is not None:
                rgba_color = get_rgba(cad_obj.color)

            # =========================== Map Vector to Vertex ========================== #

            if is_vector(cad_obj) or is_gp_vec(cad_obj):
                if isinstance(cad_obj, Iterable):
                    cad_obj = vertex(list(cad_obj))
                elif hasattr(cad_obj, "toTuple"):
                    cad_obj = vertex(cad_obj.toTuple())
                else:
                    cad_obj = vertex(cad_obj.XYZ().Coord())

                if obj_name is None:
                    obj_name = "Vector"

            # ========================= Empty list or compounds ========================= #

            if (
                not is_cadquery_sketch(cad_obj)
                and not is_vertex(cad_obj)
                and (
                    (is_wrapped(cad_obj) and cad_obj.wrapped is None)
                    or (isinstance(cad_obj, Iterable) and len(list(cad_obj)) == 0)
                )
            ):
                ocp_obj = self.handle_empty_iterables(obj_name, level)

            # ================================ Iterables ================================ #

            # Generic iterables (tuple, list, but not ShapeList)
            elif isinstance(cad_obj, (list, tuple)) and not is_build123d_shapelist(
                cad_obj
            ):
                ocp_obj = self.handle_list_tuple(
                    cad_obj, obj_name, rgba_color, sketch_local, helper_scale, level
                )

            # Compounds / topods_compounds
            elif (
                is_compound(cad_obj)
                and (is_mixed_compound(cad_obj) or unroll_compounds)
            ) or (
                is_topods_compound(cad_obj)
                and (is_mixed_compound(cad_obj) or unroll_compounds)
            ):
                ocp_obj = self.handle_compound(
                    cad_obj, obj_name, rgba_color, sketch_local, helper_scale, level
                )

            # Dicts
            elif isinstance(cad_obj, dict):
                ocp_obj = self.handle_dict(
                    cad_obj, obj_name, rgba_color, sketch_local, helper_scale, level
                )

            # =============================== Assemblies ================================ #

            elif is_build123d_assembly(cad_obj):
                ocp_obj = self.handle_build123d_assembly(
                    cad_obj,
                    obj_name,
                    rgba_color,
                    render_joints,
                    helper_scale,
                    level,
                )

            # =============================== Conversions =============================== #

            # OcpGroup
            elif isinstance(cad_obj, OcpGroup):
                ocp_obj = self.handle_ocp_group(cad_obj, obj_name)

            # OcpObject
            elif isinstance(cad_obj, OcpObject):
                ocp_obj = self.handle_ocp_obj(cad_obj, obj_name)

            # build123d ShapeList
            elif is_build123d_shapelist(cad_obj) or (
                is_cadquery(cad_obj) and not is_cadquery_empty_workplane(cad_obj)
            ):
                ocp_obj = self.handle_shape_list(
                    cad_obj, obj_name, rgba_color, show_parent, level
                )

            # build123d BuildPart, BuildSketch, BuildLine
            elif is_build123d(cad_obj):
                ocp_obj = self.handle_build123d_builder(
                    cad_obj, obj_name, rgba_color, sketch_local, render_joints, level
                )

            # TopoDS_Shape, TopoDS_Compound, TopoDS_Edge, TopoDS_Face, TopoDS_Shell,
            # TopoDS_Solid, TopoDS_Vertex, TopoDS_Wire,
            # build123d Shape, Compound, Edge, Face, Shell, Solid, Vertex
            # CadQuery shapes Solid, Shell, Face, Wire, Edge, Vertex
            elif (
                is_topods_shape(cad_obj)
                or is_build123d_shape(cad_obj)
                or is_cadquery_shape(cad_obj)
            ):
                ocp_obj = self.handle_shapes(
                    cad_obj, obj_name, render_joints, rgba_color, level
                )

            # Cadquery sketches
            elif is_cadquery_sketch(cad_obj):
                ocp_obj = self.handle_cadquery_sketch(
                    cad_obj, obj_name, rgba_color, level
                )

            # build123d Location/Plane or TopLoc_Location or gp_Pln
            elif (
                is_build123d_location(cad_obj)
                or is_toploc_location(cad_obj)
                or is_build123d_plane(cad_obj)
                or is_gp_plane(cad_obj)
                or is_cadquery_empty_workplane(cad_obj)
            ):
                ocp_obj = self.handle_locations_planes(
                    cad_obj, obj_name, rgba_color, helper_scale, sketch_local, level
                )

            # build123d Axis or gp_Ax1
            elif is_build123d_axis(cad_obj) or is_gp_axis(cad_obj):
                ocp_obj = self.handle_axis(
                    cad_obj, obj_name, rgba_color, helper_scale, sketch_local, level
                )

            else:
                print(
                    "Unknown object"
                    + ("" if obj_name is None else f" '{obj_name}'")
                    + f" of type {type(cad_obj)}"
                )
                continue

            if DEBUG:
                print(f"{'  '*level}=>", ocp_obj)

            if not (isinstance(ocp_obj, OcpGroup) and ocp_obj.length == 0):
                group.add(ocp_obj)

        group.make_unique_names()

        if group.length == 1 and isinstance(group.objects[0], OcpGroup):
            group = group.cleanup()

        return group


#
# Interface functions
#


class Progress:
    def update(self, mark):
        print(mark, end="", flush=True)


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
    progress=None,
):
    converter = OcpConverter(progress=Progress())
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
    )

    return ocp_group, converter.instances


def tessellate_group(group, instances, kwargs=None, progress=None, timeit=False):

    def get_bb_max(shapes, meshed_instances, loc=None, bbox=None):
        if loc is None:
            loc = identity_location()
        for shape in shapes["parts"]:
            new_loc = loc if shape["loc"] is None else loc * tq_to_loc(*shape["loc"])
            if shape.get("parts") is None:
                if shape["type"] == "shapes":
                    # Solids, shells and faces are instances and need to calculate
                    # the bounding box at the accumulated location
                    ind = shape["shape"]["ref"]
                    vertices = meshed_instances[ind]["vertices"]
                    bb = np_bbox(vertices, *loc_to_tq(new_loc))
                else:
                    # wires, edges, vertices already have a bounding box
                    bb = shape["bb"].to_dict()
                    # delete the BoundingBox object, it can't be serialized
                    del shape["bb"]

                if bbox is None:
                    bbox = bb
                else:
                    bbox = {
                        "xmin": min(bbox["xmin"], bb["xmin"]),
                        "xmax": max(bbox["xmax"], bb["xmax"]),
                        "ymin": min(bbox["ymin"], bb["ymin"]),
                        "ymax": max(bbox["ymax"], bb["ymax"]),
                        "zmin": min(bbox["zmin"], bb["zmin"]),
                        "zmax": max(bbox["zmax"], bb["zmax"]),
                    }
            else:
                bbox = get_bb_max(shape, meshed_instances, new_loc, bbox)
        return bbox

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
    render_normals = preset("render_normals", kwargs.get("render_normals"))

    max_accuracy = 0.0

    for i, instance in enumerate(instances):
        with Timer(timeit, f"instance({i})", "compute quality:", 2) as t:
            shape = instance["obj"]
            # A first rough estimate of the bounding box.
            # Will be too large, but is sufficient for computing the quality
            # location is not relevant here
            bb = bounding_box(shape, loc=None, optimal=False)
            quality = compute_quality(bb, deviation=deviation)
            t.info = str(bb)

            if quality > max_accuracy:
                max_accuracy = quality

        with Timer(
            timeit, f"instance({i}):{instance['name']}", "tessellate:     ", 2
        ) as t:
            mesh = tessellate(
                shape,
                instance["cache_id"],
                deviation=deviation,
                quality=quality,
                angular_tolerance=angular_tolerance,
                debug=timeit,
                compute_edges=render_edges,
                progress=None if timeit else progress,
                shape_id="n/a",
            )
            meshed_instances.append(mesh)
            t.info = (
                f"{{quality:{quality:.4f}, angular_tolerance:{angular_tolerance:.2f}}}"
            )

    shapes["normal_len"] = max_accuracy / deviation * 4 if render_normals else 0
    with Timer(timeit, "", "compute bounding box:", 2) as t:
        shapes["bb"] = get_bb_max(shapes, meshed_instances)
        t.info = str(BoundingBox(shapes["bb"]))

    return meshed_instances, shapes, states, mapping


#
# Obsolete functions
#


# TODO: change show.py to directly get bb from shapes
def combined_bb(shapes):
    return BoundingBox(shapes["bb"])


# TODO: change show.py to directly get normal_length from shapes
def get_normal_len(render_normals, shapes, deviation):
    return shapes["normal_len"]


# TODO: remove import from show.py
def conv():
    raise NotImplementedError("conv is not implemented any more")
