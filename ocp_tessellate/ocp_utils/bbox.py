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


"""Bounding boxes, OCP and numpy based."""

from __future__ import annotations

import itertools
import sys
from collections.abc import Iterable
from typing import TYPE_CHECKING, TypedDict

import numpy as np
from cachetools import LRUCache, cached

from .._kernel import adapter, kernel_of
if TYPE_CHECKING:
    from ..types import (
        TopLoc_Location,
        TopoDS_Shape,
    )

from ..utils import distance
from .topology import make_compound
from .measure import center_of_mass
from .location import loc_to_tq, rotate
from .predicates import is_topods_shape


# Caching helpers for bounding box
def make_key(
    objs: TopoDS_Shape | Iterable[TopoDS_Shape],
    loc: TopLoc_Location | None = None,
    optimal: bool = False,
) -> tuple[
    tuple[tuple[int, int], ...],
    tuple[tuple[float, float, float], tuple[float, float, float, float]]
    | tuple[None, None],
]:  # pylint: disable=unused-argument
    # optimal is not used and as such ignored
    if is_topods_shape(objs):
        objs = [objs]

    key = (tuple(((adapter(kernel_of(s)).hash_compat(s), id(s)) for s in objs)), loc_to_tq(loc))
    return key


def get_size(obj: object) -> int:
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum([
            get_size(v) + (len(k) if isinstance(k, str) else 0) for k, v in obj.items()
        ])
    elif isinstance(obj, (tuple, list)):
        size += sum([get_size(i) for i in obj])
    return size


cache = LRUCache(maxsize=16 * 1024 * 1024, getsizeof=get_size)


