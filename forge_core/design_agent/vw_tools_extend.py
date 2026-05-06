import json
import math
import os
from pathlib import Path
import vs
from functools import partial
try:
    from transformers import Tool
except Exception:
    class Tool:  # type: ignore
        name = ""
        description = ""
        inputs = []
        outputs = []

from typing import List, Optional, Union
from ast import literal_eval


STYLE_MANIFEST_ENV = "OPENBIMFORGE_STYLE_MANIFEST_PATH"
LEGACY_STYLE_MANIFEST_ENV = "TEXT2BIM_STYLE_MANIFEST_PATH"
DEFAULT_STYLE_MANIFEST = (
    Path(
        os.environ.get(
            "OPENBIMFORGE_RUNTIME_ROOT",
            str(
                Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
                / "forge_runtime"
            ),
        )
    )
    / "capabilities"
    / "vectorworks_styles.json"
)
STYLE_TOLERANCE_ENV = "OPENBIMFORGE_TOLERATE_STYLE_ERRORS"
LEGACY_STYLE_TOLERANCE_ENV = "TEXT2BIM_TOLERATE_STYLE_ERRORS"


def _style_tolerance_enabled() -> bool:
    value = os.environ.get(
        STYLE_TOLERANCE_ENV,
        os.environ.get(LEGACY_STYLE_TOLERANCE_ENV, "true"),
    )
    return value.lower() != "false"


def _load_style_manifest() -> dict:
    manifest_path = Path(
        os.environ.get(
            STYLE_MANIFEST_ENV,
            os.environ.get(LEGACY_STYLE_MANIFEST_ENV, str(DEFAULT_STYLE_MANIFEST)),
        )
    )
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _manifest_style_list(category: str) -> List[str]:
    manifest = _load_style_manifest()
    values = manifest.get(category, [])
    return [str(value) for value in values if str(value).strip()]


def _style_exists(style_name: str) -> bool:
    if not style_name:
        return False
    try:
        index = vs.Name2Index(style_name)
        return bool(index)
    except Exception:
        return False


def _pick_style_name(
    requested_style: str,
    category: str,
    fallback_candidates: List[str],
) -> Optional[str]:
    manifest_candidates = _manifest_style_list(category)
    candidate_pool = manifest_candidates or fallback_candidates

    if requested_style and _style_exists(requested_style):
        return requested_style

    for candidate in candidate_pool:
        if _style_exists(candidate):
            return candidate

    return None


def _warn_style_skip(category: str, requested_style: str) -> None:
    print(
        f"[openBIMForge][Style Fallback] Skip applying {category} style '{requested_style}' because no matching style exists in this Vectorworks environment."
    )


def _is_nil_handle(handle) -> bool:
    if handle is None:
        return True
    try:
        return handle == vs.Handle(0)
    except Exception:
        return False


def _symbol_exists(symbol_name: str) -> bool:
    if not symbol_name:
        return False
    try:
        symbol_h = vs.GetObject(symbol_name)
        if _is_nil_handle(symbol_h):
            return False
        try:
            # Vectorworks symbol definitions are type 16. A named style can be
            # retrievable by name but still fail in AddSymToWall, so do not
            # treat arbitrary named resources as insertable symbols.
            return vs.GetTypeN(symbol_h) == 16
        except Exception:
            return False
    except Exception:
        return False


def _pick_existing_symbol(
    requested_symbol: Optional[str],
    default_symbol: str,
    allowed_symbols: List[str],
    category: str,
) -> Optional[str]:
    candidates = []
    if requested_symbol:
        candidates.append(requested_symbol)
    candidates.extend(allowed_symbols)
    if default_symbol:
        candidates.append(default_symbol)

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if _symbol_exists(candidate):
            return candidate

    print(
        f"[openBIMForge][Symbol Fallback] Skip adding {category}; no matching symbol exists. Requested='{requested_symbol}'."
    )
    return None


def _coerce_vertex(vertex):
    if isinstance(vertex, str):
        vertex = literal_eval(vertex)
    if not isinstance(vertex, (list, tuple)) or len(vertex) < 2:
        raise ValueError(f"Invalid polygon vertex: {vertex}")
    return (float(vertex[0]), float(vertex[1]))


def _polygon_signed_area(vertices):
    area = 0.0
    for index, vertex in enumerate(vertices):
        next_vertex = vertices[(index + 1) % len(vertices)]
        area += vertex[0] * next_vertex[1] - next_vertex[0] * vertex[1]
    return area / 2.0


def _normalize_polygon_vertices(vertices):
    coerced = [_coerce_vertex(vertex) for vertex in vertices]

    deduped = []
    seen = set()
    for vertex in coerced:
        key = (round(vertex[0], 6), round(vertex[1], 6))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(vertex)

    if len(deduped) < 3:
        raise ValueError("Please provide at least three unique polygon vertices.")

    center_x = sum(vertex[0] for vertex in deduped) / len(deduped)
    center_y = sum(vertex[1] for vertex in deduped) / len(deduped)
    ordered = sorted(
        deduped,
        key=lambda vertex: math.atan2(vertex[1] - center_y, vertex[0] - center_x),
    )

    if _polygon_signed_area(ordered) < 0:
        ordered.reverse()

    return ordered


def _poly_vertices_from_handle(poly_h):
    if _is_nil_handle(poly_h):
        return []
    try:
        count = int(vs.GetVertNum(poly_h))
    except Exception:
        return []

    vertices = []
    for index in range(1, count + 1):
        try:
            vertex = vs.GetPolylineVertex(poly_h, index)[0]
            vertices.append(_coerce_vertex(vertex))
        except Exception:
            continue
    return vertices


def _is_axis_aligned_rectangle(vertices):
    if len(vertices) != 4:
        return False
    xs = {round(vertex[0], 6) for vertex in vertices}
    ys = {round(vertex[1], 6) for vertex in vertices}
    return len(xs) == 2 and len(ys) == 2


def _create_extruded_plate_from_vertices(vertices, thickness=250):
    safe_vertices = _normalize_polygon_vertices(vertices)
    vs.BeginXtrd(0, thickness)
    if _is_axis_aligned_rectangle(safe_vertices):
        min_x = min(vertex[0] for vertex in safe_vertices)
        max_x = max(vertex[0] for vertex in safe_vertices)
        min_y = min(vertex[1] for vertex in safe_vertices)
        max_y = max(vertex[1] for vertex in safe_vertices)
        vs.Rect((min_x, max_y), (max_x, min_y))
    else:
        vs.ClosePoly()
        vs.Poly(*safe_vertices)
    vs.EndXtrd()
    plate_h = vs.LNewObj()
    if _is_nil_handle(plate_h):
        raise ValueError("Fallback extruded slab plate could not be created.")
    return plate_h


