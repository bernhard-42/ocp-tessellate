#
# Copyright 2023 Bernhard Walter
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

"""Code to be distributed by Multiprocessing, hence a separate file"""

from multiprocessing import shared_memory

from .ocp_utils import deserialize
from .tessellator import tessellate


def mp_tess(
    name, deviation, quality, angular_tolerance, compute_faces, compute_edges, debug
):
    """This function will be pickled by multiprocessing"""
    sm = shared_memory.SharedMemory(name)
    shape = deserialize(bytes(sm.buf[0 : sm.size]))
    t = tessellate(
        [shape],
        deviation,
        quality,
        angular_tolerance,
        compute_faces,
        compute_edges,
        debug,
    )
    sm.close()
    sm.unlink()
    return (name, t)
