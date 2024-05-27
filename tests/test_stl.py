# %%
from build123d import *
from ocp_vscode import disable_native_tessellator, enable_native_tessellator, show

from ocp_tessellate.convert import tessellate_group, to_assembly

enable_native_tessellator()

b = Box(1, 1, 1)
c = fillet(b.edges(), 0.3)
show(c)

# %%
stl_name = "box.stl"
export_stl(c, stl_name)
f = import_stl(stl_name)

show(
    # Pos(2, 0, 0) * c,
    f,
    render_normals=True,
    render_edges=True,
    timeit=True,
)

# %%

import os

os.remove(stl_name)

# %%

f = import_stl("/Users/bernhard/Development/robot-dog/stl/housing.stl")
# f = import_stl("/tmp/base.stl")
pg, instances = to_assembly(f)
result = tessellate_group(pg, instances)
##
show(
    f,
    # colors=["orange"],
    # render_normals=True,
    # default_edgecolor="#bbb",
)

# %%
