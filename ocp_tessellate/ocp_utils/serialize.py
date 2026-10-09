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

import io
import os
import tempfile
from typing import TYPE_CHECKING

from .._kernel import adapter, kernel, kernel_of

if TYPE_CHECKING:
    from types import ModuleType

    from ..types import (
        TopoDS_Shape,
    )

from .predicates import is_topods_face, is_topods_shell, is_topods_solid


def ocp_hash(obj):
    if is_topods_solid(obj) or is_topods_face(obj) or is_topods_shell(obj):
        return adapter(kernel_of(obj)).hash_compat(obj)
    else:
        return ()


def serialize(
    shape: TopoDS_Shape | None, triangles: bool = False, normals: bool = False
) -> bytes | None:
    if shape is None:
        return None

    k = kernel_of(shape)
    try:
        buffer = adapter(k).bin_write(shape, triangles, normals)
    # any failure of the in-memory path falls back to a file
    except Exception:  # noqa: BLE001
        buffer = _write_via_file(k, shape, triangles, normals)
    return buffer


def _write_via_file(k: ModuleType, shape: TopoDS_Shape, triangles: bool, normals: bool) -> bytes:
    """serialize's fallback: the shape written to a temporary file in binary BRep format."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        filename = os.path.join(tmpdirname, "shape.brep")
        k.BinTools.BinTools.Write_s(
            shape, filename, triangles, normals, k.BinTools.BinTools_FormatVersion_CURRENT
        )
        with open(filename, "rb") as fd:
            return fd.read()


def deserialize(buffer: bytes | None) -> TopoDS_Shape | None:
    k = kernel()
    if buffer is None:
        return None
    return _read(k, buffer)


def _read(k: ModuleType, buffer: bytes) -> TopoDS_Shape:
    """The shape in OCCT's binary BRep format `buffer`, read with binding k."""
    shape = k.TopoDS.TopoDS_Shape()
    try:
        bio = io.BytesIO(buffer)
        k.BinTools.BinTools.Read_s(shape, bio)
    # any failure of the in-memory path falls back to a file
    except Exception:  # noqa: BLE001
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "shape.brep")
            with open(filename, "wb") as fd:
                fd.write(buffer)
            k.BinTools.BinTools.Read_s(shape, filename)
    return shape
