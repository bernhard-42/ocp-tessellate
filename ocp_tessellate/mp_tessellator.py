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

from .tessellator import cache, make_key
import multiprocessing
import multiprocessing.pool
from multiprocessing import shared_memory
from cachetools import cached
from .mp_tess import mp_tess
from .ocp_utils import serialize

pool = None


class KeyMapper:
    def __init__(self):
        self.counter = 0
        self.map = {}

    def reset(self):
        self.counter = 0
        self.map = {}

    def add(self, key):
        path = f"obj{self.counter}"
        self.counter += 1
        self.map[path] = key
        return path

    def get_key(self, path):
        return self.map.get(path)


keymap = KeyMapper()


def clear_shared_mem(path):
    try:
        s = shared_memory.SharedMemory(path)
        s.close()
        s.unlink()
    except:  # pylint: disable=bare-except
        ...


def init_pool():
    global pool  # pylint: disable=global-statement
    if pool is None:
        pool = multiprocessing.Pool(int(multiprocessing.cpu_count() * 0.8))


def close_pool():
    global pool  # pylint: disable=global-statement
    pool.close()
    pool.join()
    pool = None


def get_mp_result(apply_result):
    path, result = apply_result.get()

    # update cache to hold full result instead of ApplyResult object
    key = keymap.get_key(path)
    cache.__setitem__(key, result)

    clear_shared_mem(path)
    return result


def is_apply_result(obj):
    return isinstance(obj, multiprocessing.pool.ApplyResult)


# This will cache the ApplyResult object after calling mp_tess in an async way.
# Cache will be updated in get_mp_result so that it holds the actual result
@cached(cache, key=make_key)
def mp_tessellate(
    shapes,
    deviation,  # only provided for managing cache
    quality,
    angular_tolerance,
    compute_faces=True,
    compute_edges=True,
    debug=False,
    progress=None,
):
    shape = shapes[0]

    key = make_key(
        shape,
        deviation,
        quality,
        angular_tolerance,
        compute_edges=True,
        compute_faces=True,
    )
    path = keymap.add(key)

    clear_shared_mem(path)

    s = serialize(shape)
    sm = shared_memory.SharedMemory(path, True, len(s))
    sm.buf[: len(s)] = s

    result = pool.apply_async(
        mp_tess,
        (
            path,
            deviation,
            quality,
            angular_tolerance,
            compute_faces,
            compute_edges,
            debug,
            progress,
        ),
    )

    return result
