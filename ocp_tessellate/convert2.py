# %%
from build123d import *
from ocp_vscode import *


from ocp_tessellate.ocp_utils import *
from ocp_tessellate.cad_objects2 import OcpGroup, OcpObj, CoordAxis, CoordSystem


DEBUG = True


def _debug(msg, name=None, prefix="debug:", eol="\n"):
    if name is None:
        print(f"{prefix} {msg}", end=eol)
    else:
        print(f"{prefix} {msg} ('{name}')", end=eol)


def get_instance(obj, cache_id, name, rgba, instances, progress):
    is_instance = False
    part = None

    obj, loc = relocate(obj)

    # check if the same instance is already available
    for i, ref in enumerate(instances):
        if ref[0] == get_tshape(obj):
            # create a referential OCP_Part
            part = OcpObj(
                {"ref": i},
                name,
                loc,
                rgba,
                cache_id,
            )
            # and stop the loop
            is_instance = True

            if progress is not None:
                progress.update("-")

            break

    if not is_instance:
        # Transform the new instance to OCP
        part = conv(obj, name, rgba[:3], rgba[3])
        if not isinstance(part, OCP_PartGroup):
            # append the new instance
            instances.append((get_tshape(obj), part.shape[0]))
            # and create a referential OCP_Part
            part = OCP_Part(
                {"ref": len(instances) - 1},
                cache_id,
                part.name,
                rgba,
            )

    part.loc = loc
    part.loc_t = loc_to_tq(loc)

    return part


def class_name(obj):
    return obj.__class__.__name__


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


def unwrap(obj):
    if hasattr(obj, "wrapped"):
        return obj.wrapped
    elif isinstance(obj, (list, tuple)):
        return [x.wrapped for x in obj]
    return obj


def unify(objs, obj_name):
    if len(objs) == 1:
        ocp_obj = unwrap(objs[0])
        kind = get_kind(ocp_obj)
    else:
        objs = unwrap(objs)
        ocp_obj = make_compound(objs)
        kind = get_kind(objs[0])

    return OcpObj(ocp_obj, kind, name=obj_name)


# TODOs:
# - build123d assemblies
# - instance handling
# - extend and cut obj_names
# - CadQuery objects
# - CadQuery assemblies


