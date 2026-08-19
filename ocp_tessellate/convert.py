import enum
from hashlib import sha256
from typing import Dict, Iterable, List, Sequence, Tuple, Union

import json
import numpy as np

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
from ocp_tessellate.types import (
    Build123dBuilder,
    Build123dLocationList,
    Build123dShape,
    Build123dShapeList,
    CadqueryAssembly,
    CadquerySketch,
    CadqueryWorkplane,
    ColorLike,
    Instance,
    Wrapped,
)
from ocp_tessellate.utils import *

LINE_WIDTH = 2
POINT_SIZE = 6

EDGE_COLOR = "Silver"
THICK_EDGE_COLOR = "MediumOrchid"
VERTEX_COLOR = "MediumOrchid"
FACE_COLOR = "Violet"


def _default_or(value, fallback):
    """Return value unless it is None, in which case the fallback."""
    return fallback if value is None else value


# The duck types below are Protocols defined in ocp_tessellate.types -
# ocp_tessellate does not import build123d or CadQuery, so their objects
# are described structurally.

# build123d and CadQuery compounds
Compound = Wrapped[TopoDS_Compound]
# CadQuery Workplane
Workplane = CadqueryWorkplane
# CadQuery assemblies
Assembly = CadqueryAssembly
# build123d shape lists
ShapeList = Build123dShapeList
# build123d location lists
LocationList = Build123dLocationList
# build123d Builder Objects
BuilderObject = Build123dBuilder
# build123d or CadQuery Locations or Planes, raw or wrapped
LocationLike = Union[
    TopLoc_Location, gp_Pln, Wrapped[TopLoc_Location], Wrapped[gp_Pln], None
]
# build123d Axis
Axis = Wrapped[gp_Ax1]
# can be build123d or CadQuery shapes
ShapeLike = Union[TopoDS_Shape, Wrapped[TopoDS_Shape]]
CompoundLike = Union[TopoDS_Compound, Wrapped[TopoDS_Compound]]


class Progress:
    def update(self, mark):
        print(mark, end="", flush=True)


def get_name(obj: object, name: Union[str, None], default: str) -> str:
    """
    Get the name of the object. If the name is None, use the default name.
    If the object has a non-empty string name or label attribute, use that.

    @param obj: Any object, its name/label attributes are duck-typed
    @param name: The name of the object
    @param default: The default name

    @return: The derived name of the object
    """
    if name is not None:
        return name
    for attr in ("name", "label"):
        value = getattr(obj, attr, None)
        if isinstance(value, str) and value != "":
            return value
    return default


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
        "TopoDS_Compound": "Compound",
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
        "Compound": "compound",
    }
    kind = kinds.get(typ)
    if kind is None:
        raise ValueError(f"Unknown type: {typ}")
    return kind


def unwrap(
    obj: Union[ShapeLike, List[ShapeLike]],
) -> Union[TopoDS_Shape, List[TopoDS_Shape]]:
    """
    Unwrap the object or objects in a list  if it is wrapped.

    @param obj: The object or list of objects

    @return: The unwrapped object or list of objects
    """
    if isinstance(obj, TopoDS_Shape):
        return obj
    if not isinstance(obj, (list, tuple)):
        return obj.wrapped

    result: List[TopoDS_Shape] = []
    for x in list(obj):
        if isinstance(x, TopoDS_Shape):
            result.append(x)
        elif is_vector(x):
            result.append(vertex((x.X, x.Y, x.Z)))
        else:
            w = _to_topods(x)
            if is_topods_compound(w):
                result.extend(list_topods_compound(w))
            else:
                result.append(w)

    return result


def _to_topods(o: object) -> TopoDS_Shape:
    if isinstance(o, TopoDS_Shape):
        return o
    assert is_wrapped(o), f"expected a shape, got {o}"
    w = o.wrapped
    assert isinstance(w, TopoDS_Shape), f"expected a wrapped shape, got {w}"
    return w


def create_cache_id(obj: Union[ShapeLike, Sequence[ShapeLike]]) -> str:
    """
    The TopoDS_Shape objects are serialized and hashed to create a unique id.
    The current approach is to use the sha256 hash of the serialized object.

    @param obj: A shape (raw or wrapped) or a list/tuple of them

    @return: The unique id of the object
    """
    sha = sha256()
    objs = [obj] if not isinstance(obj, (tuple, list)) else list(obj)
    for o in objs:
        data = serialize(_to_topods(o))
        assert data is not None, "serialization failed"
        sha.update(data)

    return sha.hexdigest()


