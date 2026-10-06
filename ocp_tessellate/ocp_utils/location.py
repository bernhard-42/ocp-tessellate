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

from collections.abc import Iterator
from typing import Literal, Protocol, TypedDict, overload

import numpy as np
from numpy.typing import ArrayLike

from OCP.gp import (
    gp_Ax1,
    gp_Ax3,
    gp_Dir,
    gp_Pln,
    gp_Pnt,
    gp_Quaternion,
    gp_Trsf,
    gp_Vec,
)
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape

from .predicates import is_topods_shape, is_wrapped
from .topology import copy_topods_shape, get_tshape


class VectorLike(Protocol):
    def __iter__(self) -> Iterator[float]: ...


def tq_to_loc(
    t: tuple[float, float, float], q: tuple[float, float, float, float]
) -> TopLoc_Location:
    T = gp_Trsf()
    Q = gp_Quaternion(*q)
    V = gp_Vec(*t)
    T.SetTransformation(Q, V)
    return TopLoc_Location(T)


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
    loc = TopLoc_Location()
    TopLoc_Location.Identity(loc)
    return loc


def is_identity(loc: TopLoc_Location | None) -> bool:
    # a missing location acts as identity everywhere (see OcpObject.collect)
    if loc is None:
        return True
    return loc.IsIdentity()


def relocate(obj: TopoDS_Shape) -> tuple[TopoDS_Shape, TopLoc_Location]:
    loc = get_location(obj)

    if loc is None:
        return obj, identity_location()

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

    loc: object
    if getattr(obj, "loc", None) is not None:
        loc = getattr(obj, "loc")

    elif hasattr(obj, "location"):
        loc = _call_if_callable(getattr(obj, "location"))

    elif hasattr(obj, "to_location"):
        loc = _call_if_callable(getattr(obj, "to_location"))

    elif is_wrapped(obj) and hasattr(obj.wrapped, "Location"):
        loc = _call_if_callable(getattr(obj.wrapped, "Location"))

    elif isinstance(obj, TopLoc_Location):
        return obj

    elif is_topods_shape(obj):
        loc = obj.Location()

    else:
        return None if as_none else identity_location()

    if is_wrapped(loc):
        loc = loc.wrapped
    if isinstance(loc, TopLoc_Location):
        return loc
    raise TypeError(f"Unknown location typ {type(loc)}")


def mul_locations(
    loc1: TopLoc_Location | None, loc2: TopLoc_Location | None
) -> TopLoc_Location | None:
    if loc1 is None:
        return loc2
    if loc2 is None:
        return loc1
    return loc1 * loc2


def copy_location(loc: TopLoc_Location | None) -> TopLoc_Location | None:
    if loc is None:
        return None
    return TopLoc_Location(loc.Transformation())


class AxisCoord(TypedDict):
    origin: tuple[float, float, float]
    z_dir: tuple[float, float, float]


def get_axis_coord(axis: gp_Ax1) -> AxisCoord:
    return {
        "origin": axis.Location().Coord(),
        "z_dir": axis.Direction().Coord(),
    }


class LocationCoord(TypedDict):
    origin: tuple[float, float, float]
    x_dir: tuple[float, float, float]
    y_dir: tuple[float, float, float]
    z_dir: tuple[float, float, float]


def get_location_coord(loc: TopLoc_Location) -> LocationCoord:
    trsf = loc.Transformation()

    origin = trsf.TranslationPart()
    q = trsf.GetRotation()

    x_dir = q * gp_Vec(1, 0, 0)
    y_dir = q * gp_Vec(0, 1, 0)
    z_dir = q * gp_Vec(0, 0, 1)

    return {
        "origin": origin.Coord(),
        "x_dir": x_dir.Coord(),
        "y_dir": y_dir.Coord(),
        "z_dir": z_dir.Coord(),
    }


def loc_to_vecs(
    origin: VectorLike, x_dir: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    ax3 = gp_Ax3(gp_Pnt(*origin), gp_Dir(*z_dir), gp_Dir(*x_dir))
    o = gp_Vec(ax3.Location().XYZ())
    x = gp_Vec(ax3.XDirection().XYZ())
    y = gp_Vec(ax3.YDirection().XYZ())
    z = gp_Vec(ax3.Direction().XYZ())
    return (o, x, y, z)


def loc_from_gp_pln(pln: gp_Pln) -> TopLoc_Location:
    o = pln.Location()
    x = pln.XAxis().Direction()
    z = pln.Axis().Direction()

    ax3 = gp_Ax3(o, z, x)
    trsf = gp_Trsf()
    trsf.SetTransformation(ax3)
    trsf.Invert()
    return TopLoc_Location(trsf)


def axis_to_vecs(
    origin: VectorLike, z_dir: VectorLike
) -> tuple[gp_Vec, gp_Vec, gp_Vec, gp_Vec]:
    ax3 = gp_Ax3(gp_Pnt(*origin), gp_Dir(*z_dir))
    o = gp_Vec(ax3.Location().XYZ())
    x = gp_Vec(ax3.XDirection().XYZ())
    y = gp_Vec(ax3.YDirection().XYZ())
    z = gp_Vec(ax3.Direction().XYZ())
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
