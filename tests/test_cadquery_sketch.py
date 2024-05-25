# %%
import cadquery as cq
from ocp_vscode import show, set_defaults
from pathlib import Path

c = Path.cwd()
set_defaults(axes=True, axes0=True)

# %%

result = cq.Sketch().segment((0.0, 0), (2.0, 0.0)).segment((0.0, 2)).close()

show(result)
# %%

result = (
    cq.Sketch()
    .segment((0.0, 0), (2.0, 0.0))
    .segment((0.0, 2))
    .close()
    .arc((0.6, 0.6), 0.4, 0.0, 360.0)
    .assemble(tag="face")
    .edges("%LINE", tag="face")
    .vertices()
    .chamfer(0.2)
    .reset()
)

show(result)
# %%

result = (
    cq.Sketch()
    .trapezoid(4, 3, 90)
    .vertices()
    .circle(0.5, mode="s")
    .reset()
    .vertices()
    .fillet(0.25)
    .reset()
    .rarray(0.6, 1, 5, 1)
    .slot(01.5, 0.4, mode="s", angle=90)
    .reset()
)
show(result)

# %%

result = (
    cq.Workplane()
    .transformed((0, 90, 90), (2, 0, 0))
    .sketch()
    .trapezoid(4, 3, 90)
    .vertices()
    .circle(0.5, mode="s")
    .reset()
    .vertices()
    .fillet(0.25)
    .reset()
    .rarray(0.6, 1, 5, 1)
    .slot(1.5, 0.4, mode="s", angle=90)
    .reset()
    .finalize()
)

show(result, timeit=True)
# %%
