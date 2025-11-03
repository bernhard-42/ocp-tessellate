
## 3.1.0

**Features**

- Add functionality to trim infinite edges and faces
- Treat joints as helpers on the same level in assemblies to not change hierarchy (which could break animation)
- Add nested bounding box method for objects
- Ensure compounds with wires and edges are not seen as mixed compounds

**Fixes**

- Add compounds to get_type and get_kind parameters
- Refactor `helper_scale`, `render_*`, and `show_*` parameters as instance methods. They are now provided to the OcpConverter init.
- Improve infinite objects warnings
- Skip empty meshes
- Set the cache ID from the correct object
- Set debug parameter properly throughout the codebase
- Adapt to changed color definitions of build123d
- Switch to ruff for linting and formatting

## 3.0.17

- Make get_plane more robust
- Added additional OCP functions to ocp_utils
- Adapt to API changes of build123d

## 3.0.16

- Fix the regression to have continue indented to much for the non showable case

## 3.0.15

- Move the "unknown type " warning behind "debug=True" parameter
- Replace hard coded "DEBUG" with parameter "debug"

## 3.0.14

- Fix helix regression

## 3.0.13

- Adapt to CadQuery's change in color from RGB to RGBs
- Support compound of compound of edges

## 3.0.11, 3.0.12

- Support ShapeLists of Compounds
- Support TopoDS_CompSolid

## 3.0.10

- Support both hashing algorithms of OOCT
- Minor adaptations to build123d fixes/changes
- Fix showing assemblies in lists
- Fix detection of empty objects
- Fix exporting simple STEP imports
- Renamed tests and pytests folders


## v3.0.9

- Add support for OCP 7.8.1


## v3.0.8

- Fix regression for handling cadquery wires (wire.edges() returns one edge or one compound)
- Ensure get_face_type and get_edge_type always return int (ocp_utils.py)
- Enable switch from Extent to Size (being prepared for OCCT 7.8)
- Add get_surface and get_curve to ocp_utils.py


## v3.0.7

- none / deployment issues


## v3.0.6

- Migrate to pyproject.toml
- Support latest cadquery Sketch changes


## v3.0.5

- Remove numpy-quaternion dependency to support numpy 1 and 2