def _create_slab_fallback(poly_h, layer_uuid):
    vertices = _poly_vertices_from_handle(poly_h)
    if not vertices:
        raise ValueError("Cannot create fallback slab because polygon vertices are unavailable.")
    layer_name = vs.GetLName(vs.GetObjectByUuid(layer_uuid))
    vs.Layer(layer_name)
    plate_h = _create_extruded_plate_from_vertices(vertices)
    uuid = vs.GetObjectUuid(plate_h)
    vs.SetClass(plate_h, "Slabs")
    ok = vs.IFC_SetProperty(plate_h, 'IfcSlab', 'Description', str(uuid))
    ok = vs.IFC_SetProperty(plate_h, 'IfcSlab', 'Name', "openBIMForge fallback slab")
    print(
        "[openBIMForge][Geometry Fallback] Native Vectorworks slab failed; created an IFC-tagged extruded slab plate instead."
    )
    return uuid

def set_uuid_of_nested_pios_in_duplicated_wall(wall_h):
    def find_set_related_pios(pio_h, wall_h):
        obj_uuid = vs.GetObjectUuid(pio_h)
        h_wall_found = vs.GetParent(pio_h)
        if h_wall_found == wall_h:
            if vs.GetClass(pio_h) == "Windows":
                ok = vs.IFC_SetProperty(pio_h, 'IfcWindow', 'Description', str(obj_uuid))
            elif vs.GetClass(pio_h) == "Doors":
                ok = vs.IFC_SetProperty(pio_h, 'IfcDoor', 'Description', str(obj_uuid))
    
    partial_find_set_related_pios = partial(find_set_related_pios, wall_h=wall_h)
    vs.ForEachObject(partial_find_set_related_pios, "T=PLUGINOBJECT")

def set_ifc_property_for_duplication(hobj):
    obj_uuid = vs.GetObjectUuid(hobj)
    # add uuid to ifc
    if vs.GetClass(hobj) == "Wall":
        ok = vs.IFC_SetProperty(hobj, 'IfcWallStandardCase', 'Description', str(obj_uuid))
        # set uuid for nested PIOs
        set_uuid_of_nested_pios_in_duplicated_wall(hobj)
    elif vs.GetClass(hobj) == "Windows":
        ok = vs.IFC_SetProperty(hobj, 'IfcWindow', 'Description', str(obj_uuid))
    elif vs.GetClass(hobj) == "Doors":
        ok = vs.IFC_SetProperty(hobj, 'IfcDoor', 'Description', str(obj_uuid))
    elif vs.GetClass(hobj) == "Slabs":
        ok = vs.IFC_SetProperty(hobj, 'IfcSlab', 'Description', str(obj_uuid))
    elif vs.GetClass(hobj) == "Roofs":
        ok = vs.IFC_SetProperty(hobj, 'IfcRoof', 'Description', str(obj_uuid))
    elif vs.GetClass(hobj) == "Spaces":
        ok = vs.IFC_SetProperty(hobj, 'IfcSpace', 'Description', str(obj_uuid))


class CreateStoryLayer(Tool):
    name = "create_story_layer"
    description = """
    This tool is use to create a new story layer in Vectorworks. The new layer is created at the given elevation.
    Once a new story layer is created, it becomes the active layer in Vectorworks. All new building elements will be created on the current active story.
    Input:
        - layer_name: str, the unique name of the new story.
        - elevation: float, the elevation of the new story relative to the ground.
        - floor_index: int, the index of the new floor. Should start from 1.
    Return:
        - str, the layer_uuid of the new story layer.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, layer_name: str, elevation: float, floor_index: int):
        try:
            if vs.GetLayerByName(layer_name) == 0:
                layer_h = vs.CreateLayer(layer_name, 1)
                # this is needed otherwise no valid story_h
                vs.SetLayerLevelType(layer_h, 'Slab')
                ok = vs.CreateStory(f"{layer_name}-{floor_index}", str(floor_index))
                story_h = vs.GetObject(f"{layer_name}-{floor_index}")
                vs.SetLayerElevation(layer_h, elevation, 0)
                ok = vs.AssociateLayerWithStory(layer_h, story_h)
                vs.SetStoryElevation(story_h, elevation)
                layer_uuid = vs.GetObjectUuid(layer_h)
            else:
                layer_h = vs.GetLayerByName(layer_name)
                layer_uuid = vs.GetObjectUuid(layer_h)
            return layer_uuid
        except Exception as e:
            raise ValueError(f"Error occured during creating story layer: {e}")

class SetStoryLayerActive(Tool):
    name = "set_active_story_layer"
    description = """
    This tool is use to set the story layer with given name to active in Vectorworks. The active story layer is the layer that new elements are created on.
    Input:
        - layer_name: str, the name of the layer to set as active.
    Return:
        - str, the layer_uuid of the active layer.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, layer_name: str):
        try:
            vs.Layer(layer_name)
            layer_h = vs.ActLayer()
            uuid = vs.GetObjectUuid(layer_h)
            return uuid
        except Exception as e:
            raise ValueError(f"Error occured during setting active layer: {e}")

class CreateSpace(Tool):
    name = "create_functional_area"
    description = """
    This tool is use to create a conceptual functional area on a specified layer. The area is created from a list vertex of the that defines the room boundary.
    Usually, functional areas are created first to define the interior layout of the building, and then the rooms are separated by placing walls at the boundaries. 
    Input:
        - vertices: list of tuples, each tuple represent the 2D coordinate of a vertex that defines the boundary of the room.
        - name: str, the name of the room/functional area.
        - layer_uuid: str, the uuid of the story layer where the space will be created.
    Return:
        - str, the uuid of the created room/functional area.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, vertices: List[str], name: str, layer_uuid: str):
        try:
            # set active layer
            layer_name = vs.GetLName(vs.GetObjectByUuid(layer_uuid))
            vs.Layer(layer_name)

            vs.ClosePoly()
            if isinstance(vertices, str):
                vertices = literal_eval(vertices)
            if isinstance(vertices, list):
                safe_vertices = _normalize_polygon_vertices(vertices)
                vs.Poly(*safe_vertices)
                poly_h = vs.LNewObj()

                # lets duplicate the polygon to avoid modifying the original one
                # poly_d = vs.HDuplicate(poly_h,0,0)
                space_h = vs.Space_CreateSpace(poly_h, 0)
                uuid = vs.GetObjectUuid(space_h)
                vs.SetClass(space_h, "Spaces")
                if vs.GetClass(space_h) == "Spaces":
                    ok = vs.IFC_SetProperty(space_h, 'IfcSpace', 'Description', str(uuid))
                    ok = vs.IFC_SetProperty(space_h, 'IfcSpace', 'Name', str(name))
                return uuid
            else:
                raise Exception("Please provide a list of vertices!")
        except Exception as e:
            raise ValueError(f"Error occured during creating room: {e}")

class CreateWallTool(Tool):
    name = "create_wall"
    description = """
    This tool is use to create a wall on a specified layer. By default, the wall is created with a bottom_elevation of 0 and a top_elevation of 3000 relative to this layer.
    Input:
        - st_pt: tuple, the 2D coordinate of the starting point of the wall.
        - ed_pt: tuple, the 2D coordinate of the end point of the wall.
        - layer_uuid: str, the uuid of the story layer where the wall will be created.
    Return:
        - str, the uuid of the new created wall.
