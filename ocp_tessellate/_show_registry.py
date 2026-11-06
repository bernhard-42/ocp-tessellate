"""Which kernel an object belongs to: the registry behind `ocp_tessellate.plugin` and
`ocp_tessellate.kernels`.

A module of its own, because `ocp_utils.bbox` and `cad_objects` ask it about the objects
they meet, and `ocp_tessellate.plugin` imports both.
"""

from __future__ import annotations

import base64
import warnings
from dataclasses import dataclass
from importlib.metadata import entry_points

from ._kernel import binding_of
from .protocols import ShowProtocol, TessellationProtocol

# the entry point group of what a kernel plugin draws with, keyed by its kernel tag, whose
# value is the module that registers it:
# `[project.entry-points."ocp_viewer.kernels.show"] smlib = "ocp_viewer_smlibpy.show"`
# ocp_viewer_core reads `ocp_viewer.kernels.backend` in the backend's process
KERNEL_ENTRY_POINT_GROUP = "ocp_viewer.kernels.show"

# The version of the plugin interface this ocp-tessellate serves. A plugin states the one
# it was written against, as a number of its own: a later version passes new arguments only
# to plugins that state it, so an existing plugin keeps working.
PLUGIN_API = 1


@dataclass(frozen=True)
class _Registered:
    """What a kernel plugin told `register_show`."""

    kernel: str
    tessellation: TessellationProtocol
    show: ShowProtocol
    api: int


# kernel tag -> what its plugin registered
_show_plugins: dict[str, _Registered] = {}
# all installed plugins are imported once, when the first object is asked about
_plugins_loaded = False
# the plugins whose `is_object` was reported as raising, to report each once
_is_object_reported: set[str] = set()
# OCCT's implementation, set by the module that holds it (tessellator)
_occt_tessellation: TessellationProtocol | None = None


def register_show(kernel, tessellation, show, *, api):
    """Register a kernel with the host's `show` and `show_all`: its implementations of
    `TessellationProtocol` and `ShowProtocol`, under its kernel tag, which is the tag it
    registers its `BackendProtocol` under in ocp_viewer_core. `api` is the version of the
    plugin interface the plugin was written against, a number of its own."""
    if not isinstance(tessellation, TessellationProtocol):
        raise TypeError(f"{type(tessellation).__name__} does not implement TessellationProtocol")
    if not isinstance(show, ShowProtocol):
        raise TypeError(f"{type(show).__name__} does not implement ShowProtocol")
    if kernel == "" or kernel == "OCCT":
        raise ValueError(f"'{kernel}' is no kernel tag of a plugin: 'OCCT' names OCCT's own shapes")
    if type(api) is not int:
        raise TypeError(f"Kernel plugin '{kernel}': api must be an int, not {api!r}")
    if api < 1 or api > PLUGIN_API:
        raise ValueError(
            f"Kernel plugin '{kernel}' was written for plugin interface {api}, "
            f"this ocp-tessellate serves interface 1 to {PLUGIN_API}"
        )
    action = "re-registered" if kernel in _show_plugins else "registered"
    _show_plugins[kernel] = _Registered(kernel, tessellation, show, api)
    print(f"Kernel plugin '{kernel}' {action} for drawing ({type(show).__module__})", flush=True)


def _set_occt_tessellation(tessellation):
    global _occt_tessellation  # pylint: disable=global-statement
    _occt_tessellation = tessellation


def _load_plugins():
    """Import every installed kernel plugin, once: importing one is what registers it. A
    script usually imports only the kernel, and a debug stop sees whatever it holds."""
    global _plugins_loaded  # pylint: disable=global-statement
    if _plugins_loaded is True:
        return
    # first: a plugin's import may ask about objects itself
    _plugins_loaded = True
    for entry_point in entry_points(group=KERNEL_ENTRY_POINT_GROUP):
        try:
            entry_point.load()
        except Exception as ex:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            # a broken plugin must not break showing everything else
            warnings.warn(f"Kernel plugin '{entry_point.value}' ('{entry_point.name}') failed to load: {ex}", stacklevel=2)
            continue
        if entry_point.name not in _show_plugins:
            warnings.warn(
                f"Kernel plugin '{entry_point.value}' was imported, but did not register "
                f"its kernel tag '{entry_point.name}' with register_show",
                stacklevel=2,
            )


