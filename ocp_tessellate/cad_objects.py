#
# Copyright 2023 Bernhard Walter
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import numpy as np

from .utils import Color, Timer
from .ocp_utils import (
    bounding_box,
    get_point,
    loc_to_tq,
    get_location,
    np_bbox,
    is_line,
    line,
    make_compound,
    identity_location,
    cross,
)
from .tessellator import discretize_edge, tessellate, compute_quality
from .mp_tessellator import is_apply_result, mp_tessellate, init_pool, keymap
from .defaults import get_default

UNSELECTED = 0
SELECTED = 1
EMPTY = 3

#
# Simple Part and PartGroup classes
#


class Instance:
    def __init__(self, shape):
        self.shape = shape
        self.mesh = None
        self.quality = None


INSTANCES = []


def get_instances():
    return [instance.mesh for instance in INSTANCES]


def set_instances(instances):
    global INSTANCES
    INSTANCES = [Instance(instance) for instance in instances]


class CADObject(object):
    def __init__(self):
        self.color = Color(get_default("default_color"))

    def to_state(self):
        raise NotImplementedError("not implemented yet")

    def to_assembly(self):
        raise NotImplementedError("not implemented yet")

    def collect_shapes(
        self,
        path,
        loc,
        deviation,
        angular_tolerance,
        edge_accuracy,
        render_edges,
        parallel,
        progress,
        timeit,
    ):
        raise NotImplementedError("not implemented yet")


class OCP_Part(CADObject):
    def __init__(
        self, shape, name="Part", color=None, show_faces=True, show_edges=True
    ):
        super().__init__()
        self.name = name
        self.id = None
        self.color = Color(get_default("default_color") if color is None else color)
        self.loc = identity_location()

        self.shape = shape
        self.set_states(show_faces, show_edges)
        self.renderback = False

    def set_states(self, show_faces, show_edges):
        self.state_faces = SELECTED if show_faces else UNSELECTED
        self.state_edges = SELECTED if show_edges else UNSELECTED

    def to_state(self):
        return [self.state_faces, self.state_edges]

    def to_assembly(self):
        return OCP_PartGroup([self])

    def collect_shapes(
        self,
        path,
        loc,
        deviation,
        angular_tolerance,
        edge_accuracy,
        render_edges,
        parallel=False,
        progress=None,
        timeit=False,
    ):
        self.id = f"{path}/{self.name}"

        if isinstance(self.shape, dict):
            ind = self.shape["ref"]
            shape = [INSTANCES[ind].shape]
            mesh = INSTANCES[ind].mesh
            quality = INSTANCES[ind].quality
        else:
            ind = None
            shape = self.shape
            mesh = None

        if mesh is None:
            with Timer(timeit, self.name, "compute quality:", 2) as t:
                # A first rough estimate of the bounding box.
                # Will be too large, but is sufficient for computing the quality
                bb = bounding_box(shape, loc=get_location(loc), optimal=False)
                quality = compute_quality(bb, deviation=deviation)
                t.info = str(bb)

            with Timer(timeit, self.name, "tessellate:     ", 2) as t:
                func = mp_tessellate if parallel else tessellate
                mesh = func(
                    shape,
                    deviation=deviation,
                    quality=quality,
                    angular_tolerance=angular_tolerance,
                    debug=timeit,
                    compute_edges=render_edges,
                    progress=progress,
                )

                t.info = f"{{quality:{quality:.4f}, angular_tolerance:{angular_tolerance:.2f}}}"

        with Timer(timeit, self.name, "bounding box:   ", 2):
            combined_loc = get_location(loc, False)
            if self.loc is not None:
                combined_loc = combined_loc * self.loc
            t, q = loc_to_tq(combined_loc)
            if parallel and is_apply_result(mesh):
                # store the instance mesh
                if ind is not None and INSTANCES[ind].mesh is None:
                    INSTANCES[ind].mesh = mesh
                    INSTANCES[ind].quality = quality
                mesh = {"ref": ind, "t": t, "q": q}
                bb = {}
            else:
                bb = np_bbox(mesh["vertices"], t, q)
                # store the instance mesh
                if ind is not None and INSTANCES[ind].mesh is None:
                    INSTANCES[ind].mesh = mesh
                    INSTANCES[ind].quality = quality

                if isinstance(self.shape, dict):
                    mesh = self.shape  # return the instance id

        if isinstance(self.color, tuple):
            color = [c.web_color for c in self.color]  # pylint: disable=not-an-iterable
            alpha = 1.0
        else:
            color = self.color.web_color
            alpha = self.color.a

        return {
            "id": self.id,
            "type": "shapes",
            "name": self.name,
            "shape": mesh,
            "color": color,
            "alpha": alpha,
            "loc": None if self.loc is None else loc_to_tq(self.loc),
            "renderback": self.renderback,
            "accuracy": quality,
            "bb": bb,
        }

    def compound(self):
        return make_compound(self.shape)

    def compounds(self):
        return [self.compound()]


class OCP_Faces(OCP_Part):
    def __init__(
        self, faces, name="Faces", color=None, show_faces=True, show_edges=True
    ):
        super().__init__(
            faces, name, color, show_faces, show_edges
        )  # TODO combine faces
        self.color = Color(color or (238, 130, 238))
        self.loc = None
        self.renderback = True


