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

"""The default kernel's OCCT names, for the modules that re-export them.

Module-level OCCT names such as `ocp_utils.TopoDS_Shape` are part of the
public API (tests/test_api_surface.py), and annotations use them. They are the
default kernel's classes. Code reaches OCCT through `kernel_of()`, `kernel()`
and `ANY` instead (tests/test_kernel.py).
"""

from .ocp import *  # noqa: F403