"""
    
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, st_pt: str, ed_pt: str, layer_uuid: str):
        try:
            if isinstance(st_pt, str):
                st_pt = literal_eval(st_pt)
            if isinstance(ed_pt, str):
                ed_pt = literal_eval(ed_pt)
            else:
                st_pt = st_pt
                ed_pt = ed_pt
            # set active layer
            layer_name = vs.GetLName(vs.GetObjectByUuid(layer_uuid))
            vs.Layer(layer_name)

            vs.Wall(st_pt, ed_pt)
            hwall = vs.LNewObj()
            wall_uuid = vs.GetObjectUuid(hwall)
            vs.SetClass(hwall, "Wall")
            # add uuid to ifc
            ok = vs.IFC_SetProperty(hwall, 'IfcWallStandardCase', 'Description', str(wall_uuid))
            return wall_uuid
        except Exception as e:
            raise ValueError(f"Error occured during creating wall: {e}")

class SetWallThickness(Tool):
    name = "set_wall_thickness"
    description = """
    This tool is used to set the thickness of a wall in Vectorworks.
    Input:
        - uuid: str, the uuid of the wall object.
        - thickness: float, the new thickness of the wall.
    Return:
        - str, the uuid of the wall object that has been modified.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, uuid: str, thickness: str):
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
            if isinstance(uuid, list):
                h  = vs.GetObjectByUuid(uuid[0])
            vs.SetWallThickness(h, thickness)
            return uuid
        except Exception as e:
            raise ValueError(f"Error occured during setting wall thickness: {e}")

class SetWallHeight(Tool):
    name = "set_wall_elevation"
    description = """
    This tool is used to set the top/bottom elevation of a wall. Subtracting these two is the height of the wall itself.
    Input:
        - uuid: str, the uuid of the wall object.
        - top_elevation: float, the vertical distance from the top of the wall to the story layer where the wall was originally created.
        - bottom_elevation: float, the vertical distance from the bottom of the wall to the story layer where the wall was originally created.
    Return:
        - str, the uuid of the wall object that has been modified.
"""

    inputs = ["text", "text", "text"]
    outputs = ["text"]

    def __call__(self, uuid: str, top_elevation=None, bottom_elevation=None):

        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
            # this get is based on the ground layer
            overallHeightTop, overallHeightBottom = vs.GetWallOverallHeights(h)

            # here we try to set the wall height based on the current layer
            layer_h = vs.GetParent(h)
            base_eleva, thickness = vs.GetLayerElevation(layer_h)
            overallHeightTop = overallHeightTop - base_eleva - thickness # current top elevation to current layer
            overallHeightBottom = overallHeightBottom - base_eleva - thickness # current bottom elevation to current layer
            if top_elevation:
                overallHeightTop = top_elevation # input are relative to the current layer
            if bottom_elevation:
                overallHeightBottom = bottom_elevation # input are relative to the current layer
            # vs.AlrtDialog("New top elevation: " + str(overallHeightTop) + " bottom elevation: " + str(overallHeightBottom))
            # this set is based on ground layer, maybe because if we set ture in CreateDuplicateObjN, the wall offset will always refer to the ground layer 
            # but actually this set is based on the current layer
            vs.SetWallOverallHeights(h,0,0,"",overallHeightBottom,0,0,"",overallHeightTop)
            vs.ResetObject(h)
            return uuid
        except Exception as e:
            raise ValueError(f"Error occured during setting wall attributes: {e}")

class GetWallElevation(Tool):
    name = "get_wall_elevation"
    description = """
    This tool is used to get the top and bottom elevation of a wall in Vectorworks. Subtracting these two is the height of the wall itself.
    Input:
        - uuid: str, the uuid of the wall object.
    Return:
        - top_elevation: float, the vertical distance from the top of the wall to the story layer where the wall was originally created.
        - bottom_elevation: float, the vertical distance from the bottom of the wall to the story layer where the wall was originally created.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, uuid: str):
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
            if isinstance(uuid, list):
                h  = vs.GetObjectByUuid(uuid[0])
            # this get is based on the ground layer, so we need to convert it to the current layer
            top_elevation, bottom_elevation, _, _ = vs.GetWallHeight(h)

            layer_h = vs.GetParent(h)
            base_eleva, thickness = vs.GetLayerElevation(layer_h)
            top_elevation = top_elevation - base_eleva - thickness
            bottom_elevation = bottom_elevation - base_eleva - thickness
            
            return top_elevation, bottom_elevation
        except Exception as e:
            raise ValueError(f"Error occured during getting wall height: {e}")

class GetWallThickness(Tool):
    name = "get_wall_thickness"
    description = """
    This tool is used to get the thickness of a wall in Vectorworks.
    Input:
        - uuid: str, the uuid of the wall object.
    Return:
        - thickness: float, the thickness of the wall.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, uuid: str):
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
            if isinstance(uuid, list):
                h  = vs.GetObjectByUuid(uuid[0])
            bool, thickness = vs.GetWallThickness(h)
            if bool:
                return thickness
            else:
                raise Exception("the wall has no thickness!")
        except Exception as e:
            raise ValueError(f"Error occured during getting wall thickness: {e}")
        
