from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import imagesize

from ._kernel import adapter, kernel_of
from ._show_registry import kernel_tag_of, show_of
from .ocp_utils.location import (
    _axis_to_vecs,
    _checked_placement,
    _loc_to_vecs,
    _tq_to_loc,
)

if TYPE_CHECKING:
    from .types import (
        ColorLike,
        KernelShape,
        TopLoc_Location,
        TopoDS_Shape,
    )

from ocp_tessellate.defaults import get_default
from ocp_tessellate.ocp_utils import (
    IDENTITY_PLACEMENT,
    BoundingBox,
    Placement,
    VectorLike,
    axis_to_vecs,  # noqa: F401 - public via cad_objects (tests/api_surface.json)
    copy_location,  # noqa: F401 - public via cad_objects (tests/api_surface.json)
    copy_topods_shape,
    identity_location,  # noqa: F401 - public via cad_objects (tests/api_surface.json)
    is_identity,  # noqa: F401 - public via cad_objects (tests/api_surface.json)
    is_topods_shape as _is_topods_shape,
    line,
    loc_to_tq,  # noqa: F401 - public via cad_objects (tests/api_surface.json)
    loc_to_vecs,  # noqa: F401 - public via cad_objects (tests/api_surface.json)
    make_compound,
    mul_locations,
    mul_placements,
    rect,
    tq_to_loc,  # noqa: F401 - public via cad_objects (tests/api_surface.json)
)
from ocp_tessellate.types import (
    ConvertedVertices,
    DiscretizedEdges,
    Instance,
)
from ocp_tessellate.utils import Color, make_unique

UNSELECTED = 0
SELECTED = 1
EMPTY = 3

PROTOCOL_VERSION = 3

if TYPE_CHECKING:
    # Callbacks provided by tessellate_group to discretize edge and vertex leaves
    # during collect
    EdgeDiscretizer = Callable[
        [Sequence[KernelShape], str, str], tuple[DiscretizedEdges, BoundingBox]
    ]
    VertexConverter = Callable[
        [Sequence[KernelShape], str, str], tuple[ConvertedVertices, BoundingBox]
    ]


def _plain(placement: Placement | None) -> tuple | None:
    """A placement as the viewer and the backend get it: a plain tuple of tuples."""
    return None if placement is None else (placement.origin, placement.quaternion)


def _backend_shape(shape):
    """What a model entry of the measurement backend holds: an instance or the shapes of
    OCCT as they are, a kernel's shape with its tag, which `encode_kernel_shapes` serializes
    through the kernel's plugin."""
    obj = shape["obj"] if isinstance(shape, dict) else shape
    kernel = kernel_tag_of(obj)
    if kernel is None:
        return shape
    return {"kernel": kernel, "obj": obj}


def _copied_shape(shape):
    """A copy of an OCCT shape. A kernel's shape is immutable to the tree."""
    return copy_topods_shape(shape) if _is_topods_shape(shape) else shape


def _line_for(like, k):
    """What draws a helper of the object `like`: its plugin's `line`, given the
    coordinates of the vectors the helper computes with, else OCCT's."""
    show = show_of(like)
    if show is None:
        return line

    def kernel_line(start, end):
        return show.line(start=adapter(k).coord(start), end=adapter(k).coord(end))

    return kernel_line


