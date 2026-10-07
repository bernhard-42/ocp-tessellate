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


"""Colors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import TypeIs

from .._kernel import kernel, kernel_of
if TYPE_CHECKING:
    from ..types import (
        Quantity_ColorRGBA,
    )

from ..types import Wrapped
from .predicates import _is_quantity_color
from ..utils import Color


def is_ocp_color(obj) -> TypeIs[Wrapped[Quantity_ColorRGBA]]:
    # the guarded object is the wrapper, not the Quantity_ColorRGBA itself
    return hasattr(obj, "wrapped") and _is_quantity_color(obj.wrapped)


def get_rgba(color, alpha=None, def_color=None) -> Color | None:
    if color is None:
        if def_color is None:
            return None
        color = def_color

    if isinstance(color, Color):
        return color

    if hasattr(color, "wrapped"):  # CadQery or build123d Color
        try:
            rgba = Color(tuple(color))  # build123d
        except Exception:
            rgba = Color(color.toTuple())  # CadQuery

        if alpha is not None:
            rgba.a = alpha

    elif _is_quantity_color(color):  # OCP
        k = kernel_of(color)
        r, g, b = color.GetRGB().Values(k.Quantity.Quantity_TypeOfColor.Quantity_TOC_sRGB)
        rgba = Color((
            int(round(r * 255)),
            int(round(g * 255)),
            int(round(b * 255)),
            color.Alpha() if alpha is None else alpha,
        ))

    elif isinstance(color, str) or isinstance(color, (tuple, list)):
        rgba = Color(color, 1.0 if alpha is None else alpha)

    else:
        raise ValueError(f"Unknown color input {color} ({type(color)}")

    return rgba


def ocp_color(r: float, g: float, b: float, alpha: float = 1.0) -> Quantity_ColorRGBA:
    k = kernel()
    return k.Quantity.Quantity_ColorRGBA(r, g, b, alpha)
