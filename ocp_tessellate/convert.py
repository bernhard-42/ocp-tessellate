import enum
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Tuple, Union

from ocp_tessellate.cad_objects import (
    CoordAxis,
    CoordSystem,
    OcpGroup,
    OcpObject,
    OcpWrapper,
    OcpInstancesGroup,
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

DEBUG = False

# Alias for every object containing a "wrapped" attribute of type TopoDS_Shape
Wrapped = Any
# Alias for build123d and CadQuery compounds
Compound = Wrapped
# Alias for CadQuery objects
Workplane = Any
# Alias for CadQuery sketches
CadquerySketch = Any
# Alias for CadQuery assemblies
Assembly = Any
# Alias for build123d shape lists
ShapeList = List[Wrapped]
# Alias for build123d locaiont lists
LocationList = List[Wrapped]
# Alias for build123d Builder Objects
BuilderObject = Any
# Alias for build123d or Cadquery Locations or Planes
LocationLike = Wrapped
# Alias for build123d Axis
Axis = Wrapped
# can be build123d or CadQuery shapes
ShapeLike = Union[TopoDS_Shape, Wrapped]
CompoundLike = Union[TopoDS_Compound, Wrapped]

ColorLike = Union[str, List[float], Color]


class Progress:
    def update(self, mark):
        print(mark, end="", flush=True)


def _debug(level, msg, name=None, prefix="debug:", end="\n"):
    if DEBUG:
        prefix = "  " * level + prefix
        suffix = f" ('{name}')" if name is not None else ""
        print(f"{prefix} {msg} {suffix}", end=end, flush=True)


def get_name(obj: TopoDS_Shape, name: Union[str, None], default: str) -> str:
    """
    Get the name of the object. If the name is None, use the default name.
    If the object has a name or label attribute, use that.

    @param obj: The object of type TopoDS_Shape or a subclass
    @param name: The name of the object
    @param default: The default name

    @return: The derived name of the object
    """
    if name is None:
        if hasattr(obj, "name") and obj.name is not None and obj.name != "":
            name = obj.name
        elif hasattr(obj, "label") and obj.label is not None and obj.label != "":
            name = obj.label
        else:
            name = default
    return name


def get_type(obj: TopoDS_Shape) -> str:
    """
    Get the type of the object based on its TopoDS type

    @param obj: The object of type TopoDS_Shape or a subclass

    @return: The type of the object
    """
    kinds = {
        "TopoDS_Vertex": "Vertex",
        "TopoDS_Edge": "Edge",
        "TopoDS_Wire": "Wire",
        "TopoDS_Face": "Face",
        "TopoDS_Shell": "Shell",
        "TopoDS_Solid": "Solid",
        "TopoDS_CompSolid": "Solid",
    }
    typ = kinds.get(class_name(obj))
    if typ is None:
        raise ValueError(f"Unknown type: {type(obj)}")
    return typ


def get_kind(typ: str) -> str:
    """
    Get the kind of the object based on its type.
    The kinds "edge", "face", "solid", "vertex" are used for selecting the right
    tessellation algorithm

    @param typ: The type of the object (see get_type)

    @return: The kind of the object
    """
    kinds = {
        "Vertex": "vertex",
        "Edge": "edge",
        "Wire": "edge",
        "Face": "face",
        "Shell": "face",
        "Solid": "solid",
        "CompSolid": "solid",
    }
    kind = kinds.get(typ)
    if kind is None:
        raise ValueError(f"Unknown type: {typ}")
    return kind


def unwrap(
    obj: Union[TopoDS_Shape, List[TopoDS_Shape], ShapeLike, List[ShapeLike]],
) -> Union[TopoDS_Shape, List[TopoDS_Shape]]:
    """
    Unwrap the object or objects in a list  if it is wrapped.

    @param obj: The object or list of objects

    @return: The unwrapped object or list of objects
    """
    if hasattr(obj, "wrapped"):
        return obj.wrapped
    elif isinstance(obj, (list, tuple)):
        result = []
        for x in obj:
            if hasattr(x, "wrapped"):
                if is_topods_compound(x.wrapped):
                    result.extend(list_topods_compound(x.wrapped))
                elif is_vector(x):
                    result.append(vertex((x.X, x.Y, x.Z)))
                else:
                    result.append(x.wrapped)
            else:
                result.append(x)

        return result
    return obj


def create_cache_id(obj: TopoDS_Shape) -> str:
    """
    The TopoDS_Shape objects are serialized and hashed to create a unique id.
    The current approach is to use the sha256 hash of the serialized object.

    @param obj: The object of type TopoDS_Shape or a subclass

    @return: The unique id of the object
    """
    sha = sha256()
    objs = [obj] if not isinstance(obj, (tuple, list)) else obj
    for o in objs:
        sha.update(serialize(o.wrapped if is_wrapped(o) else o))

    return sha.hexdigest()


class OcpConverter:
    """The class to filter obejcts and convert them to OcpObject and OcpGroup hierarchies."""

    def __init__(self, progress: Union[Progress, None] = None):
        """The initializer of the OcpConverter.
        @param progress: The progress class to provide updates during the conversion
        """
        self.instances: List[TopoDS_Shape] = []
        self.ocp = None
        self.progress = progress
        self.default_color = get_default("default_color")

    # ============================== Create instances =============================== #

    def get_instance(
        self, obj: TopoDS_Shape, cache_id: str, name: str
    ) -> Tuple[int, TopLoc_Location]:
        """
        Identify if the object is already available in the instances list based on
        comparing their TShapes.
        If not, create a new instance and add it to the list.

        @param obj: The object of type TopoDS_Shape or a subclass
        @param cache_id: The unique id of the object
        @param name: The name of the object

        @return: The reference to the object in the instances list and the location
        """
        ref = None

        # Create the relocated object as a copy
        loc = obj.Location()  # Get location
        obj2 = downcast(obj.Moved(loc.Inverted()))

        # check if the same instance is already available
        for i, instance in enumerate(self.instances):
            if instance["obj"].TShape() == obj2.TShape():
                ref = i

                if self.progress is not None:
                    self.progress.update("-")

                break

        if ref is None:
            # append the new instance
            ref = len(self.instances)
            self.instances.append({"obj": obj2, "cache_id": cache_id, "name": name})

        return ref, loc

    def unify(
        self,
        objs: Union[TopoDS_Shape, List[TopoDS_Shape]],
        kind: str,
        name: str,
        color: Union[ColorLike, Tuple[ColorLike, ColorLike, ColorLike], None],
        alpha: float,
    ) -> OcpObject:
        """
        Unify the objects in a list to a single TopoDS_Shape or a TopoDS_Compound for
        solids, shells and faces or to a list of edges or vertices.

        @param objs: The list of objects
        @param kind: The kind of the objects
        @param name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the object

        @return: The unified OcpObject
        """
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
            alpha,
            kind=kind,
        )

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

    def get_color_for_object(
        self,
        obj: TopoDS_Shape,
        color: Union[ColorLike, Tuple[ColorLike, ColorLike, ColorLike], None] = None,
        alpha: Union[float, None] = None,
        kind: Union[str, None] = None,
    ) -> Union[Color, Tuple[ColorLike, ColorLike, ColorLike]]:
        """
        Get the color of the object based on the object type and the default colors.

        @param obj: The object of type TopoDS_Shape or a subclass
        @param color: The color of the object
        @param alpha: The alpha value of the object
        @param kind: The kind of the object

        @return: The color of the object
        """
        default_colors = {
            # ocp types
            "TopoDS_Edge": THICK_EDGE_COLOR,
            "TopoDS_Face": FACE_COLOR,
            "TopoDS_Shell": FACE_COLOR,
            "TopoDS_Solid": self.default_color,
            "TopoDS_CompSolid": self.default_color,
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
            if isinstance(color, tuple) and not isinstance(color[0], (int, float)):
                # return triple color array for CoordSystems
                return (Color(color[0]), Color(color[1]), Color(color[2]))
            else:
                col_a = Color(color)

        elif hasattr(obj, "color") and obj.color is not None:
            col_a = Color(obj.color)

        # elif color is None and is_topods_compound(obj) and kind is not None:
        elif color is None and kind is not None:
            col_a = Color(default_colors[kind])

        # else return default color
        else:
            col_a = Color(default_colors.get(class_name(unwrap(obj))))

        # Try the onjects alpha first
        if hasattr(obj, "alpha") and obj.alpha is not None:
            col_a.a = obj.alpha

        # A given alpha overwrites the objects alpha
        if alpha is not None:
            col_a.a = alpha

        return col_a

    # ============================= Iterate Containers ============================== #

    def _unroll_iterable(
        self,
        objs: Iterable[
            Tuple[
                Union[str, None],
                Union[ShapeLike, List[ShapeLike], Dict[str, ShapeLike]],
            ]
        ],
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        sketch_local: bool,
        helper_scale: float,
        level: int,
    ) -> OcpGroup:
        """
        Unroll the objects in an iterable and convert them to OcpObject and OcpGroup hierarchies.

        @param objs: The list of objects
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param sketch_local: The flag to render the sketch local
        @param helper_scale: The scale of the helper objects
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        ocp_obj: OcpGroup = OcpGroup(name=obj_name)
        for name, obj in objs:

            result = self.to_ocp(
                obj,
                names=[name],
                colors=[color],
                alphas=[alpha],
                sketch_local=sketch_local,
                helper_scale=helper_scale,
                level=level + 1,
            )
            if result.length > 0:
                ocp_obj.add(result.cleanup())

        return ocp_obj.make_unique_names()

    def handle_list_tuple(
        self,
        cad_obj: Union[ShapeLike, List[ShapeLike]],
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        sketch_local: bool,
        helper_scale: float,
        level: int,
    ) -> OcpGroup:
        """
        Handle lists and tuples of objects.

        @param cad_obj: The list or tuple of objects
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param sketch_local: The flag to render the sketch_local
        @param helper_scale: The scale of the helper objects
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        _debug(level, "handle_list_tuple", obj_name)
        return self._unroll_iterable(
            zip([None] * len(cad_obj), cad_obj),
            get_name(cad_obj, obj_name, "List"),
            color,
            alpha,
            sketch_local,
            helper_scale,
            level,
        )

    def handle_dict(
        self,
        cad_obj: Dict[str, ShapeLike],
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        sketch_local: bool,
        helper_scale: float,
        level: int,
    ) -> OcpGroup:
        """
        Handle dictionaries of objects.

        @param cad_obj: The dictionary of objects
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param sketch_local: The flag to render the sketch_local
        @param helper_scale: The scale of the helper objects

        @return: The OcpGroup hierarchy
        """
        _debug(level, "handle_dict", obj_name)

        return self._unroll_iterable(
            cad_obj.items(),
            get_name(cad_obj, obj_name, "Dict"),
            color,
            alpha,
            sketch_local,
            helper_scale,
            level,
        )

    def handle_compound(
        self,
        cad_obj: CompoundLike,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        sketch_local: bool,
        helper_scale: float,
        level: int,
    ) -> OcpGroup:
        """
        Handle compounds and topods_compounds.

        @param cad_obj: The compound or topods_compound
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param sketch_local: The flag to render the sketch_local
        @param helper_scale: The scale of the helper objects
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        _debug(level, f"handle_compound", obj_name)

        if is_compound(cad_obj) or is_compsolid(cad_obj):
            cad_objs = list(list_topods_compound(cad_obj.wrapped))
        elif is_topods_compound(cad_obj) or is_topods_compsolid(cad_obj):
            cad_objs = list(list_topods_compound(cad_obj))

        default_name = "Compound"
        if is_compsolid(cad_obj) or is_topods_compsolid(cad_obj):
            default_name = "CompSolid"

        return self._unroll_iterable(
            zip([None] * len(cad_objs), cad_objs),
            get_name(cad_obj, obj_name, default_name),
            color,
            alpha,
            sketch_local,
            helper_scale,
            level,
        )

    # ================================= Assemblies ================================== #

    def handle_build123d_assembly(
        self,
        cad_obj: Compound,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        render_joints: bool,
        helper_scale: float,
        level: int,
    ) -> OcpGroup:
        """
        Handle build123d assemblies.

        @param cad_obj: The build123d assembly (Compound with children)
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param render_joints: The flag to render the joints
        @param helper_scale: The scale of the helper objects
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        _debug(level, "handle_build123d_assembly", obj_name)

        name = get_name(cad_obj, obj_name, "Assembly")
        location = get_location(cad_obj, as_none=False)
        ocp_obj = OcpGroup(name=name, loc=location)

        for child in cad_obj.children:
            sub_obj = self.to_ocp(
                child,
                names=[None if child.label == "" else child.label],
                colors=[child.color if color is None else color],
                alphas=[alpha],
                helper_scale=helper_scale,
                render_joints=render_joints,
                level=level + 1,
            )
            if sub_obj.length == 1 and len(child.children) == 0:
                ocp_obj.add(sub_obj.objects[0])
            else:
                ocp_obj.add(sub_obj)

        if render_joints and hasattr(cad_obj, "joints") and len(cad_obj.joints) > 0:
            joints = self.to_ocp(
                *[j.symbol for j in cad_obj.joints.values()],
                names=list(cad_obj.joints.keys()),
                level=level + 1,
            )
            joints.name = f"{name}_joints"
            # an Assembly has the location already in the group, hence relocate
            # the joint to compensate for the location
            # (remember: joint.location = joint.parent.location * joint.relative_location)
            if joints.loc is None:
                joints.loc = location.Inverted()
            else:
                joints.loc = location.Inverted() * joints.loc
            ocp_obj.add(joints)

        return ocp_obj.make_unique_names()

    def handle_cadquery_assembly(
        self,
        cad_obj: Assembly,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        render_mates: bool,
        helper_scale: float,
        level: int,
    ) -> OcpGroup:
        """
        Handle cadquery assemblies.

        @param cad_obj: The cadquery assembly
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param render_mates: The flag to render the mates
        @param helper_scale: The scale of the helper objects
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        _debug(level, "handle_cadquery_assembly", obj_name)
        name = get_name(cad_obj, obj_name, "Assembly")

        ocp_obj = OcpGroup(name=name, loc=get_location(cad_obj, as_none=False))
        if cad_obj.obj is not None:
            sub_obj = self.to_ocp(
                cad_obj.obj,
                names=[cad_obj.name],
                colors=[cad_obj.color if color is None else color],
                alphas=alpha,
                helper_scale=helper_scale,
                render_mates=render_mates,
                level=level + 1,
            )
            ocp_obj.add(sub_obj.objects[0])

        if render_mates:
            top = cad_obj
            while top.parent is not None:
                top = top.parent
            if hasattr(top, "mates") and top.mates is not None:
                mates = OcpGroup(
                    [
                        CoordSystem(
                            name,
                            get_tuple(mate_def.mate.origin),
                            get_tuple(mate_def.mate.x_dir),
                            get_tuple(mate_def.mate.z_dir),
                            helper_scale,
                        ).to_ocp()
                        for name, mate_def in top.mates.items()
                        if mate_def.assembly == cad_obj
                    ],
                    name=f"{cad_obj.name}_mates",
                    loc=identity_location(),  # mates inherit the parent location, so actually add a no-op
                )
                if len(mates.objects) > 0:
                    ocp_obj.add(mates)

        for child in cad_obj.children:
            sub_obj = self.to_ocp(
                child,
                names=[child.name],
                helper_scale=helper_scale,
                render_mates=render_mates,
                level=level + 1,
            )
            ocp_obj.add(sub_obj)

        return ocp_obj

    # ================================= Conversions ================================= #

    def handle_parent(
        self,
        cad_obj: Union[ShapeLike, Compound, Workplane, List],
        level: int,
    ) -> List[OcpObject]:
        """
        Handle the parent of an objects.

        @param cad_obj: The object or objects
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        parent = None
        if hasattr(cad_obj, "parent") and cad_obj.parent is not None:
            parent = cad_obj.parent
            topo = False
        elif hasattr(cad_obj, "topo_parent") and cad_obj.topo_parent is not None:
            parent = cad_obj.topo_parent
            topo = True
        elif (
            isinstance(cad_obj, List)
            and len(cad_obj) > 0
            and hasattr(cad_obj[0], "topo_parent")
        ):
            parent = [c.topo_parent for c in cad_obj]
            topo = True

        ind = 0
        parents: List[OcpObject] = []
        while parent is not None:
            pname = "_parent" if ind == 0 else f"_parent({ind})"
            p = self.to_ocp(
                list(set(parent)) if isinstance(parent, list) else parent,
                names=[pname],
                colors=None,
                level=level + 1,
            )
            for o in p.objects:
                if o.kind == "solid":
                    o.state_faces = 0
                elif o.kind == "face":
                    o.state_edges = 0
            parents.insert(0, p)
            if isinstance(parent, list):
                parent = list(
                    set(
                        [
                            c.topo_parent
                            for c in parent
                            if hasattr(c, "topo_parent") and c.topo_parent is not None
                        ]
                    )
                )
                if len(parent) == 0:
                    parent = None
            else:
                parent = parent.topo_parent if topo else None
            ind -= 1

        return parents

    def handle_location_list(
        self,
        cad_obj: LocationList,
        obj_name: Union[str, None],
        helper_scale: float,
        level: int,
    ) -> OcpGroup:
        """
        Handle build123d location lists.

        @param cad_obj: The build123d location list
        @param obj_name: The name of the object
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        _debug(level, "handle_location_list (build123d LocationList)", obj_name)
        group = OcpGroup(name=get_name(cad_obj, obj_name, "LocationList"))
        for loc in cad_obj:
            group.add(
                self.handle_locations_planes(
                    loc, "Location", helper_scale, level=level + 1
                )
            )
        group.make_unique_names()
        return group

    def _handle_list(self, cad_obj, name, obj_name, color, alpha):
        """internal method"""
        # convert wires to edges
        if len(cad_obj) > 0 and is_wire(cad_obj[0]):
            objs = []
            for obj in cad_obj:
                if isinstance(obj.edges(), (list, tuple)):
                    objs.extend([e.wrapped for e in obj.edges()])
                else:
                    # special case cadquery wire
                    if is_topods_edge(obj.edges().wrapped):
                        objs.append(obj.edges().wrapped)
                    elif is_topods_compound(obj.edges().wrapped):
                        objs.extend([e.wrapped for e in list(obj.edges())])
                    else:
                        raise ValueError(f"Unknown edge type: {obj.edges()}")
            typ = "Wire"

        # unwrap everything else
        else:
            objs = unwrap(cad_obj)
            typ = get_type(objs[0])

        kind = get_kind(typ)
        rgba = self.get_color_for_object(objs[0], color)
        if alpha is not None:
            rgba.a = alpha
        return self.unify(
            objs,
            kind=kind,
            name=get_name(cad_obj, obj_name, f"{name}({typ})"),
            color=rgba,
            alpha=alpha,
        )

    def handle_workplane(
        self,
        cad_obj: Workplane,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        show_parent: bool,
        level: int,
    ) -> Union[OcpGroup, OcpObject]:
        """
        Handle cadquery Workplane.

        @param cad_obj: The cadquery Workplane
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param show_parent: The flag to show the parent
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        parent_obj = cad_obj

        _debug(level, "handle_workplane (cadquery Workplane)", obj_name)
        name = "Workplane"

        # Resolve cadquery Workplane
        cad_obj = cad_obj.vals()  # type: ignore [union-attr]
        if len(cad_obj) > 0:
            if is_compound(cad_obj[0]):
                cad_obj = flatten([list(obj) for obj in cad_obj])
            elif is_cadquery_sketch(cad_obj[0]):
                return self.to_ocp(cad_obj).cleanup()

        ocp_obj = self._handle_list(cad_obj, name, obj_name, color, alpha)

        if show_parent:
            parents = self.handle_parent(parent_obj, level)
            parents = [parents[0].objects[0]]

            return OcpGroup(parents + [ocp_obj], name=ocp_obj.name)
        else:
            return ocp_obj

    def handle_shape_list(
        self,
        cad_obj: ShapeList,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        show_parent: bool,
        level: int,
    ) -> Union[OcpGroup, OcpObject]:
        """
        Handle build123d shape lists.

        @param cad_obj: The build123d ShapeList
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param show_parent: The flag to show the parent
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        parent_obj = cad_obj

        _debug(level, "handle_shapelist (build123d ShapeList)", obj_name)
        name = "ShapeList"

        ocp_obj = self._handle_list(cad_obj, name, obj_name, color, alpha)

        if show_parent:
            parents = self.handle_parent(parent_obj, level)
            return OcpGroup(parents + [ocp_obj], name=ocp_obj.name)
        else:
            return ocp_obj

    def handle_shapes(
        self,
        cad_obj: Union[ShapeLike, Compound],
        obj_name: Union[str, None],
        render_joints: bool,
        show_parent: bool,
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
    ) -> Union[OcpGroup, OcpObject]:
        """
        Handle build123d or Cadquery shapes.

        @param cad_obj: The shape or shapes
        @param obj_name: The name of the object
        @param render_joints: The flag to render the joints
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
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

        color = self.get_color_for_object(cad_obj, color, alpha, kind=get_kind(typ))

        ocp_obj = self.unify(
            [obj] if edges is None else edges,
            kind=get_kind(typ),
            name=name,
            color=color,
            alpha=alpha,
        )

        if render_joints and hasattr(cad_obj, "joints") and len(cad_obj.joints) > 0:
            joints = self.to_ocp(
                *[j.symbol for j in cad_obj.joints.values()],
                names=list(cad_obj.joints.keys()),
                level=level + 1,
            )
            joints.name = "joints"
            ocp_obj.name = "shape"
            return OcpGroup([ocp_obj, joints], name=name)

        if show_parent and (
            (hasattr(cad_obj, "parent") and cad_obj.parent is not None)
            or (hasattr(cad_obj, "topo_parent") and cad_obj.topo_parent is not None)
        ):
            parents = self.handle_parent(
                cad_obj if isinstance(cad_obj, (list, tuple)) else [cad_obj], level
            )
            return OcpGroup(parents + [ocp_obj], name=ocp_obj.name)

        return ocp_obj

    def handle_build123d_builder(
        self,
        cad_obj: BuilderObject,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        sketch_local: bool,
        render_joints: bool,
        level: int,
    ) -> OcpGroup:
        """
        Handle build123d Builder objects.

        @param cad_obj: The build123d Builder object
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param sketch_local: The flag to render the sketch_local
        @param render_joints: The flag to render the joints
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
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
            colors=[
                cad_obj.color if color is None and hasattr(cad_obj, "color") else color
            ],
            alphas=[
                cad_obj.alpha if alpha is None and hasattr(cad_obj, "alpha") else alpha
            ],
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
                colors=[color],
                render_joints=render_joints,
                level=level + 1,
            ).objects[0]
            ocp_obj_local.color.a = 0.2
            ocp_obj.add(ocp_obj_local)

        return ocp_obj.cleanup()

    def handle_cadquery_sketch(
        self,
        cad_obj: CadquerySketch,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
    ) -> OcpGroup:
        """
        Handle cadquery sketches.

        @param cad_obj: The cadquery sketch
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        _debug(level, "cadquery Sketch", obj_name)

        if not list(cad_obj._faces):  # empty compound
            cad_obj._faces = []

        if not isinstance(cad_obj._faces, (list, tuple)):
            cad_obj._faces = [cad_obj._faces]

        cad_objs = []
        names: List[str | None] = []
        bb = BoundingBox()
        size = 5
        for typ, objs, calc_bb in [
            ("Face", list(cad_obj._faces), True),
            ("Edge", list(cad_obj._edges), True),
            (
                "Selection",
                [] if cad_obj._selection is None else list(cad_obj._selection),
                False,
            ),
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
                    bb.update(BoundingBox(compound))

        size = max(bb.xsize, bb.ysize, bb.zsize, 0.1)

        name = get_name(cad_obj, obj_name, "Sketch")
        result = self.to_ocp(
            *cad_objs,
            names=names,
            colors=[color] * len(cad_objs),
            alphas=[alpha] * len(cad_objs),
            level=level,
            helper_scale=size / 20,
        )
        result.name = name
        return result

    def handle_locations_planes(
        self,
        cad_obj: LocationLike,
        obj_name: Union[str, None],
        helper_scale: float,
        level: int,
    ) -> OcpObject:
        """
        Handle locations and planes.

        @param cad_obj: The location or plane
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param helper_scale: The scale of the helper objects
        @param sketch_local: The flag to render the sketch_local
        @param level: The level of the hierarchy

        @return: The OcpObject
        """
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
        ).to_ocp()
        return ocp_obj

    def handle_axis(
        self,
        cad_obj: Axis,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        helper_scale: float,
        level: int,
    ) -> OcpObject:
        """
        Handle build123d Axis.

        @param cad_obj: The build123d Axis
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param helper_scale: The scale of the helper objects
        @param sketch_local: The flag to render the sketch_local
        @param level: The level of the hierarchy

        @return: The OcpObject
        """
        _debug(level, "build123d Axis", obj_name)

        if is_wrapped(cad_obj):
            cad_obj = cad_obj.wrapped
        coord = get_axis_coord(cad_obj)
        name = get_name(cad_obj, obj_name, "Axis")
        ocp_obj = CoordAxis(
            name,
            coord["origin"],
            coord["z_dir"],
            color,
            size=helper_scale,
        ).to_ocp()
        return ocp_obj

    def handle_ocp_wrapper(
        self, cad_obj: OcpWrapper, obj_name: Union[str, None]
    ) -> OcpObject:
        """
        Handle OcpWrapper objects.

        @param cad_obj: The OcpWrapper object
        @param obj_name: The name of the object

        @return: The OcpObject
        """
        name = get_name(cad_obj, obj_name, "ImageFace")
        ocp_obj = cad_obj.to_ocp()
        ocp_obj.name = name
        if ocp_obj.kind in ["solid", "imageface", "face", "shell"]:
            ref, loc = self.get_instance(
                cad_obj.objs[0], create_cache_id(cad_obj.objs[0]), name
            )
            ocp_obj.loc = cad_obj.loc * loc
            ocp_obj.ref = ref
            ocp_obj.obj = None
        return ocp_obj

    # ================================ Empty objects ================================ #

    def handle_empty_iterables(
        self, obj_name: Union[Wrapped, Compound, List], level: int
    ) -> OcpObject:
        """
        Handle empty objects.

        @param obj_name: The name of the object
        @param level: The level of the hierarchy

        @return: The OcpObject
        """
        _debug(level, "Empty object")
        name = "Object" if obj_name is None else obj_name
        return OcpObject(
            "vertex",
            obj=vertex((0, 0, 0)),
            name=f"{name} (empty)",
            color=Color((0, 0, 0, 0.01)),
            width=0.1,
        )

    # ======================== Iterate and identify objects ========================= #

    def to_ocp(
        self,
        *cad_objs: Union[
            ShapeLike, Compound, Workplane, List, Dict, Assembly, OcpWrapper
        ],
        names: Union[List[Union[str, None]], None] = None,
        colors: Union[List[Union[ColorLike, None]], None] = None,
        alphas: Union[List[Union[float, None]], None] = None,
        loc: LocationLike = None,
        render_mates: bool = False,
        render_joints: bool = False,
        helper_scale: float = 1.0,
        default_color: Union[ColorLike, None] = None,
        show_parent: bool = False,
        sketch_local: bool = False,
        unroll_compounds: bool = False,
        level=0,
    ) -> OcpGroup:
        """
        Convert a list of objects to an OcpObject or OcpGroup hierarchy.

        @param cad_objs: The list of objects
        @param names: The list of names for the objects
        @param colors: The list of colors for the objects
        @param alphas: The list of alpha values for the objects
        @param loc: The location of the objects
        @param render_mates: The flag to render the mates
        @param render_joints: The flag to render the joints
        @param helper_scale: The scale of the helper objects
        @param default_color: The default color of the objects
        @param show_parent: The flag to show the parent
        @param sketch_local: The flag to render the sketch local
        @param unroll_compounds: The flag to unroll compounds
        @param level: The level of the hierarchy

        @return: The OcpObject or OcpGroup hierarchy
        """
        if loc is None:
            loc = identity_location()
        group = OcpGroup(loc=loc)

        # ============================= Validate parameters ============================= #

        if names is None:
            names = [None] * len(cad_objs)
        elif isinstance(names, (tuple, list)):
            if len(names) != len(cad_objs):
                raise ValueError("Length of names does not match the number of objects")
            names = make_unique(names)
        else:
            raise ValueError(f"Invalid type {type(names)} for names")

        if alphas is None:
            alphas = [None] * len(cad_objs)
        elif isinstance(alphas, (tuple, list)):
            if len(alphas) != len(cad_objs):
                raise ValueError(
                    "Length of alphas does not match the number of objects"
                )
        else:
            raise ValueError(f"Invalid type {type(alphas)} for alphas")

        if colors is None:
            colors = [None] * len(cad_objs)
        elif isinstance(colors, (tuple, list)):
            if len(colors) != len(cad_objs):
                raise ValueError(
                    "Length of colors does not match the number of objects"
                )
        else:
            raise ValueError(f"Invalid type {type(colors)} for colors")

        if default_color is not None:
            self.default_color = default_color

        # =========================== Loop over all objects ========================== #

        for cad_obj, obj_name, color, alpha in zip(cad_objs, names, colors, alphas):  # type: ignore [arg-type]

            # =================== Silently skip enums and known types =================== #
            if (
                isinstance(cad_obj, enum.Enum)
                or is_ocp_color(cad_obj)
                or isinstance(cad_obj, (int, float, bool, str, np.number, np.ndarray))
            ):
                continue

            # =========================== Map Vector to Vertex ========================== #

            if is_vector(cad_obj) or is_gp_vec(cad_obj):
                if isinstance(cad_obj, Iterable):
                    target = list(cad_obj)
                elif hasattr(cad_obj, "toTuple"):
                    target = cad_obj.toTuple()
                else:
                    target = cad_obj.XYZ().Coord()  # type: ignore [union-attr]

                cad_obj = vertex(target)

            # ========================= Empty list or compounds ========================= #

            if (
                not is_cadquery_sketch(cad_obj)
                and not is_vertex(cad_obj)
                and (
                    (is_wrapped(cad_obj) and cad_obj.wrapped is None)
                    or (
                        isinstance(cad_obj, Iterable)
                        and (len(list(cad_obj)) == 0 or is_empty_compound(cad_obj))
                    )
                )
            ):
                ocp_obj: Union[OcpGroup, OcpObject] = self.handle_empty_iterables(
                    obj_name, level
                )

            # ================================ Iterables ================================ #

            # Generic iterables (tuple, list, but not ShapeList)
            elif isinstance(cad_obj, (list, tuple)) and not (
                (
                    is_build123d_shapelist(cad_obj)
                    and all(type(cad_obj[0]) == type(o) for o in cad_obj)
                )
                and not any([class_name(o) == "Compound" for o in cad_obj])
            ):
                ocp_obj = self.handle_list_tuple(
                    cad_obj, obj_name, color, alpha, sketch_local, helper_scale, level
                )
                if ocp_obj.length == 0:
                    ocp_obj.add(self.handle_empty_iterables(obj_name, level))

            # Compounds / topods_compounds
            elif (
                is_compound(cad_obj)
                and (is_mixed_compound(cad_obj.wrapped) or unroll_compounds)
                and not is_build123d_assembly(cad_obj)
                and not is_compsolid(cad_obj.wrapped)
            ) or (
                is_topods_compound(cad_obj)
                and (is_mixed_compound(cad_obj) or unroll_compounds)
                and not is_build123d_assembly(cad_obj)
                and not is_compsolid(cad_obj)
            ):
                ocp_obj = self.handle_compound(
                    cad_obj, obj_name, color, alpha, sketch_local, helper_scale, level
                )

            # Dicts
            elif isinstance(cad_obj, dict):
                ocp_obj = self.handle_dict(
                    cad_obj, obj_name, color, alpha, sketch_local, helper_scale, level
                )

            # =============================== Assemblies ================================ #

            elif is_build123d_assembly(cad_obj):
                ocp_obj = self.handle_build123d_assembly(
                    cad_obj,
                    obj_name,
                    color,
                    alpha,
                    render_joints,
                    helper_scale,
                    level,
                )

            elif is_cadquery_assembly(cad_obj):
                ocp_obj = self.handle_cadquery_assembly(
                    cad_obj,
                    obj_name,
                    color,
                    alpha,
                    render_mates,
                    helper_scale,
                    level,
                )
            # =============================== Conversions =============================== #

            # OcpGroup
            elif isinstance(cad_obj, OcpInstancesGroup):
                cad_obj.apply_offset(len(self.instances))
                ocp_obj = cad_obj.ocpgrp
                self.instances += cad_obj.instances

            # OcpWrapper (ImageFace, CoordSystem, CoordAxis, etc.)
            elif isinstance(cad_obj, OcpWrapper):
                ocp_obj = self.handle_ocp_wrapper(cad_obj, obj_name)

            # build123d ShapeList
            elif is_build123d_shapelist(cad_obj):
                ocp_obj = self.handle_shape_list(
                    cad_obj, obj_name, color, alpha, show_parent, level
                )

            # CadQuery Workplane objects
            elif is_cadquery(cad_obj) and not is_cadquery_empty_workplane(cad_obj):
                ocp_obj = self.handle_workplane(
                    cad_obj, obj_name, color, alpha, show_parent, level
                )

            # build123d LocationLists
            elif is_build123d_locationlist(cad_obj):
                ocp_obj = self.handle_location_list(
                    cad_obj, obj_name, helper_scale, level
                )

            # build123d BuildPart, BuildSketch, BuildLine
            elif is_build123d(cad_obj):
                ocp_obj = self.handle_build123d_builder(
                    cad_obj, obj_name, color, alpha, sketch_local, render_joints, level
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
                    cad_obj,
                    obj_name,
                    render_joints,
                    show_parent,
                    color,
                    alpha,
                    level,
                )

            # Cadquery sketches
            elif is_cadquery_sketch(cad_obj):
                ocp_obj = self.handle_cadquery_sketch(
                    cad_obj, obj_name, color, alpha, level
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
                    cad_obj, obj_name, helper_scale, level
                )

            # build123d Axis or gp_Ax1
            elif is_build123d_axis(cad_obj) or is_gp_axis(cad_obj):
                ocp_obj = self.handle_axis(
                    cad_obj, obj_name, color, helper_scale, level
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


def to_ocpgroup(
    *cad_objs: Union[ShapeLike, Compound, Workplane, List, Dict, Assembly, OcpWrapper],
    names: Union[List[Union[str, None]], None] = None,
    colors: Union[List[Union[ColorLike, None]], None] = None,
    alphas: Union[List[Union[float, None]], None] = None,
    render_mates: bool = False,
    render_joints: bool = False,
    helper_scale: float = 1.0,
    default_color: Union[ColorLike, None] = None,
    show_parent: bool = False,
    show_sketch_local: bool = True,
    loc: LocationLike = None,
    progress: Union[Progress, None] = None,
) -> Tuple[OcpGroup, List[Any]]:
    """
    Central converter routine to convert a list of objects to an OcpGroup hierarchy.

    @param cad_objs: The list of objects
    @param names: The list of names for the objects
    @param colors: The list of colors for the objects
    @param alphas: The list of alpha values for the objects
    @param render_mates: The flag to render the mates
    @param render_joints: The flag to render the joints
    @param helper_scale: The scale of the helper objects
    @param default_color: The default color of the objects
    @param show_parent: The flag to show the parent
    @param show_sketch_local: The flag to render the sketch local
    @param loc: The location of the objects
    @param progress: The progress bar

    @return: The OcpGroup hierarchy
    """
    converter = OcpConverter(progress=progress)
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


def tessellate_group(
    group: OcpGroup,
    instances: List[TopoDS_Shape],
    kwargs: Union[Dict, None] = None,
    progress: Union[Progress, None] = None,
    timeit: bool = False,
) -> Tuple[List, Dict, Dict, Dict]:
    """
    Tessellate a OcpGroup and instances as converted by to_ocp_group.

    @param group: The OcpGroup
    @param instances: The instances of the group
    @param kwargs: The keyword arguments
    @param progress: The progress bar
    @param timeit: The flag to measure the time

    @return: The meshed instances, the shapes, and the mapping
    """

    def get_bb_max(shapes, meshed_instances, loc=None, bbox=None):
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

        # Increase bounding box dimensions that are too small
        # Will only be used to calculate the viewing box size of the group
        for a in ["x", "y", "z"]:
            if bbox[f"{a}max"] - bbox[f"{a}min"] < 1e-6:
                bbox[f"{a}max"] += 0.1
                bbox[f"{a}min"] -= 0.1

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
        top_loc = (
            identity_location() if shapes["loc"] is None else tq_to_loc(*shapes["loc"])
        )
        shapes["bb"] = get_bb_max(shapes, meshed_instances, top_loc)

        t.info = str(BoundingBox(shapes["bb"]))

    return meshed_instances, shapes, mapping


#
# Obsolete functions, just for compatibility
#


def to_assembly(
    *cad_objs: Union[ShapeLike, Compound, Workplane, List, Dict, Assembly, OcpWrapper],
    names: Union[List[Union[str, None]], None] = None,
    colors: Union[List[Union[ColorLike, None]], None] = None,
    alphas: Union[List[Union[float, None]], None] = None,
    render_mates: bool = False,
    render_joints: bool = False,
    helper_scale: float = 1.0,
    default_color: Union[ColorLike, None] = None,
    show_parent: bool = False,
    show_sketch_local: bool = True,
    loc: LocationLike = None,
    progress: Union[Progress, None] = None,
) -> Tuple[OcpGroup, List[Any]]:
    """
    Compatibility wrapper for the converter routine to convert a list of
    objects to an OcpGroup hierarchy.

    @param cad_objs: The list of objects
    @param names: The list of names for the objects
    @param colors: The list of colors for the objects
    @param alphas: The list of alpha values for the objects
    @param render_mates: The flag to render the mates
    @param render_joints: The flag to render the joints
    @param helper_scale: The scale of the helper objects
    @param default_color: The default color of the objects
    @param show_parent: The flag to show the parent
    @param show_sketch_local: The flag to render the sketch local
    @param loc: The location of the objects
    @param progress: The progress bar

    @return: The OcpGroup hierarchy
    """
    warn("to_assembly is obsolete, use to_ocpgroup")
    return to_ocpgroup(
        *cad_objs,
        names=names,
        colors=colors,
        alphas=alphas,
        render_mates=render_mates,
        render_joints=render_joints,
        helper_scale=helper_scale,
        default_color=default_color,
        show_parent=show_parent,
        show_sketch_local=show_sketch_local,
        loc=loc,
        progress=progress,
    )


# TODO: change show.py to directly get bb from shapes
def combined_bb(shapes):
    return BoundingBox(shapes["bb"])


# TODO: change show.py to directly get normal_length from shapes
def get_normal_len(render_normals, shapes, deviation):
    return shapes["normal_len"]


# TODO: remove import from show.py
def conv():
    raise NotImplementedError("conv is not implemented any more")


#
# Convert objects to the javascript format needed for testing three-cad-viewer
#

import json
import re

import numpy as np


def numpy_to_js(var, obj, indent=None):
    class NumpyArrayEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, np.integer):
                return int(o)
            if isinstance(o, np.floating):
                return float(o)
            if isinstance(o, np.ndarray):
                return o.tolist()

            return super(NumpyArrayEncoder, self).default(o)

    # Version 3 of the three-cad-viewer protocol requires Float32Array and Int8Array
    result = json.dumps(obj, cls=NumpyArrayEncoder, indent=indent)
    # for att in ["vertices", "normals", "edges", "obj_vertices"]:
    #     result = re.sub(
    #         rf'"{att}": \[(.*?)\]', rf'"{att}": new Float32Array([ \1 ])', result
    #     )
    # for att in [
    #     "triangles",
    #     "face_types",
    #     "edge_types",
    #     "triangles_per_face",
    #     "segments_per_edge",
    # ]:
    #     result = re.sub(
    #         rf'"{att}": \[(.*?)\]', rf'"{att}": new Uint32Array([ \1 ])', result
    #     )
    if var is None:
        return result
    else:
        return f"var {var} = {result};"


def export_three_cad_viewer_js(var, *objs, names=None, filename=None):
    def decode(instances, shapes):
        def walk(obj):
            typ = None
            for attr in obj.keys():
                if attr == "parts":
                    for part in obj["parts"]:
                        walk(part)

                elif attr == "type":
                    typ = obj["type"]

                elif attr == "shape":
                    if typ == "shapes":
                        if obj["shape"].get("ref") is not None:
                            ind = obj["shape"]["ref"]
                            obj["shape"] = instances[ind]

        walk(shapes)

    part_group, instances = to_ocpgroup(*objs, names=names)
    instances, shapes, map = tessellate_group(part_group, instances)
    decode(instances, shapes)

    j = numpy_to_js(var, shapes)
    if filename is None:
        return j
    else:
        with open(filename, "w") as fd:
            fd.write(j)
        return json.dumps({"exported": filename})