class SetWallStyle(Tool):
    name = "set_wall_style"
    description = """
    This tool is used to set the style of a wall in Vectorworks.
    Input:
        - uuid: str, the uuid of the wall object.
        - style_name: str, the name of the style. Following wall style names are avaliable: ["Exterior Concrete Wall", "Exterior Wood Wall", "Exterior Brick Wall", "Interior Concrete Wall", "Interior Wood Wall", "Interior Brick Wall]
    Return:
        - str, the uuid of the wall object that has been modified.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, uuid: str, style_name: str):
        fallback_styles = [
            "Exterior Concrete Wall",
            "Interior Concrete Wall",
            "Interior Wood Wall",
            "Exterior Wood Wall",
            "Exterior Brick Wall",
            "Interior Brick Wall",
        ]
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
            if isinstance(uuid, list):
                h  = vs.GetObjectByUuid(uuid[0])
            resolved_style = _pick_style_name(
                style_name,
                "wall_styles",
                fallback_styles,
            )
            if resolved_style:
                # somehow no need to set the index of the style for the wall??
                vs.SetWallStyle(h, resolved_style,0,0)
            elif _style_tolerance_enabled():
                _warn_style_skip("wall", style_name)
            else:
                raise Exception(f"Style name {style_name} not found!")
            return uuid
        except Exception as e:
            raise ValueError(f"Error occured during setting wall style: {e}")

class AddWindowToWall(Tool):
    name = "add_window_to_wall"
    description = """
    This tool is used to add a window to a wall in Vectorworks. Once a window is added to a wall, it is part of the wall and will be moved/duplicated/rotated with the wall. Always remember to assign the returned window uuid when using this function.
    Input:
        - wall_uuid: str, the uuid of the wall object to which the window will be added.
        - window_elevation: float, the elevation of the window from the bottom of the wall.
        - window_offset: float, the offset of the window from the starting point of the wall.
        - window_name: str, the name of the window object to be added.
    Return:
        - str, the uuid of the window object that has been added to the wall.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, wall_uuid: str, window_elevation: float, window_offset: float, window_name: str = None):
        try:
            default_window_name = ""
            allowed_window_names = _manifest_style_list("window_symbols")
            if isinstance(wall_uuid, str):
                hwall = vs.GetObjectByUuid(wall_uuid)
            if isinstance(wall_uuid, list):
                hwall = vs.GetObjectByUuid(wall_uuid[0])
            if _is_nil_handle(hwall):
                print("[openBIMForge][Window Fallback] Skip window because wall handle is NIL.")
                return ""
            resolved_window_name = _pick_existing_symbol(
                window_name,
                default_window_name,
                allowed_window_names,
                "window",
            )
            if not resolved_window_name:
                return ""
            # get wall bottom elevation, this is based on the ground layer, but somehow it works for windows
            _, wall_bottom_elevation, _, _  = vs.GetWallHeight(hwall)
            try:
                vs.AddSymToWall(
                    hwall,
                    window_offset,
                    wall_bottom_elevation,
                    0,
                    0,
                    resolved_window_name,
                )
            except Exception as symbol_error:
                print(
                    f"[openBIMForge][Window Fallback] Skip window symbol '{resolved_window_name}' because AddSymToWall failed: {symbol_error}"
                )
                return ""
    
            windows_h = vs.LNewObj()
            if _is_nil_handle(windows_h):
                print(
                    f"[openBIMForge][Window Fallback] AddSymToWall did not create a window for symbol '{resolved_window_name}'."
                )
                return ""
            ok = vs.SetObjectWallHeight(windows_h, hwall, wall_bottom_elevation)
            window_uuid = vs.GetObjectUuid(windows_h)
            # TODO. set class does not work for windows?? we have to set it in symbol settings in software
            vs.SetClass(windows_h, "Windows")
            # add uuid to ifc
            ok = vs.IFC_SetProperty(windows_h, 'IfcWindow', 'Description', str(window_uuid))
            # add window name to ifc
            ok = vs.IFC_SetProperty(windows_h, 'IfcWindow', 'Name', str(resolved_window_name))

            return window_uuid
        except Exception as e:
            raise ValueError(f"Error occured during adding window to wall: {e}") 

class AddDoorToWall(Tool):
    name = "add_door_to_wall"
    description = """
    This tool is used to add a door to a wall in Vectorworks. Once a door is added to a wall, it is part of the wall and will be moved/duplicated/rotated with the wall. Always remember to assign the returned door uuid when using this function.
    Input:
        - wall_uuid: str, the uuid of the wall object to which the door will be added.
        - door_elevation: float, the elevation of the door from the bottom of the wall.
        - door_offset: float, the offset of the door from the starting point of the wall.
        - door_name: str, the name of the door object to be added.
    Return:
        - str, the uuid of the door object that has been added to the wall.
    """
    inputs = ["text", "text"]
    outputs = ["text"]
    
    def __call__(self, wall_uuid: str, door_elevation: float, door_offset: float, door_name: str = None):
        try:
            default_door_name = ""
            allowed_door_names = _manifest_style_list("door_symbols")
            if isinstance(wall_uuid, str):
                hwall = vs.GetObjectByUuid(wall_uuid)
            if isinstance(wall_uuid, list):
                hwall = vs.GetObjectByUuid(wall_uuid[0])
            if _is_nil_handle(hwall):
                print("[openBIMForge][Door Fallback] Skip door because wall handle is NIL.")
                return ""
            resolved_door_name = _pick_existing_symbol(
                door_name,
                default_door_name,
                allowed_door_names,
                "door",
            )
            if not resolved_door_name:
                return ""
            # get wall bottom elevation
            _, wall_bottom_elevation, _, _  = vs.GetWallHeight(hwall)
            try:
                vs.AddSymToWall(
                    hwall,
                    door_offset,
                    wall_bottom_elevation,
                    0,
                    0,
                    resolved_door_name,
                )
            except Exception as symbol_error:
                print(
                    f"[openBIMForge][Door Fallback] Skip door symbol '{resolved_door_name}' because AddSymToWall failed: {symbol_error}"
                )
                return ""

            doors_h = vs.LNewObj()
            if _is_nil_handle(doors_h):
                print(
                    f"[openBIMForge][Door Fallback] AddSymToWall did not create a door for symbol '{resolved_door_name}'."
                )
                return ""
            ok = vs.SetObjectWallHeight(doors_h, hwall, wall_bottom_elevation)
            door_uuid = vs.GetObjectUuid(doors_h)
            # TODO: set class does not work for doors?? we have to set it in symbol settings in software
            vs.SetClass(doors_h, "Doors")
            # add uuid to ifc
            ok = vs.IFC_SetProperty(doors_h, 'IfcDoor', 'Description', str(door_uuid))
            # add door name to ifc
            ok = vs.IFC_SetProperty(doors_h, 'IfcDoor', 'Name', str(resolved_door_name))

            return door_uuid
        except Exception as e:
            raise ValueError(f"Error occured during adding door to wall: {e}")

class Move(Tool):
    name = "move_obj"
    description = """
    This tool is use to move an element in Vetorworks. It can only move the given element within the layer where it is placed but not duplicate it.
    Input:
        - uuid: str, the unique uuid of the element to move.
        - xDistance: float, moving distance in x direction.
        - yDistance: float, moving distance in y direction.
        - zDistance: float, moving distance in z direction.
    Return:
        - None
"""
    
    inputs = ["text", "text", "text", "text"]
    outputs = ["text"]

    def __call__(self, uuid: List[str], xDistance, yDistance, zDistance):
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
                if h != vs.Handle(0):
                    # think about the special case of moving roof, we will get the roof slab uuid(equal to the roof uuid) but we have to move the whole roof
                    if vs.GetClass(h) == "Roof_Slabs" or vs.GetClass(h) == "Roofs":
                        # get the roof slab
                        ok, roof_slab_uuid, iType = vs.IFC_GetEntityProp(h, 'Tag')
                        roof_slab_h = vs.GetObjectByUuid(roof_slab_uuid)
                        # move together
                        vs.Move3DObj(h, xDistance, yDistance, zDistance)
                        vs.Move3DObj(roof_slab_h, xDistance, yDistance, zDistance)
                    else:
                        vs.Move3DObj(h, xDistance, yDistance, zDistance)
                else:
                    raise Exception("Can't move the element: either it does not exist or unvalid uuid!")
                # vs.AlrtDialog(f"element {uuid} moved!")
            elif isinstance(uuid, list):
                for id in uuid:
                    h  = vs.GetObjectByUuid(id)
                    if h != vs.Handle(0):
                    # think about the special case of moving roof, we will get the roof slab uuid(equal to the roof uuid) but we have to move the whole roof
                        if vs.GetClass(h) == "Roof_Slabs" or vs.GetClass(h) == "Roofs":
                            # get the roof slab
                            ok, roof_slab_uuid, iType = vs.IFC_GetEntityProp(h, 'Tag')
                            roof_slab_h = vs.GetObjectByUuid(roof_slab_uuid)
                            # move together
                            vs.Move3DObj(h, xDistance, yDistance, zDistance)
                            vs.Move3DObj(roof_slab_h, xDistance, yDistance, zDistance)
                        else:
                            vs.Move3DObj(h, xDistance, yDistance, zDistance)
                    else:
                        raise Exception("Can't move the element: either it does not exist or unvalid uuid!")
            else:
                raise Exception("uuid type not supported!")
        except Exception as e:
            raise ValueError(f"Error occured during moving element: {e}")