class OcpObject:
    # set by ImageFace.to_ocp for kind "imageface" and consumed in collect
    image: str | None = None
    image_type: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    height: float | None = None

    def __init__(
        self,
        kind: str,
        obj: KernelShape | list[KernelShape] | None = None,
        ref: int | None = None,
        cache_id: str | None = None,
        name: str = "Object",
        loc: Placement | None = None,
        color: Color | ColorLike | list[Color] | tuple[Color, ...] | None = None,
        width: float | None = None,
        show_faces: bool = True,
        show_edges: bool = True,
        material: str | None = None,
    ):
        if obj is None and ref is None:
            raise ValueError("Either obj or ref must be provided")

        self.id: str | None = None
        self.obj = obj
        self.kind = kind
        self.ref = ref
        self.cache_id = cache_id
        self.name = name
        self.set_states(show_faces, show_edges)
        self.loc = loc
        # a tuple color deliberately goes through Color() unchanged: per-item
        # colors are only supported as a list, everything else is one color
        self.color: Color | list[Color] | None
        if isinstance(color, list):
            self.color = [Color(c) for c in color]
        elif color is not None:
            self.color = Color(color)
        else:
            self.color = None
        self.width = width
        self.material = material
        self.normalize_uvs = True
        self.helpers: OcpGroup | None = None

    @property
    def loc(self) -> Placement | None:
        """Where the object is in the group above it, for every kernel."""
        return self._loc

    @loc.setter
    def loc(self, loc: Placement | None) -> None:
        self._loc = _checked_placement(loc, "loc")

    def dump(self, ind: int = 0) -> str:
        if self.obj is None:
            obj_repl = f"ref={self.ref}"
        else:
            obj_repl = f"class={self.obj.__class__.__name__}"

        return (
            f"{' ' * ind}OcpObject name='{self.name}' kind={self.kind}, "
            f"{obj_repl}, "
            f"color={self.color}, loc={self.loc}, "
            f"cache_id={'' if self.cache_id is None else self.cache_id[:10]}..."
        )

    def __repr__(self):
        return self.dump()

    def copy(self) -> OcpObject:
        if self.obj is None:
            obj = None
        elif isinstance(self.obj, list):
            obj = [_copied_shape(o) for o in self.obj]
        else:
            obj = _copied_shape(self.obj)

        return OcpObject(
            self.kind,
            obj,
            self.ref,
            self.cache_id,
            self.name,
            self.loc,
            self.color,
            self.width,
            self.state_faces == SELECTED,
            self.state_edges == SELECTED,
            self.material,
        )

    def set_states(self, show_faces: bool, show_edges: bool) -> None:
        self.state_faces = SELECTED if show_faces else UNSELECTED
        self.state_edges = SELECTED if show_edges else UNSELECTED

    def to_state(self) -> list[int]:
        if self.kind in ("solid", "face"):
            return [self.state_faces, self.state_edges]
        else:
            return [EMPTY, SELECTED]

    def collect(
        self,
        path: str,
        instances: list[Instance],
        loc: Placement | None,
        discretize_edges: EdgeDiscretizer | None,
        convert_vertices: VertexConverter | None,
    ):
        self.id = f"{path}/{self.name}"
        texture = None

        combined_loc = mul_placements(loc, self.loc)

        if self.kind == "imageface":
            image = {"data": self.image, "format": self.image_type}
            texture = {"image": image, "width": self.width, "height": self.height}
            self.kind = "face"

        if self.kind in ("solid", "face", "shell"):
            # unify guarantees shape kinds are deduplicated into an instance
            # ref with a single resolved color
            assert self.ref is not None, f"'{self.name}' has no instance ref"
            assert isinstance(self.color, Color), (
                f"'{self.name}' has no resolved color"
            )
            return {"id": self.id, "shape": _backend_shape(instances[self.ref]), "loc": _plain(combined_loc)}, {
                "id": self.id,
                "type": "shapes",
                "subtype": self.kind,
                "name": self.name,
                "shape": {"ref": self.ref},
                "state": self.to_state(),
                "color": self.color.web_color,
                "alpha": self.color.a,
                "material": self.material,
                "normalize_uvs": self.normalize_uvs,
                "texture": texture,
                "loc": _plain(self.loc),
                "renderback": self.kind == "face",
                "accuracy": None,
                "bb": None,
            }

        elif self.kind in ("edge", "vertex"):
            # unify guarantees edge/vertex kinds keep their shapes and a color
            assert self.obj is not None, f"'{self.name}' has no shapes"
            assert self.color is not None, f"'{self.name}' has no color"
            convert = convert_vertices if self.kind == "vertex" else discretize_edges
            assert convert is not None, f"no converter for kind {self.kind}"
            objs = self.obj if isinstance(self.obj, (list, tuple)) else [self.obj]
            self.obj = objs
            values, bb = convert(objs, self.name, self.id)

            if isinstance(self.color, Color):
                color = self.color.web_color
            else:
                color = [c.web_color for c in self.color]

            result = (
                {"id": self.id, "shape": _backend_shape(self.obj), "loc": _plain(combined_loc)},
                {
                    "id": self.id,
                    "type": "edges" if self.kind == "edge" else "vertices",
                    "name": self.name,
                    "shape": values,
                    "state": self.to_state(),
                    "color": color,
                    "material": self.material,
                    "loc": _plain(self.loc),
                    "bb": bb,
                },
            )
            if self.kind == "edge":
                result[1]["width"] = self.width
            else:
                result[1]["size"] = self.width
            return result

        else:
            raise NotImplementedError(f"Kind {self.kind} not implemented")