def to_ocp(*cad_objs, names=None, helper_scale=1, sketch_local=False, instances=None):
    group = OcpGroup()

    if names is None:
        names = [None] * len(cad_objs)

    if instances is None:
        instances = []

    for cad_obj, obj_name in zip(cad_objs, names):

        # ================================= Prepare =================================

        # build123d BuildPart, BuildSketch, BuildLine
        if is_build123d(cad_obj):
            if DEBUG:
                _debug("Convert build123d builder object to topology object", obj_name)
            obj = cad_obj._obj

        # build123d Plane
        elif is_build123d_plane(cad_obj) and hasattr(cad_obj, "location"):
            if DEBUG:
                _debug("Map plane to its location", obj_name)
            obj = cad_obj.location

        # Use input object
        else:
            obj = cad_obj

        # ================================= Loops =================================

        # build123d ShapeList (needs to be handled before the generic tuple or list case)
        if is_build123d_shapelist(obj):
            if DEBUG:
                _debug("build123d ShapeList", obj_name)
            objs = unwrap(obj)
            ocp_obj = OcpObj(
                make_compound(objs),
                get_kind(objs[0]),
                name=get_name(obj, obj_name, "ShapeList"),
            )

        # Generic iterables (tuple, list) or mixed type compounds
        elif isinstance(obj, (list, tuple)) or (
            is_compound(obj) and is_mixed_compound(obj)
        ):
            kind = "List" if isinstance(obj, (list, tuple)) else "Mixed Compound"
            if DEBUG:
                _debug(kind, obj_name)
            obj_name = get_name(obj, obj_name, kind.split(" ")[-1])
            ocp_obj = OcpGroup(name=obj_name)
            for i, el in enumerate(obj):
                result = to_ocp(
                    el,
                    names=[f"{obj_name}[{i}]"],
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
                result = to_ocp(
                    el,
                    names=[name],
                    sketch_local=sketch_local,
                    instances=instances,
                )
                ocp_obj.add(result)

        # ================================= Conversions =================================

        # bild123d BuildPart().part
        elif is_build123d_part(obj):
            if DEBUG:
                _debug("build123d part", obj_name)
            objs = obj.solids()
            obj_name = get_name(obj, obj_name, "Solid" if len(objs) == 1 else "Solids")
            ocp_obj = unify(objs, obj_name)

        # build123d BuildSketch().sketch
        elif is_build123d_sketch(obj):
            if DEBUG:
                _debug("build123d Sketch", obj_name)
            objs = obj.faces()
            obj_name = get_name(obj, obj_name, "Face" if len(objs) == 1 else "Faces")
            ocp_obj = unify(objs, obj_name)

            if sketch_local:
                ocp_obj = OcpGroup([ocp_obj], name=obj_name)
                obj_local = cad_obj.sketch_local
                objs = obj_local.faces()
                obj_name = f"{obj_name}_local"
                ocp_obj.add(unify(objs, obj_name))

        # build123d BuildLine().line
        elif is_build123d_curve(obj):
            if DEBUG:
                _debug("build123d Curve", obj_name)
            objs = obj.edges()
            obj_name = get_name(obj, obj_name, "Edge" if len(objs) == 1 else "Edges")
            ocp_obj = unify(objs, obj_name)

        # build123d Shape, Compound, Edge, Face, Shell, Solid, Vertex, Wire
        elif is_build123d_shape(obj):
            if DEBUG:
                _debug(f"build123d Shape", obj_name, eol="")
            objs = get_downcasted_shape(obj.wrapped)
            obj_name = get_name(obj, obj_name, class_name(obj))
            ocp_obj = unify(objs, obj_name)
            if DEBUG:
                _debug(class_name(ocp_obj.obj), prefix="")

        # build123d Location or TopLoc_Location
        elif is_build123d_location(obj) or is_toploc_location(obj):
            if DEBUG:
                _debug("build123d Location or TopLoc_Location", obj_name)
            coord = get_location_coord(
                obj.wrapped if is_build123d_location(obj) else obj
            )
            obj_name = get_name(obj, obj_name, "Location")
            ocp_obj = CoordSystem(
                obj_name,
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
            obj_name = get_name(obj, obj_name, "Axis")
            ocp_obj = CoordAxis(
                obj_name,
                coord["origin"],
                coord["z_dir"],
                size=helper_scale,
            )

        # TopoDS_Compound (needs to be handled before the TopoDS_Shape case
        elif is_topods_compound(obj):
            if DEBUG:
                _debug("TopoDS_Compound", obj_name)
            objs = [obj]
            obj_name = get_name(obj, obj_name, "Compound")
            ocp_obj = unify(objs, obj_name)

        # TopoDS_Shape, TopoDS_Edge, TopoDS_Face, TopoDS_Shell, TopoDS_Solid, TopoDS_Vertex, TopoDS_Wire
        # TODO TopoDS_CompSolid?
        elif is_topods_shape(obj):
            if DEBUG:
                _debug("TopoDS_Shape", obj_name)
            objs = get_downcasted_shape(obj)
            name = get_name(obj, obj_name, class_name(objs[0]))
            ocp_obj = unify(objs, obj_name)

        else:
            raise ValueError(f"Unknown object type: {obj}")

        group.add(ocp_obj)

    if group.length == 1:
        return group.objs[0]

    group.make_unique_names()
    return group


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # END # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
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


to_ocp([el for el in b.edges()], names=["a"])
# %%


# BuildPart   =part=>   Part      =solids()=>   [Solid, ...]   =wrapped=> [TopoDS_Solid, ...]
#                       Part      =shells()=>   [Shell, ...]   =wrapped=> [TopoDS_Shell, ...]
# BuildSketch =sketch=> Sketch    =faces()=>    [Face, ...]    =wrapped=> [TopoDS_Face, ...]
# BuildLine   =line=>   Curve     =edges()=>    [Edge, ...]    =wrapped=> [TopoDS_Edge, ...]
#                       Curve     =wires()=>    [Wire, ...]    =wrapped=> [TopoDS_Wire, ...]
#                       Curve     =vertices()=> [Vertex, ...]  =wrapped=> [TopoDS_Vertex, ...]
#                       Location                               =wrapped=> TopLoc_Location
#                       Plane     =location()=> Location       =wrapped=> TopLoc_Location


# Shape
#     Compound
#     Edge
#     Face
#     Shell
#     Solid
#     Vertex
#     Wire

# TopoDS_Shape
#     TopoDS_CompSolid
#     TopoDS_Compound
#     TopoDS_Edge
#     TopoDS_Face
#     TopoDS_Shell
#     TopoDS_Solid
#     TopoDS_Vertex
#     TopoDS_Wire

# %%
