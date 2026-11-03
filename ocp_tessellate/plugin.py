"""The building blocks of a kernel plugin: objects of a kernel other than OCCT,
shown through the regular pipeline (docs/ExternalKernel.md).

A plugin writes `tessellate`, `discretize_edges`, `bounding_box` and `convert`
for its kernel and a show function; `convert` builds `OcpExternalObject`s with
`external_tessellate`, `external_edges`, `external_coord_system` and
`external_coord_axis`, and the show function hands `external_scene` to the
host's `show`. `SURFACE_TYPES` and `CURVE_TYPES` are the type codes of a
Tessellation by name.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
from cachetools import cached

from ocp_tessellate._kernel import kernel
from ocp_tessellate.cad_objects import SELECTED, OcpObject
from ocp_tessellate.ocp_utils import (
    BoundingBox,
    copy_location,
    mul_locations as _mul_locations,
)
from ocp_tessellate.tessellator import (
    cache as _tessellation_cache,
    make_key as _make_key,
)
from ocp_tessellate.types import ConvertedVertices, DiscretizedEdges, ExternalInstance
from ocp_tessellate.utils import Color

if TYPE_CHECKING:
    from .types import ColorLike, Tessellation

__all__ = [
    "CURVE_TYPES",
    "SURFACE_TYPES",
    "OcpExternalObject",
    "external_coord_axis",
    "external_coord_system",
    "external_edges",
    "external_scene",
    "external_tessellate",
]


class OcpExternalObject(OcpObject):
    """An object of another kernel than OCCT, with what meshes it.

    A solid, face or shell brings `tessellate(deviation, quality,
    angular_tolerance, compute_edges, progress) -> Tessellation`, its
    `bounding_box` (a BoundingBox) and a `cache_id`; an edge brings
    `discretize_edges(deviation, edge_accuracy, helper_scale) ->
    (DiscretizedEdges, BoundingBox)`; a vertex brings its `points`, the
    coordinates (n, 3). OcpConverter.to_ocp registers the instance of a solid,
    face or shell (its `ref`), sets `helper_scale`, and gives an object without
    a color the default of its kind.

    A solid, face or shell with a `kernel` tag and its `body` has an entry in the
    measurement backend's model, `{"id", "shape": {"kernel": kernel, "obj": body},
    "loc"}`: ocp_viewer_core's backend hands it to the plugin registered under
    the tag, which serializes the body before the model is sent and measures it
    there. Without a tag the object has no entry. See docs/ExternalKernel.md.
    """

    def __init__(
        self,
        kind: str,
        name: str,
        *,
        tessellate: Callable[..., Tessellation] | None = None,
        bounding_box: BoundingBox | None = None,
        cache_id: str | None = None,
        discretize_edges: Callable[..., tuple[DiscretizedEdges, BoundingBox]] | None = None,
        points: object = None,
        color: Color | ColorLike | list[Color] | tuple[Color, ...] | None = None,
        width: float | None = None,
        show_faces: bool = True,
        show_edges: bool = True,
        material: str | None = None,
        kernel: str | None = None,
        body: object = None,
    ):
        if kind in ("solid", "face", "shell"):
            if tessellate is None or bounding_box is None or cache_id is None:
                raise ValueError(f"an external {kind} needs tessellate, bounding_box and cache_id")
            if kernel is not None and body is None:
                raise ValueError(f"an external {kind} with the kernel tag '{kernel}' needs its body")
        elif kernel is not None:
            raise ValueError(f"only a solid, face or shell is measured by its kernel, not a {kind}")
        elif kind == "edge":
            if discretize_edges is None:
                raise ValueError("an external edge needs discretize_edges")
            if width is None:
                width = 2  # convert.LINE_WIDTH
        elif kind == "vertex":
            if points is None:
                raise ValueError("an external vertex needs points")
            if width is None:
                width = 6  # convert.POINT_SIZE
        else:
            raise ValueError(f"an external object is a solid, face, shell, edge or vertex, not a {kind}")
        # the object stands in for the OCCT shape: `collect` hands it to the
        # converters of tessellate_group, which ask it for its segments or points
        super().__init__(
            kind,
            obj=self,
            cache_id=cache_id,
            name=name,
            color=color,
            width=width,
            show_faces=show_faces,
            show_edges=show_edges,
            material=material,
        )
        self.tessellate = tessellate
        self.bounding_box = bounding_box
        self.discretize_edges = discretize_edges
        self.points = None if points is None else np.asarray(points, dtype=np.float32).reshape(-1, 3)
        self.helper_scale: float = 1.0  # set by OcpConverter.to_ocp
        # the measurement backend's entry: the plugin's kernel tag and the body it measures
        self.kernel = kernel
        self.body = body

    @property
    def is_instance(self) -> bool:
        """Whether this is a solid, face or shell: an instance to register and tessellate."""
        return self.kind in ("solid", "face", "shell")

    def instance(self) -> ExternalInstance:
        assert self.cache_id is not None, f"'{self.name}' has no cache_id"
        return {"obj": self, "cache_id": self.cache_id, "name": self.name}

    def vertices(self) -> tuple[ConvertedVertices, BoundingBox]:
        """The points of a vertex leaf as the pipeline wants them, with their box."""
        assert self.points is not None, f"'{self.name}' has no points"
        return {"obj_vertices": self.points.ravel()}, _points_box(self.points)

    def copy(self) -> OcpExternalObject:
        result = OcpExternalObject(
            self.kind,
            self.name,
            tessellate=self.tessellate,
            bounding_box=self.bounding_box,
            cache_id=self.cache_id,
            discretize_edges=self.discretize_edges,
            points=self.points,
            color=self.color,  # a Color, a list of Colors (one per edge) or None
            width=self.width,
            show_faces=self.state_faces == SELECTED,
            show_edges=self.state_edges == SELECTED,
            material=self.material,
            kernel=self.kernel,
            body=self.body,
        )
        result.ref = self.ref
        result.loc = copy_location(self.loc)
        result.helper_scale = self.helper_scale
        return result

    def collect(self, path, instances, loc, discretize_edges, convert_vertices):
        if self.is_instance:
            assert self.ref is not None, f"'{self.name}' is not registered (OcpConverter.to_ocp does that)"
        _, mesh = super().collect(path, instances, loc, discretize_edges, convert_vertices)
        if self.is_instance and mesh["loc"] is None:
            # at the origin: an identity, which the viewer applies to a shape
            mesh["loc"] = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        if self.kernel is None:
            # no entry in the backend's model: nothing would measure it
            return None, mesh
        # the backend's entry, placed as an OCCT instance is (OcpObject.collect):
        # by the locations of the groups above and the object's own
        if loc is None:
            combined_loc = self.loc
        elif self.loc is None:
            combined_loc = loc
        else:
            combined_loc = _mul_locations(loc, self.loc)
        return {"id": self.id, "shape": {"kernel": self.kernel, "obj": self.body}, "loc": combined_loc}, mesh


def _geomabs_values(enum, names):
    """The values of the GeomAbs enum members `GeomAbs_<name>` by name, as plain
    ints (the members are int-like enums in one binding, enums with a value in
    the other)."""
    values = {}
    for name in names:
        member = getattr(enum, f"GeomAbs_{name}")
        values[name] = int(getattr(member, "value", member))
    return values


# The type codes of faces and edges in a Tessellation: the values of OCCT's
# GeomAbs_SurfaceType and GeomAbs_CurveType by name, read from the binding, for
# kernels that are not OCCT (get_face_type and get_edge_type read them off OCCT
# shapes).
SURFACE_TYPES: dict[str, int] = _geomabs_values(
    kernel().GeomAbs.GeomAbs_SurfaceType,
    [
        "Plane",
        "Cylinder",
        "Cone",
        "Sphere",
        "Torus",
        "BezierSurface",
        "BSplineSurface",
        "SurfaceOfRevolution",
        "SurfaceOfExtrusion",
        "OffsetSurface",
        "OtherSurface",
    ],
)
CURVE_TYPES: dict[str, int] = _geomabs_values(
    kernel().GeomAbs.GeomAbs_CurveType,
    [
        "Line",
        "Circle",
        "Ellipse",
        "Hyperbola",
        "Parabola",
        "BezierCurve",
        "BSplineCurve",
        "OffsetCurve",
        "OtherCurve",
    ],
)


def _points_box(points) -> BoundingBox:
    """The BoundingBox of points (n, 3)."""
    flat = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    lo, hi = flat.min(axis=0), flat.max(axis=0)
    return BoundingBox({
        "xmin": float(lo[0]), "xmax": float(hi[0]),
        "ymin": float(lo[1]), "ymax": float(hi[1]),
        "zmin": float(lo[2]), "zmax": float(hi[2]),
    })


def _external_color(obj, color, alpha) -> Color | None:
    """A given color, else the object's own `color` attribute (as
    get_color_for_object reads it), else None for the default of the kind."""
    own = getattr(obj, "color", None)
    if color is not None:
        c = Color(color)
    elif own is not None:
        c = Color(own)
    else:
        return None
    if alpha is not None:
        c.a = alpha
    return c


@cached(_tessellation_cache, key=lambda *args, tessellate=None, **kwargs: _make_key(*args, **kwargs))
def _tessellate_external(
    body, cache_key, deviation, quality, angular_tolerance, compute_edges=True,
    compute_faces=True, debug=False, progress=None, shape_id="", *, tessellate,
):
    """A kernel's `tessellate(body, quality, angular_tolerance, compute_edges)` in
    the OCCT tessellator's cache, keyed as make_key keys OCCT shapes (cache_key,
    deviation, angular_tolerance, compute_edges, ...); a hit reports "c"."""
    if progress is not None:
        progress.update("+")
    return tessellate(body, quality, angular_tolerance, compute_edges)


def external_tessellate(
    kind, name, body, tessellate, bounding_box, cache_id=None, color=None, alpha=None, kernel=None
) -> OcpExternalObject:
    """A solid, face or shell of another kernel as an OcpExternalObject: `body` is
    the kernel's object, `tessellate(body, quality, angular_tolerance,
    compute_edges) -> Tessellation` the kernel's tessellator, `bounding_box` its
    BoundingBox. With a `cache_id`, a string that identifies the geometry, the
    tessellation goes through the OCCT tessellator's cache; without one it is
    computed at every show. The color is `color`, else the body's own `color`
    attribute, else the host's default of the kind. With a `kernel` tag the body
    is measured by the backend plugin registered under it (ocp_viewer_core)."""

    def tessellate_body(deviation, quality, angular_tolerance, compute_edges=True, progress=None):
        if cache_id is None:
            if progress is not None:
                progress.update("+")
            return tessellate(body, quality, angular_tolerance, compute_edges)
        return _tessellate_external(
            body, cache_id, deviation, quality, angular_tolerance,
            compute_edges=compute_edges, progress=progress, tessellate=tessellate,
        )

    return OcpExternalObject(
        kind, name, tessellate=tessellate_body, bounding_box=bounding_box,
        cache_id=cache_id if cache_id is not None else f"uncached-{id(body)}",
        color=_external_color(body, color, alpha),
        kernel=kernel,
        body=None if kernel is None else body,
    )


def external_edges(name, edges, discretize_edges, color=None, alpha=None) -> OcpExternalObject:
    """Edges of another kernel as an OcpExternalObject: `edges` is what the
    kernel's `discretize_edges(edges, deviation, edge_accuracy) ->
    DiscretizedEdges` takes; the leaf's bounding box is that of the segments."""

    def discretize(deviation, edge_accuracy=None, helper_scale=1.0):
        values = discretize_edges(edges, deviation, edge_accuracy)
        return values, _points_box(values["edges"])

    return OcpExternalObject("edge", name, discretize_edges=discretize, color=_external_color(edges, color, alpha))


def _aligned(values, count, what):
    """`values` as a list of `count` entries, None for all when None is given."""
    if values is None:
        return [None] * count
    values = list(values)
    if len(values) != count:
        raise ValueError(f"Length of {what} does not match the number of objects")
    return values


def external_scene(objects, convert, names=None, colors=None, alphas=None):
    """The scene of a kernel plugin, what its show function hands to the host's
    `show`: every object converted by the kernel's `convert(obj, name, color,
    alpha)` (an OcpExternalObject or an OcpGroup), with `names`, `colors` and
    `alphas` aligned to the objects as `show` aligns them. Returns the scene and
    the three aligned lists, to be passed on to `show`.

    The host's `show` reads a `color` attribute of every object it is given and
    makes a Color of it; a coordinate system carries a list of colors, which
    Color() cannot take, so its first color is named in the returned `colors`
    instead (the object keeps its own, the pipeline ignores the list entry for a
    prebuilt object)."""
    count = len(objects)
    names = _aligned(names, count, "names")
    colors = _aligned(colors, count, "colors")
    alphas = _aligned(alphas, count, "alphas")
    scene = []
    for i, (obj, name, color, alpha) in enumerate(zip(objects, names, colors, alphas)):
        item = convert(obj, name if name is not None else f"shape{i}", color, alpha)
        if isinstance(item, OcpExternalObject) and isinstance(item.color, list) and color is None:
            colors[i] = item.color[0]
        scene.append(item)
    return scene, names, colors, alphas


def _external_edges(name, pairs_at, color):
    """An OcpExternalObject of straight segments, built at the helper scale the
    pipeline hands in: `pairs_at(size)` gives the segments as (start, end) pairs."""

    def discretize_edges(deviation, edge_accuracy=None, helper_scale=1.0):
        pts = np.asarray(pairs_at(helper_scale), dtype=np.float32).reshape(-1, 2, 3)
        values = {
            "edges": pts.ravel(),
            "segments_per_edge": np.ones(len(pts), dtype=np.int32),
            "edge_types": np.zeros(len(pts), dtype=np.int32),
            "obj_vertices": pts.reshape(-1, 3).ravel(),
        }
        return values, _points_box(pts)

    return OcpExternalObject("edge", name, discretize_edges=discretize_edges, color=color, width=2)


def _occt_x_direction(z):
    """The X direction OCCT's gp_Ax3(P, N) picks for a normal N: from N's smallest
    component (gp_Ax2's rule), so that external arrows match CoordAxis."""
    a, b, c = z
    aa, ba, ca = abs(a), abs(b), abs(c)
    if ba <= aa and ba <= ca:
        x = np.array([-c, 0.0, a]) if aa > ca else np.array([c, 0.0, -a])
    elif aa <= ba and aa <= ca:
        x = np.array([0.0, -c, b]) if ba > ca else np.array([0.0, c, -b])
    else:
        x = np.array([-b, a, 0.0]) if aa > ba else np.array([b, -a, 0.0])
    return x / np.linalg.norm(x)


def external_coord_system(name, origin, x_dir, z_dir):
    """A coordinate system as an OcpExternalObject, for a location or plane of
    another kernel: its x, y and z axes as one-segment edges in red, green and
    blue, of the length `helper_scale` the pipeline resolves (what CoordSystem
    draws for OCCT, without OCCT geometry)."""
    o, x, z = (np.asarray(v, dtype=np.float64) for v in (origin, x_dir, z_dir))
    x, z = x / np.linalg.norm(x), z / np.linalg.norm(z)
    y = np.cross(z, x)

    def pairs_at(size):
        return [(o, o + size * x), (o, o + size * y), (o, o + size * z)]

    return _external_edges(name, pairs_at, [Color("red"), Color("green"), Color("blue")])


def external_coord_axis(name, origin, direction, color=None):
    """An axis arrow as an OcpExternalObject, for an axis of another kernel: the
    shaft of length `helper_scale` and the ten segments of a pyramid head at 70 %
    of it, black by default (what CoordAxis draws for OCCT, the same points)."""
    o, z = np.asarray(origin, dtype=np.float64), np.asarray(direction, dtype=np.float64)
    z = z / np.linalg.norm(z)
    x = _occt_x_direction(z)
    y = np.cross(z, x)

    def pairs_at(size):
        f = 0.7
        tip, dz = o + size * z, o + size * f * z
        dx, dy = size * ((1 - f) / 4) * x, size * ((1 - f) / 4) * y
        return [
            (o, tip),
            (tip, dz - dx), (tip, dz + dx), (tip, dz - dy), (tip, dz + dy),
            (dz - dx, dz + dx), (dz - dy, dz + dy), (dz - dy, dz + dx), (dz - dy, dz - dx),
            (dz + dy, dz + dx), (dz + dy, dz - dx),
        ]

    return _external_edges(name, pairs_at, Color("black") if color is None else Color(color))
