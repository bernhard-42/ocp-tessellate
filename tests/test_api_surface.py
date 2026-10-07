"""Guard the public API surface of ocp_tessellate.

The snapshot `api_surface.json` records, per public module, every public name
with its kind and, for functions, classes and their methods, the parameters
(name, kind, default; annotations are left out on purpose, so that widening a
type from OCP to OCP | nanocct does not count as an API change).

What counts as the surface of a module:
- functions and classes defined in ocp_tessellate, with their parameters
- OCCT objects (OCP or nanocct classes, enums, functions) re-exported by name
- other module-level values (constants, caches, type aliases), by type name
Not part of it: imported modules, third-party functions and classes (numpy,
cachetools, typing, ...), typing constructs, the names `stepreader` gets from
`from build123d import *`, and helpers of the private package
ocp_tessellate._kernel (kernel_of, kernel, ...) that modules import.

Allowed differences to the snapshot:
- the names in DELIBERATE_REMOVALS are gone
- every OCCT name (kind "occt") is gone: since 4.0.0 ocp_tessellate hides the
  OCCT bindings and exports none of their classes; a module that exposes one
  fails
- the names in DELIBERATE_ADDITIONS are new
- names in OPTIONAL may be missing when the optional package is not installed

Regenerate the snapshot (only when the API is meant to change):
    python tests/test_api_surface.py --update
"""

import __future__

import importlib
import inspect
import json
import sys
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("api_surface.json")

MODULES = [
    "ocp_tessellate",
    "ocp_tessellate.cad_objects",
    "ocp_tessellate.convert",
    "ocp_tessellate.defaults",
    "ocp_tessellate.ocp_utils",
    "ocp_tessellate.stepreader",
    "ocp_tessellate.tessellator",
    "ocp_tessellate.trace",
    "ocp_tessellate.types",
    "ocp_tessellate.utils",
]

OWN_PREFIX = "ocp_tessellate"
# the private kernel package: what it defines is internal, even when a module
# imports it (ocp_tessellate._version is private too, but ot_version_info is API)
PRIVATE_PREFIX = "ocp_tessellate._kernel"
OCCT_PREFIXES = ("OCP", "nanocct")
TYPING_MODULES = ("typing", "typing_extensions")

# third-party modules whose re-exported objects are not part of the surface even
# when they are plain values (numpy.typing.NDArray is a types.GenericAlias in
# numpy 2.4 and a typing.TypeAliasType in numpy 2.5)
FOREIGN_VALUE_MODULES = ("numpy.typing",)

# names removed on purpose since the snapshot was taken, see docs/nanocct-concept.md
DELIBERATE_REMOVALS: dict[str, set[str]] = {
    # the native tessellator (ocp_addons) is gone
    "ocp_tessellate.tessellator": {"NATIVE", "NativeTessellator", "TesselatorProtocol"},
    "ocp_tessellate.types": {"TesselatorProtocol"},
    # the downcast table of one binding (convert has it by star import)
    "ocp_tessellate.ocp_utils": {"downcast_LUT"},
    "ocp_tessellate.convert": {"downcast_LUT"},
}

# names added on purpose since the snapshot was taken, see docs/nanocct-concept.md
# the OCCT side of ocp-viewer-core's measurements and materials, dual binding
# (4.0.0); convert has them by star import
_VIEWER_HELPERS = {
    "angle_between",
    "closest_directions",
    "face_normal",
    "make_vis_material",
    "vis_material_values",
    "ALPHA_MODES",
    "VisMaterialValues",
    # converters between the bindings
    "to_nanocct",
    "to_ocp",
}
DELIBERATE_ADDITIONS: dict[str, set[str]] = {
    "ocp_tessellate.ocp_utils": _VIEWER_HELPERS,
    "ocp_tessellate.convert": _VIEWER_HELPERS,
}

# kinds of entries that are gone everywhere: the bindings are hidden (4.0.0)
REMOVED_KINDS = {"occt"}

# names that only exist when an optional package is installed
OPTIONAL = {
    "ocp_tessellate.stepreader": {"clone"},  # needs build123d
}

# modules whose star import of a third-party package is not part of the surface
FOREIGN_STAR_IMPORTS = {
    "ocp_tessellate.stepreader": "build123d",
}

def _top_package(module_name):
    if module_name is None:
        return ""
    return module_name.split(".")[0]


def _default_repr(value):
    if value is inspect.Parameter.empty:
        return None
    text = repr(value)
    if " at 0x" in text:
        return f"<{type(value).__name__}>"
    return text


def _params(obj):
    try:
        signature = inspect.signature(obj)
    except (TypeError, ValueError):
        return None
    return [
        [p.name, p.kind.name, _default_repr(p.default)]
        for p in signature.parameters.values()
    ]


def _members(cls):
    members = {}
    for name, value in vars(cls).items():
        if name.startswith("_") and name != "__init__":
            continue
        if isinstance(value, (staticmethod, classmethod)):
            members[name] = {"kind": type(value).__name__, "params": _params(value.__func__)}
        elif isinstance(value, property):
            members[name] = {"kind": "property"}
        elif inspect.isfunction(value):
            members[name] = {"kind": "method", "params": _params(value)}
        else:
            members[name] = {"kind": "attribute"}
    return members


def _foreign_value_ids():
    ids = set()
    for module_name in FOREIGN_VALUE_MODULES:
        module = importlib.import_module(module_name)
        for name in dir(module):
            if not name.startswith("_"):
                ids.add(id(getattr(module, name)))
    return ids


