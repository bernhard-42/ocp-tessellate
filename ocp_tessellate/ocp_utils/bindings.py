#
# Copyright 2026 Bernhard Walter
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

"""Convert OCCT objects between the bindings: to_ocp and to_nanocct.

Where OCP and nanocct are both installed, one process can hold objects of both,
but they cannot be combined: a cadquery (OCP) shape cannot be fused with a
build123d-on-nanocct one. These functions make the object of the other binding:

- shapes (TopoDS_*) travel in OCCT's binary BRep format, with triangulations and
  normals, in the newest format version both bindings know (the smaller of their
  BinTools_FormatVersion_UPPER), so an older OCCT can read what a newer one writes
- gp_Pnt, gp_Vec, gp_Dir, gp_XYZ, gp_Trsf, TopLoc_Location, gp_Ax1, gp_Ax2,
  gp_Ax3, gp_Pln, Quantity_Color and Quantity_ColorRGBA are rebuilt from their
  values

Both are copies: a shape gets a new TShape, so two shapes converted one by one no
longer share sub-shapes (a compound converted as a whole keeps its sharing), and
a location is flattened to one transformation. Values agree to the last bits
(directions and transformations are re-normalised, which can move them by a few
ulp; OCCT's own BinTools round trip does the same to locations).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeVar

from .._kernel import adapter, binding, binding_of
from .serialize import _read
from .topology import downcast

if TYPE_CHECKING:
    from types import ModuleType

T = TypeVar("T")


def to_ocp(obj: T) -> T:
    """The OCP object for the OCP or nanocct object obj; obj itself if it is OCP.

    An ImportError if OCP is not installed, a TypeError for an object that is
    not OCCT or of a type that cannot be converted.
    """
    return _to_binding(obj, "OCP")


def to_nanocct(obj: T) -> T:
    """The nanocct object for the OCP or nanocct object obj; obj itself if it is
    nanocct.

    An ImportError if nanocct is not installed, a TypeError for an object that is
    not OCCT or of a type that cannot be converted.
    """
    return _to_binding(obj, "nanocct")


def _to_binding(obj, name: Literal["OCP", "nanocct"]):
    source = binding_of(obj)
    if source is None:
        raise TypeError(f"not an OCP or nanocct object: {type(obj).__qualname__}")
    target = binding(name)
    if source is target:
        return obj

    kind = type(obj).__name__
    if kind.startswith("TopoDS_"):
        return _shape(obj, source, target)
    if kind in ("gp_Pnt", "gp_Vec", "gp_Dir", "gp_XYZ"):
        return getattr(target.gp, kind)(obj.X(), obj.Y(), obj.Z())
    if kind == "gp_Trsf":
        return _trsf(obj, target)
    if kind == "TopLoc_Location":
        if obj.IsIdentity():
            # a location built from an identity gp_Trsf is not IsIdentity()
            return target.TopLoc.TopLoc_Location()
        return target.TopLoc.TopLoc_Location(_trsf(obj.Transformation(), target))
    if kind == "gp_Ax1":
        return target.gp.gp_Ax1(_to_binding(obj.Location(), name), _to_binding(obj.Direction(), name))
    if kind == "gp_Ax2":
        return target.gp.gp_Ax2(
            _to_binding(obj.Location(), name),
            _to_binding(obj.Direction(), name),
            _to_binding(obj.XDirection(), name),
        )
    if kind == "gp_Ax3":
        ax3 = target.gp.gp_Ax3(
            _to_binding(obj.Location(), name),
            _to_binding(obj.Direction(), name),
            _to_binding(obj.XDirection(), name),
        )
        if obj.Direct() is False:
            # a left-handed system: (P, N, Vx) makes the right-handed one
            ax3.YReverse()
        return ax3
    if kind == "gp_Pln":
        return target.gp.gp_Pln(_to_binding(obj.Position(), name))
    if kind == "Quantity_Color":
        # Red(), Green() and Blue() are linear RGB
        return target.Quantity.Quantity_Color(
            obj.Red(), obj.Green(), obj.Blue(), target.Quantity.Quantity_TypeOfColor.Quantity_TOC_RGB
        )
    if kind == "Quantity_ColorRGBA":
        return target.Quantity.Quantity_ColorRGBA(_to_binding(obj.GetRGB(), name), obj.Alpha())
    raise TypeError(f"cannot convert {source.__name__}.{kind} to {name}")


def _shape(shape, source: ModuleType, target: ModuleType):
    # the newest format both bindings write and read
    version = min(adapter(source).bin_format_upper, adapter(target).bin_format_upper)
    buffer = adapter(source).bin_write(shape, True, True, version)
    result = _read(target, buffer)
    if type(shape).__name__ == "TopoDS_Shape":
        return result
    return downcast(result)


def _trsf(trsf, target: ModuleType):
    result = target.gp.gp_Trsf()
    result.SetValues(*[trsf.Value(row, col) for row in (1, 2, 3) for col in (1, 2, 3, 4)])
    return result