class DeleteTool(Tool):
    name = "delete_element"
    description = """
    This tool is use to delete an elemnt or a list of elements in Vectorworks. Story layers cannot be deleted.
    Input:
        - uuid: str or a list of string, the unique uuids of the elements to delete.
    Return:
        - None
"""

    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, uuid: Union[str, List[str]]):
        try:
            if isinstance(uuid, str):
                h = vs.GetObjectByUuid(uuid)
                if vs.GetClass(h) == "Roofs" or vs.GetClass(h) == "Roof_Slabs":
                    # get the roof slab
                    ok, roof_slab_uuid, iType = vs.IFC_GetEntityProp(h, 'Tag')
                    roof_slab_h = vs.GetObjectByUuid(roof_slab_uuid)
                    vs.DelObject(roof_slab_h)
                    vs.DelObject(h)
                else: 
                    vs.DelObject(h)
                vs.AlrtDialog(f"element {uuid} deleted!")
            elif isinstance(uuid, list):
                for id in uuid:
                    h = vs.GetObjectByUuid(id)
                    if vs.GetClass(h) == "Roofs" or vs.GetClass(h) == "Roof_Slabs":
                        # get the roof slab
                        ok, roof_slab_uuid, iType = vs.IFC_GetEntityProp(h, 'Tag')
                        roof_slab_h = vs.GetObjectByUuid(roof_slab_uuid)
                        vs.DelObject(roof_slab_h)
                        vs.DelObject(h)
                    else: 
                        vs.DelObject(h)
                vs.AlrtDialog(f"elements deleted!")
            else:
                vs.AlrtDialog("handle type not supported")
        except Exception as e:
            raise ValueError(f"Error occured during deleting element: {e}")

class FindSelect(Tool):
    name = "find_selected_element"
    description= """
    This tool is use to find the mouse selected element in current active story layer in Vectorworks. If there are no selected elements found, it will return an empty list.
    Input:
        - None
    Return:
        - list of str, the uuids of the selected elements.
"""
    inputs = []
    outputs = ["text"]

    def __call__(self):
        try:
            selected_obj_list =[]
            current_layer = vs.ActLayer()
            if current_layer != None:
                current_obj = vs.FSObject(current_layer)
                while current_obj != None:
                    uuid = vs.GetObjectUuid(current_obj)
                    selected_obj_list.append(uuid)
                    current_obj = vs.NextSObj(current_obj)
            else:
                vs.AlrtDialog("No layer exsists!")
            
            vs.AlrtDialog(f"selected objs' uuids: {str(selected_obj_list)}")
            return selected_obj_list
        except Exception as e:
            raise ValueError(f"Error occured during finding selected element: {e}")


class CreatePolygon(Tool):
    name = "create_polygon"
    description = """
    This tool is use to create a polygon on a specified story layer using its vertices in Vectorworks.
    Input:
        - vertices: list of tuples, each tuple represent the 2D coordinate of a vertex of the polygon.
        - layer_uuid: str, the uuid of the story layer where the polygon will be created.
    Return:
        - str, the uuid of the created polygon.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, vertices: List[str], layer_uuid: str):
        try:
            # set active layer
            layer_name = vs.GetLName(vs.GetObjectByUuid(layer_uuid))
            vs.Layer(layer_name)

            vs.ClosePoly()
            if isinstance(vertices, str):
                vertices = literal_eval(vertices)
            if isinstance(vertices, list):
                safe_vertices = _normalize_polygon_vertices(vertices)
                vs.Poly(*safe_vertices)
                hpoly = vs.LNewObj()
                uuid = vs.GetObjectUuid(hpoly)
                return uuid
            else:
                raise Exception("Please provide a list of vertices!")
        except Exception as e:
            raise ValueError(f"Error occured during creating polygon: {e}")

class GetPolygonVertex(Tool):
    name = "get_polygon_vertex"
    description = """
    This tool is use to get a desired vertex at the given index in the polygon's vertex array in Vectorworks.
    Input:
        - uuid: str, the uuid of the polygon object.
        - at: int, the index of the desired vertex.
    Return:
        - tuple, the 2D coordinate of the desired vertex of the polygon.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, uuid: str, at: int):
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
                # In Verctorworks, the index of the first vertex start with 1
                valid_at = at+1
                temp = vs.GetPolylineVertex(h, valid_at)
                return temp[0]
        except Exception as e:
            raise ValueError(f"Error occured during getting polygon vertex: {e}")

class GetVertNum(Tool):
    name = "get_vertex_count"
    description = """
    This tool is use to get the number of vertices in a polygon in Vectorworks.
    Input:
        - uuid: str, the uuid of the polygon object.
    Return:
        - int, the number of vertices in the input polygon.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, uuid: str):
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
                num = vs.GetVertNum(h)
                return num
        except Exception as e:
            raise ValueError(f"Error occured during getting vertex count: {e}")

class CreateSlab(Tool):
    name = "create_slab"
    description = """
    This tool is use to create a slab from a polygon profile on a specified layer in Vectorworks.
    Input:
        - profile_id: str, the uuid of a ploygon object that determines the profile of the slab.
        - layer_uuid: str, the uuid of the story layer where the slab will be created.
    Return:
        - str, the uuid of the created slab.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, profile_id: List[str], layer_uuid: str):
        try:
            if isinstance(profile_id, str):
                # set active layer
                layer_name = vs.GetLName(vs.GetObjectByUuid(layer_uuid))
                vs.Layer(layer_name)

                poly_h = vs.GetObjectByUuid(profile_id)
                if _is_nil_handle(poly_h):
                    raise ValueError("Cannot create slab because polygon profile handle is NIL.")
                # lets duplicate the polygon to avoid modifying the original one
                poly_d = vs.HDuplicate(poly_h,0,0)
                if _is_nil_handle(poly_d):
                    raise ValueError("Cannot create slab because duplicated polygon profile handle is NIL.")
                slab_h = vs.CreateSlab(poly_d)
            if isinstance(profile_id, list):
                # set active layer
                layer_name = vs.GetLName(vs.GetObjectByUuid(layer_uuid))
                vs.Layer(layer_name)

                poly_h = vs.GetObjectByUuid(profile_id[0])
                if _is_nil_handle(poly_h):
                    raise ValueError("Cannot create slab because polygon profile handle is NIL.")
                # lets duplicate the polygon to avoid modifying the original one
                poly_d = vs.HDuplicate(poly_h,0,0)
                if _is_nil_handle(poly_d):
                    raise ValueError("Cannot create slab because duplicated polygon profile handle is NIL.")
                slab_h = vs.CreateSlab(poly_d)
            if _is_nil_handle(slab_h):
                return _create_slab_fallback(poly_h, layer_uuid)
        
            uuid = vs.GetObjectUuid(slab_h)
            vs.SetClass(slab_h, "Slabs")
            # add uuid to ifc
            ok = vs.IFC_SetProperty(slab_h, 'IfcSlab', 'Description', str(uuid))
            return uuid
        except Exception as e:
            raise ValueError(f"Error occured during creating slab: {e}")

