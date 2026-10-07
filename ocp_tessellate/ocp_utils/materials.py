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

"""Visual materials of OCCT documents (XCAFDoc_VisMaterial) as plain values.

A material is read into, and made from, the values its PBR block holds: base
color (sRGB) and alpha, metallic, roughness, refraction index and emissive
factor (linear RGB), plus alpha mode, alpha cutoff and double-sidedness. A
common (Phong-style) material is read through OCCT's ConvertToPbrMaterial.

The emissive factor exists in OCP 7.9 and nanocct, but not in OCP 8: there it
reads as None and is not written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from .._kernel import adapter, kernel, kernel_of

if TYPE_CHECKING:
    from types import ModuleType

    from ..types import (
        XCAFDoc_VisMaterial,
    )

# Graphic3d_AlphaMode without its prefix, as alpha_mode reads and takes them
ALPHA_MODES = ("Opaque", "Mask", "Blend", "MaskBlend", "BlendAuto")


class VisMaterialValues(TypedDict):
    name: str | None
    color: tuple[float, float, float]
    alpha: float
    metallic: float
    roughness: float
    ior: float
    emissive: tuple[float, float, float] | None
    alpha_mode: str
    alpha_cutoff: float
    double_sided: bool


def vis_material_values(vis_material: XCAFDoc_VisMaterial) -> VisMaterialValues | None:
    """The values of an XCAFDoc_VisMaterial, None for an empty material.

    - name: the raw name, None if the material has none
    - color: base color as sRGB ratios; alpha: its alpha
    - metallic, roughness, ior (refraction index)
    - emissive: linear RGB, None where the binding does not bind it (OCP 8)
    - alpha_mode: one of ALPHA_MODES; alpha_cutoff: the cutoff of mode "Mask"
    - double_sided
    """
    k = kernel_of(vis_material)
    if vis_material.IsEmpty():
        return None

    if vis_material.HasPbrMaterial():
        pbr = vis_material.PbrMaterial()
    else:
        pbr = vis_material.ConvertToPbrMaterial()

    raw_name = vis_material.RawName()
    name = None
    if raw_name is not None:
        name = raw_name.ToCString()

    r, g, b = pbr.BaseColor.GetRGB().Values(k.Quantity.Quantity_TypeOfColor.Quantity_TOC_sRGB)
    return {
        "name": name,
        "color": (r, g, b),
        "alpha": pbr.BaseColor.Alpha(),
        "metallic": pbr.Metallic,
        "roughness": pbr.Roughness,
        "ior": pbr.RefractionIndex,
        "emissive": adapter(k).emissive_of(pbr),
        "alpha_mode": _alpha_mode_name(k, vis_material.AlphaMode()),
        "alpha_cutoff": vis_material.AlphaCutOff(),
        "double_sided": vis_material.IsDoubleSided(),
    }


def make_vis_material(
    name: str,
    color: tuple[float, float, float] | None = None,
    alpha: float = 1.0,
    metallic: float | None = None,
    roughness: float | None = None,
    ior: float | None = None,
    emissive: tuple[float, float, float] | None = None,
    alpha_mode: str | None = None,
    alpha_cutoff: float | None = None,
    double_sided: bool = False,
) -> XCAFDoc_VisMaterial:
    """A new XCAFDoc_VisMaterial with a PBR block, in kernel() (no OCCT object
    decides its binding).

    The values are those of vis_material_values; None keeps OCCT's default (for
    color the default base color, with `alpha` applied). `emissive` is dropped
    where the binding does not bind it (OCP 8). `alpha_mode` is one of
    ALPHA_MODES, None keeps OCCT's default (BlendAuto); `alpha_cutoff` is passed
    with it when given.
    """
    k = kernel()
    pbr = k.XCAFDoc.XCAFDoc_VisMaterialPBR()

    if color is not None:
        rgb = k.Quantity.Quantity_Color(
            color[0], color[1], color[2], k.Quantity.Quantity_TypeOfColor.Quantity_TOC_sRGB
        )
        pbr.BaseColor = k.Quantity.Quantity_ColorRGBA(rgb, alpha)
    else:
        base_color = pbr.BaseColor
        base_color.SetAlpha(alpha)
        pbr.BaseColor = base_color

    if metallic is not None:
        pbr.Metallic = metallic
    if roughness is not None:
        pbr.Roughness = roughness
    if ior is not None:
        pbr.RefractionIndex = ior
    if emissive is not None:
        adapter(k).set_emissive(pbr, emissive)

    vis_material = k.XCAFDoc.XCAFDoc_VisMaterial()
    vis_material.SetPbrMaterial(pbr)
    vis_material.SetRawName(k.TCollection.TCollection_HAsciiString(name))

    if alpha_mode is not None:
        mode = _alpha_mode(k, alpha_mode)
        if alpha_cutoff is None:
            vis_material.SetAlphaMode(mode)
        else:
            vis_material.SetAlphaMode(mode, alpha_cutoff)
    elif alpha_cutoff is not None:
        raise ValueError("alpha_cutoff needs an alpha_mode")

    if double_sided is True:
        vis_material.SetDoubleSided(True)

    return vis_material


def _alpha_modes(k: ModuleType) -> dict:
    """Graphic3d_AlphaMode of binding k by the names of ALPHA_MODES."""
    modes = k.Graphic3d.Graphic3d_AlphaMode
    return {
        "Opaque": modes.Graphic3d_AlphaMode_Opaque,
        "Mask": modes.Graphic3d_AlphaMode_Mask,
        "Blend": modes.Graphic3d_AlphaMode_Blend,
        "MaskBlend": modes.Graphic3d_AlphaMode_MaskBlend,
        "BlendAuto": modes.Graphic3d_AlphaMode_BlendAuto,
    }


def _alpha_mode(k: ModuleType, name: str):
    by_name = _alpha_modes(k)
    if name not in by_name:
        raise ValueError(f"alpha_mode must be one of {ALPHA_MODES}, not {name!r}")
    return by_name[name]


def _alpha_mode_name(k: ModuleType, mode) -> str:
    for name, value in _alpha_modes(k).items():
        if mode == value:
            return name
    raise ValueError(f"unknown Graphic3d_AlphaMode {mode!r}")
