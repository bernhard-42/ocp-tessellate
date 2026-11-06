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


"""Locations, axes and their conversions."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal, NamedTuple, Protocol, TypedDict, overload

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .._kernel import adapter, kernel, kernel_of

if TYPE_CHECKING:
    from types import ModuleType

    from ..types import (
        TopLoc_Location,
        TopoDS_Shape,
        gp_Ax1,
        gp_Pln,
        gp_Vec,
    )

from .predicates import (
    is_toploc_location,
    is_topods_shape,
    is_wrapped,
)
from .topology import copy_topods_shape, get_tshape


class VectorLike(Protocol):
    def __iter__(self) -> Iterator[float]: ...


def tq_to_loc(
    t: tuple[float, float, float], q: tuple[float, float, float, float]
) -> TopLoc_Location:
    return _tq_to_loc(kernel(), t, q)


def _tq_to_loc(
    k: ModuleType, t: tuple[float, float, float], q: tuple[float, float, float, float]
) -> TopLoc_Location:
    """tq_to_loc in binding k, for a location that goes with an OCCT object."""
    T = k.gp.gp_Trsf()
    Q = k.gp.gp_Quaternion(*q)
    V = k.gp.gp_Vec(*t)
    T.SetTransformation(Q, V)
    return k.TopLoc.TopLoc_Location(T)


@overload
def loc_to_tq(
    loc: TopLoc_Location,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]: ...
@overload
def loc_to_tq(loc: None) -> tuple[None, None]: ...
def loc_to_tq(
    loc: TopLoc_Location | None,
) -> (
    tuple[tuple[float, float, float], tuple[float, float, float, float]]
    | tuple[None, None]
):
    if loc is None:
        return (None, None)

    T = loc.Transformation()
    t = T.TranslationPart()
    q = T.GetRotation()
    return ((t.X(), t.Y(), t.Z()), (q.X(), q.Y(), q.Z(), q.W()))


def identity_location() -> TopLoc_Location:
    k = kernel()
    loc = k.TopLoc.TopLoc_Location()
    k.TopLoc.TopLoc_Location.Identity(loc)
    return loc


class Placement(NamedTuple):
    """Where an object is, as plain numbers: what the tree of OcpObjects and OcpGroups
    holds for every kernel, and what the viewer and the backend get as a tuple."""

    origin: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]  # x, y, z, w

    @classmethod
    def from_axes(
        cls,
        origin: tuple[float, float, float],
        x_dir: tuple[float, float, float],
        z_dir: tuple[float, float, float],
    ) -> Placement:
        """The placement of a frame given by its directions, for a kernel without
        quaternions. As in CoordSystem, y is `z x x`, and z wins over an x that is not
        orthogonal to it."""
        z = np.asarray(z_dir, dtype=np.float64)
        x = np.asarray(x_dir, dtype=np.float64)
        if np.linalg.norm(z) == 0:
            raise ValueError("Placement.from_axes: z_dir has no length")
        if np.linalg.norm(x) == 0:
            raise ValueError("Placement.from_axes: x_dir has no length")
        z = z / np.linalg.norm(z)
        y = np.cross(z, x)
        if np.linalg.norm(y) < 1e-12:
            raise ValueError("Placement.from_axes: x_dir and z_dir are parallel")
        y = y / np.linalg.norm(y)
        x = np.cross(y, z)
        m = np.column_stack((x, y, z))

        # the rotation matrix as a quaternion, from its largest component, which stays
        # exact at rotations of 180 degrees
        trace = np.trace(m)
        if trace > 0:
            s = 2 * np.sqrt(1 + trace)
            q = ((m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, s / 4)
        else:
            i = int(np.argmax(np.diag(m)))
            j, k = (i + 1) % 3, (i + 2) % 3
            s = 2 * np.sqrt(1 + m[i, i] - m[j, j] - m[k, k])
            v = np.zeros(4)
            v[i] = s / 4
            v[j] = (m[j, i] + m[i, j]) / s
            v[k] = (m[k, i] + m[i, k]) / s
            v[3] = (m[k, j] - m[j, k]) / s
            q = tuple(v)
        return cls(
            (float(origin[0]), float(origin[1]), float(origin[2])),
            (float(q[0]), float(q[1]), float(q[2]), float(q[3])),
        )

    @classmethod
    def from_occt(cls, loc: TopLoc_Location) -> Placement:
        """The placement of an OCCT location, of either binding."""
        if loc is None:
            raise TypeError("Placement.from_occt: no location given")
        return cls(*loc_to_tq(loc))

    def mul(self, other: Placement | None) -> Placement:
        """`self * other`: other in the frame of self. A missing other acts as identity."""
        if other is None:
            return self
        rotated = _rotated(self.quaternion, other.origin)
        origin = (
            self.origin[0] + rotated[0],
            self.origin[1] + rotated[1],
            self.origin[2] + rotated[2],
        )
        return Placement(origin, _mul_quaternions(self.quaternion, other.quaternion))

    def inverted(self) -> Placement:
        x, y, z, w = self.quaternion
        conjugate = (-x, -y, -z, w)
        ox, oy, oz = _rotated(conjugate, self.origin)
        return Placement((-ox, -oy, -oz), conjugate)

    def is_identity(self) -> bool:
        return self == IDENTITY_PLACEMENT

    def matrix(self) -> NDArray[np.float64]:
        """The rigid motion `P' = R P + t` as a 4 x 4 matrix, for a kernel that places
        objects by one."""
        (tx, ty, tz), (x, y, z, w) = self
        return np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), tx],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), ty],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), tz],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )


IDENTITY_PLACEMENT = Placement((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def _checked_placement(value: object, what: str) -> Placement | None:
    """`value` as it is, if it is a Placement or None: the one type of location in the tree."""
    if value is None or isinstance(value, Placement):
        return value
    raise TypeError(f"{what} must be a Placement or None, not {type(value).__name__}")


def _checked_plugin_placement(value: object, what: str) -> Placement | None:
    """`value` as it is, if it is a placement the viewer can use: what a kernel plugin returned
    is not known to be one. Not for the tree's own `.loc`, which every object sets."""
    placement = _checked_placement(value, what)
    if placement is None:
        return None
    origin, quaternion = placement
    if len(origin) != 3 or len(quaternion) != 4:
        raise ValueError(f"{what} must have an origin of 3 and a quaternion of 4 numbers, not {placement!r}")
    x, y, z, w = quaternion
    if abs(x * x + y * y + z * z + w * w - 1.0) > 1e-6:
        raise ValueError(f"{what} must have a unit quaternion, not {placement!r}")
    return placement


