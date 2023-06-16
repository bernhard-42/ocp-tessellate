# %%
import cadquery as cq
import build123d as bd
from ocp_tessellate.utils import Color
from ocp_tessellate.ocp_utils import get_rgba
from ocp_vscode import show

# %%

print(get_rgba(cq.Color("red")))
print(get_rgba(cq.Color("green"), 0.5))
print(get_rgba(bd.Color("blue")))
print(get_rgba(Color("red")))
print(get_rgba(cq.Color("red").wrapped))
print(get_rgba("red"))

# %%

s = bd.Sphere(1)
b = bd.Box(1, 2, 3)
b1 = bd.Pos(X=3) * b
b2 = bd.Pos(X=-3) * b

show(
    s,
    b1,
    b2,
    names=["s", "b1", "b2"],
    colors=["red", "green", "blue"],
    alphas=[0.8, 0.6, 0.4],
    default_edgecolor="yellow",
    timeit=True,
)

# %%

show(
    bd.Pos(1, 2, 3) * b,
    b.faces(),
    b.edges(),
    b.vertices(),
    default_facecolor="yellow",
    default_thickedgecolor=(0, 0.2, 0.8),
    default_vertexcolor="red",
    default_edgecolor="magenta",
    default_color=(0, 0, 255),
)
# %%