class OcpConverter:
    """The class to filter obejcts and convert them to OcpObject and OcpGroup hierarchies."""

    def __init__(
        self,
        progress: Union[Progress, None] = None,
        helper_scale: float = 1.0,
        render_joints=False,
        render_mates=False,
        show_parent=False,
        show_locals=True,
        debug: bool = False,
    ):
        """The initializer of the OcpConverter.
        @param progress: The progress class to provide updates during the conversion
        """
        self.instances: List[Instance] = []
        self.ocp = None
        self.progress = progress
        self.helper_scale = helper_scale
        self.render_joints = render_joints
        self.render_mates = render_mates
        self.show_parent = show_parent
        self.show_locals = show_locals
        self.debug = debug
        self.default_color = get_default("default_color")
        # Precedence for the three colors below: an explicit argument to
        # to_ocp wins, then a value set via set_defaults, then the module
        # constant. The constant is last rather than absent because
        # ocp_vscode <= 4.x assigns to it directly on every show, and that
        # has to keep working until those assignments are gone.
        self.default_facecolor = _default_or(
            get_default("default_facecolor"), FACE_COLOR
        )
        self.default_thickedgecolor = _default_or(
            get_default("default_thickedgecolor"), THICK_EDGE_COLOR
        )
        self.default_vertexcolor = _default_or(
            get_default("default_vertexcolor"), VERTEX_COLOR
        )

    def _debug(self, level, msg, name=None, prefix="debug:", end="\n"):
        if self.debug:
            prefix = "  " * level + prefix
            suffix = f" ('{name}')" if name is not None else ""
            print(f"{prefix} {msg} {suffix}", end=end, flush=True)

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

    def trim_infinite_objs(
        self, obj: TopoDS_Shape, name: str
    ) -> Union[TopoDS_Shape, None]:
        # Degenerate OCCT artifacts (edges without geometry, faces without a
        # surface) are dropped by returning None; they would make the
        # length/area calls below raise. Zero-area faces with a valid surface
        # pass through here and are dropped by the mesher instead - detecting
        # them would need an area computation, which is expensive.
        if is_topods_face(obj):
            if is_degenerated_face(obj):
                print(f"Info: Ignoring degenerated face of '{name}' (no surface)")
                return None
            if area(obj) > 1e90:
                print(
                    f"Warning: Scaling down infinite face '{name}' to a rectangle of side length "
                    f"10 * helper_scale = {10 * self.helper_scale}"
                )
                return trim_infinite_face(obj, 10 * self.helper_scale)

        elif is_topods_edge(obj):
            if is_degenerated_edge(obj):
                print(
                    f"Info: Ignoring degenerated edge of '{name}' (zero length or no geometry)"
                )
                return None
            if length(obj) > 1e90:
                print(
                    f"Warning: Scaling down infinite edge '{name}' to length "
                    f"10 * helper_scale = {10 * self.helper_scale}"
                )
                return trim_infinite_edge(obj, 5 * self.helper_scale)
        return obj

    def get_material_for_object(self, obj, material=None):
        """
        Get the material for the object. If an explicit material is given, use it.
        Otherwise, check if the object has a .material attribute.

        @param obj: The object
        @param material: The explicit material string

        @return: The material string or None
        """
        if material:
            return material
        elif hasattr(obj, "material") and obj.material:
            return obj.material
        else:
            return None

    def unify(
        self,
        objs: Sequence[TopoDS_Shape],
        kind: str,
        name: str,
        color: Union[ColorLike, Tuple[ColorLike, ColorLike, ColorLike], None],
        alpha: Union[float, None],
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpObject:
        """
        Unify the objects in a list to a single TopoDS_Shape or a TopoDS_Compound for
        solids, shells and faces or to a list of edges or vertices.

        @param objs: The list of objects
        @param kind: The kind of the objects
        @param name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the object
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The unified OcpObject
        """
        def trim_all(objs: Iterable[TopoDS_Shape]) -> List[TopoDS_Shape]:
            # trim_infinite_objs returns None for degenerate artifacts - drop them
            trimmed = [self.trim_infinite_objs(o, name) for o in objs]
            return [o for o in trimmed if o is not None]

        # Try to downcast to one TopoDS_Shape
        if len(objs) == 1:
            ocp_obj = objs[0]
            # unroll TopoDS_Compound
            if is_topods_compound(ocp_obj):
                ocp_objs = list(list_topods_compound(ocp_obj))
                if len(ocp_objs) == 1:
                    ocp_obj = self.trim_infinite_objs(downcast(ocp_objs[0]), name)
                elif kind in ["edge", "vertex"]:
                    ocp_obj = trim_all(ocp_objs)
            else:
                ocp_obj = self.trim_infinite_objs(ocp_obj, name)

        # else make a TopoDS_Compound
        elif kind in ["solid", "face", "shell"]:
            trimmed = trim_all(objs)
            ocp_obj = make_compound(trimmed) if len(trimmed) > 0 else None

        # and for vertices and edges, keep the list
        else:
            ocp_obj = trim_all(objs)

        if ocp_obj is None or (isinstance(ocp_obj, list) and len(ocp_obj) == 0):
            # everything was a degenerate artifact - emit the same placeholder
            # an empty input produces so names/colors stay aligned
            return self.handle_empty_iterables(name, 0)

        if isinstance(ocp_obj, TopoDS_Shape):
            first = ocp_obj
        else:
            first = ocp_obj[0]

        rgba = self.get_color_for_object(first, color, alpha, kind=kind)
        material = self.get_material_for_object(first, material)

        if kind in ("solid", "face", "shell"):
            # solid/face/shell kinds always unify into a single shape
            assert isinstance(ocp_obj, TopoDS_Shape), f"not unified: {ocp_obj}"
            cache_id = create_cache_id(ocp_obj)
            ref, loc = self.get_instance(ocp_obj, cache_id, name)
            ocp_object = OcpObject(
                kind,
                ref=ref,
                name=name,
                loc=loc,
                color=rgba,
                cache_id=cache_id,
                material=material,
            )
        else:
            ocp_object = OcpObject(
                kind,
                obj=ocp_obj,
                name=name,
                color=rgba,
                width=LINE_WIDTH if kind == "edge" else POINT_SIZE,
                material=material,
            )

        if mode is not None:
            ocp_object.state_faces = mode[0]
            ocp_object.state_edges = mode[1]

        return ocp_object

    def get_color_for_object(
        self,
        obj: ShapeLike,
        color: Union[ColorLike, Tuple[ColorLike, ColorLike, ColorLike], None] = None,
        alpha: Union[float, None] = None,
        kind: Union[str, None] = None,
    ) -> Union[Color, Tuple[Color, Color, Color]]:
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
            "TopoDS_Edge": self.default_thickedgecolor,
            "TopoDS_Face": self.default_facecolor,
            "TopoDS_Shell": self.default_facecolor,
            "TopoDS_Solid": self.default_color,
            "TopoDS_CompSolid": self.default_color,
            "TopoDS_Vertex": self.default_vertexcolor,
            "TopoDS_Wire": self.default_thickedgecolor,
            # kind of objects
            "edge": self.default_thickedgecolor,
            "wire": self.default_thickedgecolor,
            "face": self.default_facecolor,
            "shell": self.default_facecolor,
            "solid": self.default_color,
            "vertex": self.default_vertexcolor,
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
        # the values go straight back into the to_ocp dispatcher
        objs: Iterable[Tuple[Union[str, None], object]],
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
        loc: Union[TopLoc_Location, None] = None,
    ) -> OcpGroup:
        """
        Unroll the objects in an iterable and convert them to OcpObject and OcpGroup hierarchies.

        @param objs: The list of objects
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        ocp_obj: OcpGroup = OcpGroup(name=obj_name, loc=loc)
        for name, obj in objs:
            result = self.to_ocp(
                obj,
                names=[name],
                colors=[color],
                alphas=[alpha],
                materials=[material],
                modes=[mode],
                level=level + 1,
                resolve_helpers=False,
            )
            if result.length > 0:
                c_result = result.cleanup() if result.can_be_cleaned_up else result
                ocp_obj.add(c_result)
                if c_result.helpers is not None:
                    ocp_obj.add(c_result.helpers)
                    c_result.helpers = None

        return ocp_obj.make_unique_names()

    def handle_list_tuple(
        self,
        # elements are dispatched individually via to_ocp
        cad_obj: Union[Sequence[object], Build123dShapeList],
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        default_name: str = "List",
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpGroup:
        """
        Handle lists and tuples of objects.

        @param cad_obj: The list or tuple of objects
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        self._debug(level, "handle_list_tuple", obj_name)
        return self._unroll_iterable(
            zip([None] * len(cad_obj), cad_obj),
            get_name(cad_obj, obj_name, default_name),
            color,
            alpha,
            level,
            material,
            mode,
        )

    def handle_dict(
        self,
        # values are dispatched individually via to_ocp; the dispatcher can
        # only prove dict-ness, so keys/values stay gradually typed
        cad_obj: dict,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpGroup:
        """
        Handle dictionaries of objects.

        @param cad_obj: The dictionary of objects
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        self._debug(level, "handle_dict", obj_name)

        return self._unroll_iterable(
            cad_obj.items(),
            get_name(cad_obj, obj_name, "Dict"),
            color,
            alpha,
            level,
            material,
            mode,
            loc=get_location(cad_obj, as_none=True),
        )

    def handle_compound(
        self,
        cad_obj: CompoundLike,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpGroup:
        """
        Handle compounds and topods_compounds.

        @param cad_obj: The compound or topods_compound
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        self._debug(level, "handle_compound", obj_name)

        if is_compound(cad_obj) or is_compsolid(cad_obj):
            cad_objs = list(list_topods_compound(cad_obj.wrapped))
        elif is_topods_compound(cad_obj) or is_topods_compsolid(cad_obj):
            cad_objs = list(list_topods_compound(cad_obj))
        else:
            raise ValueError(f"Not a compound: {cad_obj}")

        if hasattr(cad_obj, "color") and cad_obj.color is not None:
            color = Color(cad_obj.color)

        default_name = "Compound"
        if is_compsolid(cad_obj) or is_topods_compsolid(cad_obj):
            default_name = "CompSolid"

        return self._unroll_iterable(
            zip([None] * len(cad_objs), cad_objs),
            get_name(cad_obj, obj_name, default_name),
            color,
            alpha,
            level,
            material,
            mode,
        )

    # ================================= Assemblies ================================== #

    def handle_build123d_assembly(
        self,
        cad_obj: Build123dShape,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpGroup:
        """
        Handle build123d assemblies.

        @param cad_obj: The build123d assembly (Compound with children)
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        self._debug(level, "handle_build123d_assembly", obj_name)

        name = get_name(cad_obj, obj_name, "Assembly")
        location = get_location(cad_obj, as_none=False)
        ocp_obj = OcpGroup(name=name, loc=location)

        for child in cad_obj.children:
            child_material = material
            if not material:
                m = getattr(child, "material", None)
                if isinstance(m, str):
                    child_material = m
            sub_obj = self.to_ocp(
                child,
                names=[None if child.label == "" else child.label],
                colors=[child.color if color is None else color],
                alphas=[alpha],
                materials=[child_material],
                modes=[mode],
                level=level + 1,
                resolve_helpers=False,
            )
            if (
                isinstance(sub_obj, OcpGroup)
                and sub_obj.length == 1
                and len(child.children) == 0
            ):
                ocp_obj.add(sub_obj.objects[0])
                if sub_obj.objects[0].helpers is not None:
                    ocp_obj.add(sub_obj.objects[0].helpers)
                    sub_obj.objects[0].helpers = None

            elif isinstance(sub_obj, OcpGroup) and sub_obj.helpers is not None:
                ocp_obj.add(sub_obj)
                ocp_obj.add(sub_obj.helpers)
                sub_obj.helpers = None

            else:
                ocp_obj.add(sub_obj)

        cad_joints = (
            getattr(cad_obj, "joints", None) if self.render_joints else None
        )
        if isinstance(cad_joints, dict) and len(cad_joints) > 0:
            joints = self.to_ocp(
                *[j.symbol for j in cad_joints.values()],
                names=[str(k) for k in cad_joints.keys()],
                level=level + 1,
            )
            joints.name = f"{name}.joints"
            # Move the joint group to the same location as the object and adapt the single
            # joints location to be relative to the group
            joints.loc = location
            for joint in joints.objects:
                if joint.loc is None:
                    joint.loc = location.Inverted()
                else:
                    joint.loc = location.Inverted() * joint.loc
            ocp_obj.helpers = joints

        return ocp_obj.make_unique_names()

    def handle_cadquery_assembly(
        self,
        cad_obj: Assembly,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpGroup:
        """
        Handle cadquery assemblies.

        @param cad_obj: The cadquery assembly
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        self._debug(level, "handle_cadquery_assembly", obj_name)
        name = get_name(cad_obj, obj_name, "Assembly")

        ocp_obj = OcpGroup(name=name, loc=get_location(cad_obj, as_none=False))
        if cad_obj.obj is not None:
            cq_material = material
            if not material:
                m = getattr(cad_obj, "material", None)
                if isinstance(m, str):
                    cq_material = m
            sub_obj = self.to_ocp(
                cad_obj.obj,
                names=[cad_obj.name],
                colors=[cad_obj.color if color is None else color],
                alphas=[alpha],
                materials=[cq_material],
                modes=[mode],
                level=level + 1,
            )
            ocp_obj.add(sub_obj.objects[0])

        if self.render_mates:
            top = cad_obj
            while top.parent is not None:
                top = top.parent
            mates_def = getattr(top, "mates", None)
            if isinstance(mates_def, dict):
                mates = OcpGroup(
                    [
                        CoordSystem(
                            name,
                            get_tuple(mate_def.mate.origin),
                            get_tuple(mate_def.mate.x_dir),
                            get_tuple(mate_def.mate.z_dir),
                            self.helper_scale,
                        ).to_ocp()
                        for name, mate_def in mates_def.items()
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
                level=level + 1,
            )
            ocp_obj.add(sub_obj)

        return ocp_obj

    # ================================= Conversions ================================= #

    def handle_parent(
        self,
        cad_obj: object,
        level: int,
    ) -> List[OcpGroup]:
        """
        Handle the parent of an objects.

        @param cad_obj: The object or objects, parent attributes are duck-typed
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        parent: object = None
        if getattr(cad_obj, "parent", None) is not None:
            parent = getattr(cad_obj, "parent")
        elif getattr(cad_obj, "topo_parent", None) is not None:
            parent = getattr(cad_obj, "topo_parent")
        elif (
            isinstance(cad_obj, list)
            and len(cad_obj) > 0
            and hasattr(cad_obj[0], "topo_parent")
        ):
            parent = [getattr(c, "topo_parent") for c in cad_obj]

        p = self.to_ocp(
            list(set(parent)) if isinstance(parent, list) else parent,
            names=["_parent"],
            colors=None,
            level=level + 1,
        )
        for o in p.objects:
            if isinstance(o, OcpObject):
                if o.kind == "solid":
                    o.state_faces = 0
                elif o.kind == "face":
                    o.state_edges = 0

        return [p]

    def handle_location_list(
        self,
        cad_obj: LocationList,
        obj_name: Union[str, None],
        level: int,
    ) -> OcpGroup:
        """
        Handle build123d location lists.

        @param cad_obj: The build123d location list
        @param obj_name: The name of the object
        @param level: The level of the hierarchy

        @return: The OcpGroup hierarchy
        """
        self._debug(level, "handle_location_list (build123d LocationList)", obj_name)
        group = OcpGroup(name=get_name(cad_obj, obj_name, "LocationList"))
        for loc in cad_obj:
            group.add(self.handle_locations_planes(loc, "Location", level=level + 1))
        group.make_unique_names()
        return group

    def _handle_list(
        self, cad_obj, name, obj_name, color, alpha, material=None, mode=None
    ):
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
            unwrapped = unwrap(cad_obj)
            assert not isinstance(unwrapped, TopoDS_Shape), (
                "a list input unwraps to a list"
            )
            objs = unwrapped
            typ = get_type(objs[0])

        kind = get_kind(typ)
        rgba = self.get_color_for_object(objs[0], color)
        assert isinstance(rgba, Color), "single objects resolve to a single color"
        if alpha is not None:
            rgba.a = alpha
        return self.unify(
            objs,
            kind=kind,
            name=get_name(cad_obj, obj_name, f"{name}({typ})"),
            color=rgba,
            alpha=alpha,
            material=material,
            mode=mode,
        )

    def handle_workplane(
        self,
        cad_obj: Workplane,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> Union[OcpGroup, OcpObject]:
        """
        Handle cadquery Workplane.

        @param cad_obj: The cadquery Workplane
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        parent_obj = cad_obj

        self._debug(level, "handle_workplane (cadquery Workplane)", obj_name)
        name = "Workplane"

        # Resolve cadquery Workplane
        vals: List[object] = list(cad_obj.vals())
        if len(vals) > 0:
            if is_compound(vals[0]):
                flat: List[object] = []
                for obj in vals:
                    assert isinstance(obj, Iterable), f"expected a compound: {obj}"
                    flat.extend(obj)
                vals = flat
            elif is_cadquery_sketch(vals[0]):
                return self.to_ocp(vals).cleanup()

        ocp_obj = self._handle_list(
            vals, name, obj_name, color, alpha, material, mode
        )

        if self.show_parent and level == 0:  # show just one level in CadQuery
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
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> Union[OcpGroup, OcpObject]:
        """
        Handle build123d shape lists.

        @param cad_obj: The build123d ShapeList
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        parent_obj = cad_obj

        self._debug(level, "handle_shapelist (build123d ShapeList)", obj_name)
        name = "ShapeList"

        ocp_obj = self._handle_list(
            cad_obj, name, obj_name, color, alpha, material, mode
        )

        if self.show_parent:
            parents = self.handle_parent(parent_obj, level)
            return OcpGroup(parents + [ocp_obj], name=ocp_obj.name)
        else:
            return ocp_obj

    def handle_shapes(
        self,
        cad_obj: Union[ShapeLike, Compound],
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> Union[OcpGroup, OcpObject]:
        """
        Handle build123d or Cadquery shapes.

        @param cad_obj: The shape or shapes
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

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

        self._debug(level, f"handle_shapes ({t}) ({class_name(obj)})", obj_name)

        edges = None
        if is_topods_wire(obj):
            typ, edges = "Wire", list(get_edges(obj))
        elif is_topods_compound(obj):
            typ = get_compound_type(obj)
            if typ == "Wire" or typ == "Edge":
                edges = list(get_edges(obj))
        else:
            typ = type_name(obj)

        name = get_name(cad_obj, obj_name, typ)

        rgba = self.get_color_for_object(cad_obj, color, alpha, kind=get_kind(typ))
        material = self.get_material_for_object(cad_obj, material)

        ocp_obj = self.unify(
            [obj] if edges is None else edges,
            kind=get_kind(typ),
            name=name,
            color=rgba,
            alpha=alpha,
            material=material,
            mode=mode,
        )

        cad_joints = (
            getattr(cad_obj, "joints", None) if self.render_joints else None
        )
        if isinstance(cad_joints, dict) and len(cad_joints) > 0:
            joints = self.to_ocp(
                *[j.symbol for j in cad_joints.values()],
                names=[str(k) for k in cad_joints.keys()],
                level=level + 1,
            )

            joints.name = f"{name}.joints"
            # Move the joint group to the same location as the object and adapt the single
            # joints location to be relative to the group
            loc = ocp_obj.loc
            assert loc is not None, "joints require a located object"
            joints.loc = loc
            for joint in joints.objects:
                if joint.loc is None:
                    joint.loc = loc.Inverted()
                else:
                    joint.loc = loc.Inverted() * joint.loc
            ocp_obj.helpers = joints

        if self.show_parent and (
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
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpGroup | OcpObject:
        """
        Handle build123d Builder objects.

        @param cad_obj: The build123d Builder object
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """

        def add_local(
            local_objects: Iterable[Wrapped[TopoDS_Shape]],
            prefix: str,
            kind: str,
            color: Union[Color, None],
            ocp_obj: Union[OcpObject, OcpGroup],
        ) -> OcpGroup:
            obj_local = self.unify(
                [f.wrapped for f in local_objects],
                kind=kind,
                name=f"{prefix}_local",
                color=color,
                alpha=None,
                material=None,
                mode=None,
            )
            assert isinstance(obj_local.color, Color), (
                f"Unknown color type {type(obj_local.color)}"
            )
            if prefix == "line":
                obj_local.color = obj_local.color.set_saturation(0.2)
            else:
                obj_local.color.a = 0.2

            obj = ocp_obj
            if obj.helpers is not None:
                helpers = obj.helpers
                obj.helpers = None
                obj = OcpGroup(name=prefix)
                obj.add(ocp_obj)
                obj.add(helpers)
            else:
                obj.name = prefix
            ocp_obj = OcpGroup(name=obj_name)
            ocp_obj.add(obj)
            ocp_obj.add(obj_local)
            return ocp_obj

        self._debug(level, f"handle_build123d_builder {cad_obj._obj_name}", obj_name)

        def get_color(color: object) -> Union[Color, None]:
            if color is None:
                return None
            return Color(color)

        builder_color = get_color(getattr(cad_obj, "color", color))
        m = getattr(cad_obj, "material", None)
        builder_material = m if isinstance(m, str) else material

        # Builder objects are homogeneous compounds (a sketch is all faces, a line
        # is all edges) - the user's "one thing", not the N inner shapes that compose
        # it. Bypass ShapeList unrolling and unify directly into a single OcpObject.
        if is_build123d_part(cad_obj):
            part = cad_obj.part
            assert part is not None, "BuildPart has no part"
            obj_name = get_name(cad_obj, obj_name, "Solid")
            part_color = get_color(part.color)
            part_color = builder_color if part_color is None else part_color
            part_alpha = (
                part_color.a
                if (part_color is not None and isinstance(part_color.a, (int, float)))
                else 1.0
            )
            part_material = getattr(part, "material", None)
            if not isinstance(part_material, str):
                part_material = builder_material

            ocp_obj = self.to_ocp(
                part,
                names=[obj_name],
                colors=[part_color],
                alphas=[part_alpha],
                materials=[part_material],
                modes=[mode],
                level=level + 1,
                resolve_helpers=False,
            ).cleanup()
            local_shape = getattr(cad_obj, "part_local", None)
            local_args = ("part", "solid", part_color)

        elif is_build123d_sketch(cad_obj):
            sketch = cad_obj.sketch
            assert sketch is not None, "BuildSketch has no sketch"
            obj_name = get_name(cad_obj, obj_name, "Face")
            sketch_color = get_color(sketch.color)
            sketch_color = builder_color if sketch_color is None else sketch_color
            sketch_alpha = (
                sketch_color.a
                if (
                    sketch_color is not None
                    and isinstance(sketch_color.a, (int, float))
                )
                else 1.0
            )
            sketch_material = getattr(sketch, "material", None)
            if not isinstance(sketch_material, str):
                sketch_material = None
            ocp_obj = self.unify(
                [f.wrapped for f in sketch.faces()],
                kind="face",
                name=obj_name,
                color=sketch_color,
                alpha=sketch_alpha,
                material=builder_material
                if sketch_material is None
                else sketch_material,
                mode=mode,
            )
            local_shape = getattr(cad_obj, "sketch_local", None)
            local_args = ("sketch", "face", sketch_color)

        elif is_build123d_line(cad_obj):
            b3d_line = cad_obj.line
            assert b3d_line is not None, "BuildLine has no line"
            obj_name = get_name(cad_obj, obj_name, "Edge")
            line_color = get_color(b3d_line.color)
            line_color = builder_color if line_color is None else line_color
            line_alpha = (
                line_color.a
                if (line_color is not None and isinstance(line_color.a, (int, float)))
                else 1.0
            )
            ocp_obj = self.unify(
                [e.wrapped for e in b3d_line.edges()],
                kind="edge",
                name=obj_name,
                color=line_color,
                alpha=line_alpha,
                mode=mode,
            )
            local_shape = getattr(cad_obj, "line_local", None)
            local_args = ("line", "edge", line_color)
        else:
            raise TypeError(f"Not a build123d builder type {type(cad_obj)}")

        if self.show_locals and local_shape is not None:
            prefix, local_kind, local_color = local_args
            local_objects = (
                local_shape.edges() if local_kind == "edge" else local_shape.faces()
            )
            ocp_obj = add_local(local_objects, prefix, local_kind, local_color, ocp_obj)
        elif ocp_obj.helpers is not None:
            helpers = ocp_obj.helpers
            ocp_obj.helpers = None
            group = OcpGroup(name=obj_name)
            group.add(ocp_obj)
            group.add(helpers)
            ocp_obj = group

        return ocp_obj

    def handle_cadquery_sketch(
        self,
        cad_obj: CadquerySketch,
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        alpha: float,
        level: int,
        material: Union[str, None] = None,
        mode: Union[Tuple[int, int], None] = None,
    ) -> OcpGroup:
        """
        Handle cadquery sketches.

        @param cad_obj: The cadquery sketch
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy
        @param material: The material string
        @param mode: The (state_faces, state_edges) 2-tuple of 0/1 ints

        @return: The OcpGroup hierarchy
        """
        self._debug(level, "cadquery Sketch", obj_name)

        # do not mutate the user's sketch - normalize _faces into a local list
        faces_src = cad_obj._faces
        faces: List[object]
        if isinstance(faces_src, (list, tuple)):
            faces = list(faces_src)
        else:
            # a single (possibly empty) compound
            assert isinstance(faces_src, Iterable), (
                f"cadquery Sketch._faces is not iterable: {faces_src}"
            )
            faces = [faces_src] if len(list(faces_src)) > 0 else []

        cad_objs: List[Union[TopoDS_Shape, List[TopLoc_Location]]] = []
        names: List[str | None] = []
        bb = BoundingBox()

        selection = cad_obj._selection
        for typ, objs, calc_bb in [
            ("Face", faces, True),
            ("Edge", list(cad_obj._edges), True),
            (
                "Selection",
                [] if selection is None else list(selection),
                False,
            ),
        ]:
            if len(objs) > 0:
                compound: Union[TopoDS_Shape, List[TopLoc_Location]]
                if is_location(objs[0]):
                    assert selection is not None
                    locations: List[TopLoc_Location] = []
                    for obj in selection:
                        assert is_location(obj), f"expected a location: {obj}"
                        for loc in cad_obj.locs:
                            locations.append(loc.wrapped * obj.wrapped)
                    compound = locations
                else:
                    shapes: List[TopoDS_Shape] = []
                    for obj in objs:
                        assert is_shape(obj), f"expected a shape: {obj}"
                        for loc in cad_obj.locs:
                            shapes.append(downcast(obj.wrapped.Moved(loc.wrapped)))
                    compound = make_compound(shapes)
                cad_objs.append(compound)
                names.append(typ)

                if calc_bb:
                    bb.update(BoundingBox(compound))

        name = get_name(cad_obj, obj_name, "Sketch")
        result = self.to_ocp(
            *cad_objs,
            names=names,
            colors=[color] * len(cad_objs),
            alphas=[alpha] * len(cad_objs),
            materials=[material] * len(cad_objs),
            modes=[mode] * len(cad_objs),
            level=level,
        )
        result.name = name
        return result

    def handle_locations_planes(
        self,
        cad_obj: Union[LocationLike, CadqueryWorkplane],
        obj_name: Union[str, None],
        level: int,
    ) -> OcpObject:
        """
        Handle locations and planes.

        @param cad_obj: The location or plane (or an empty cadquery Workplane)
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy

        @return: The OcpObject
        """
        if is_build123d_location(cad_obj) or is_toploc_location(cad_obj):
            self._debug(level, "build123d Location or TopLoc_Location", obj_name)

        elif (
            is_build123d_plane(cad_obj)
            and hasattr(cad_obj, "location")
            or is_gp_plane(cad_obj)
        ):
            self._debug(level, "build123d Plane or gp_Pln", obj_name)

        elif is_cadquery_empty_workplane(cad_obj):
            self._debug(level, "cadquery Workplane", obj_name)

        loc: TopLoc_Location
        if is_build123d_plane(cad_obj) and hasattr(cad_obj, "location"):
            location = getattr(cad_obj, "location")
            assert is_location(location), f"not a location: {location}"
            loc = location.wrapped
            def_name = "Plane"

        elif is_gp_plane(cad_obj):
            def_name = "Plane"
            loc = loc_from_gp_pln(cad_obj)

        elif is_cadquery_empty_workplane(cad_obj):
            def_name = "Workplane"
            loc = cad_obj.plane.location.wrapped

        elif is_build123d_location(cad_obj):
            def_name = "Location"
            loc = cad_obj.wrapped

        else:
            def_name = "Location"
            assert is_toploc_location(cad_obj), f"not a location: {cad_obj}"
            loc = cad_obj

        coord = get_location_coord(loc)
        name = get_name(cad_obj, obj_name, def_name)
        ocp_obj = CoordSystem(
            name,
            coord["origin"],
            coord["x_dir"],
            coord["z_dir"],
            size=self.helper_scale,
        ).to_ocp()
        return ocp_obj

    def handle_axis(
        self,
        cad_obj: Union[Axis, gp_Ax1],
        obj_name: Union[str, None],
        color: Union[ColorLike, None],
        level: int,
    ) -> OcpObject:
        """
        Handle build123d Axis or gp_Ax1.

        @param cad_obj: The build123d Axis or gp_Ax1
        @param obj_name: The name of the object
        @param color: The color of the object
        @param alpha: The alpha value of the color
        @param level: The level of the hierarchy

        @return: The OcpObject
        """
        self._debug(level, "build123d Axis", obj_name)

        if isinstance(cad_obj, gp_Ax1):
            axis = cad_obj
        else:
            axis = cad_obj.wrapped
        coord = get_axis_coord(axis)
        name = get_name(cad_obj, obj_name, "Axis")
        ocp_obj = CoordAxis(
            name,
            coord["origin"],
            coord["z_dir"],
            None if color is None else Color(color),
            size=self.helper_scale,
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
        self, obj_name: Union[str, None], level: int
    ) -> OcpObject:
        """
        Handle empty objects.

        @param obj_name: The name of the object
        @param level: The level of the hierarchy

        @return: The OcpObject
        """
        self._debug(level, "Empty object")
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
        # to_ocp is the dispatcher: it accepts anything, identifies known kinds
        # via the is_* predicates and skips the rest (debug message only)
        *cad_objs: object,
        names: Union[List[Union[str, None]], None] = None,
        colors: Union[List[Union[ColorLike, None]], None] = None,
        alphas: Union[List[Union[float, None]], None] = None,
        materials: Union[List[Union[str, None]], None] = None,
        modes: Union[List[Union[Tuple[int, int], None]], None] = None,
        loc: Union[TopLoc_Location, None] = None,
        default_color: Union[ColorLike, None] = None,
        default_facecolor: Union[ColorLike, None] = None,
        default_thickedgecolor: Union[ColorLike, None] = None,
        default_vertexcolor: Union[ColorLike, None] = None,
        unroll_compounds: bool = False,
        level: int = 0,
        resolve_helpers=True,
    ) -> OcpGroup:
        """
        Convert a list of objects to an OcpObject or OcpGroup hierarchy.

        @param cad_objs: The list of objects
        @param names: The list of names for the objects
        @param colors: The list of colors for the objects
        @param alphas: The list of alpha values for the objects
        @param materials: The list of material strings for the objects
        @param modes: The list of (state_faces, state_edges) 2-tuples (0/1 ints) for the objects
        @param loc: The location of the objects
        @param default_color: The default color of the objects
        @param default_facecolor: Color of a face shown on its own
        @param default_thickedgecolor: Color of an edge or wire shown on its own
        @param default_vertexcolor: Color of a vertex shown on its own
        @param unroll_compounds: The flag to unroll compounds
        @param level: The level of the hierarchy

        @return: The OcpObject or OcpGroup hierarchy
        """
        if loc is None:
            loc = identity_location()
        # ensures group.can_be_cleaned_up works
        group = OcpGroup(name=None, loc=loc)

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

        if materials is None:
            materials = [None] * len(cad_objs)
        elif isinstance(materials, (tuple, list)):
            if len(materials) != len(cad_objs):
                raise ValueError(
                    "Length of materials does not match the number of objects"
                )
        else:
            raise ValueError(f"Invalid type {type(materials)} for materials")

        if modes is None:
            modes = [None] * len(cad_objs)
        elif isinstance(modes, (tuple, list)):
            if len(modes) != len(cad_objs):
                raise ValueError("Length of modes does not match the number of objects")
        else:
            raise ValueError(f"Invalid type {type(modes)} for modes")

        if default_color is not None:
            self.default_color = default_color
        if default_facecolor is not None:
            self.default_facecolor = default_facecolor
        if default_thickedgecolor is not None:
            self.default_thickedgecolor = default_thickedgecolor
        if default_vertexcolor is not None:
            self.default_vertexcolor = default_vertexcolor

        # =========================== Loop over all objects ========================== #

        for cad_obj, obj_name, color, alpha, material, mode in zip(
            cad_objs, names, colors, alphas, materials, modes
        ):
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
                    x, y, z = cad_obj
                    cad_obj = vertex((x, y, z))
                elif hasattr(cad_obj, "toTuple"):
                    x, y, z = getattr(cad_obj, "toTuple")()
                    cad_obj = vertex((x, y, z))
                else:
                    assert is_gp_vec(cad_obj), f"not a vector: {cad_obj}"
                    cad_obj = vertex(cad_obj)

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
                    and all(type(cad_obj[0]) is type(o) for o in cad_obj)
                )
                and not any([class_name(o) == "Compound" for o in cad_obj])
            ):
                ocp_obj = self.handle_list_tuple(
                    cad_obj, obj_name, color, alpha, level, material, mode=mode
                )

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
                    cad_obj, obj_name, color, alpha, level, material, mode=mode
                )

            # Dicts
            elif isinstance(cad_obj, dict):
                ocp_obj = self.handle_dict(
                    cad_obj, obj_name, color, alpha, level, material, mode=mode
                )

            # =============================== Assemblies ================================ #

            elif is_build123d_assembly(cad_obj):
                ocp_obj = self.handle_build123d_assembly(
                    cad_obj,
                    obj_name,
                    color,
                    alpha,
                    level,
                    material,
                    mode=mode,
                )

            elif is_cadquery_assembly(cad_obj):
                ocp_obj = self.handle_cadquery_assembly(
                    cad_obj,
                    obj_name,
                    color,
                    alpha,
                    level,
                    material,
                    mode=mode,
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
                # Treat shapelists like lists
                # ocp_obj = self.handle_shape_list(cad_obj, obj_name, color, alpha, level, material)
                ocp_obj = self.handle_list_tuple(
                    cad_obj,
                    obj_name,
                    color,
                    alpha,
                    level,
                    material,
                    default_name="ShapeList",
                    mode=mode,
                )

            # CadQuery Workplane objects
            elif is_cadquery(cad_obj) and not is_cadquery_empty_workplane(cad_obj):
                ocp_obj = self.handle_workplane(
                    cad_obj, obj_name, color, alpha, level, material, mode=mode
                )

            # build123d LocationLists
            elif is_build123d_locationlist(cad_obj):
                ocp_obj = self.handle_location_list(cad_obj, obj_name, level)

            # build123d BuildPart, BuildSketch, BuildLine
            elif is_build123d(cad_obj):
                ocp_obj = self.handle_build123d_builder(
                    cad_obj, obj_name, color, alpha, level, material, mode=mode
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
                    color,
                    alpha,
                    level,
                    material,
                    mode=mode,
                )

            # Cadquery sketches
            elif is_cadquery_sketch(cad_obj):
                ocp_obj = self.handle_cadquery_sketch(
                    cad_obj, obj_name, color, alpha, level, material, mode=mode
                )

            # build123d Location/Plane or TopLoc_Location or gp_Pln
            elif (
                is_build123d_location(cad_obj)
                or is_toploc_location(cad_obj)
                or is_build123d_plane(cad_obj)
                or is_gp_plane(cad_obj)
                or is_cadquery_empty_workplane(cad_obj)
            ):
                ocp_obj = self.handle_locations_planes(cad_obj, obj_name, level)

            # build123d Axis or gp_Ax1
            elif is_build123d_axis(cad_obj) or is_gp_axis(cad_obj):
                ocp_obj = self.handle_axis(cad_obj, obj_name, color, level)

            else:
                if self.debug:
                    print(
                        "Unknown object"
                        + ("" if obj_name is None else f" '{obj_name}'")
                        + f" of type {type(cad_obj)}"
                    )
                continue

            if self.debug:
                print(f"{'  ' * level}=>", ocp_obj)

            if not (isinstance(ocp_obj, OcpGroup) and ocp_obj.length == 0):
                group.add(ocp_obj)
                if resolve_helpers and ocp_obj.helpers is not None:
                    group.add(ocp_obj.helpers)
                    ocp_obj.helpers = None

        group.make_unique_names()

        if group.length == 1 and isinstance(group.objects[0], OcpGroup):
            cleaned = group.cleanup()
            assert isinstance(cleaned, OcpGroup)
            group = cleaned

        return group


#
# Interface functions
#


def to_ocpgroup(
    *cad_objs: object,
    names: Union[List[Union[str, None]], None] = None,
    colors: Union[List[Union[ColorLike, None]], None] = None,
    alphas: Union[List[Union[float, None]], None] = None,
    materials: Union[List[Union[str, None]], None] = None,
    modes: Union[List[Union[Tuple[int, int], None]], None] = None,
    render_mates: bool = False,
    render_joints: bool = False,
    helper_scale: float = 1.0,
    default_color: Union[ColorLike, None] = None,
    default_facecolor: Union[ColorLike, None] = None,
    default_thickedgecolor: Union[ColorLike, None] = None,
    default_vertexcolor: Union[ColorLike, None] = None,
    show_parent: bool = False,
    show_locals: bool = True,
    loc: Union[TopLoc_Location, None] = None,
    progress: Union[Progress, None] = None,
    debug: bool = False,
) -> Tuple[OcpGroup, List[Instance]]:
    """
    Central converter routine to convert a list of objects to an OcpGroup hierarchy.

    @param cad_objs: The list of objects
    @param names: The list of names for the objects
    @param colors: The list of colors for the objects
    @param alphas: The list of alpha values for the objects
    @param materials: The list of material strings for the objects
    @param modes: The list of (state_faces, state_edges) 2-tuples (0/1 ints) for the objects
    @param render_mates: The flag to render the mates
    @param render_joints: The flag to render the joints
    @param helper_scale: The scale of the helper objects
    @param default_color: The default color of the objects
    @param default_facecolor: Color of a face shown on its own
    @param default_thickedgecolor: Color of an edge or wire shown on its own
    @param default_vertexcolor: Color of a vertex shown on its own
    @param show_parent: The flag to show the parent
    @param show_locals: The flag to render the part/sketch/line based on XY plane
    @param loc: The location of the objects
    @param progress: The progress bar

    @return: The OcpGroup hierarchy
    """
    converter = OcpConverter(
        progress=progress,
        helper_scale=helper_scale,
        render_joints=render_joints,
        render_mates=render_mates,
        show_parent=show_parent,
        show_locals=show_locals,
        debug=debug,
    )
    ocp_group = converter.to_ocp(
        *cad_objs,
        names=names,
        colors=colors,
        alphas=alphas,
        materials=materials,
        modes=modes,
        loc=loc,
        default_color=default_color,
        default_facecolor=default_facecolor,
        default_thickedgecolor=default_thickedgecolor,
        default_vertexcolor=default_vertexcolor,
    )

    if ocp_group.name is None:
        ocp_group.name = "Group"

    return ocp_group, converter.instances


def tessellate_group(
    group: OcpGroup,
    instances: List[Instance],
    kwargs: Union[Dict, None] = None,
    progress: Union[Progress, None] = None,
    timeit: bool = False,
) -> Tuple[List, Dict, Dict]:
    """
    Tessellate a OcpGroup and instances as converted by to_ocp_group.

    @param group: The OcpGroup
    @param instances: The instances of the group
    @param kwargs: The keyword arguments
    @param progress: The progress bar
    @param timeit: The flag to measure the time

    @return: The meshed instances, the shapes, and the mapping
    """
    if kwargs is None:
        kwargs = {}

    def get_bb_max(
        shapes,
        meshed_instances,
        loc: Union[TopLoc_Location, None] = None,
        bbox: Union[Dict[str, float], None] = None,
    ) -> Union[Dict[str, float], None]:
        for shape in shapes["parts"]:
            # mul_locations treats a missing location as identity
            new_loc = (
                loc
                if shape["loc"] is None
                else mul_locations(loc, tq_to_loc(*shape["loc"]))
            )
            if shape.get("parts") is None:
                bb: Dict[str, float]
                if shape["type"] == "shapes":
                    # Solids, shells and faces are instances and need to calculate
                    # the bounding box at the accumulated location
                    ind = shape["shape"]["ref"]
                    vertices = meshed_instances[ind]["vertices"]
                    if len(vertices) == 0:
                        continue
                    npb = np_bbox(vertices, *loc_to_tq(new_loc))
                    assert npb is not None, "np_bbox of non-empty vertices"
                    bb = {
                        "xmin": npb["xmin"],
                        "xmax": npb["xmax"],
                        "ymin": npb["ymin"],
                        "ymax": npb["ymax"],
                        "zmin": npb["zmin"],
                        "zmax": npb["zmax"],
                    }
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
        if bbox is not None:
            for kmin, kmax in (("xmin", "xmax"), ("ymin", "ymax"), ("zmin", "zmax")):
                if bbox[kmax] - bbox[kmin] < 1e-6:
                    bbox[kmax] += 0.1
                    bbox[kmin] -= 0.1

        return bbox

    def _discretize_edges(obj, name, id_):
        with Timer(timeit, name, "bounding box:", 2) as t:
            deviation = preset("deviation", kwargs.get("deviation"))
            edge_accuracy = preset("edge_accuracy", kwargs.get("edge_accuracy"))

            bb = bounding_box(obj)
            quality = compute_quality(bb, deviation=deviation)
            deflection = quality / 10 if edge_accuracy is None else edge_accuracy
            t.info = str(bb)

        with Timer(timeit, name, "discretize:  ", 2) as t:
            t.info = f"quality: {quality}, deflection: {deflection}"
            disc_edges = discretize_edges(obj, deflection, id_)

        return disc_edges, bb

    def _convert_vertices(obj, _name, id_):
        bb = bounding_box(obj)
        vertices = convert_vertices(obj, id_)

        return vertices, bb

    mapping, shapes = group.collect(
        "", instances, None, _discretize_edges, _convert_vertices
    )

    # Find which instance refs have materials so we only compute UVs when needed
    def _refs_with_materials(parts):
        refs = {}
        for part in parts:
            if "parts" in part:
                refs.update(_refs_with_materials(part["parts"]))
            elif part.get("type") == "shapes" and part.get("material"):
                refs[part["shape"]["ref"]] = part.get("normalize_uvs", True)
        return refs

    material_refs = _refs_with_materials(shapes.get("parts", []))

    meshed_instances = []
    ref_remap = {}

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
                compute_uvs=(i in material_refs),
                normalize_uvs=material_refs.get(i, True),
            )
            if len(mesh["vertices"]) == 0:
                t.info = f"instance {i} ignored (empty mesh)"
            else:
                ref_remap[i] = len(meshed_instances)
                meshed_instances.append(mesh)
                t.info = (
                    f"quality:{quality:.4f}, angular_tolerance:{angular_tolerance:.2f}"
                )

    # Drop shape entries that referenced an empty mesh and remap the rest
    # so refs stay valid after filtering.
    def _remap_shape_refs(parts):
        filtered = []
        for part in parts:
            if "parts" in part:
                _remap_shape_refs(part["parts"])
                filtered.append(part)
            elif (
                part.get("type") == "shapes"
                and isinstance(part.get("shape"), dict)
                and "ref" in part["shape"]
            ):
                old_ref = part["shape"]["ref"]
                if old_ref in ref_remap:
                    part["shape"]["ref"] = ref_remap[old_ref]
                    filtered.append(part)
            else:
                filtered.append(part)
        parts[:] = filtered

    _remap_shape_refs(shapes.get("parts", []))

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
    *cad_objs: object,
    names: Union[List[Union[str, None]], None] = None,
    colors: Union[List[Union[ColorLike, None]], None] = None,
    alphas: Union[List[Union[float, None]], None] = None,
    modes: Union[List[Union[Tuple[int, int], None]], None] = None,
    render_mates: bool = False,
    render_joints: bool = False,
    helper_scale: float = 1.0,
    default_color: Union[ColorLike, None] = None,
    default_facecolor: Union[ColorLike, None] = None,
    default_thickedgecolor: Union[ColorLike, None] = None,
    default_vertexcolor: Union[ColorLike, None] = None,
    show_parent: bool = False,
    show_locals: bool = True,
    loc: Union[TopLoc_Location, None] = None,
    progress: Union[Progress, None] = None,
) -> Tuple[OcpGroup, List[Instance]]:
    """
    Compatibility wrapper for the converter routine to convert a list of
    objects to an OcpGroup hierarchy.

    @param cad_objs: The list of objects
    @param names: The list of names for the objects
    @param colors: The list of colors for the objects
    @param alphas: The list of alpha values for the objects
    @param modes: The list of (state_faces, state_edges) 2-tuples (0/1 ints) for the objects
    @param render_mates: The flag to render the mates
    @param render_joints: The flag to render the joints
    @param helper_scale: The scale of the helper objects
    @param default_color: The default color of the objects
    @param default_facecolor: Color of a face shown on its own
    @param default_thickedgecolor: Color of an edge or wire shown on its own
    @param default_vertexcolor: Color of a vertex shown on its own
    @param show_parent: The flag to show the parent
    @param show_locals: The flag to render the sketch local
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
        modes=modes,
        render_mates=render_mates,
        render_joints=render_joints,
        helper_scale=helper_scale,
        default_color=default_color,
        default_facecolor=default_facecolor,
        default_thickedgecolor=default_thickedgecolor,
        default_vertexcolor=default_vertexcolor,
        show_parent=show_parent,
        show_locals=show_locals,
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


def export_three_cad_viewer_js(
    var,
    *objs,
    names=None,
    colors=None,
    alphas=None,
    modes=None,
    filename=None,
    keep_instances=False,
):
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

    part_group, instances = to_ocpgroup(
        *objs, names=names, colors=colors, alphas=alphas, modes=modes
    )
    instances, shapes, map = tessellate_group(part_group, instances)
    if keep_instances:
        j = json.dumps(numpy_to_buffer_json({"instances": instances, "shapes": shapes}))
    else:
        decode(instances, shapes)

        j = numpy_to_js(var, shapes)

    if filename is None:
        return j
    else:
        with open(filename, "w") as fd:
            fd.write(j)
        return json.dumps({"exported": filename})
