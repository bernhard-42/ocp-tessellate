# %%
import numpy as np
from build123d import *
from ocp_vscode import *
from ocp_vscode.show import Progress
from ocp_tessellate.convert import tessellate_group, combined_bb, to_assembly
from ocp_tessellate.ocp_utils import np_bbox

p = Progress()
# %%
# generate boxes (may need to run this block a few times to see error)
ni, nj = 10000, 30  # loop through ni rows, each with nj boxes

for i in range(ni):
    d = i % 20
    boxes = []  # partlist
    keys = []
    for j in range(nj):
        # x = 0.1 + 0.9 * np.random.rand()  # box will be random size 0-1
        x = 0.1 + (i + j) / (ni + nj)
        box = Pos(2 * d, j, 0) * Box(2 * x, x, x)
        boxes.append(box)

        del box

    result = to_assembly(boxes)
    instances, shapes, states, mapping = tessellate_group(result, progress=p)
    for j in range(nj):
        print(
            i,
            j,
            ":",
            shapes["parts"][j]["loc"][0],
            np_bbox(
                instances[shapes["parts"][j]["shape"]["ref"]]["vertices"],
                shapes["parts"][j]["loc"][0],
                (0, 0, 0, 1),
            ),
        )

    # get bb
    bb = combined_bb(shapes)
    shapes["bb"] = bb.to_dict()

    # check that bb is correct
    if bb.xmin < (2 * d - 1) or bb.xmax > (2 * d + 1):
        #        show(boxes)  # shapes and states
        print("==>", bb.xmin, bb.xmax)
        break

    del shapes, states
