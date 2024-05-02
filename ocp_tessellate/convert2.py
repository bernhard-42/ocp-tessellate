# %%
from build123d import *
from ocp_vscode import *


from ocp_tessellate.ocp_utils import *
from ocp_tessellate.utils import make_unique
from ocp_tessellate.cad_objects2 import OcpGroup, OcpObj, CoordAxis, CoordSystem


DEBUG = True


def _debug(msg, name=None, prefix="debug:", eol="\n"):
    if name is None:
        print(f"{prefix} {msg}", end=eol)
    else:
        print(f"{prefix} {msg} ('{name}')", end=eol)


def class_name(obj):
    return obj.__class__.__name__


def type_name(obj):
    return class_name(obj).split("_")[1]


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
        "TopoDS_Shell": "face",
        "TopoDS_Solid": "solid",
        "TopoDS_Vertex": "vertex",
        "TopoDS_Wire": "edge",
    }
    return kinds.get(class_name(obj))


def get_color(obj, color=None, alpha=None):
    default_colors = {
        "TopoDS_Edge": "MediumOrchid",
        "TopoDS_Face": "Violet",
        "TopoDS_Shell": "Violet",
        "TopoDS_Solid": (232, 176, 36),
        "TopoDS_Vertex": "MediumOrchid",
        "TopoDS_Wire": "MediumOrchid",
    }
    if color is not None:
        col_a = Color(color)

    elif hasattr(obj, "color") and obj.color is not None:
        col_a = Color(obj.color)

    # else return default color
    col_a = Color(default_colors.get(class_name(unwrap(obj))))
    if alpha is not None:
        col_a.a = alpha

    return col_a


def unwrap(obj):
    if hasattr(obj, "wrapped"):
        return obj.wrapped
    elif isinstance(obj, (list, tuple)):
        return [x.wrapped for x in obj]
    return obj


# TODOs:
# - CadQuery objects
# - CadQuery assemblies


