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

from .utils import warn


class Defaults:
    def __init__(self):
        self.reset_defaults()

    def get_defaults(self):
        return self.defaults

    def get_default(self, key, default_value=None):
        return self.defaults.get(key, default_value)

    def set_defaults(self, **kwargs):
        """Set defaults for CAD viewer

        Valid keywords:

        DISPLAY OPTIONS
        - viewer:             Name of the sidecar viewer (default=""):
                              "" uses the default sidecar (if exists) and None forces to use notebook cell
        - anchor:             How to open sidecar: "right", "split-right", "split-bottom", ... (default="right")
        - cad_width:          Width of CAD view part of the view (default=800)
        - tree_width:         Width of navigation tree part of the view (default=250)
        - height:             Height of the CAD view (default=600)
        - theme:              Theme "light" or "dark" (default="light")
        - pinning:            Allow replacing the CAD View by a canvas screenshot (default=True in cells, else False)

        TESSELLATION OPTIONS
        - angular_tolerance:  Shapes: Angular deflection in radians for tessellation (default=0.2)
        - deviation:          Shapes: Deviation from linear deflection value (default=0.1)
        - edge_accuracy:      Edges: Precision of edge discretization (default=None, i.e. mesh quality / 100)
        - default_color:      Default face color (default=(232, 176, 36))
        - default_edgecolor:  Default edge color (default="#707070")
        - optimal_bb:         Use optimal bounding box (default=False)
        - render_normals:     Render vertex normals(default=False)
        - render_edges:       Render edges  (default=True)
        - render_mates:       Render mates (for MAssemblies, default=False)
        - render_joints:      Render build12d joints (default=False)
        - helper_scale:         Scale of rendered mates (for MAssemblies, default=1)

        VIEWER OPTIONS
        - control:            Use trackball controls ('trackball') or orbit controls ('orbit') (default='trackball')
        - up:                 Use z-axis ('Z') or y-axis ('Y') as up direction for the camera (or 'L' for legacy z-axis up mode)
        - axes:               Show axes (default=False)
        - axes0:              Show axes at (0,0,0) (default=False)
        - grid:               Show grid (default=[False, False, False])
        - ticks:              Hint for the number of ticks in both directions (default=10)
        - ortho:              Use orthographic projections (default=True)
        - transparent:        Show objects transparent (default=False)
        - black_edges:        Show edges in black (default=False)
        - position:           Absolute camera position that will be scaled (default=None)
        - quaternion:         Camera rotation as quaternion (x, y, z, w) (default=None)
        - target:             Camera target to look at (default=None)
        - zoom:               Zoom factor of view (default=2.5)
        - reset_camera:       Reset camera position, rotation and zoom to default (default=True)
        - zoom_speed:         Mouse zoom speed (default=1.0)
        - pan_speed:          Mouse pan speed (default=1.0)
        - rotate_speed:       Mouse rotate speed (default=1.0)
        - ambient_intensity   Intensity of ambient light (default=0.75)
        - direct_intensity    Intensity of direct lights (default=0.15)
        - show_parent:        Show the parent for edges, faces and vertices objects (default=False)
        - show_sketch_local:  In build123d show local sketch in addition to relocate sketch (default=True)
        - show_bbox:          Show bounding box (default=False)
        - tools:              Show the viewer tools like the object tree (default=True)
        - glass:              Show the viewer in glass mode, i.e (CAD navigation as transparent overlay (default=False)
        - timeit:             Show rendering times, levels = False, 0,1,2,3,4,5 (default=False)
        - js_debug:           Enable debug output in browser console (default=False)

        NOT SUPPORTED ANY MORE:
        - mac_scrollbar       The default now
        - bb_factor:          Removed
        - display             Use 'viewer="<viewer title>"' (for sidecar display) or 'viewer=None' (for cell display)
        - quality             Use 'deviation'to control smoothness of rendered edges
        """

        for k, v in kwargs.items():
            if self.get_default(k, float("nan")) == float("nan"):
                print(f"Paramater {k} is not a valid argument for show()")
            else:
                self.defaults[k] = v

    def reset_defaults(self):
        self.defaults = {
            #
            # display options
            #
            "viewer": "",
            "anchor": "right",
            "cad_width": 800,
            "tree_width": 250,
            "height": 600,
            "theme": "light",
            "pinning": False,
            #
            # render options
            #
            "angular_tolerance": 0.2,
            "deviation": 0.1,
            "edge_accuracy": None,
            "default_color": (232, 176, 36),
            "default_edgecolor": "#707070",
            "default_opacity": 0.5,
            "optimal_bb": False,
            "render_normals": False,
            "render_edges": True,
            "render_mates": False,
            "render_joints": False,
            "helper_scale": 1,
            #
            # viewer options
            #
            "control": "trackball",
            "up": "Z",
            "axes": False,
            "axes0": False,
            "grid": [False, False, False],
            "ticks": 10,
            "ortho": True,
            "transparent": False,
            "black_edges": False,
            "ambient_intensity": 1.0,
            "direct_intensity": 1.1,
            "metalness": 0.3,
            "roughness": 0.65,
            "reset_camera": True,
            "show_parent": False,
            "show_sketch_local": True,
            "show_bbox": False,
            "position": None,
            "quaternion": None,
            "target": None,
            "zoom": None,
            "zoom_speed": 1.0,
            "pan_speed": 1.0,
            "rotate_speed": 1.0,
            "collapse": 3,
            "tools": True,
            "glass": False,
            "timeit": False,
            "js_debug": False,
        }