class BoundingBox(object):
    def __init__(self, obj=None, optimal=False):
        self.optimal = optimal
        if obj is None:
            self.xmin = self.xmax = self.ymin = self.ymax = self.zmin = self.zmax = 0
        elif isinstance(obj, BoundingBox):
            self.xmin = obj.xmin
            self.xmax = obj.xmax
            self.ymin = obj.ymin
            self.ymax = obj.ymax
            self.zmin = obj.zmin
            self.zmax = obj.zmax
        elif isinstance(obj, dict):
            self.xmin = obj["xmin"]
            self.xmax = obj["xmax"]
            self.ymin = obj["ymin"]
            self.ymax = obj["ymax"]
            self.zmin = obj["zmin"]
            self.zmax = obj["zmax"]
        else:
            bbox = self._bounding_box(obj)
            self.xmin, self.xmax, self.ymin, self.ymax, self.zmin, self.zmax = bbox

        self._calc()

    def _center_of_mass(self, obj):
        return center_of_mass(obj)

    def _bounding_box(self, obj, tol=1e-6):
        k = kernel_of(obj)
        bbox = k.Bnd.Bnd_Box()
        if self.optimal:
            k.BRepTools.BRepTools.Clean_s(obj)
            k.BRepBndLib.BRepBndLib.AddOptimal_s(obj, bbox)
        else:
            k.BRepBndLib.BRepBndLib.Add_s(obj, bbox)
        if not bbox.IsVoid():
            # The corners, not Get(): on OCP 8 Get() resolves to the overload returning
            # the Bnd_Box::Limits struct, which is not bound and always raises, and
            # OCP 7.9 has no GetXMin() and friends. CornerMin/CornerMax exist in all
            # bindings and return the same values.
            p_min, p_max = bbox.CornerMin(), bbox.CornerMax()
            return (p_min.X(), p_max.X(), p_min.Y(), p_max.Y(), p_min.Z(), p_max.Z())
        else:
            c = self._center_of_mass(obj)
            bb = (
                c[0] - tol,
                c[0] + tol,
                c[1] - tol,
                c[1] + tol,
                c[2] - tol,
                c[2] + tol,
            )
            print("\nVoid Bounding Box", bb)
            return bb

    def _calc(self):
        self.xsize = self.xmax - self.xmin
        self.ysize = self.ymax - self.ymin
        self.zsize = self.zmax - self.zmin
        self.center = (
            self.xmin + self.xsize / 2.0,
            self.ymin + self.ysize / 2.0,
            self.zmin + self.zsize / 2.0,
        )
        self.max = max([
            abs(x)
            for x in (
                self.xmin,
                self.xmax,
                self.ymin,
                self.ymax,
                self.zmin,
                self.zmax,
            )
        ])

    def is_empty(self):
        return (
            (abs(self.xmax - self.xmin) < 0.01)
            and (abs(self.ymax - self.ymin) < 0.01)
            and (abs(self.zmax - self.zmin) < 0.01)
        )

    def max_dist_from_center(self):
        return max([
            distance(self.center, v)
            for v in itertools.product(
                (self.xmin, self.xmax),
                (self.ymin, self.ymax),
                (self.zmin, self.zmax),
            )
        ])

    def max_dist_from_origin(self):
        return max([
            np.linalg.norm(v)
            for v in itertools.product(
                (self.xmin, self.xmax),
                (self.ymin, self.ymax),
                (self.zmin, self.zmax),
            )
        ])

    def update(self, bb, minimize=False):
        lower, upper = (max, min) if minimize else (min, max)

        if isinstance(bb, BoundingBox):
            self.xmin = lower(bb.xmin, self.xmin)
            self.xmax = upper(bb.xmax, self.xmax)
            self.ymin = lower(bb.ymin, self.ymin)
            self.ymax = upper(bb.ymax, self.ymax)
            self.zmin = lower(bb.zmin, self.zmin)
            self.zmax = upper(bb.zmax, self.zmax)
        elif isinstance(bb, dict):
            self.xmin = lower(bb["xmin"], self.xmin)
            self.xmax = upper(bb["xmax"], self.xmax)
            self.ymin = lower(bb["ymin"], self.ymin)
            self.ymax = upper(bb["ymax"], self.ymax)
            self.zmin = lower(bb["zmin"], self.zmin)
            self.zmax = upper(bb["zmax"], self.zmax)
        else:
            raise ValueError("Wrong bounding box param")

        self._calc()

    def to_dict(self):
        return {
            "xmin": float(self.xmin),
            "xmax": float(self.xmax),
            "ymin": float(self.ymin),
            "ymax": float(self.ymax),
            "zmin": float(self.zmin),
            "zmax": float(self.zmax),
        }

    def __repr__(self):
        return "{xmin:%.2f, xmax:%.2f, ymin:%.2f, ymax:%.2f, zmin:%.2f, zmax:%.2f}" % (
            self.xmin,
            self.xmax,
            self.ymin,
            self.ymax,
            self.zmin,
            self.zmax,
        )


@cached(cache, key=make_key)
def bounding_box(objs, loc=None, optimal=False):
    if isinstance(objs, (list, tuple)):
        compound = make_compound(objs)
    else:
        compound = objs

    return BoundingBox(
        compound if loc is None else compound.Moved(loc), optimal=optimal
    )


def nested_bounding_box(objs):
    def bb(objs, total=None):
        if total is None:
            total = BoundingBox()

        if isinstance(objs, (list, tuple)):
            for obj in objs:
                total.update(bb(obj, total))
        elif isinstance(objs, dict):
            for obj in objs.values():
                total.update(bb(obj, total))
        else:
            try:
                new_bb = bounding_box(objs.wrapped)
                total.update(new_bb)
            except Exception:
                pass
        return total

    return bb(objs)


class NumpyBBox(TypedDict):
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float


def np_bbox(
    p: np.ndarray,
    t: tuple[float, float, float] | np.ndarray | None = None,
    q: tuple[float, float, float, float] | None = None,
) -> NumpyBBox | None:
    if p.size == 0:
        return None

    n_p = p.reshape(-1, 3)
    if t is None or q is None:
        v = n_p
    else:
        n_t = np.asarray(t)
        v = rotate(q, n_p) + n_t

    bbmin = np.min(v, axis=0)
    bbmax = np.max(v, axis=0)
    return {
        "xmin": bbmin[0],
        "xmax": bbmax[0],
        "ymin": bbmin[1],
        "ymax": bbmax[1],
        "zmin": bbmin[2],
        "zmax": bbmax[2],
    }
