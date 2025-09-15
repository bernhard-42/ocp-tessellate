# %%
import os

from build123d import *
from ocp_vscode import *

# enable_native_tessellator()

b = Box(1, 1, 1)
c = fillet(b.edges(), 0.3)
show(c)

# %%
stl_name = "box.stl"
export_stl(c, stl_name)
f = import_stl(stl_name)

show(
    Pos(2, 0, 0) * c,
    f,
    render_normals=True,
    render_edges=True,
    timeit=True,
)


# %%

f = import_stl("box.stl")

show(f, Pos(2, 0, 0) * c)

# %%

os.remove(stl_name)
