import bpy
import bmesh
import os
import re
from array import array
from mathutils import Vector
import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator


def scale_cm(scene):
    return scene.unit_settings.scale_length * 100.0


def to_cm(value_in_blender_units, scene):
    return value_in_blender_units * scale_cm(scene)


def to_cm2(value_in_blender_units_sq, scene):
    scale = scale_cm(scene)
    return value_in_blender_units_sq * (scale ** 2)


def to_cm3(value_in_blender_units_cu, scene):
    scale = scale_cm(scene)
    return value_in_blender_units_cu * (scale ** 3)


def bmesh_from_object(obj, depsgraph):
    bm = bmesh.new()
    obj_eval = obj.evaluated_get(depsgraph)
    bm.from_object(obj_eval, depsgraph)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def compute_mesh_dimensions_cm(obj, depsgraph, scene):
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    if not mesh or not mesh.vertices:
        if mesh:
            obj_eval.to_mesh_clear()
        return 0.0, 0.0, 0.0

    try:
        world_matrix = obj_eval.matrix_world
        min_corner = Vector((float("inf"), float("inf"), float("inf")))
        max_corner = Vector((float("-inf"), float("-inf"), float("-inf")))

        for v in mesh.vertices:
            p = world_matrix @ v.co
            min_corner.x = min(min_corner.x, p.x)
            min_corner.y = min(min_corner.y, p.y)
            min_corner.z = min(min_corner.z, p.z)
            max_corner.x = max(max_corner.x, p.x)
            max_corner.y = max(max_corner.y, p.y)
            max_corner.z = max(max_corner.z, p.z)

        width_cm = to_cm(max_corner.x - min_corner.x, scene)
        length_cm = to_cm(max_corner.y - min_corner.y, scene)
        height_cm = to_cm(max_corner.z - min_corner.z, scene)
        return width_cm, height_cm, length_cm
    finally:
        obj_eval.to_mesh_clear()


def compute_volume_cm3(obj, depsgraph, scene):
    obj_eval = obj.evaluated_get(depsgraph)
    bm = bmesh_from_object(obj, depsgraph)
    try:
        # Convert to world space so object transforms (especially scale)
        # are included in volume output.
        bm.transform(obj_eval.matrix_world)
        volume = bm.calc_volume(signed=False)
    except Exception:
        volume = 0.0
    finally:
        bm.free()
    return to_cm3(volume, scene)


def compute_surface_area_cm2(obj, depsgraph, scene):
    obj_eval = obj.evaluated_get(depsgraph)
    bm = bmesh_from_object(obj, depsgraph)
    try:
        # Convert to world space so object transforms (especially scale)
        # are included in area output.
        bm.transform(obj_eval.matrix_world)
        area = sum(face.calc_area() for face in bm.faces)
    finally:
        bm.free()
    return to_cm2(area, scene)