class OcpGroup:
    def __init__(
        self,
        objs: list[OcpObject | OcpGroup] | None = None,
        name: str | None = "Group",
        loc: Placement | None = None,
    ):
        self.id: str | None = None
        self.objects: list[OcpObject | OcpGroup] = [] if objs is None else objs
        self.name = name
        self.kind = "group"
        self.loc = loc
        self.helpers: OcpGroup | None = None

    @property
    def loc(self) -> Placement | None:
        """Where the group is in the group above it, for every kernel."""
        return self._loc

    @loc.setter
    def loc(self, loc: Placement | None) -> None:
        self._loc = _checked_placement(loc, "loc")

    def dump(self, ind: int = 0) -> str:
        result = f"{' ' * ind}OcpGroup('{self.name}', loc={self.loc}\n"
        for obj in self.objects:
            result += obj.dump(ind + 4) + "\n"
        return result + f"{' ' * ind})"

    def __repr__(self):
        return self.dump()

    @property
    def can_be_cleaned_up(self) -> bool:
        return (
            self.name is None
            and (self.loc is None or self.loc.is_identity())
            and len(self.objects) == 1
        )

    @property
    def length(self) -> int:
        return len(self.objects)

    def add(self, *objs: OcpObject | OcpGroup) -> None:
        for obj in objs:
            self.objects.append(obj)

    def make_unique_names(self, python_enumeration: bool = False) -> OcpGroup:
        if self.length > 1:
            names = make_unique([obj.name for obj in self.objects], python_enumeration)
            for obj, name in zip(self.objects, names):
                # make_unique maps None to None, so only named objects change
                if name is not None:
                    obj.name = name
        return self

    def cleanup(self) -> OcpObject | OcpGroup:
        if self.length == 1:
            result = self.objects[0]
            result.loc = mul_placements(self.loc, result.loc)
            return result

        return self

    def to_state(self, parents=None):
        parents = parents or ()
        result = {}
        for i, obj in enumerate(self.objects):
            if isinstance(obj, OcpGroup):
                for k, v in obj.to_state((*parents, i)).items():
                    result[k] = v
            else:
                result[str(obj.id)] = obj.to_state()
        return result

    def count_shapes(self):
        def c(pg):
            count = 0
            for p in pg.objects:
                if isinstance(p, OcpGroup):
                    count += c(p)
                else:
                    count += 1
            return count

        return c(self)

    def collect(
        self,
        path: str,
        instances: list[Instance],
        loc: Placement | None = None,
        discretize_edges: EdgeDiscretizer | None = None,
        convert_vertices: VertexConverter | None = None,
    ):
        self.id = f"{path}/{self.name}"

        combined_loc = mul_placements(loc, self.loc)

        result = {
            "version": PROTOCOL_VERSION,
            "parts": [],
            "loc": _plain(self.loc),
            "name": self.name,
            "id": self.id,
        }

        map = {"parts": [], "id": self.id}

        for obj in self.objects:
            mapping, mesh = obj.collect(
                self.id, instances, combined_loc, discretize_edges, convert_vertices
            )
            result["parts"].append(mesh)
            map["parts"].append(mapping)
        return map, result


