from alg123d import *
import numpy as np
from ocp_tessellate.convert import to_assembly, tessellate_group

b = Box(1, 1, 1)
show(b, default_edgecolor=(255, 0, 0))
# %%

f = Face.import_stl("chamfer_box.stl")
pg1 = to_assembly(f)
r1 = tessellate_group(pg1)
t1 = np.asarray(r1[1]["parts"][0]["shape"]["triangles"]).reshape(-1, 3)
v1 = np.asarray(r1[1]["parts"][0]["shape"]["vertices"]).reshape(-1, 3)
n1 = np.asarray(r1[1]["parts"][0]["shape"]["normals"]).reshape(-1, 3)

show(f, render_normals=True)


# %%

b = Box(1, 1, 1, align=Align.CENTER)
c = chamfer(b, b.edges(), 0.1)

pg2 = to_assembly(c)
r2 = tessellate_group(pg2)
t2 = np.asarray(r2[0][0]["triangles"]).reshape(-1, 3)
v2 = np.asarray(r2[0][0]["vertices"]).reshape(-1, 3)
n2 = np.asarray(r2[0][0]["normals"]).reshape(-1, 3)
# %%

show(c, render_normals=True)

# %%

# f = Face.import_stl("/Users/bernhard/Development/robot-dog/stl/base.stl")
f = Face.import_stl("/tmp/base.stl")
pg = to_assembly(f)
result = tessellate_group(pg)

show(
    f,
    colors=["orange"],
    render_normals=True,
    default_edgecolor="red",
)

# %%

show(f)

# %%
