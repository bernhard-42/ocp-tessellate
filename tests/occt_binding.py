"""The OCCT bindings the tests build raw OCCT objects with.

Tests that combine raw OCCT objects with build123d or CadQuery objects must use
the binding those libraries were built for: BINDING. Tests of ocp_tessellate's
own dispatch run once per installed binding: INSTALLED.
"""

import importlib
import importlib.util
import os

import build123d

# the top-level package of the OCCT classes build123d wraps: "OCP" or "nanocct"
BINDING = type(build123d.Box(1, 1, 1).wrapped).__module__.partition(".")[0]

INSTALLED = [b for b in ("OCP", "nanocct") if importlib.util.find_spec(b) is not None]

# the binding of what no OCCT object decides in this run: the one OCCT_BINDING
# names, else the first installed (OCP before nanocct). Where both bindings are
# installed, run the suite once per binding: OCCT_BINDING=OCP and =nanocct.
_WANTED = os.environ.get("OCCT_BINDING")
DEFAULT_BINDING = _WANTED if _WANTED is not None else INSTALLED[0]


def root(binding: str):
    """The binding's top-level package, the module OCP or nanocct: ocp_tessellate's kernel."""
    return importlib.import_module(binding)


def occt(package: str, name: str, binding: str = BINDING):
    """The class `name` of the OCCT package `package`, e.g. occt("gp", "gp_Pnt")."""
    return getattr(importlib.import_module(f"{binding}.{package}"), name)