class OcpInstancesGroup:
    def __init__(self, instances: list[Instance], ocpgrp: OcpGroup):
        self.ocpgrp = ocpgrp
        self.instances = instances

    def apply_offset(self, offset: int, obj: OcpObject | OcpGroup | None = None) -> None:
        if obj is None:
            obj = self.ocpgrp
        if isinstance(obj, OcpGroup):
            for o in obj.objects:
                self.apply_offset(offset, o)
        else:
            if obj.ref is not None:
                obj.ref += offset


class OcpWrapper:
    def __init__(
        self,
        objs: Sequence[KernelShape],
        kind: str,
        name: str,
        color: Color | list[Color],
        loc: Placement | None = None,
        width: float | None = None,
        show_edges: bool = True,
        show_faces: bool = True,
    ):
        self.objs = objs
        self.kind = kind
        self.name = name
        self.color = color
        self.loc = IDENTITY_PLACEMENT if loc is None else loc
        self.width = width
        self.show_edges = show_edges
        self.show_faces = show_faces

    def to_ocp(self) -> OcpObject:
        return OcpObject(
            self.kind,
            self.objs,
            name=self.name,
            loc=self.loc,
            color=self.color,
            width=self.width,
            show_edges=self.show_edges,
            show_faces=self.show_faces,
        )


class CoordAxis(OcpWrapper):
    def __init__(
        self,
        name: str,
        origin: VectorLike,
        z_dir: VectorLike,
        color: Color | ColorLike | None = None,
        size: float = 1,
        like: object = None,
    ):
        """An axis arrow, built by the kernel of `like`, the object it depicts: with the
        `line` of its plugin, or in the binding of an OCCT object. Without `like`,
        nanocct where it is installed, else OCP.
        """
        color = Color("black") if color is None else Color(color)
        k = kernel_of(like)
        line = _line_for(like, k)
        o, x, y, z = _axis_to_vecs(k, origin, z_dir)
        # vectors of _axis_to_vecs: one binding at runtime (kernel_of / kernel_of_all); the OCP | nanocct unions cannot say so (known limit, ty in a venv with both bindings)
        edge = line(o, o + size * z)  # ty: ignore[unsupported-operator]
        f = 0.7
        dz = size * f * z
        dx = size * ((1 - f) / 4) * x
        dy = size * ((1 - f) / 4) * y
        a = [
            line(o + size * z, o + dz - dx),  # ty: ignore[unsupported-operator]
            line(o + size * z, o + dz + dx),  # ty: ignore[unsupported-operator]
            line(o + size * z, o + dz - dy),  # ty: ignore[unsupported-operator]
            line(o + size * z, o + dz + dy),  # ty: ignore[unsupported-operator]
            line(o + dz - dx, o + dz + dx),  # ty: ignore[unsupported-operator]
            line(o + dz - dy, o + dz + dy),  # ty: ignore[unsupported-operator]
            line(o + dz - dy, o + dz + dx),  # ty: ignore[unsupported-operator]
            line(o + dz - dy, o + dz - dx),  # ty: ignore[unsupported-operator]
            line(o + dz + dy, o + dz + dx),  # ty: ignore[unsupported-operator]
            line(o + dz + dy, o + dz - dx),  # ty: ignore[unsupported-operator]
        ]

        super().__init__([edge] + a, "edge", name, color, width=2)


class CoordSystem(OcpWrapper):
    def __init__(
        self,
        name: str,
        origin: VectorLike,
        x_dir: VectorLike,
        z_dir: VectorLike,
        size: float = 1,
        like: object = None,
    ):
        """A coordinate system, built by the kernel of `like`, the object it depicts: with
        the `line` of its plugin, or in the binding of an OCCT object. Without `like`,
        nanocct where it is installed, else OCP.
        """
        k = kernel_of(like)
        line = _line_for(like, k)
        o, x, y, z = _loc_to_vecs(k, origin, x_dir, z_dir)
        # vectors of _loc_to_vecs: one binding at runtime (kernel_of / kernel_of_all); the OCP | nanocct unions cannot say so (known limit, ty in a venv with both bindings)
        x_edge = line(o, o + size * x)  # ty: ignore[unsupported-operator]
        y_edge = line(o, o + size * y)  # ty: ignore[unsupported-operator]
        z_edge = line(o, o + size * z)  # ty: ignore[unsupported-operator]

        colors = [Color("red"), Color("green"), Color("blue")]
        super().__init__([x_edge, y_edge, z_edge], "edge", name, colors, width=2)


