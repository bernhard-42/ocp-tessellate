# %%
import gc
import random

from build123d import *
from ocp_vscode import *

from ocp_tessellate.convert import combined_bb, tessellate_group, to_assembly
from ocp_tessellate.ocp_utils import np_bbox


class Progress:
    """Progress indicator for tessellation"""

    def __init__(self, levels=None):
        if levels is None:
            self.levels = "+c-*"
        else:
            self.levels = levels

    def update(self, mark="+"):
        """Update progress indicator"""
        if mark in self.levels:
            end = ""
            if mark == "c":
                print("\nCache hit!")
                end = "\n"
            print(mark, end=end, flush=True)


# %%
from ocp_tessellate.tessellator import cache

cache.clear()
n = 1000
I, J = list(range(1, 100)), list(range(n))
random.shuffle(J)
random.shuffle(I)
y = 0
for jj, j in enumerate(J):
    for ii, i in enumerate(I):
        print(ii, jj, (i, j), flush=True)
        x = i / 10
        y += 2 * x

        box = Pos(y, y, y) * Box(x, x, x, align=(Align.MIN, Align.MIN, Align.MIN))

        group, instances = to_assembly(box)
        instances, shapes, mapping = tessellate_group(
            group, instances, progress=Progress("c")
        )
        bb = combined_bb(shapes)
        if not (abs(bb.xmin - y) < 1e-6 and abs(bb.xmax - (y + x)) < 1e-5):
            print(i, ":", y, y + x)
            print(bb)
            print(box.bounding_box())
            raise RuntimeError("Cache hit")
        del box
        gc.collect()
