"""The OCCT bindings the tests build raw OCCT objects with.

Tests that combine raw OCCT objects with build123d or CadQuery objects must use
the binding those libraries were built for: build123d_binding(). Tests of
ocp_tessellate's own dispatch run once per installed binding: INSTALLED.
"""

import functools
import importlib
import importlib.util

INSTALLED = [b for b in ("OCP", "nanocct") if importlib.util.find_spec(b) is not None]

# the binding of what no OCCT object decides: nanocct if it is installed, else
# OCP. The OCP default is tested where nanocct is not installed, and in
# test_kernel.py's installation cases, which hide a binding in a subprocess.
DEFAULT_BINDING = "nanocct" if "nanocct" in INSTALLED else "OCP"


@functools.cache
def build123d_binding() -> str:
    """The top-level package of the OCCT classes build123d wraps: "OCP" or "nanocct".

    build123d is imported here and not at module level, so that the tests of
    ocp_tessellate's own dispatch, which import this module, also run where
    build123d is not installed.
    """
    import build123d

    return type(build123d.Box(1, 1, 1).wrapped).__module__.partition(".")[0]


def root(binding: str):
    """The binding's top-level package, the module OCP or nanocct: ocp_tessellate's kernel."""
    return importlib.import_module(binding)


def occt(package: str, name: str, binding: str | None = None):
    """The class `name` of the OCCT package `package`, e.g. occt("gp", "gp_Pnt").

    Without `binding`, the one build123d wraps.
    """
    if binding is None:
        binding = build123d_binding()
    return getattr(importlib.import_module(f"{binding}.{package}"), name)
