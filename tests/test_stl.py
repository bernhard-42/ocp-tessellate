from alg123d import *
import numpy as np
from ocp_tessellate.convert import to_assembly, tessellate_group

b = Box(1, 1, 1)
c = chamfer(b, b.edges(), 0.1)
show(c, default_edgecolor=(255, 0, 0))
stl_name = "chamfer_box.stl"
c.export_stl(stl_name)

# %%

f = import_stl(stl_name)

show(c @ Pos(2, 0, 0), f, render_normals=True)

# %%

import os

os.remove(stl_name)

# %%

# f = Face.import_stl("/Users/bernhard/Development/robot-dog/stl/base.stl")
f = import_stl("/tmp/base.stl")
pg = to_assembly(f)
result = tessellate_group(pg)

show(
    f,
    colors=["orange"],
    render_normals=True,
    default_edgecolor="#bbb",
)

# %%
