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


"""Serialize shapes and hash them."""

from __future__ import annotations

from typing import TYPE_CHECKING

import io
import os
import tempfile

from .._kernel import adapter, kernel, kernel_of
if TYPE_CHECKING:
    from ..types import (
        TopoDS_Shape,
    )

from .predicates import is_topods_face, is_topods_shell, is_topods_solid


def ocp_hash(obj):
    if is_topods_solid(obj) or is_topods_face(obj) or is_topods_shell(obj):
        return adapter(kernel_of(obj)).hash_compat(obj)
    else:
        return ()


# TODO replace with https://github.com/MatthiasJ1/ocp_serializer when published
def serialize(
    shape: TopoDS_Shape | None, triangles: bool = False, normals: bool = False
) -> bytes | None:
    if shape is None:
        return None

    k = kernel_of(shape)
    try:
        buffer = adapter(k).bin_write(shape, triangles, normals)
    except Exception:
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "shape.brep")
            k.BinTools.BinTools.Write_s(
                shape, filename, False, False, k.BinTools.BinTools_FormatVersion_CURRENT
            )
            with open(filename, "rb") as fd:
                buffer = fd.read()
    return buffer


def deserialize(buffer: bytes | None) -> TopoDS_Shape | None:
    k = kernel()
    if buffer is None:
        return None

    shape = k.TopoDS.TopoDS_Shape()
    try:
        bio = io.BytesIO(buffer)
        k.BinTools.BinTools.Read_s(shape, bio)
    except Exception:
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "shape.brep")
            with open(filename, "wb") as fd:
                fd.write(buffer)
            k.BinTools.BinTools.Read_s(shape, filename)
    return shape