def render_camera_to_path(scene, camera, output_path, obj, use_matcap=False):
    original_camera = scene.camera
    original_filepath = scene.render.filepath
    original_format = scene.render.image_settings.file_format
    original_color_mode = scene.render.image_settings.color_mode
    original_film_transparent = scene.render.film_transparent
    original_resolution_x = scene.render.resolution_x
    original_resolution_y = scene.render.resolution_y
    original_resolution_percentage = scene.render.resolution_percentage

    # Isolate the render to just target object + active camera.
    visibility_states = []
    for scene_obj in scene.objects:
        visibility_states.append(
            (scene_obj, scene_obj.hide_render, scene_obj.hide_get())
        )
        keep_visible = scene_obj == obj or scene_obj == camera
        scene_obj.hide_render = not keep_visible
        scene_obj.hide_set(not keep_visible)

    # Force viewport shading for OpenGL render.
    shading = None
    shading_backup = {}
    display = getattr(scene, "display", None)
    if display is not None:
        shading = getattr(display, "shading", None)
    if shading is not None:
        backup_attrs = (
            "type",
            "light",
            "color_type",
            "single_color",
            "background_type",
            "background_color",
            "show_specular_highlight",
            "show_shadows",
            "show_cavity",
            "show_object_outline",
            "show_xray",
            "matcap_name",
        )
        for attr in backup_attrs:
            if hasattr(shading, attr):
                value = getattr(shading, attr)
                if hasattr(value, "copy"):
                    value = value.copy()
                shading_backup[attr] = value

        if hasattr(shading, "type"):
            shading.type = "SOLID"
        
        if use_matcap:
            if hasattr(shading, "light"):
                shading.light = "MATCAP"
            if hasattr(shading, "color_type"):
                shading.color_type = "OBJECT"
            if hasattr(shading, "background_type"):
                shading.background_type = "VIEWPORT"
        else:
            if hasattr(shading, "light"):
                shading.light = "FLAT"
            if hasattr(shading, "color_type"):
                shading.color_type = "SINGLE"
            if hasattr(shading, "single_color"):
                shading.single_color = (0.0, 0.0, 0.0)
            if hasattr(shading, "background_type"):
                shading.background_type = "WORLD"
            if hasattr(shading, "background_color"):
                shading.background_color = (1.0, 1.0, 1.0)
            
        if hasattr(shading, "show_specular_highlight"):
            shading.show_specular_highlight = False
        if hasattr(shading, "show_shadows"):
            shading.show_shadows = False
        if hasattr(shading, "show_cavity"):
            shading.show_cavity = False
        if hasattr(shading, "show_object_outline"):
            shading.show_object_outline = False
        if hasattr(shading, "show_xray"):
            shading.show_xray = False

    try:
        scene.camera = camera
        scene.render.filepath = output_path
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.film_transparent = True

        resolution_px = max(16, int(getattr(scene, "conform_render_resolution_px", 1024)))
        scene.render.resolution_x = resolution_px
        scene.render.resolution_y = resolution_px
        scene.render.resolution_percentage = 100

        try:
            bpy.ops.render.opengl(write_still=True, view_context=False)
        except Exception:
            bpy.ops.render.render(write_still=True)

        png_path = output_path if output_path.lower().endswith(
            ".png") else output_path + ".png"
        if os.path.exists(png_path):
            path = png_path
        elif os.path.exists(output_path):
            path = output_path
        else:
            path = ""
        return path
    finally:
        scene.camera = original_camera
        scene.render.filepath = original_filepath
        scene.render.image_settings.file_format = original_format
        scene.render.image_settings.color_mode = original_color_mode
        scene.render.film_transparent = original_film_transparent
        scene.render.resolution_x = original_resolution_x
        scene.render.resolution_y = original_resolution_y
        scene.render.resolution_percentage = original_resolution_percentage

        if shading is not None:
            for attr, value in shading_backup.items():
                try:
                    setattr(shading, attr, value)
                except Exception:
                    pass

        # Restore object visibility.
        for scene_obj, hide_render, hide_viewport in visibility_states:
            scene_obj.hide_render = hide_render
            scene_obj.hide_set(hide_viewport)


def silhouette_area_cm2(image_path, camera, scene, threshold):
    if not image_path or not os.path.exists(image_path):
        return 0.0

    img = None
    try:
        img = bpy.data.images.load(image_path)
        return _silhouette_area_from_image(img, camera, scene, threshold)
    finally:
        if img is not None:
            bpy.data.images.remove(img)

