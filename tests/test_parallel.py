# %%
import os
from ocp_vscode import show, show_object

os.environ["OCP_CACHE_SIZE_MB"] = "1024"

import cadquery as cq
from build123d import *

from ocp_tessellate.stepreader import StepReader
import time

# %%

reader = StepReader()
reader.load("/tmp/RC_Buggy_2_front_suspension.stp")
rc = reader.to_cadquery()

# %%

t = time.time()
show(rc, up="Y", parallel=True, timeit=False)
print("\n", time.time() - t)

# %%

t = time.time()
show(rc, up="Y", parallel=True, timeit=False)
print("\n", time.time() - t)

# %%