class OCP_Edges(CADObject):
    def __init__(self, edges, name="Edges", color=None, width=1):
        super().__init__()
        self.shape = edges
        self.name = name
        self.id = None

        if color is not None:
            if isinstance(color, (list, tuple)) and isinstance(color[0], Color):
                self.color = color
            elif isinstance(color, Color):
                self.color = color
            else:
                self.color = Color(color)
        self.loc = None
        self.width = width

    def to_state(self):
        return [EMPTY, SELECTED]

    def to_assembly(self):
        return OCP_PartGroup([self])

    def collect_shapes(
        self,
        path,
        loc,
        deviation,
        angular_tolerance,
        edge_accuracy,
        render_edges,
        parallel=False,
        progress=None,
        timeit=False,
    ):
        self.id = f"{path}/{self.name}"

        with Timer(timeit, self.name, "bounding box:", 2) as t:
            bb = bounding_box(self.shape, loc=get_location(loc))
            quality = compute_quality(bb, deviation=deviation)
            deflection = quality / 100 if edge_accuracy is None else edge_accuracy
            t.info = str(bb)

        with Timer(timeit, self.name, "discretize:  ", 2) as t:
            t.info = f"quality: {quality}, deflection: {deflection}"
            edges = []
            for edge in self.shape:
                d = discretize_edge(edge, deflection)
                if len(d) == 1 and not is_line(edge):
                    num = int(0.1 / deflection)
                    d = discretize_edge(edge, num=num)
                edges.extend(d)
            edges = np.asarray(edges)

        if progress is not None:
            progress.update("e")

        color = (
            [c.web_color for c in self.color]
            if isinstance(self.color, tuple)
            else self.color.web_color
        )

        return {
            "id": self.id,
            "type": "edges",
            "name": self.name,
            "shape": edges,
            "color": color,
            "loc": None if self.loc is None else loc_to_tq(self.loc),
            "width": self.width,
            "bb": bb.to_dict(),
        }


class OCP_Vertices(CADObject):
    def __init__(self, vertices, name="Vertices", color=None, size=1):
        super().__init__()
        self.shape = vertices
        self.name = name
        self.id = None
        self.color = Color(color or (148, 0, 211))
        self.loc = None
        self.size = size

    def to_state(self):
        return [EMPTY, SELECTED]

    def to_assembly(self):
        return OCP_PartGroup([self])

    def collect_shapes(
        self,
        path,
        loc,
        deviation,
        angular_tolerance,
        edge_accuracy,
        render_edges,
        parallel=False,
        progress=None,
        timeit=False,
    ):
        self.id = f"{path}/{self.name}"

        bb = bounding_box(self.shape, loc=get_location(loc))

        if progress is not None:
            progress.update("v")

        return {
            "id": self.id,
            "type": "vertices",
            "name": self.name,
            "shape": np.asarray(
                [get_point(vertex) for vertex in self.shape], dtype="float32"
            ),
            "color": self.color.web_color,
            "loc": None if self.loc is None else loc_to_tq(self.loc),
            "size": self.size,
            "bb": bb.to_dict(),
        }


class OCP_PartGroup(CADObject):
    def __init__(self, objects, name="Group", loc=None):
        super().__init__()
        self.objects = objects
        self.name = name
        self.loc = identity_location() if loc is None else loc
        self.id = None

    def to_nav_dict(self):
        return {
            "type": "node",
            "name": self.name,
            "id": self.id,
            "children": [obj.to_nav_dict() for obj in self.objects],
        }

    def to_assembly(self):
        return self

    def add(self, cad_obj):
        self.objects.append(cad_obj)

    def add_list(self, cad_objs):
        self.objects += cad_objs

    def collect_shapes(
        self,
        path,
        loc,
        deviation,
        angular_tolerance,
        edge_accuracy,
        render_edges,
        parallel=False,
        progress=None,
        timeit=False,
    ):
        self.id = f"{path}/{self.name}"

        if loc is None and self.loc is None:
            combined_loc = None
        elif loc is None:
            combined_loc = self.loc
        else:
            combined_loc = loc * self.loc

        result = {
            "parts": [],
            "loc": None if self.loc is None else loc_to_tq(self.loc),
            "name": self.name,
            "id": self.id,
        }
        for obj in self.objects:
            result["parts"].append(
                obj.collect_shapes(
                    self.id,
                    combined_loc,
                    deviation,
                    angular_tolerance,
                    edge_accuracy,
                    render_edges,
                    parallel,
                    progress,
                    timeit,
                )
            )
        return result

    def to_state(self, parents=None):  # pylint: disable=arguments-differ
        parents = parents or ()
        result = {}
        for i, obj in enumerate(self.objects):
            if isinstance(obj, OCP_PartGroup):
                for k, v in obj.to_state((*parents, i)).items():
                    result[k] = v
            else:
                result[str(obj.id)] = obj.to_state()
        return result

    def count_shapes(self):
        def c(pg):
            count = 0
            for p in pg.objects:
                if isinstance(p, OCP_PartGroup):
                    count += c(p)
                else:
                    count += 1
            return count

        return c(self)

    def compounds(self):
        result = []
        for obj in self.objects:
            result += obj.compounds()
        return result

    def compound(self):
        return make_compound(self.compounds())


class CoordSystem(OCP_Edges):
    def __init__(self, name, origin, X, Z, size=1):
        Y = cross(X, Z)
        x_edge = line(origin, [o + v * size for o, v in zip(origin, X)])
        y_edge = line(origin, [o + v * size for o, v in zip(origin, Y)])
        z_edge = line(origin, [o + v * size for o, v in zip(origin, Z)])
        colors = (Color("red"), Color("green"), Color("blue"))
        super().__init__([x_edge, y_edge, z_edge], name, colors, width=3)