def _is_private(module_name):
    if module_name is None:
        return False
    return module_name == PRIVATE_PREFIX or module_name.startswith(PRIVATE_PREFIX + ".")


def _describe(obj, foreign_ids):
    """Return the description of a module attribute, or None if not part of the surface."""
    if inspect.ismodule(obj) or id(obj) in foreign_ids:
        return None
    if inspect.isclass(obj) or inspect.isroutine(obj):
        if _is_private(getattr(obj, "__module__", None)):
            return None
    elif _is_private(type(obj).__module__):
        return None

    if inspect.isclass(obj) or inspect.isroutine(obj):
        package = _top_package(getattr(obj, "__module__", None))
        if package == OWN_PREFIX:
            if inspect.isclass(obj):
                return {
                    "kind": "class",
                    "bases": [b.__qualname__ for b in obj.__bases__],
                    "params": _params(obj),
                    "members": _members(obj),
                }
            return {"kind": "function", "params": _params(obj)}
        if package in OCCT_PREFIXES:
            return {"kind": "occt"}
        return None

    type_module = type(obj).__module__
    if _top_package(type_module) in OCCT_PREFIXES:
        return {"kind": "occt"}
    if type_module in TYPING_MODULES:
        return None
    return {"kind": "value", "type": type(obj).__name__}


def _foreign_star_names(module_name):
    package = FOREIGN_STAR_IMPORTS.get(module_name)
    if package is None:
        return set()
    try:
        foreign = importlib.import_module(package)
    except ImportError:
        return set()
    # a star import binds the names in __all__, or all public names without it
    names = getattr(foreign, "__all__", None)
    if names is None:
        return {name for name in dir(foreign) if not name.startswith("_")}
    return set(names)


def _is_language_plumbing(name, obj):
    """`from __future__ import annotations` and `from typing import TYPE_CHECKING`."""
    if name == "annotations" and obj is __future__.annotations:
        return True
    return name == "TYPE_CHECKING" and obj is False


def collect_surface():
    surface = {}
    foreign_ids = _foreign_value_ids()
    for module_name in MODULES:
        module = importlib.import_module(module_name)
        excluded = _foreign_star_names(module_name)
        entries = {}
        for name in sorted(dir(module)):
            if name.startswith("_") or name in excluded:
                continue
            if _is_language_plumbing(name, getattr(module, name)):
                continue
            description = _describe(getattr(module, name), foreign_ids)
            if description is not None:
                entries[name] = description
        surface[module_name] = entries
    return surface


def _compare_params(where, expected, actual, problems):
    if expected == actual:
        return
    problems.append(f"{where}: parameters changed\n    was {expected}\n    now {actual}")


def _compare_entry(where, expected, actual, problems):
    if expected["kind"] != actual["kind"]:
        problems.append(f"{where}: kind changed from {expected['kind']} to {actual['kind']}")
        return
    if "type" in expected and expected["type"] != actual.get("type"):
        problems.append(f"{where}: type changed from {expected['type']} to {actual.get('type')}")
    if "bases" in expected and expected["bases"] != actual.get("bases"):
        problems.append(f"{where}: bases changed from {expected['bases']} to {actual.get('bases')}")
    if "params" in expected:
        _compare_params(where, expected["params"], actual.get("params"), problems)
    if "members" in expected:
        actual_members = actual.get("members", {})
        for name, member in expected["members"].items():
            if name not in actual_members:
                problems.append(f"{where}.{name}: removed")
            else:
                _compare_entry(f"{where}.{name}", member, actual_members[name], problems)
        for name in sorted(set(actual_members) - set(expected["members"])):
            problems.append(f"{where}.{name}: added")


def compare(expected_surface, actual_surface):
    problems = []
    for module_name in MODULES:
        expected = expected_surface.get(module_name, {})
        actual = actual_surface.get(module_name, {})
        removals = DELIBERATE_REMOVALS.get(module_name, set())
        optional = OPTIONAL.get(module_name, set())
        for name, entry in expected.items():
            if name in removals or entry["kind"] in REMOVED_KINDS:
                if name in actual:
                    problems.append(f"{module_name}.{name}: should be removed")
                continue
            if name not in actual:
                if name not in optional:
                    problems.append(f"{module_name}.{name}: removed")
                continue
            _compare_entry(f"{module_name}.{name}", entry, actual[name], problems)
        additions = DELIBERATE_ADDITIONS.get(module_name, set())
        for name in sorted(set(actual) - set(expected)):
            if name not in additions:
                problems.append(f"{module_name}.{name}: added")
        for name in sorted(additions - set(actual)):
            problems.append(f"{module_name}.{name}: should be added")
        for name, entry in actual.items():
            if entry["kind"] in REMOVED_KINDS and name in expected:
                pass  # reported above as "should be removed"
            elif entry["kind"] in REMOVED_KINDS:
                problems.append(f"{module_name}.{name}: exposes an OCCT object")
    return problems


def test_api_surface():
    expected = json.loads(SNAPSHOT.read_text())
    problems = compare(expected, collect_surface())
    assert problems == [], "API surface changed:\n" + "\n".join(problems)


if __name__ == "__main__":
    if sys.argv[1:] == ["--update"]:
        SNAPSHOT.write_text(json.dumps(collect_surface(), indent=1, sort_keys=True) + "\n")
        print(f"wrote {SNAPSHOT}")
    else:
        print(__doc__)