class SetSlabHeight(Tool):
    name = "set_slab_height"
    description = """
    This tool is use to set the height(elevation) of a slab in Vectorworks.
    Input:
        - slab_id: str, the uuid of the slab object.
        - height: float, the height of the slab relative to the story layer where the slab was originally created.
    Return:
        - str, the uuid of the modified slab.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, slab_id: str, height: float):
        try:
            if not slab_id:
                print("[openBIMForge][Slab Fallback] Skip slab height because slab id is empty.")
                return ""
            if isinstance(slab_id, str):
                slab_h = vs.GetObjectByUuid(slab_id)
            if isinstance(slab_id, list):
                slab_h = vs.GetObjectByUuid(slab_id[0])
            if _is_nil_handle(slab_h):
                print("[openBIMForge][Slab Fallback] Skip slab height because slab handle is NIL.")
                return slab_id
            if vs.GetClass(slab_h) == "Slabs" and vs.GetTypeN(slab_h) != 86:
                ok, offset, rotationX, rotationY, rotationZ = vs.GetEntityMatrix(slab_h)
                if ok:
                    new_offset = (offset[0], offset[1], height)
                    vs.SetEntityMatrix(slab_h, new_offset, rotationX, rotationY, rotationZ)
                    vs.ResetObject(slab_h)
                return slab_id
            # check if the slab is a roof slab, which is acutally a roof's uuid
            if vs.GetClass(slab_h) == "Roofs":
                # in this case we delegate the height setting to the roof
                set_roof_attribute = SetRoofAttributes()
                roof_id = set_roof_attribute(slab_id, eave_height=height)
                return roof_id
            # need to be careful with this
            # seems like the height is the height to the ground layer, not the story layer, so we need to convert it
            # layer_h = vs.GetParent(slab_h)
            # base_eleva, thickness = vs.GetLayerElevation(layer_h)
            ok, offset, rotationX, rotationY, rotationZ = vs.GetEntityMatrix(slab_h)
            # original_elevation = vs.GetObjectVariableReal(slab_h, 174) # this is aquivalent to vs.GetSlabHeight, will however return 0 if the slab is paste on the corresponding layer
            original_elevation_to_layer = offset[2] # this is the height of the slab relative to the story layer where the slab is now pasted
            # vs.AlrtDialog(f"original_elevation_to_layer: {original_elevation_to_layer}")
            height = height - original_elevation_to_layer
            # height = height + base_eleva + thickness
            # vs.SetSlabHeight(slab_h, height) # BUG! this is not working, so we use the SetEntityMatrix instead
            new_offset =(offset[0], offset[1], height)  # set the height to the offset
            vs.SetEntityMatrix(slab_h, new_offset, rotationX, rotationY, rotationZ)
            vs.ResetObject(slab_h)
            return slab_id
        except Exception as e:
            raise ValueError(f"Error occured during setting slab height: {e}")

class GetSlabHeight(Tool):
    name = "get_slab_height"
    description = """
    This tool is use to get the height(elevation) of a slab in Vectorworks.
    Input:
        - slab_id: str, the uuid of the slab object.
    Return:
        - float, the height of the slab relative to the story layer where the slab was originally created.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, slab_id: str):
        try:
            if isinstance(slab_id, str):
                slab_h = vs.GetObjectByUuid(slab_id)
            if isinstance(slab_id, list):
                slab_h = vs.GetObjectByUuid(slab_id[0])

            # update: now we use the GetEntityMatrix to get the height
            ok, offset, rotationX, rotationY, rotationZ = vs.GetEntityMatrix(slab_h)
            # offset[2] is the height of the slab relative to the story layer where the slab is now pasted
            height = offset[2]
            return height
        except Exception as e:
            raise ValueError(f"Error occured during getting slab height: {e}")

class SetSlabStyle(Tool):
    name = "set_slab_style"
    description = """
    This tool is use to set the style of a slab in Vectorworks.
    Input:
        - slab_id: str, the uuid of the slab object.
        - style_name: str, the name of the style.
    Return:
        - str, the uuid of the modified slab.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, slab_id: str, style_name: str):
        fallback_styles = [
            "Concrete Slab",
            "Generic-Floor Assembly-300mm",
            "Generic-Slab-150mm",
        ]
        try:
            if isinstance(slab_id, str):
                slab_h = vs.GetObjectByUuid(slab_id)
            if isinstance(slab_id, list):
                slab_h = vs.GetObjectByUuid(slab_id[0])
            resolved_style = _pick_style_name(
                style_name,
                "slab_styles",
                fallback_styles,
            )
            if resolved_style:
                index = vs.Name2Index(resolved_style)
                if index:
                    vs.SetSlabStyle(slab_h, index)
            elif _style_tolerance_enabled():
                _warn_style_skip("slab", style_name)
            else:
                raise Exception(f"Style name {style_name} not found!")
            return slab_id
        except Exception as e:
            raise ValueError(f"Error occured during setting slab style: {e}")
    
class DuplicateObj(Tool):
    name = "duplicate_obj"
    description = """
    This tool is use to duplicate an element to a specified layer in Vectorworks. The relative position of the duplicate element within its layer is the same as that of the original element within its layer.
    Note that when duplicating a wall that includes doors and windows, the doors and windows within it will also be duplicated.
    It is not recommended to use this tool to duplicate doors and windows directly. It is preferable to first add the doors and windows to the wall, and then duplicate the wall.
    Best practice is to use the element from the ground floor as dulication source, and then duplicate it to the target story layer.
    The story layer cannot be duplicated. 
    Input:
        - element_uuid: str, the unique uuid of an element to duplicate.
        - layer_uuid: str, the uuid of the story layer where the copies will be placed.
        - n: int, the number of copies to make.
    Return:
        - list of str, the list of uuids of the copies. Its recommended to use this list to further manipulate the copies.
