# %%
import build123d as bd
import cadquery as cq
from ocp_vscode import show

from ocp_tessellate.ocp_utils import get_rgba
from ocp_tessellate.utils import Color

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
    default_facecolor="green",
    default_thickedgecolor=(0, 0.0, 1.0),
    default_vertexcolor="red",
    default_edgecolor="cyan",
    default_color=(255, 0, 255),
)
# %%
