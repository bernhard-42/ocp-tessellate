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

"""The OCCT bindings ocp_tessellate runs on.

ocp_tessellate is to support OCP (cadquery-ocp) and nanocct, installed alone or
together (docs/nanocct-concept.md). Everything binding-specific lives in a
kernel module - `ocp.py` - and the rest of the package reaches OCCT only
through a kernel:

- `kernel_of(obj)`: the kernel of an OCCT object, of the OCCT object a
  build123d or CadQuery object wraps, or of the first such object in a list or
  tuple; the default kernel when there is none
- `kernel()`: the default kernel
- `ANY.<Name>`: the class <Name> of every installed binding, for isinstance()

The package probes are the only imports inside `try`: a kernel module imports
its binding at top level, so a name missing in one version fails loudly
instead of looking like a binding that is not installed.
"""

from types import ModuleType
from typing import TYPE_CHECKING

HAS_OCP = True
try:
    import OCP  # noqa: F401
except ImportError:
    HAS_OCP = False

HAS_NANOCCT = True
try:
    import nanocct  # noqa: F401  # ty: ignore[unresolved-import]
except ImportError:
    HAS_NANOCCT = False

if HAS_OCP is False:
    # the nanocct kernel follows (docs/nanocct-concept.md, section 9, step 7)
    raise ImportError("ocp_tessellate needs OCP (cadquery-ocp)")

from . import ocp as ocp_kernel  # noqa: E402

KERNELS: tuple[ModuleType, ...] = (ocp_kernel,)

# the top-level package of an OCCT class -> its kernel
_BY_PACKAGE: dict[str, ModuleType] = {"OCP": ocp_kernel}
# OCCT classes already seen -> their kernel
_BY_TYPE: dict[type, ModuleType] = {}


def kernel() -> ModuleType:
    """The default kernel."""
    return ocp_kernel


def _find(obj: object) -> ModuleType | None:
    cls = type(obj)
    found = _BY_PACKAGE.get(cls.__module__.partition(".")[0])
    if found is not None:
        _BY_TYPE[cls] = found
        return found
    if isinstance(obj, (list, tuple)):
        # not any other iterable: a generator would be consumed
        for item in obj:
            found = _find(item)
            if found is not None:
                return found
        return None
    wrapped = getattr(obj, "wrapped", None)
    if wrapped is not None and wrapped is not obj:
        return _find(wrapped)
    return None


def kernel_of(obj: object) -> ModuleType:
    """The kernel of obj, see the module docstring."""
    found = _BY_TYPE.get(type(obj))
    if found is not None:
        return found
    found = _find(obj)
    if found is None:
        return kernel()
    return found


class _AnyKernel:
    """`ANY.TopoDS_Face` is the tuple of TopoDS_Face classes of all kernels."""

    def __getattr__(self, name: str) -> tuple[type, ...]:
        classes = tuple(getattr(k, name) for k in KERNELS)
        self.__dict__[name] = classes
        return classes


if TYPE_CHECKING:
    # for the type checker the default kernel's classes, so that
    # isinstance(x, ANY.TopoDS_Face) narrows x to TopoDS_Face as before
    from . import default as ANY
else:
    ANY = _AnyKernel()