def get_defaults():
    return DEFAULTS.get_defaults()


def get_default(key, default_value=None):
    return DEFAULTS.get_default(key, default_value)


def set_defaults(**kwargs):
    if isinstance(kwargs.get("grid"), bool):
        warn(
            "Using bool for grid is deprecated, please use (xy-grid, xz-grid. yz-grid)",
            DeprecationWarning,
            "once",
        )
        kwargs["grid"] = (kwargs["grid"], False, False)

    DEFAULTS.set_defaults(**kwargs)


def apply_defaults(**kwargs):
    result = dict(get_defaults())
    for k, v in kwargs.items():
        if result.get(k, float("nan")) != float(
            "nan"
        ):  # use a value that will never be used ("" and None are used)
            result[k] = v
        else:
            print(f"unknown parameter {k}")

    for k in ["anchor", "theme", "pinning"]:
        # omit create args that cannot be set after viewer is created, unless explicit given
        # -> leading to a warning
        if kwargs.get(k) is None:
            del result[k]

    return result


def reset_defaults():
    DEFAULTS.reset_defaults()


def create_args(config):
    adapt = lambda key: "title" if key == "viewer" else key

    return {
        adapt(k): v
        for k, v in config.items()
        if k
        in [
            "viewer",
            "title",
            "anchor",
            "cad_width",
            "tree_width",
            "height",
            "theme",
            "pinning",
            "tools",
            "glass",
        ]
    }


def add_shape_args(config):
    args = {
        k: v
        for k, v in config.items()
        if k
        in [
            "control",
            "up",
            "axes",
            "axes0",
            "grid",
            "ticks",
            "ortho",
            "transparent",
            "black_edges",
            "position",
            "quaternion",
            "target",
            "zoom",
            "reset_camera",
            "ambient_intensity",
            "direct_intensity",
            "default_edgecolor",
            "zoom_speed",
            "pan_speed",
            "rotate_speed",
            "clipIntersection",
            "clipPlaneHelpers",
            "clipNormal",
            "collapse",
            "tools",
            "glass",
            "cad_width",
            "tree_width",
            "height",
            "timeit",
            "js_debug",
        ]
    }

    return args


def tessellation_args(config):
    return {
        k: v
        for k, v in config.items()
        if k
        in [
            "angular_tolerance",
            "deviation",
            "edge_accuracy",
            "default_color",
            "default_edgecolor",
            "optimal_bb",
            "render_normals",
            "render_edges",
            "render_mates",
            "render_joints",
            "helper_scale",
            "quality",
        ]
    }


def show_args(config):
    args = create_args(config)
    args.update(add_shape_args(config))

    if config.get("normal_len") is not None:
        args["normal_len"] = config["normal_len"]
    args["title"] = config.get("viewer")
    return args


def preset(key, value):
    return get_default(key) if value is None else value


DEFAULTS = Defaults()
