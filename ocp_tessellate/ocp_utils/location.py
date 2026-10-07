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
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, overload

import numpy as np
from numpy.typing import ArrayLike

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
    return loc1 * loc2


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
    k = kernel()
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
    k = kernel()
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