class OcpConverter:
    def __init__(self):
        self.instances = []
        self.ocp = None

    def get_instance(self, obj, kind, cache_id, name, rgba, progress=None):
        is_instance = False
        ocp_obj = None

        obj, loc = relocate(obj)

        # check if the same instance is already available
        for i, instance in enumerate(self.instances):
            if instance[0] == get_tshape(obj):
                # create a referential OCP_Part
                ocp_obj = OcpObj(
                    kind,
                    ref=i,
                    name=name,
                    loc=loc,
                    color=rgba,
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
            # and create a referential OCP_Part
            ocp_obj = OcpObj(
                kind,
                ref=ref,
                name=name,
                loc=loc,
                color=rgba,
                cache_id=cache_id,
            )

        return ocp_obj

    def unify(self, objs, name, color, alpha):
        if len(objs) == 1:
            ocp_obj = unwrap(objs[0])
            kind = get_kind(ocp_obj)
        else:
            objs = unwrap(objs)
            ocp_obj = make_compound(objs)
            kind = get_kind(objs[0])

        if kind in ("solid", "face"):
            return self.get_instance(
                ocp_obj, kind, id(ocp_obj), name, get_color(objs[0], color, alpha)
            )
        return OcpObj(
            kind, obj=ocp_obj, name=name, color=get_color(objs[0], color, alpha)
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
    ):
        group = OcpGroup()

        # ============================= Validate parameters ============================= #

        if names is None:
            names = [None] * len(cad_objs)
        else:
            names = make_unique(names)
            if len(names) != len(cad_objs):
                raise ValueError("Length of names does not match the number of objects")

        if colors is None:
            colors = [None] * len(cad_objs)
        if len(colors) != len(cad_objs):
            raise ValueError("Length of colors does not match the number of objects")

        if alphas is None:
            alphas = [None] * len(cad_objs)
        if len(alphas) != len(cad_objs):
            raise ValueError(
                "Length of alpha values does not match the number of objects"
            )

        if default_color is None:
            default_color = (
                get_default("default_color") if default_color is None else default_color
            )

        if instances is None:
            instances = []

        for cad_obj, obj_name, obj_color, obj_alpha in zip(
            cad_objs, names, colors, alphas
        ):

            # ================================= Prepare ================================= #

            # Convert build123d BuildPart, BuildSketch, BuildLine to topology object
            if is_build123d(cad_obj):
                if DEBUG:
                    _debug(
                        "Convert build123d builder object to topology object", obj_name
                    )
                obj = cad_obj._obj

            # build123d Plane
            elif is_build123d_plane(cad_obj) and hasattr(cad_obj, "location"):
                if DEBUG:
                    _debug("Map plane to its location", obj_name)
                obj = cad_obj.location

            # Use input object
            else:
                obj = cad_obj

            # ================================== Loops ================================== #

            # build123d ShapeList (needs to be handled before the generic tuple/list case)
            if is_build123d_shapelist(obj):
                if DEBUG:
                    _debug("build123d ShapeList", obj_name)
                objs = unwrap(obj)
                ocp_obj = OcpObj(
                    get_kind(objs[0]),
                    obj=make_compound(objs),
                    name=get_name(obj, obj_name, "ShapeList"),
                )

            # Generic iterables (tuple, list) or mixed type compounds
            elif isinstance(obj, (list, tuple)) or (
                is_compound(obj) and is_mixed_compound(obj)
            ):
                kind = "List" if isinstance(obj, (list, tuple)) else "Mixed Compound"
                if DEBUG:
                    _debug(kind, obj_name)
                name = get_name(obj, obj_name, kind.split(" ")[-1])
                ocp_obj = OcpGroup(name=name)
                for i, el in enumerate(obj):
                    result = self.to_ocp(
                        el,
                        names=[f"{name}[{i}]"],
                        sketch_local=sketch_local,
                        instances=instances,
                    )
                    ocp_obj.add(result)

                if ocp_obj.length > 1:
                    ocp_obj.make_unique_names()

            # Dicts
            elif isinstance(obj, dict):
                if DEBUG:
                    _debug("dict", obj_name)
                ocp_obj = OcpGroup(name=obj_name)
                for name, el in obj.items():
                    result = self.to_ocp(
                        el,
                        names=[name],
                        sketch_local=sketch_local,
                        instances=instances,
                    )
                    ocp_obj.add(result)

            # =============================== Assemblies ================================ #

            elif is_build123d_assembly(cad_obj):
                if DEBUG:
                    _debug("build123d Assembly", obj_name)
                name = get_name(obj, obj_name, "Assembly")
                ocp_obj = OcpGroup(name=name, loc=get_location(obj, as_none=False))

                for child in obj.children:
                    sub_obj = self.to_ocp(
                        child, helper_scale=helper_scale, instances=instances
                    )
                    if isinstance(sub_obj, OcpGroup):
                        if sub_obj.length == 1:
                            if sub_obj.objects[0].loc is None:
                                sub_obj.objects[0].loc = sub_obj.loc
                            else:
                                sub_obj.objects[0].loc = (
                                    sub_obj.loc * sub_obj.objects[0].loc
                                )
                            sub_obj = sub_obj.objects[0]

                    ocp_obj.add(sub_obj)

            # =============================== Conversions =============================== #

            # bild123d BuildPart().part
            elif is_build123d_part(obj):
                if DEBUG:
                    _debug("build123d part", obj_name)
                objs = obj.solids()
                name = get_name(obj, obj_name, "Solid" if len(objs) == 1 else "Solids")
                ocp_obj = self.unify(objs, name, obj_color, obj_alpha)

            # build123d BuildSketch().sketch
            elif is_build123d_sketch(obj):
                if DEBUG:
                    _debug("build123d Sketch", obj_name)
                objs = obj.faces()
                name = get_name(obj, obj_name, "Face" if len(objs) == 1 else "Faces")
                ocp_obj = self.unify(objs, name, obj_color, obj_alpha)

                if sketch_local:
                    ocp_obj.name = "sketch"
                    ocp_obj = OcpGroup([ocp_obj], name=name)
                    obj_local = cad_obj.sketch_local
                    objs = obj_local.faces()
                    ocp_obj.add(self.unify(objs, "sketch_local"), obj_color, obj_alpha)

            # build123d BuildLine().line
            elif is_build123d_curve(obj):
                if DEBUG:
                    _debug("build123d Curve", obj_name)
                objs = obj.edges()
                name = get_name(obj, obj_name, "Edge" if len(objs) == 1 else "Edges")
                ocp_obj = self.unify(objs, name, obj_color, obj_alpha)

            # build123d Shape, Compound, Edge, Face, Shell, Solid, Vertex, Wire
            elif is_build123d_shape(obj):
                if DEBUG:
                    _debug(f"build123d Shape", obj_name, eol="")
                objs = get_downcasted_shape(obj.wrapped)
                name = get_name(obj, obj_name, type_name(objs[0]))
                ocp_obj = self.unify(objs, name, obj_color, obj_alpha)
                if DEBUG:
                    _debug(class_name(ocp_obj.obj), prefix="")

            # TopoDS_Shape, TopoDS_Compound, TopoDS_Edge, TopoDS_Face, TopoDS_Shell,
            # TopoDS_Solid, TopoDS_Vertex, TopoDS_Wire
            elif is_topods_shape(obj):
                if DEBUG:
                    _debug("TopoDS_Shape", obj_name)
                objs = get_downcasted_shape(obj)
                name = get_name(obj, obj_name, type_name(objs[0]))
                ocp_obj = self.unify(objs, name, obj_color, obj_alpha)

            # build123d Location or TopLoc_Location
            elif is_build123d_location(obj) or is_toploc_location(obj):
                if DEBUG:
                    _debug("build123d Location or TopLoc_Location", obj_name)
                coord = get_location_coord(
                    obj.wrapped if is_build123d_location(obj) else obj
                )
                name = get_name(obj, obj_name, "Location")
                ocp_obj = CoordSystem(
                    name,
                    coord["origin"],
                    coord["x_dir"],
                    coord["z_dir"],
                    size=helper_scale,
                )

            # build123d Axis
            elif is_build123d_axis(obj):
                if DEBUG:
                    _debug("build123d Axis", obj_name)
                coord = get_axis_coord(obj.wrapped)
                name = get_name(obj, obj_name, "Axis")
                ocp_obj = CoordAxis(
                    name,
                    coord["origin"],
                    coord["z_dir"],
                    size=helper_scale,
                )

            else:
                raise ValueError(f"Unknown object type: {obj}")

            group.add(ocp_obj)

        if group.length == 1:
            return group.objs[0]

        group.make_unique_names()
        return group


# =================================================================================== #
# ======================================= END ======================================= #
# =================================================================================== #

b = Box(1, 2, 3)
b2 = Box(1, 1, 1) - Box(2, 2, 0.2)

with BuildPart() as bp:
    Box(1, 1, 1)

with BuildPart() as bp2:
    Box(1, 1, 1)
    Box(2, 2, 0.2, mode=Mode.SUBTRACT)

r = Rectangle(1, 2)
r2 = Rectangle(1, 2) - Rectangle(2, 0.2)

with BuildSketch() as bs:
    Rectangle(1, 1)

with BuildSketch() as bs2:
    Rectangle(1, 1)
    Rectangle(2, 0.2, mode=Mode.SUBTRACT)

l = Line((0, 0), (0, 1))
l2 = Line((0, 0), (0, 1)) - Line((0, 0.4), (0, 0.6))

with BuildLine() as bl:
    Line((0, 0), (0, 1))

with BuildLine() as bl2:
    Line((0, 0), (0, 1))
    Line((0, 0.4), (0, 0.6), mode=Mode.SUBTRACT)


# Create some objects to add to the compounds
s1 = Solid.make_box(1, 1, 1).move(Location((3, 3, 3)))
s1.label, s1.color = "box", "red"

s2 = Solid.make_cone(2, 1, 2).move(Location((-3, 3, 3)))
s2.label, s2.color = "cone", "green"

s3 = Solid.make_cylinder(1, 2).move(Location((-3, -3, 3)))
s3.label, s3.color = "cylinder", "blue"

s4 = Solid.make_sphere(2).move(Location((3, 3, -3)))
s4.label = "sphere"

s5 = Solid.make_torus(3, 1).move(Location((-3, 3, -3)))
s5.label, s5.color = "torus", "cyan"

c2 = Compound(label="c2", children=[s2, s3])
c3 = Compound(label="c3", children=[s4, s5])
c1 = Compound(label="c1", children=[s1, c2, c3])
show(b)
# %%
