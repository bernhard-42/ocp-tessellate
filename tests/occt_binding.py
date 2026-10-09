"""The OCCT bindings the tests build raw OCCT objects with.

Tests that combine raw OCCT objects with build123d or CadQuery objects must use
the binding those libraries were built for: build123d_binding(). Tests of
ocp_tessellate's own dispatch run once per installed binding: INSTALLED.
"""

import functools
import importlib
import importlib.util
import os

INSTALLED = [b for b in ("OCP", "nanocct") if importlib.util.find_spec(b) is not None]

# the binding of what no OCCT object decides in this run: the one OCCT_BINDING
# names, else the first installed (OCP before nanocct). Where both bindings are
# installed and build123d is the nanocct one, it sets OCCT_BINDING=nanocct on
# import and refuses OCCT_BINDING=OCP, so the suite runs with nanocct and the
# OCP default is tested by the modules that do not import build123d:
#   OCCT_BINDING=OCP python -m pytest tests/test_kernel.py tests/test_materials.py
_WANTED = os.environ.get("OCCT_BINDING")
DEFAULT_BINDING = _WANTED if _WANTED is not None else INSTALLED[0]


@functools.cache
def build123d_binding() -> str:
    """The top-level package of the OCCT classes build123d wraps: "OCP" or "nanocct".

    build123d is imported here and not at module level, so that the tests of
    ocp_tessellate's own dispatch, which import this module, also run where
    build123d cannot be imported (OCCT_BINDING=OCP beside the nanocct build123d).
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
