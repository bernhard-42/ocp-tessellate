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

"""The OCCT bindings ocp_tessellate runs on, hidden from its users.

ocp_tessellate supports OCP (cadquery-ocp) and nanocct, installed alone or
together (docs/nanocct-concept.md). The kernel of an object is its binding, the
module `OCP` or `nanocct`, and the code reaches OCCT through it with OCCT's own
package structure, which both bindings share:

    k = kernel_of(shape)
    poly = k.BRep.BRep_Tool.Triangulation_s(face, k.TopLoc.TopLoc_Location())

- `kernel()`: the binding for what no OCCT object decides - the only one
  installed, else the one the environment variable OCCT_BINDING names (OCP if
  it is unset).
- `kernel_of(obj)`: the binding of the OCCT object obj, `kernel()` for anything
  else (tuples, None).
- `kernel_of_all(objs)`: the one binding of the OCCT objects in a sequence, for
  functions that take several (make_compound, cross), `kernel()` if there are
  none; a TypeError for objects of two bindings.
- `binding_of(obj)`: the binding of obj, None if it is not an OCCT object (for
  predicates).
- `binding(name)`: the binding module "OCP" or "nanocct" by name, for the
  converters between the bindings (ocp_utils.to_ocp / to_nanocct).
- `adapter(k)`: what differs between the bindings and OCP versions - downcasts,
  collection classes, calling conventions, the tessellation loops - from
  `ocp_adapter.py` or `nanocct_adapter.py`.

The binding of an object is the top-level package of its class's module,
decided once per class and cached - for classes that are not OCCT as well.
Wrappers (build123d, CadQuery) are not looked into: callers pass `.wrapped`.
The package probes are the only imports inside `try`; the adapters import their
binding at top level, so a name missing in one version fails loudly instead of
looking like a binding that is not installed.
"""

import os
from collections.abc import Sequence
from types import ModuleType
from typing import Literal

# the top-level package of an OCCT class -> its binding
_BY_PACKAGE: dict[str, ModuleType] = {}

# the binding -> its adapter
_ADAPTERS: dict[ModuleType, ModuleType] = {}

# classes already seen -> their binding, None for classes that are not OCCT
_BY_TYPE: dict[type, ModuleType | None] = {}

# Only the probe is inside `try`: an ImportError from the adapter (a name missing
# in one version) raises instead of looking like a binding that is not installed.
try:
    import OCP
except ImportError:
    HAS_OCP = False
else:
    HAS_OCP = True
    from . import ocp_adapter

    _BY_PACKAGE["OCP"] = OCP
    _ADAPTERS[OCP] = ocp_adapter


try:
    import nanocct
except ImportError:
    HAS_NANOCCT = False
else:
    HAS_NANOCCT = True
    from . import nanocct_adapter

    _BY_PACKAGE["nanocct"] = nanocct
    _ADAPTERS[nanocct] = nanocct_adapter

if HAS_OCP is False and HAS_NANOCCT is False:
    raise ImportError("ocp_tessellate needs OCP (cadquery-ocp) or nanocct")


# the installed bindings, OCP first
KERNELS: tuple[ModuleType, ...] = tuple(_BY_PACKAGE.values())

# The environment variable OCCT_BINDING ("OCP" or "nanocct") names the binding of
# what no OCCT object decides, read once at import and fixed for the process, so
# all threads agree. The ecosystem's other libraries (ocpsvg) read the same
# variable at import, so one switch configures them all; there is no setter,
# because ocpsvg could not follow one.
_BINDINGS = ("OCP", "nanocct")


def _initial_preference() -> Literal["OCP", "nanocct"]:
    """The binding OCCT_BINDING names, OCP if it is unset."""
    wanted = os.environ.get("OCCT_BINDING")
    if wanted is None:
        return "OCP"
    if wanted == "OCP":
        if HAS_OCP is False:
            raise ImportError("OCCT_BINDING=OCP, but OCP is not installed")
        return "OCP"
    if wanted == "nanocct":
        if HAS_NANOCCT is False:
            raise ImportError("OCCT_BINDING=nanocct, but nanocct is not installed")
        return "nanocct"
    raise ImportError(f"OCCT_BINDING must be one of {_BINDINGS}, not {wanted!r}")


# the binding of what no OCCT object decides, fixed at import; read only by kernel()
_PREFERRED: Literal["OCP", "nanocct"] = _initial_preference()


def kernel() -> ModuleType:
    """The binding for what no OCCT object decides.

    The only binding installed, else the one OCCT_BINDING names (OCP if unset).
    """
    if HAS_OCP is False or _PREFERRED == "nanocct":
        return nanocct
    return OCP


def binding_of(obj: object) -> ModuleType | None:
    """The binding of obj, None if obj is not an OCCT object."""
    cls = type(obj)
    try:
        return _BY_TYPE[cls]
    except KeyError:
        found = _BY_PACKAGE.get(cls.__module__.partition(".")[0])
        _BY_TYPE[cls] = found
        return found


def kernel_of(obj: object) -> ModuleType:
    """The binding of the OCCT object obj, kernel() if obj is not one."""
    found = binding_of(obj)
    if found is None:
        return kernel()
    return found


def kernel_of_all(objs: Sequence[object]) -> ModuleType:
    """The one binding of the OCCT objects in objs (other objects are ignored).

    kernel() if there is none, a TypeError if they belong to two bindings.
    """
    found: set[ModuleType] = set()
    for obj in objs:
        binding = binding_of(obj)
        if binding is not None:
            found.add(binding)
    if len(found) > 1:
        raise TypeError("objects of two bindings, OCP and nanocct, cannot be combined")
    if len(found) == 1:
        return found.pop()
    return kernel()


def binding(name: str) -> ModuleType:
    """The binding module named `name` ("OCP" or "nanocct"); an ImportError if it
    is not installed."""
    if name not in _BINDINGS:
        raise ValueError(f"the binding is one of {_BINDINGS}, not {name!r}")
    found = _BY_PACKAGE.get(name)
    if found is None:
        raise ImportError(f"{name} is not installed")
    return found


def adapter(k: ModuleType) -> ModuleType:
    """What differs in binding k: the module ocp_adapter.py or nanocct_adapter.py."""
    return _ADAPTERS[k]