def _mul_quaternions(a, b) -> tuple[float, float, float, float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _rotated(q, v) -> tuple[float, float, float]:
    x, y, z, w = q
    px, py, pz = v
    # v + 2 w (q x v) + 2 q x (q x v)
    cx, cy, cz = y * pz - z * py, z * px - x * pz, x * py - y * px
    return (
        px + 2 * (w * cx + y * cz - z * cy),
        py + 2 * (w * cy + z * cx - x * cz),
        pz + 2 * (w * cz + x * cy - y * cx),
    )


def mul_placements(a: Placement | None, b: Placement | None) -> Placement | None:
    """`a * b` where a may be missing too, which a method cannot take: a missing placement
    acts as identity."""
    if a is None:
        return b
    return a.mul(b)


def is_identity(loc: TopLoc_Location | None) -> bool:
    # a missing location acts as identity everywhere (see OcpObject.collect)
    if loc is None:
        return True
    return loc.IsIdentity()


def relocate(obj: TopoDS_Shape) -> tuple[TopoDS_Shape, TopLoc_Location]:
    loc = get_location(obj)

    if loc is None:
        return obj, kernel_of(obj).TopLoc.TopLoc_Location()

    obj2 = copy_topods_shape(obj)

    tshape = get_tshape(obj2)
    obj2.Move(loc.Inverted())
    obj2.TShape(tshape)

    return obj2, loc


def _call_if_callable(value: object) -> object:
    """cadquery exposes some locations as zero-argument methods."""
    if callable(value):
        # duck-typed zero-argument call, ty cannot know the signature
        return value()  # ty: ignore[call-top-callable]
    return value


@overload
def get_location(
    obj: object, as_none: Literal[True] = ...
) -> TopLoc_Location | None: ...
@overload
def get_location(obj: object, as_none: Literal[False]) -> TopLoc_Location: ...
def get_location(obj: object, as_none: bool = True) -> TopLoc_Location | None:
    if obj is None:
        return None if as_none else identity_location()

    loc: object = getattr(obj, "loc", None)
    if loc is None:
        if hasattr(obj, "location"):
            loc = _call_if_callable(obj.location)

        elif hasattr(obj, "to_location"):
            loc = _call_if_callable(obj.to_location)

        elif is_wrapped(obj) and hasattr(obj.wrapped, "Location"):
            loc = _call_if_callable(obj.wrapped.Location)

        elif is_toploc_location(obj):
            return obj

        elif is_topods_shape(obj):
            loc = obj.Location()

        else:
            return None if as_none else identity_location()

    if is_wrapped(loc):
        loc = loc.wrapped
    if is_toploc_location(loc):
        return loc
    raise TypeError(f"Unknown location typ {type(loc)}")


def mul_locations(
    loc1: TopLoc_Location | None, loc2: TopLoc_Location | None
) -> TopLoc_Location | None:
    if loc1 is None:
        return loc2
    if loc2 is None:
        return loc1
    if kernel_of(loc1) is not kernel_of(loc2):
        # ocp_tessellate creates no locations of its own above the user's objects,
        # and a CAD object and its children share one binding: this is a bug
        raise TypeError(
            f"locations of two bindings: {type(loc1).__module__} and {type(loc2).__module__}"
        )
    # checked above: one binding at runtime (kernel_of / kernel_of_all); the OCP | nanocct unions cannot say so (known limit, ty in a venv with both bindings)
    return loc1 * loc2  # ty: ignore[unsupported-operator]


def copy_location(loc: TopLoc_Location | None) -> TopLoc_Location | None:
    k = kernel_of(loc)
    if loc is None:
        return None
    return k.TopLoc.TopLoc_Location(loc.Transformation())


class AxisCoord(TypedDict):
    origin: tuple[float, float, float]
    z_dir: tuple[float, float, float]


def get_axis_coord(axis: gp_Ax1) -> AxisCoord:
    k = kernel_of(axis)
    return {
        "origin": adapter(k).coord(axis.Location()),
        "z_dir": adapter(k).coord(axis.Direction()),
    }


class LocationCoord(TypedDict):
    origin: tuple[float, float, float]
    x_dir: tuple[float, float, float]
    y_dir: tuple[float, float, float]
    z_dir: tuple[float, float, float]


def get_location_coord(loc: TopLoc_Location) -> LocationCoord:
    k = kernel_of(loc)
    trsf = loc.Transformation()

    origin = trsf.TranslationPart()
    q = trsf.GetRotation()

    x_dir = q * k.gp.gp_Vec(1, 0, 0)
    y_dir = q * k.gp.gp_Vec(0, 1, 0)
    z_dir = q * k.gp.gp_Vec(0, 0, 1)

    return {
        "origin": adapter(k).coord(origin),
        "x_dir": adapter(k).coord(x_dir),
        "y_dir": adapter(k).coord(y_dir),
        "z_dir": adapter(k).coord(z_dir),
    }


def loc_to_vecs(
    origin: VectorLike, x_dir: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    return _loc_to_vecs(kernel(), origin, x_dir, z_dir)


def _loc_to_vecs(
    k: ModuleType, origin: VectorLike, x_dir: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    """loc_to_vecs in binding k, for vectors that go with an OCCT object."""
    ax3 = k.gp.gp_Ax3(k.gp.gp_Pnt(*origin), k.gp.gp_Dir(*z_dir), k.gp.gp_Dir(*x_dir))
    o = k.gp.gp_Vec(ax3.Location().XYZ())
    x = k.gp.gp_Vec(ax3.XDirection().XYZ())
    y = k.gp.gp_Vec(ax3.YDirection().XYZ())
    z = k.gp.gp_Vec(ax3.Direction().XYZ())
    return (o, x, y, z)


def loc_from_gp_pln(pln: gp_Pln) -> TopLoc_Location:
    k = kernel_of(pln)
    o = pln.Location()
    x = pln.XAxis().Direction()
    z = pln.Axis().Direction()

    ax3 = k.gp.gp_Ax3(o, z, x)
    trsf = k.gp.gp_Trsf()
    trsf.SetTransformation(ax3)
    trsf.Invert()
    return k.TopLoc.TopLoc_Location(trsf)


def axis_to_vecs(
    origin: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    return _axis_to_vecs(kernel(), origin, z_dir)


def _axis_to_vecs(
    k: ModuleType, origin: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    """axis_to_vecs in binding k, for vectors that go with an OCCT object."""
    ax3 = k.gp.gp_Ax3(k.gp.gp_Pnt(*origin), k.gp.gp_Dir(*z_dir))
    o = k.gp.gp_Vec(ax3.Location().XYZ())
    x = k.gp.gp_Vec(ax3.XDirection().XYZ())
    y = k.gp.gp_Vec(ax3.YDirection().XYZ())
    z = k.gp.gp_Vec(ax3.Direction().XYZ())
    return (o, x, y, z)


def rotate(q: tuple[float, float, float, float], v: ArrayLike) -> np.ndarray:
    x, y, z, w = q
    x2 = 2 * x * x
    y2 = 2 * y * y
    z2 = 2 * z * z
    xy = 2 * x * y
    xz = 2 * x * z
    yz = 2 * y * z
    xw = 2 * x * w
    yw = 2 * y * w
    zw = 2 * z * w

    R = np.array([
        [1 - y2 - z2, xy - zw, xz + yw],
        [xy + zw, 1 - x2 - z2, yz - xw],
        [xz - yw, yz + xw, 1 - x2 - y2],
    ])
    return np.dot(v, R.T)