"""
                
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, element_uuid: Union[str, List[str]], layer_uuid: str, n: int):
        try:
            objs_uuid = []
            if isinstance(element_uuid, str):
                if not element_uuid:
                    return objs_uuid
                obj = vs.GetObjectByUuid(element_uuid)
                if obj != vs.Handle(0):
                    for i in range(n):
                        # BUG: when triger the copy command fpr a wall via webpalette, the windows and doors within the walls will disappear. However, when run the script in the built-in script editor, it works fine. 
                        # if vs.GetTypeN(obj) == 31:
                        if vs.GetClass(obj) == "xxx": # (never used), this method will not work for wall with doors and windows
                            # set active layer
                            layer_h = vs.GetLayer(obj)
                            layer_name = vs.GetLName(layer_h)
                            # set active layer
                            vs.Layer(layer_name)
                            vs.DSelectAll()
                            vs.SetSelect(obj)
                            vs.DoMenuTextByName('Copy', 0)
                            # switch to the target layer
                            vs.Layer(vs.GetLName(vs.GetObjectByUuid(layer_uuid)))
                            vs.DoMenuTextByName('Paste In Place', 0) 
                            vs.ForEachObjectInLayer(vs.ResetObject, 0, 2, 0)
                            hobj = vs.FSObject(vs.GetObjectByUuid(layer_uuid))
                            obj_uuid = vs.GetObjectUuid(hobj)
                            objs_uuid.append(obj_uuid)
                            vs.ForEachObjectInLayer(set_ifc_property_for_duplication, 2, 1, 0)
                            vs.DSelectAll()
                        else:
                            if vs.GetClass(obj) == "Slabs":
                                hobj = vs.CreateDuplicateObjN(obj, vs.GetObjectByUuid(layer_uuid), False)
                            else:
                                # because of the BUG mentioned above, we need to do it this way
                                hobj = vs.CreateDuplicateObjN(obj, vs.GetObjectByUuid(layer_uuid), True)
                                vs.ResetObject(hobj)
                            obj_uuid = vs.GetObjectUuid(hobj)
                            objs_uuid.append(obj_uuid)
                            # add uuid to ifc
                            set_ifc_property_for_duplication(hobj)

            if isinstance(element_uuid, list):
                for id in element_uuid:
                    if not id:
                        continue
                    obj = vs.GetObjectByUuid(id)
                    if obj != vs.Handle(0):
                        for i in range(n):
                            if vs.GetTypeN(obj) == 31:
                                # set active layer
                                layer_name = vs.GetLName(obj)
                                vs.Layer(layer_name)
                                vs.DSelectAll()
                                vs.SelectAll()
                                vs.DoMenuTextByName('Copy', 0)
                                # switch to the target layer
                                vs.Layer(vs.GetLName(vs.GetObjectByUuid(layer_uuid)))
                                vs.DoMenuTextByName('Paste In Place', 0)
                                vs.ForEachObjectInLayer(set_ifc_property_for_duplication, 2, 1, 0)
                            else:
                                if vs.GetClass(obj) == "Slabs":
                                    hobj = vs.CreateDuplicateObjN(obj, vs.GetObjectByUuid(layer_uuid), False)
                                else:
                                    hobj = vs.CreateDuplicateObjN(obj, vs.GetObjectByUuid(layer_uuid), True)     
                                obj_uuid = vs.GetObjectUuid(hobj)
                                objs_uuid.append(obj_uuid)
                                # add uuid to ifc
                                set_ifc_property_for_duplication(hobj)                    
                # elevation, thickness = vs.GetLayerElevation(vs.GetObjectByUuid(layer_uuid))
                # vs.SetLayerElevation(vs.GetObjectByUuid(layer_uuid), 0, 0)
                # vs.SetLayerElevation(vs.GetObjectByUuid(layer_uuid), elevation, 0)

            return objs_uuid
        except Exception as e:
            raise ValueError(f"Error occured during duplicating element: {e}")

class RotateObj(Tool):
    name = "rotate_obj"
    description = """
    This tool is use to rotate an element in Vectorworks.
    Input:
        - uuid: str, the unique uuid of the element to rotate.
        - angle: float, the angle in degrees to rotate the element.
        - center: tuple, the 2D coordinate of the center of rotation. By default, it is the center of the element.(optional)
    Return:
        - str, the uuid of the rotated element.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, uuid: str, angle: float, center: tuple=None):
        try:
            if isinstance(uuid, str):
                h  = vs.GetObjectByUuid(uuid)
            if isinstance(uuid, list):
                h  = vs.GetObjectByUuid(uuid[0])
            if center:
                vs.HRotate(h, center, angle)
            else:
                center = vs.HCenter(h)
                vs.HRotate(h, center, angle)
            return uuid
        except Exception as e:
            raise ValueError(f"Error occured during rotating element: {e}")

class CreateRoof(Tool):
    name = "create_pitched_roof"
    description = """
    This tool is use to create a pitched roof from a polygon profile on a specified layer in Vectorworks.
    Input:
        - profile_id: str, the uuid of a ploygon object that determines the profile(base) of the roof.
        - layer_uuid: str, the uuid of the story layer where the roof will be created.
        - slope: float, the slope of the roof in degrees. It cannot be less than 5.
        - eave_overhang: float, the eave overhang of the roof.
        - eave_height: float, the elevation of the roof relative to the specified layer. Usually the height of the wall on this floor.
        - roof_thickness: float, the thickness of the roof.
    Return:
        - str, the uuid of the created roof.
"""
    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, profile_id: List[str], layer_uuid :str, slope: float = 30, eave_overhang: float = 300, eave_height: float = 2700, roof_thickness: float = 300):
        try:
            # set active layer
            layer_name = vs.GetLName(vs.GetObjectByUuid(layer_uuid))
            vs.Layer(layer_name)
            
            if isinstance(profile_id, str):
                poly_h = vs.GetObjectByUuid(profile_id)
            if isinstance(profile_id, list):
                poly_h = vs.GetObjectByUuid(profile_id[0])
            #dobule check the slope value
            if slope < 5:
                slope = 5
            hroof = vs.CreateRoof(False,0,300,1,0)
            num = vs.GetVertNum(poly_h)
            for i in range(num):
                i = i+1
                vertex = vs.GetPolylineVertex(poly_h,i)[0]
                vs.AppendRoofEdge(hroof, vertex, slope, eave_overhang, eave_height)
            bearingInsetDistance = 0
            vs.SetRoofAttributes(hroof, False, bearingInsetDistance, roof_thickness, 1, 0)
            vs.SetClass(hroof, "Roofs")
        
            uuid = vs.GetObjectUuid(hroof)
            # add uuid to ifc
            ok = vs.IFC_SetProperty(hroof, 'IfcRoof', 'Description', str(uuid))

            # create a slab under the roof for solibri checking purpose
            slab_h = vs.CreateSlab(poly_h)
            roof_slab_style = _pick_style_name(
                "slabstyleroof",
                "roof_slab_styles",
                ["slabstyleroof", "Concrete Slab", "Generic-Floor Assembly-300mm"],
            )
            if roof_slab_style:
                index = vs.Name2Index(roof_slab_style)
                if index:
                    vs.SetSlabStyle(slab_h, index)
            elif _style_tolerance_enabled():
                _warn_style_skip("roof_slab", "slabstyleroof")
            else:
                raise ValueError("Style name slabstyleroof not found!")
            vs.SetClass(slab_h, "Roof_Slabs")
            # weird thing is that if the slab is placed on the higher story layer, the set slab height is based on the ground level???
            base_elva, thickness = vs.GetLayerElevation(vs.GetObjectByUuid(layer_uuid))
            vs.SetSlabHeight(slab_h, eave_height+ base_elva+ thickness)
            vs.ResetObject(slab_h)

            roof_slab_uuid = vs.GetObjectUuid(slab_h)
            # add roof uuid to ifc, since solibri will probably use the slab as roof
            ok = vs.IFC_SetProperty(slab_h, 'IfcSlab', 'Description', str(uuid))

            # also, add the roof slab uuid to the roof ifc property in order to link them
            ok = vs.IFC_SetProperty(hroof, 'IfcRoof', 'Tag', str(roof_slab_uuid))

            return uuid
        except Exception as e:
            raise ValueError(f"Error occured during creating pitched roof: {e}")