class ImageFace(OcpWrapper):
    def __init__(
        self,
        image_path: str,
        scale: float | tuple[float, float] = 1.0,
        origin_pixels: tuple[float, float] = (0, 0),
        location=None,
        name: str = "ImageFace",
    ):
        self.image_width, self.image_height = imagesize.get(image_path)
        x = origin_pixels[0]
        y = self.image_height - origin_pixels[1]

        if isinstance(scale, (int, float)):
            scale = (scale, scale)

        ws = self.image_width * scale[0]
        hs = self.image_height * scale[1]
        xs = x * scale[0]
        ys = y * scale[1]

        loc = location.wrapped if hasattr(location, "wrapped") else location
        # the face in the binding of the location, kernel() without one
        k = kernel_of(loc)
        plane = rect(ws, hs, k.gp.gp_Ax3())
        o = _tq_to_loc(k, (ws / 2 - xs, hs / 2 - ys, 0), (0, 0, 0, 1))
        placed = mul_locations(loc, o)
        assert placed is not None, "o is a location"

        super().__init__(
            [plane], "imageface", name, Color("white"), show_edges=True, loc=Placement.from_occt(placed)
        )

        with open(image_path, "rb") as f:
            self.image = base64.b64encode(f.read()).decode("utf-8")
            self.image_type = image_path.split(".")[-1]

        self.width = ws
        self.height = hs

    def to_ocp(self) -> OcpObject:
        result = super().to_ocp()
        result.image = self.image
        result.image_type = self.image_type
        result.image_width = self.image_width
        result.image_height = self.image_height
        result.width = self.width
        result.height = self.height
        return result


class OCP_Part(OcpWrapper):
    def __init__(
        self,
        shape: TopoDS_Shape,
        name: str = "Part",
        color: Color | None = None,
        show_faces: bool = True,
        show_edges: bool = True,
    ):
        if color is None:
            color = Color(get_default("default_color"))

        super().__init__(
            [shape], "solid", name, color, show_faces=show_faces, show_edges=show_edges
        )


class OCP_Faces(OCP_Part):
    def __init__(
        self,
        faces: list[TopoDS_Shape],
        name: str = "Faces",
        color: Color | None = None,
        show_faces: bool = True,
        show_edges: bool = True,
    ):
        if color is None:
            color = Color("Violet")
        obj = make_compound(faces)
        super().__init__(obj, name, color, show_faces, show_edges)


class OCP_Edges(OcpWrapper):
    def __init__(
        self,
        edges: list[TopoDS_Shape],
        name: str = "Edges",
        color: Color | list[Color] | None = None,
        width: float = 1,
    ):
        if color is None:
            color = Color("MediumOrchid")
        super().__init__(edges, "edge", name, color, width=width)
        self.width = 2


class OCP_Vertices(OcpWrapper):
    def __init__(
        self,
        vertices: list[TopoDS_Shape],
        name: str = "Vertices",
        color: Color | None = None,
        size: float = 1,
    ):
        if color is None:
            color = Color("MediumOrchid")
        super().__init__(vertices, "vertex", name, color, width=size)
        self.width = 6


class OCP_PartGroup(list):
    def __init__(
        self,
        objects: list[OcpWrapper],
        name: str = "Group",
        loc: TopLoc_Location | None = None,
    ):
        super().__init__(objects)
        self.objs = objects
        self.loc = loc
        self.name = name
        # _index, not index, to avoid shadowing list.index
        self._index = 0

    def __iter__(self):
        self._index = 0
        return self

    def __next__(self) -> OcpWrapper:
        if self._index < len(self.objs):
            result = self.objs[self._index]
            self._index += 1
            return result
        else:
            raise StopIteration

    def __getitem__(self, i):
        return self.objs[i]

    def __len__(self) -> int:
        return len(self.objs)
