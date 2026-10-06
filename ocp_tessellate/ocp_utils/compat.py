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


"""The public names for OCP version and binding differences.

The differences themselves live in the kernels (`ocp_tessellate._kernel`). These
names are the default kernel's: the TopTools map classes, the shape hash and the
OCCT version.
"""

from .._kernel import kernel
from .._kernel.default import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

__all__ = [
    "TopTools_IndexedDataMapOfShapeListOfShape",
    "TopTools_IndexedMapOfShape",
    "hash_compat",
    "occt_version",
]

hash_compat = kernel().hash_compat


def occt_version() -> str:
    return kernel().version()