def _registered_of(obj) -> _Registered | None:
    """The registration of the plugin that owns `obj`, or None. Never raises: it is
    asked about whatever a scope holds. A plugin whose `is_object` raises is reported."""
    _load_plugins()
    # OCCT's shape is `to_ocp`'s, whatever a plugin's `is_object` would answer, as in `tessellation_of`
    if binding_of(obj) is not None:
        return None
    for registered in _show_plugins.values():
        try:
            if registered.show.is_object(obj=obj) is True:
                return registered
        except Exception as ex:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            if registered.kernel not in _is_object_reported:
                _is_object_reported.add(registered.kernel)
                warnings.warn(f"is_object of kernel plugin '{registered.kernel}' raised: {ex!r}", stacklevel=2)
    return None


def _first(obj):
    """A list of shapes belongs to the kernel of its first shape."""
    if isinstance(obj, (list, tuple)) and len(obj) > 0:
        return obj[0]
    return obj


def show_of(obj) -> ShowProtocol | None:
    """The `ShowProtocol` of the plugin that owns `obj`, or None, also for OCCT objects:
    their dispatch is `to_ocp`'s. Never raises."""
    registered = _registered_of(obj)
    return None if registered is None else registered.show


def children_of(show: ShowProtocol, obj) -> list | None:
    """What `show.get_children` returned for `obj`, checked: None, or (name, child, relative
    placement) entries."""
    children = show.get_children(obj=obj)
    if children is None:
        return None
    for entry in children:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            raise TypeError(
                f"{type(show).__name__}.get_children must return (name, child, relative placement) "
                f"entries, not {entry!r}"
            )
    return children


def tessellation_of(obj) -> TessellationProtocol:
    """The `TessellationProtocol` of a shape or a list of shapes: OCCT's for an OCCT
    shape, or for no shape at all, else its plugin's. Raises for anything else, so it
    is for what is known to be a shape: wrappers are not looked into, callers pass
    `.wrapped`."""
    first = _first(obj)
    if binding_of(first) is not None or (isinstance(first, (list, tuple)) and len(first) == 0):
        assert _occt_tessellation is not None, "ocp_tessellate.tessellator sets it"
        return _occt_tessellation
    registered = _registered_of(first)
    if registered is None:
        raise TypeError(f"unsupported kernel: {type(first).__name__}")
    return registered.tessellation


def kernel_tag_of(obj) -> str | None:
    """The kernel tag of a shape or a list of shapes, None for an OCCT shape."""
    first = _first(obj)
    if binding_of(first) is not None:
        return None
    registered = _registered_of(first)
    return None if registered is None else registered.kernel


def is_external_object(obj) -> bool:
    """Whether a registered kernel plugin owns `obj`."""
    return _registered_of(obj) is not None


def encode_kernel_shapes(mapping: dict) -> dict:
    """The backend's model with every kernel shape `{"kernel": tag, "obj": shape}` replaced by
    base64 of its plugin's `serialize` bytes: the pre-pass before the model is sent, so the
    codec never sees a kernel's object. OCCT entries are untouched (the codec writes them),
    and the mapping given is not changed."""

    def walk(parts: list[dict]) -> list[dict]:
        result = []
        for part in parts:
            if part.get("parts") is not None:
                result.append({**part, "parts": walk(part["parts"])})
                continue
            shape = part["shape"]
            if isinstance(shape, dict) and "kernel" in shape:
                data = _show_plugins[shape["kernel"]].show.serialize(shape=shape["obj"])
                shape = {"kernel": shape["kernel"], "obj": base64.b64encode(data).decode("utf-8")}
            result.append({**part, "shape": shape})
        return result

    return {**mapping, "parts": walk(mapping["parts"])}