def _silhouette_area_from_image(img, camera, scene, threshold):
    if img is None:
        return 0.0

    if not camera or camera.type != "CAMERA" or camera.data.type != "ORTHO":
        return 0.0

    width = img.size[0]
    height = img.size[1]
    if width == 0 or height == 0:
        return 0.0

    # Copy pixel buffer in one shot (RGBA float32) without external deps.
    pixels = array("f", [0.0]) * (width * height * 4)
    img.pixels.foreach_get(pixels)

    silhouette_pixels_gray = 0
    silhouette_pixels_alpha = 0
    alpha_has_variation = False
    for i in range(0, len(pixels), 4):
        alpha = pixels[i + 3]
        if alpha < 0.999:
            alpha_has_variation = True
        if alpha > threshold:
            silhouette_pixels_alpha += 1

        gray = (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3.0
        if gray < threshold:
            silhouette_pixels_gray += 1

    silhouette_pixels = (
        silhouette_pixels_alpha if alpha_has_variation
        else silhouette_pixels_gray
    )

    total_pixels = width * height
    if total_pixels == 0:
        return 0.0

    original_resolution_x = scene.render.resolution_x
    original_resolution_y = scene.render.resolution_y
    original_resolution_percentage = scene.render.resolution_percentage
    try:
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        frame = camera.data.view_frame(scene=scene)
    finally:
        scene.render.resolution_x = original_resolution_x
        scene.render.resolution_y = original_resolution_y
        scene.render.resolution_percentage = original_resolution_percentage

    min_x = min(v.x for v in frame)
    max_x = max(v.x for v in frame)
    min_y = min(v.y for v in frame)
    max_y = max(v.y for v in frame)

    ortho_w = max_x - min_x
    ortho_h = max_y - min_y
    if ortho_w <= 0.0 or ortho_h <= 0.0:
        return 0.0

    frame_area_cm2 = to_cm(ortho_w, scene) * to_cm(ortho_h, scene)
    per_pixel_cm2 = frame_area_cm2 / total_pixels
    return silhouette_pixels * per_pixel_cm2


def blend_shape_keys(obj, from_name, to_name, t):
    keys = obj.data.shape_keys
    if keys is None:
        return False

    for kb in keys.key_blocks:
        if kb.name != "Basis":
            kb.value = 0.0

    if from_name not in keys.key_blocks or to_name not in keys.key_blocks:
        return False

    from_kb = keys.key_blocks[from_name]
    to_kb = keys.key_blocks[to_name]
    from_kb.value = 1.0 - t
    to_kb.value = t
    return True


_INTERPOLATION_SHAPE_KEY_NAME = "CONFORM Interpolated Shape"


def remove_conform_interpolation_shape_key(obj):
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return
    key_blocks = obj.data.shape_keys.key_blocks
    if _INTERPOLATION_SHAPE_KEY_NAME in key_blocks:
        obj.shape_key_remove(key_blocks[_INTERPOLATION_SHAPE_KEY_NAME])


def apply_bcs_interpolation_shape_keys(
        obj, key_names, scores, interval_index, t, method):
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return False

    key_blocks = obj.data.shape_keys.key_blocks
    if len(key_names) < 2:
        return False
    scores = np.asarray(scores, dtype=np.float64)
    if scores.shape != (len(key_names),):
        return False
    for key_name in key_names:
        if key_name not in key_blocks:
            return False

    interval_index = max(0, min(interval_index, len(key_names) - 2))
    t = max(0.0, min(1.0, float(t)))
    vertex_count = len(key_blocks[key_names[0]].data)
    if any(len(key_blocks[name].data) != vertex_count for name in key_names):
        return False

    if _INTERPOLATION_SHAPE_KEY_NAME not in key_blocks:
        interpolation_shape_key = obj.shape_key_add(name=_INTERPOLATION_SHAPE_KEY_NAME, from_mix=False)
    else:
        interpolation_shape_key = key_blocks[_INTERPOLATION_SHAPE_KEY_NAME]

    coordinates = np.empty((len(key_names), vertex_count, 3), dtype=np.float64)
    flat_coordinates = coordinates.reshape(len(key_names), -1)
    for row, name in enumerate(key_names):
        key_blocks[name].data.foreach_get("co", flat_coordinates[row])

    sample_score = scores[interval_index] + (
        t * (scores[interval_index + 1] - scores[interval_index]))
    try:
        if method == "PCHIP":
            interpolator = PchipInterpolator(
                scores, coordinates, axis=0, extrapolate=False)
        elif method == "CUBIC_NOT_A_KNOT":
            interpolator = CubicSpline(
                scores, coordinates, axis=0, bc_type="not-a-knot",
                extrapolate=False)
        elif method == "CUBIC_NATURAL":
            interpolator = CubicSpline(
                scores, coordinates, axis=0, bc_type="natural",
                extrapolate=False)
        else:
            return False
        interpolated = interpolator(sample_score)
    except ValueError:
        return False
    interpolation_shape_key.data.foreach_set("co", interpolated.ravel())

    for kb in key_blocks:
        if kb.name.lower() != "basis":
            kb.value = 0.0
    interpolation_shape_key.value = 1.0
    return True


def shape_key_enum_items(_self, context):
    obj = context.scene.conform_target_object
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return []

    items = []
    for idx, kb in enumerate(obj.data.shape_keys.key_blocks):
        if kb.name == _INTERPOLATION_SHAPE_KEY_NAME:
            continue
        items.append((kb.name, kb.name, f"Shape key: {kb.name}", idx))
    return items


def mesh_bounds_world(obj, depsgraph):
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    if not mesh or not mesh.vertices:
        if mesh:
            obj_eval.to_mesh_clear()
        return None, None

    world_matrix = obj_eval.matrix_world
    min_corner = Vector((float("inf"), float("inf"), float("inf")))
    max_corner = Vector((float("-inf"), float("-inf"), float("-inf")))

    for v in mesh.vertices:
        p = world_matrix @ v.co
        min_corner.x = min(min_corner.x, p.x)
        min_corner.y = min(min_corner.y, p.y)
        min_corner.z = min(min_corner.z, p.z)
        max_corner.x = max(max_corner.x, p.x)
        max_corner.y = max(max_corner.y, p.y)
        max_corner.z = max(max_corner.z, p.z)

    obj_eval.to_mesh_clear()
    center = (min_corner + max_corner) * 0.5
    dims = max_corner - min_corner
    return center, dims


def orient_camera_to_target(camera_obj, target):
    direction = target - camera_obj.location
    if direction.length == 0.0:
        return
    camera_obj.rotation_euler = direction.normalized().to_track_quat("-Z",
                                                                     "Y").to_euler()


def get_or_create_camera(scene, camera_name):
    cam_obj = scene.objects.get(camera_name)
    if cam_obj is None or cam_obj.type != "CAMERA":
        cam_data = bpy.data.cameras.new(camera_name)
        cam_obj = bpy.data.objects.new(camera_name, cam_data)
        scene.collection.objects.link(cam_obj)
    return cam_obj


def place_cameras(scene, obj, depsgraph):
    center, dims = mesh_bounds_world(obj, depsgraph)
    if center is None or dims is None:
        return None, None

    distance_factor = 4.0
    scale_padding = scene.conform_ortho_padding

    width = max(dims.x, 0.001)
    length = max(dims.y, 0.001)
    height = max(dims.z, 0.001)
    max_dim = max(width, length, height)

    lateral_cam = scene.conform_lateral_camera
    if lateral_cam is None or lateral_cam.type != "CAMERA":
        lateral_cam = get_or_create_camera(scene, "Lateral_Camera")

    dorsal_cam = scene.conform_dorsal_camera
    if dorsal_cam is None or dorsal_cam.type != "CAMERA":
        dorsal_cam = get_or_create_camera(scene, "Dorsal_Camera")

    lateral_cam.data.type = "ORTHO"
    dorsal_cam.data.type = "ORTHO"

    lateral_cam.location = Vector(
        (center.x + max_dim * distance_factor, center.y, center.z))
    dorsal_cam.location = Vector(
        (center.x, center.y, center.z + max_dim * distance_factor))

    orient_camera_to_target(lateral_cam, center)
    orient_camera_to_target(dorsal_cam, center)

    lateral_cam.data.ortho_scale = max(length, height) * scale_padding
    dorsal_cam.data.ortho_scale = max(width, length) * scale_padding

    scene.conform_lateral_camera = lateral_cam
    scene.conform_dorsal_camera = dorsal_cam
    return lateral_cam, dorsal_cam


def safe_name(name):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def export_obj(obj, filepath, context):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    prev_active = context.view_layer.objects.active
    prev_selected = list(context.selected_objects)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj
    try:
        bpy.ops.wm.obj_export(
            filepath=filepath,
            export_selected_objects=True,
        )
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for o in prev_selected:
            o.select_set(True)
        context.view_layer.objects.active = prev_active


def parse_shape_keys_by_day(obj):
    if not obj or obj.type != "MESH" or obj.data.shape_keys is None:
        return []
    pattern = re.compile(r"(?<!\d)(\d{1,6})(?!\d)")
    keys = []
    seen = set()
    for kb in obj.data.shape_keys.key_blocks:
        if kb.name.lower() == "basis":
            continue
        m = pattern.search(kb.name)
        if not m:
            continue
        days = int(m.group(1))
        if days in seen:
            continue
        seen.add(days)
        keys.append((days, kb))
    keys.sort(key=lambda x: x[0])
    return keys


def map_slider_to_days_linear(slider, min_days, max_days):
    s = max(0.0, min(1.0, float(slider)))
    if min_days == max_days:
        return float(min_days)
    return float(min_days) + s * (float(max_days) - float(min_days))


def _apply_mapped_days_to_shape_keys(obj, mapped_days, keys=None):
    if not obj or obj.type != "MESH" or obj.data.shape_keys is None:
        return
    if keys is None:
        keys = parse_shape_keys_by_day(obj)
    if not keys:
        return

    for kb in obj.data.shape_keys.key_blocks:
        if kb.name.lower() != "basis":
            kb.value = 0.0

    day_values = [d for d, _ in keys]
    min_days, max_days = day_values[0], day_values[-1]

    if mapped_days < min_days:
        return
    if mapped_days >= max_days:
        keys[-1][1].value = 1.0
        return

    for (dl, kl), (dr, kr) in zip(keys, keys[1:]):
        if dl <= mapped_days < dr:
            span = dr - dl
            t = (mapped_days - dl) / span if span else 0.0
            kl.value = 1.0 - t
            kr.value = t
            return


__all__ = (
    "shape_key_enum_items",
    "blend_shape_keys",
    "apply_bcs_interpolation_shape_keys",
    "remove_conform_interpolation_shape_key",
    "compute_mesh_dimensions_cm",
    "compute_volume_cm3",
    "compute_surface_area_cm2",
    "safe_name",
    "render_camera_to_path",
    "silhouette_area_cm2",
    "export_obj",
    "place_cameras",
    "parse_shape_keys_by_day",
    "map_slider_to_days_linear",
)
