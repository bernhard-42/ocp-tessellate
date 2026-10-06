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


"""Recognise build123d and CadQuery objects by duck typing."""

from collections.abc import Iterable
from typing import TypeGuard

from typing_extensions import TypeIs

from .._kernel import ANY
from .._kernel.default import (
    gp_Ax1,
    gp_Pln,
    TopLoc_Location,
    TopoDS_Compound,
    TopoDS_Shape,
    TopoDS_Shell,
)

from ..types import (
    Build123dBuilder,
    Build123dLineBuilder,
    Build123dPartBuilder,
    Build123dSheetBuilder,
    Build123dSketchBuilder,
    Build123dVector,
    Build123dGroupBy,
    Build123dLocationList,
    Build123dShape,
    Build123dShapeList,
    CadqueryAssembly,
    CadquerySketch,
    CadqueryWorkplane,
    Wrapped,
)
from .predicates import (
    is_gp_axis,
    is_gp_plane,
    is_toploc_location,
    is_topods_compound,
    is_topods_shape,
    is_topods_shell,
    is_wrapped,
)


def _has(obj, attrs):
    return all([hasattr(obj, a) for a in attrs])


def is_cadquery(obj) -> TypeIs[CadqueryWorkplane]:
    return _has(obj, ["objects", "ctx", "val"])


def is_cadquery_shape(obj) -> TypeIs[Wrapped[TopoDS_Shape]]:
    return _has(obj, ["wrapped", "forConstruction"]) and is_topods_shape(obj.wrapped)


def is_cadquery_assembly(obj) -> TypeIs[CadqueryAssembly]:
    return _has(obj, ["obj", "loc", "name", "children"])


def is_cadquery_massembly(obj) -> TypeGuard[CadqueryAssembly]:
    return _has(obj, ["obj", "loc", "name", "children", "mates"])


def is_cadquery_sketch(obj) -> TypeIs[CadquerySketch]:
    return (
        hasattr(obj, "_faces") and hasattr(obj, "_edges") and hasattr(obj, "_selection")
    )


def is_cadquery_empty_workplane(obj) -> TypeGuard[CadqueryWorkplane]:
    return is_cadquery(obj) and len(obj.objects) == 0


    # (len(obj.objects) == 0 or (len(obj.objects) == 1 and is_vector(obj.objects[0])))
def is_vector(obj) -> TypeIs[Build123dVector]:
    return hasattr(obj, "wrapped") and isinstance(obj.wrapped, ANY.gp_Vec)


def is_massembly(obj) -> TypeGuard[CadqueryAssembly]:
    return _has(obj, ["obj", "loc", "name", "children", "mates"])


def is_build123d(obj) -> TypeIs[Build123dBuilder]:
    return _has(obj, ["_obj", "_obj_name", "_tag"]) and not isinstance(obj, type)


def is_build123d_part(obj) -> TypeGuard[Build123dPartBuilder]:
    return is_build123d(obj) and obj._obj_name == "part"


def is_build123d_sheet(obj) -> TypeGuard[Build123dSheetBuilder]:
    return is_build123d(obj) and obj._obj_name == "sheet"


def is_build123d_sketch(obj) -> TypeGuard[Build123dSketchBuilder]:
    return is_build123d(obj) and obj._obj_name == "sketch"


def is_build123d_line(obj) -> TypeGuard[Build123dLineBuilder]:
    return is_build123d(obj) and obj._obj_name == "line"


def is_build123d_shape(obj) -> TypeIs[Build123dShape]:
    return _has(obj, ["wrapped", "children"]) and is_topods_shape(obj.wrapped)


def is_build123d_shell(obj) -> TypeIs[Wrapped[TopoDS_Shell]]:
    return hasattr(obj, "wrapped") and is_topods_shell(obj.wrapped)


def is_build123d_compound(obj) -> TypeIs[Wrapped[TopoDS_Compound]]:
    return hasattr(obj, "wrapped") and is_topods_compound(obj.wrapped)


def is_build123d_assembly(obj) -> TypeGuard[Build123dShape]:
    return (
        (is_build123d_compound(obj) or is_build123d_shape(obj))
        and hasattr(obj, "children")
        and isinstance(obj.children, (list, tuple))
        and len(obj.children) > 0
        # and (
        #     (len(obj.children) == 0 and obj.parent is not None)
        #     or (len(obj.children) > 0 and obj.parent is None)
        # )
    )


def is_build123d_shapelist(obj) -> TypeIs[Build123dShapeList]:
    return (
        isinstance(obj, Iterable)
        and hasattr(obj, "first")
        and hasattr(obj, "last")
        and hasattr(obj, "filter_by")
    )


def is_build123d_groupby(obj) -> TypeIs[Build123dGroupBy]:
    return (
        isinstance(obj, Iterable)
        and hasattr(obj, "groups")
        and hasattr(obj, "group_for")
    )


def is_build123d_locationlist(obj) -> TypeIs[Build123dLocationList]:
    return (
        isinstance(obj, Iterable)
        and hasattr(obj, "locations")
        and hasattr(obj, "__enter__")
        and hasattr(obj, "__exit__")
    )


def is_build123d_plane(obj) -> TypeIs[Wrapped[gp_Pln]]:
    return is_wrapped(obj) and is_gp_plane(obj.wrapped)


def is_build123d_location(obj) -> TypeIs[Wrapped[TopLoc_Location]]:
    return is_wrapped(obj) and is_toploc_location(obj.wrapped)


def is_build123d_axis(obj) -> TypeIs[Wrapped[gp_Ax1]]:
    return is_wrapped(obj) and is_gp_axis(obj.wrapped)