class SetRoofAttributes(Tool):
    name = "set_pitched_roof_attributes"
    description = """
    This tool is use to set the new attributes of a pitched roof in Vectorworks. Attributes that need to be changed can be optionally entered.
    Input:
        - roof_id: str, the uuid of the roof object.
        - slope: float, the slope of the roof in degrees (optional).
        - eave_overhang: float, the eave overhang of the roof (optional).
        - eave_height: float, the height(elevation) of the roof from the story layer where the roof was originally created (optional).
        - roof_thickness: float, the thickness of the roof (optional).
    Return:
        - str, the uuid of the modified roof.
    """
    inputs = ["text", "text", "text", "text", "text"]
    outputs = ["text"]

    def __call__(self, roof_id: str, slope: float = None, eave_overhang: float = None, eave_height: float = None, roof_thickness: float = None):
        try:
            # Get roof handle
            if isinstance(roof_id, str):
                roof_h = vs.GetObjectByUuid(roof_id)
            elif isinstance(roof_id, list):
                roof_h = vs.GetObjectByUuid(roof_id[0])
            else:
                raise ValueError(f"Invalid roof_id type: {type(roof_id)}")
            
            # Check if roof handle is valid
            if not roof_h:
                raise ValueError(f"Could not find roof object with ID: {roof_id}")
            
            # Get number of vertices
            ver_n = vs.GetRoofVertices(roof_h)
            
            # Check if roof has vertices
            if ver_n <= 0:
                raise ValueError(f"Roof has no vertices (ver_n = {ver_n})")
            
            old_eaveHeight_original_list = []
            
            for index in range(ver_n):
                index = index + 1  # Vectorworks uses 1-based indexing
                
                # Get roof edge info
                result = vs.GetRoofEdge(roof_h, index)
                if not result or len(result) < 5:
                    raise ValueError(f"Failed to get roof edge data for index {index}")
                
                bool_success, old_vertexPt, old_slope, old_overhang, old_eaveHeight = result
                
                if not bool_success:
                    raise ValueError(f"GetRoofEdge failed for index {index}")
                
                old_eaveHeight_original_list.append(old_eaveHeight)
                
                # Update slope if provided
                if slope is not None:
                    old_slope = slope
                
                # Update overhang if provided
                if eave_overhang is not None:
                    old_overhang = eave_overhang
                
                # Update eave height if provided
                if eave_height is not None:
                    # Consider the layer elevation
                    layer_h = vs.GetParent(roof_h)
                    if not layer_h:
                        raise ValueError("Could not get parent layer of roof")
                    
                    base_eleva, thickness = vs.GetLayerElevation(layer_h)
                    old_eaveHeight = eave_height + base_eleva + thickness
                
                # Set the updated roof edge
                vs.SetRoofEdge(roof_h, index, old_vertexPt, old_slope, old_overhang, old_eaveHeight)
            
            # Handle eave height changes (only if we have vertices)
            if eave_height is not None and old_eaveHeight_original_list:
                old_eaveHeight_original = old_eaveHeight_original_list[0]
                
                # Set the roof slab height
                ok, roof_slab_uuid, iType = vs.IFC_GetEntityProp(roof_h, 'Tag')
                if ok and roof_slab_uuid:
                    roof_slab_h = vs.GetObjectByUuid(roof_slab_uuid)
                    if roof_slab_h:
                        layer_h = vs.GetParent(roof_h)
                        base_eleva, thickness = vs.GetLayerElevation(layer_h)
                        
                        # Calculate new slab height
                        new_slab_height = eave_height + base_eleva + thickness - old_eaveHeight_original
                        vs.SetSlabHeight(roof_slab_h, new_slab_height)
                        vs.ResetObject(roof_slab_h)
                    else:
                        print(f"Warning: Could not find roof slab object with UUID: {roof_slab_uuid}")
                else:
                    print("Warning: Could not get roof slab UUID from IFC properties")
        
            # Handle roof thickness changes
            if roof_thickness is not None:
                roof_attrs = vs.GetRoofAttributes(roof_h)
                if roof_attrs and len(roof_attrs) >= 6:
                    bool_roof, genGableWall, bearingInset, roofThick, miterType, vertMiter = roof_attrs
                    if bool_roof:
                        vs.SetRoofAttributes(roof_h, genGableWall, bearingInset, roof_thickness, miterType, vertMiter)
                    else:
                        raise ValueError("GetRoofAttributes returned False")
                else:
                    raise ValueError("Failed to get roof attributes")
            
            return roof_id
            
        except Exception as e:
            raise ValueError(f"Error occurred during setting roof attributes for {roof_id}: {e}")

class SetRoofStyle(Tool):
    name = "set_pitched_roof_style"
    description = """
    This tool is use to set the style of a pitched roof in Vectorworks.
    Input:
        - roof_id: str, the uuid of the roof object.
        - style_name: str, the name of the style. Following roof style names are avaliable: ["Low Slope Concrete w/ Rigid Insulation", "Sloped Wood Struct Insul Flat Clay Tile"]
    Return:
        - str, the uuid of the modified roof.
"""
    inputs = ["text", "text"]
    outputs = ["text"]

    def __call__(self, roof_id: str, style_name: str):
        fallback_styles = [
            "Low Slope Concrete w/ Rigid Insulation",
            "Sloped Wood Struct Insul Flat Clay Tile",
        ]
        try:
            if isinstance(roof_id, str):
                roof_h = vs.GetObjectByUuid(roof_id)
            if isinstance(roof_id, list):
                roof_h = vs.GetObjectByUuid(roof_id[0])
            resolved_style = _pick_style_name(
                style_name,
                "roof_styles",
                fallback_styles,
            )
            if resolved_style:
                index = vs.Name2Index(resolved_style)
                if index:
                    vs.SetRoofStyle(roof_h, index)
            elif _style_tolerance_enabled():
                _warn_style_skip("roof", style_name)
            else:
                raise Exception(f"Style name {style_name} not found!")
            return roof_id
        except Exception as e:
            raise ValueError(f"Error occured during setting roof style: {e}")
