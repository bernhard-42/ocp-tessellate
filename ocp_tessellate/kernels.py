"""What a host asks about kernels: which one owns an object, and its implementations.

A plugin builds on `ocp_tessellate.plugin`; this module is for the hosts and the pipeline.
"""

from ocp_tessellate import tessellator  # noqa: F401 - registers what tessellation_of answers for OCCT
from ocp_tessellate._show_registry import (
    KERNEL_ENTRY_POINT_GROUP,
    PLUGIN_API,
    encode_kernel_shapes,
    is_external_object,
    kernel_tag_of,
    show_of,
    tessellation_of,
)

__all__ = [
    "KERNEL_ENTRY_POINT_GROUP",
    "PLUGIN_API",
    "encode_kernel_shapes",
    "is_external_object",
    "kernel_tag_of",
    "show_of",
    "tessellation_of",
]
