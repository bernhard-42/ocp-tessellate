import pytest

from ocp_tessellate import prefer_nanocct


@pytest.fixture(autouse=True)
def _default_binding_preference():
    """prefer_nanocct is process-wide: every test starts and ends without it."""
    prefer_nanocct(False)
    yield
    prefer_nanocct(False)
