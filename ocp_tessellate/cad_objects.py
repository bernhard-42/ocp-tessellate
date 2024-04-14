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

import base64
import numpy as np

from .utils import Color, Timer
from .ocp_utils import (
    bounding_box,
    loc_to_tq,
    tq_to_loc,
    get_location,
    np_bbox,
    line,
    rect,
    axis_to_vecs,
    loc_to_vecs,
    identity_location,
    make_compound,
)
from .tessellator import (
    convert_vertices,
    discretize_edges,
    tessellate,
    compute_quality,
    face_mapper,
    edge_mapper,
    vertex_mapper,
)
from .mp_tessellator import is_apply_result, mp_tessellate, init_pool, keymap
from .defaults import get_default
import imagesize

UNSELECTED = 0
SELECTED = 1
EMPTY = 3

PROTOCOL_VERSION = 3

#
# Simple Part and PartGroup classes
#


class Instance:
    def __init__(self, shape):
        self.shape = shape
        self.mesh = None
        self.quality = None


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
        instances,
        meshed_instances,
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
        self,
        shape,
        cache_id=None,
        name="Part",
        color=None,
        show_faces=True,
        show_edges=True,
    ):
        super().__init__()
        self.name = name
        self.id = None
        self.cache_id = id(shape) if cache_id is None else cache_id
        self.color = Color(get_default("default_color") if color is None else color)
        self.loc = identity_location()
        self.texture = None
        self.shape = shape
        self.set_states(show_faces, show_edges)
        self.renderback = False
        self.solid = True

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
        instances,
        meshed_instances,
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
            if isinstance(instances[ind], Instance):
                mesh = instances[ind].mesh
            else:
                shape = instances[ind][1]
                if not isinstance(shape, (list, tuple)):
                    shape = [shape]
                meshed_instances[ind] = Instance(shape)
                mesh = None
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
                    self.cache_id,
                    deviation=deviation,
                    quality=quality,
                    angular_tolerance=angular_tolerance,
                    debug=timeit,
                    compute_edges=render_edges,
                    progress=progress,
                    shape_id=self.id,
                )

                t.info = f"{{quality:{quality:.4f}, angular_tolerance:{angular_tolerance:.2f}}}"

        with Timer(timeit, self.name, "bounding box:   ", 2):
            combined_loc = get_location(loc, False)
            if self.loc is not None:
                combined_loc = combined_loc * self.loc
            t, q = loc_to_tq(combined_loc)

            if parallel and is_apply_result(mesh):
                # store the instance mesh
                if ind is not None and meshed_instances[ind].mesh is None:
                    meshed_instances[ind].mesh = mesh
                    meshed_instances[ind].quality = quality
                mesh = {"ref": ind, "t": t, "q": q}
                bb = {}
            else:
                bb = np_bbox(mesh["vertices"], t, q)
                # store the instance mesh
                if ind is not None and meshed_instances[ind].mesh is None:
                    meshed_instances[ind].mesh = mesh
                    meshed_instances[ind].quality = quality

                if isinstance(self.shape, dict):
                    mesh = self.shape  # return the instance id

        if isinstance(self.color, tuple):
            color = [c.web_color for c in self.color]  # pylint: disable=not-an-iterable
            alpha = 1.0
        else:
            color = self.color.web_color
            alpha = self.color.a

        texture = None
        subtype = "solid" if self.solid else "faces"

        if isinstance(self, ImageFace):
            subtype = "image"
            image = {"data": self.image, "format": self.image_type}
            texture = {"image": image, "width": self.width, "height": self.height}

        return dict(id=self.id, shape=shape, loc=combined_loc), {
            "id": self.id,
            "type": "shapes",
            "subtype": subtype,
            "name": self.name,
            "shape": mesh,
            "color": color,
            "texture": texture,
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
        self,
        faces,
        cache_id=None,
        name="Faces",
        color=None,
        show_faces=True,
        show_edges=True,
    ):
        super().__init__(
            faces, cache_id, name, color, show_faces, show_edges
        )  # TODO combine faces
        self.color = Color(color or (238, 130, 238))
        self.loc = None
        self.renderback = True
        self.solid = False


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
        instances,
        meshed_instances,
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
            disc_edges = discretize_edges(self.shape, deflection, self.id)

        if progress is not None:
            progress.update("e")

        color = (
            [c.web_color for c in self.color]
            if isinstance(self.color, tuple)
            else self.color.web_color
        )

        return dict(id=self.id, shape=self.shape, loc=None), {
            "id": self.id,
            "type": "edges",
            "name": self.name,
            "shape": disc_edges,
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
        instances,
        meshed_instances,
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
        vertices = convert_vertices(self.shape, self.id)

        if progress is not None:
            progress.update("v")

        return dict(id=self.id, shape=self.shape, loc=None), {
            "id": self.id,
            "type": "vertices",
            "name": self.name,
            "shape": vertices,
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
        instances,
        meshed_instances,
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
            "version": PROTOCOL_VERSION,
            "parts": [],
            "loc": None if self.loc is None else loc_to_tq(self.loc),
            "name": self.name,
            "id": self.id,
        }

        map = {"parts": [], "id": self.id}

        for obj in self.objects:
            mapping, mesh = obj.collect_shapes(
                self.id,
                instances,
                meshed_instances,
                combined_loc,
                deviation,
                angular_tolerance,
                edge_accuracy,
                render_edges,
                parallel,
                progress,
                timeit,
            )
            result["parts"].append(mesh)
            map["parts"].append(mapping)
        return map, result

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


class CoordAxis(OCP_Edges):
    def __init__(self, name, origin, z_dir, size=1):
        o, x, y, z = axis_to_vecs(origin, z_dir)
        edge = line(o, o + size * z)
        a2 = line(o + size * z, o + size * 0.9 * z - size * 0.025 * x)
        a3 = line(o + size * z, o + size * 0.9 * z + size * 0.025 * x)
        a4 = line(o + size * z, o + size * 0.9 * z - size * 0.025 * y)
        a5 = line(o + size * z, o + size * 0.9 * z + size * 0.025 * y)
        # c = circle((o + size * 0.9 * z).Coord(), z_dir, 0.025)
        colors = Color("black")
        super().__init__([edge, a2, a3, a4, a5], name, colors, width=3)


class CoordSystem(OCP_Edges):
    def __init__(self, name, origin, x_dir, z_dir, size=1):
        o, x, y, z = loc_to_vecs(origin, x_dir, z_dir)
        x_edge = line(o, o + size * x)
        y_edge = line(o, o + size * y)
        z_edge = line(o, o + size * z)

        colors = (Color("red"), Color("green"), Color("blue"))
        super().__init__([x_edge, y_edge, z_edge], name, colors, width=3)


class ImageFace(OCP_Faces):
    def __init__(
        self,
        image_path,
        scale=1.0,
        origin_pixels=(0, 0),
        location=None,
        name="ImagePlane",
    ):
        self.image_width, self.image_height = imagesize.get(image_path)
        x = origin_pixels[0]
        y = self.image_height - origin_pixels[1]

        if isinstance(scale, (int, float)):
            scale = (scale, scale)

        ws = int(self.image_width * scale[0])
        hs = int(self.image_height * scale[1])
        xs = int(x * scale[0])
        ys = int(y * scale[1])

        plane = rect(ws, hs)
        super().__init__(
            [plane],
            id(plane),
            name=name,
            show_edges=True,
        )

        with open(image_path, "rb") as f:
            self.image = base64.b64encode(f.read()).decode("utf-8")
            self.image_type = image_path.split(".")[-1]
        self.name = name
        self.width = ws
        self.height = hs

        loc = location.wrapped if hasattr(location, "wrapped") else location
        o = tq_to_loc((ws / 2 - xs, hs / 2 - ys, 0), (0, 0, 0, 1))
        self.loc = loc * o if loc is not None else o
