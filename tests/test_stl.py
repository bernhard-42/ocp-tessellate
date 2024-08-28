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

f = import_stl("tests/box.stl")

show(f, Pos(2, 0, 0) * c)

# %%

import os

os.remove(stl_name)
