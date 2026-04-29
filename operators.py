import bpy
import csv
import os
from .figures import export_figures
from .core import (
    blend_shape_keys,
    export_obj,
    compute_mesh_dimensions_cm,
    place_cameras,
    safe_name,
    shape_key_enum_items,
    silhouette_area_cm2,
    compute_surface_area_cm2,
    compute_volume_cm3,
    render_camera_to_path,
    map_slider_to_days_linear,
    _apply_mapped_days_to_shape_keys,
)


def mesh_object_poll(_self, obj):
    return obj is not None and obj.type == "MESH"


def camera_poll(_self, obj):
    return obj is not None and obj.type == "CAMERA"


def sequence_keys_by_age(scene, obj):
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return []
    keys = []
    for item in scene.conform_shapekey_sequence:
        if item.key_name in obj.data.shape_keys.key_blocks:
            key_block = obj.data.shape_keys.key_blocks[item.key_name]
            keys.append((float(item.bcs_score), key_block))
    keys.sort(key=lambda x: x[0])
    return keys


def sequence_shape_keys(scene, obj):
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return []
    keys = []
    for item in scene.conform_shapekey_sequence:
        if item.key_name in obj.data.shape_keys.key_blocks:
            keys.append(obj.data.shape_keys.key_blocks[item.key_name])
    return keys


def update_shape_age_slider(self, context):
    scene = self
    obj = scene.conform_target_object
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return

    if getattr(scene, "conform_mode", "BCS") == "AGE":
        keys = sequence_keys_by_age(scene, obj)
        if not keys:
            return
        min_days, max_days = keys[0][0], keys[-1][0]
        mapped_days = map_slider_to_days_linear(
            scene.shape_age_slider, min_days, max_days)
        _apply_mapped_days_to_shape_keys(obj, mapped_days, keys)
        return

    keys = sequence_shape_keys(scene, obj)
    if len(keys) < 2:
        return

    slider_val = max(0.0, min(1.0, float(scene.shape_age_slider)))
    segment_count = len(keys) - 1
    if slider_val >= 1.0:
        for kb in obj.data.shape_keys.key_blocks:
            if kb.name.lower() != "basis":
                kb.value = 0.0
        keys[-1].value = 1.0
        return

    position = slider_val * segment_count
    index = int(position)
    t = position - index

    for kb in obj.data.shape_keys.key_blocks:
        if kb.name.lower() != "basis":
            kb.value = 0.0

    keys[index].value = 1.0 - t
    keys[index + 1].value = t


class CONFORM_OT_add_shapekey(bpy.types.Operator):
    bl_idname = "conform.add_shapekey"
    bl_label = "Add Shape Key to Sequence"
    bl_options = {"REGISTER", "UNDO"}

    key_name: bpy.props.EnumProperty(
        name="Shape Key",
        items=shape_key_enum_items,
    )

    def invoke(self, context, event):
        obj = context.scene.conform_target_object
        if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
            self.report({"ERROR"}, "Select a mesh with shape keys first")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "key_name", text="Key")

    def execute(self, context):
        scene = context.scene
        item = scene.conform_shapekey_sequence.add()
        item.key_name = self.key_name
        if len(scene.conform_shapekey_sequence) > 1:
            item.bcs_score = scene.conform_shapekey_sequence[-2].bcs_score
        else:
            item.bcs_score = 5.0
        scene.conform_shapekey_sequence_index = len(
            scene.conform_shapekey_sequence) - 1
        return {"FINISHED"}


class CONFORM_OT_remove_shapekey(bpy.types.Operator):
    bl_idname = "conform.remove_shapekey"
    bl_label = "Remove Shape Key from Sequence"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        seq = scene.conform_shapekey_sequence
        idx = scene.conform_shapekey_sequence_index
        if 0 <= idx < len(seq):
            seq.remove(idx)
            scene.conform_shapekey_sequence_index = max(0, idx - 1)
        return {"FINISHED"}


class CONFORM_OT_move_shapekey(bpy.types.Operator):
    bl_idname = "conform.move_shapekey"
    bl_label = "Move Shape Key"
    bl_options = {"REGISTER", "UNDO"}

    direction: bpy.props.EnumProperty(
        items=[("UP", "Up", ""), ("DOWN", "Down", "")],
    )

    def execute(self, context):
        scene = context.scene
        seq = scene.conform_shapekey_sequence
        idx = scene.conform_shapekey_sequence_index
        new_idx = idx - 1 if self.direction == "UP" else idx + 1
        if 0 <= new_idx < len(seq):
            seq.move(idx, new_idx)
            scene.conform_shapekey_sequence_index = new_idx
        return {"FINISHED"}


class CONFORM_OT_export_shapekey_steps(bpy.types.Operator):
    bl_idname = "conform.export_shapekey_steps"
    bl_label = "Generate .CSV"
    bl_description = "Export width, height, length, lateral/dorsal 2D areas, volume, and 3D surface area per shapekey step"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        obj = scene.conform_target_object

        if obj is None or obj.type != "MESH":
            self.report(
                {"ERROR"}, "Select a mesh target object in the add-on panel")
            return {"CANCELLED"}

        if obj.data.shape_keys is None:
            self.report({"ERROR"}, "Target object has no shape keys")
            return {"CANCELLED"}

        sequence = list(scene.conform_shapekey_sequence)
        if len(sequence) < 2:
            self.report(
                {"ERROR"}, "Add at least two shape keys to the blending sequence")
            return {"CANCELLED"}

        key_blocks = obj.data.shape_keys.key_blocks
        pairs = [
            (
                sequence[i].key_name,
                sequence[i + 1].key_name,
                sequence[i].bcs_score,
                sequence[i + 1].bcs_score,
            )
            for i in range(len(sequence) - 1)
        ]

        for from_k, to_k, _from_bcs, _to_bcs in pairs:
            if from_k not in key_blocks:
                self.report(
                    {"ERROR"}, f"Shape key '{from_k}' not found on object")
                return {"CANCELLED"}
            if to_k not in key_blocks:
                self.report(
                    {"ERROR"}, f"Shape key '{to_k}' not found on object")
                return {"CANCELLED"}

        age_mode = scene.conform_mode == "AGE"
        include_bbox = scene.conform_include_bbox
        should_export_figures = scene.conform_export_figures

        if age_mode:
            age_keys = sequence_keys_by_age(scene, obj)
            if not age_keys:
                self.report(
                    {"ERROR"}, "No valid shape keys selected in the sequence")
                return {"CANCELLED"}
            min_age = int(round(age_keys[0][0]))
            max_age = int(round(age_keys[-1][0]))
            step_days = max(1, int(scene.shape_age_step_days))
            sample_days = list(range(min_age, max_age + 1, step_days))
            if not sample_days or sample_days[-1] != max_age:
                sample_days.append(max_age)
            total_rows = len(sample_days)
        else:
            steps = max(2, scene.conform_steps)
            pair_count = len(pairs)
            # Consecutive pairs share one boundary sample; keep it only once.
            total_rows = (pair_count * steps) - max(0, pair_count - 1)

        base_output = bpy.path.abspath(scene.conform_output_dir)
        os.makedirs(base_output, exist_ok=True)

        lateral_cam = scene.conform_lateral_camera
        dorsal_cam = scene.conform_dorsal_camera
        do_render = lateral_cam is not None and dorsal_cam is not None

        image_dir = os.path.join(base_output, "images")
        matcap_dir = os.path.join(base_output, "matcap")
        obj_dir = os.path.join(base_output, "3d_objects")
        if do_render:
            if scene.conform_save_images:
                os.makedirs(image_dir, exist_ok=True)
            if scene.conform_save_matcap:
                os.makedirs(matcap_dir, exist_ok=True)
        if scene.conform_export_obj:
            os.makedirs(obj_dir, exist_ok=True)

        csv_path = os.path.join(base_output, "measurements.csv")
        depsgraph = context.evaluated_depsgraph_get()

        # Cache and restore original shape key values after export.
        original_values = {kb.name: kb.value for kb in key_blocks}

        wm = context.window_manager
        wm.progress_begin(0, total_rows)
        global_step = 0
        samples = []

        try:
            with open(csv_path, "w", newline="") as f:
                score_label = "Age (days)" if scene.conform_mode == "AGE" else "BCS"
                writer = csv.writer(f)
                header = [
                    "Key",
                    "Step",
                    "Blend Factor",
                    score_label,
                    "Object",
                    "From Key",
                    "To Key",
                ]
                if include_bbox:
                    header.extend([
                        "Width (cm)",
                        "Height (cm)",
                        "Length (cm)",
                    ])
                header.extend([
                    "Volume (cm^3)",
                    "3D Surface Area (cm^2)",
                    "2D Lateral Area (cm^2)",
                    "2D Dorsal Area (cm^2)",
                    "Lateral Image",
                    "Dorsal Image",
                    "Lateral Matcap",
                    "Dorsal Matcap",
                ])
                writer.writerow(header)

                if age_mode:
                    for step, day in enumerate(sample_days):
                        wm.progress_update(global_step)
                        _apply_mapped_days_to_shape_keys(obj, float(day), age_keys)
                        score = float(day)
                        from_key = age_keys[0][1].name
                        to_key = age_keys[-1][1].name
                        for (dl, kl), (dr, kr) in zip(age_keys, age_keys[1:]):
                            if dl <= day <= dr:
                                from_key = kl.name
                                to_key = kr.name
                                break
                        context.view_layer.update()

                        if include_bbox:
                            width_cm, height_cm, length_cm = compute_mesh_dimensions_cm(
                                obj, depsgraph, scene)
                        volume_cm3 = compute_volume_cm3(obj, depsgraph, scene)
                        area3d_cm2 = compute_surface_area_cm2(obj, depsgraph, scene)

                        lateral_area_cm2 = 0.0
                        dorsal_area_cm2 = 0.0
                        lateral_img = ""
                        dorsal_img = ""
                        lateral_mat = ""
                        dorsal_mat = ""

                        if do_render:
                            slug = f"{safe_name(from_key)}_to_{safe_name(to_key)}_age{int(day)}d"
                            
                            # Render Silhouettes
                            lateral_base = os.path.join(image_dir, f"{slug}_lateral")
                            dorsal_base = os.path.join(image_dir, f"{slug}_dorsal")
                            lateral_img = render_camera_to_path(scene, lateral_cam, lateral_base, obj, use_matcap=False)
                            dorsal_img = render_camera_to_path(scene, dorsal_cam, dorsal_base, obj, use_matcap=False)
                            
                            lateral_area_cm2 = silhouette_area_cm2(lateral_img, lateral_cam, scene, 0.5)
                            dorsal_area_cm2 = silhouette_area_cm2(dorsal_img, dorsal_cam, scene, 0.5)

                            # Render Matcaps
                            if scene.conform_save_matcap:
                                lateral_mat_base = os.path.join(matcap_dir, f"{slug}_lateral_matcap")
                                dorsal_mat_base = os.path.join(matcap_dir, f"{slug}_dorsal_matcap")
                                lateral_mat = render_camera_to_path(scene, lateral_cam, lateral_mat_base, obj, use_matcap=True)
                                dorsal_mat = render_camera_to_path(scene, dorsal_cam, dorsal_mat_base, obj, use_matcap=True)

                            if not scene.conform_save_images:
                                for path in (lateral_img, dorsal_img):
                                    if path and os.path.exists(path):
                                        os.remove(path)
                                lateral_img = ""
                                dorsal_img = ""

                        if scene.conform_export_obj:
                            slug = f"{safe_name(from_key)}_to_{safe_name(to_key)}_age{int(day)}d"
                            obj_path = os.path.join(obj_dir, f"{slug}.obj")
                            export_obj(obj, obj_path, context)

                        sequence_progress = (
                            global_step / float(total_rows - 1)
                            if total_rows > 1 else 0.0
                        )

                        sample = {
                            "sequence_progress": sequence_progress,
                            "blend_factor": 0.0,
                            "age_days": score,
                            "volume_cm3": volume_cm3,
                            "area3d_cm2": area3d_cm2,
                            "lateral_area_cm2": lateral_area_cm2,
                            "dorsal_area_cm2": dorsal_area_cm2,
                        }
                        if include_bbox:
                            sample.update({
                                "width_cm": width_cm,
                                "height_cm": height_cm,
                                "length_cm": length_cm,
                            })
                        samples.append(sample)

                        row = [
                            0,
                            step,
                            0.0,
                            score,
                            obj.name,
                            from_key,
                            to_key,
                        ]
                        if include_bbox:
                            row.extend([
                                width_cm,
                                height_cm,
                                length_cm,
                            ])
                        row.extend([
                            volume_cm3,
                            area3d_cm2,
                            lateral_area_cm2,
                            dorsal_area_cm2,
                            os.path.basename(
                                lateral_img) if lateral_img else "",
                            os.path.basename(dorsal_img) if dorsal_img else "",
                            os.path.basename(
                                lateral_mat) if lateral_mat else "",
                            os.path.basename(
                                dorsal_mat) if dorsal_mat else "",
                        ])
                        writer.writerow(row)

                        global_step += 1
                        bpy.ops.wm.redraw_timer(
                            type="DRAW_WIN_SWAP", iterations=1)
                else:
                    for key_idx, (from_key, to_key, from_bcs, to_bcs) in enumerate(pairs):
                        step_start = 0 if key_idx == 0 else 1
                        for step in range(step_start, steps):
                            wm.progress_update(global_step)
                            t = step / float(steps - 1)
                            score = from_bcs + ((to_bcs - from_bcs) * t)
                            ok = blend_shape_keys(obj, from_key, to_key, t)
                            if not ok:
                                self.report(
                                    {"ERROR"}, "Could not apply shape key values")
                                return {"CANCELLED"}
                            context.view_layer.update()

                            if include_bbox:
                                width_cm, height_cm, length_cm = compute_mesh_dimensions_cm(
                                    obj, depsgraph, scene)
                            volume_cm3 = compute_volume_cm3(obj, depsgraph, scene)
                            area3d_cm2 = compute_surface_area_cm2(
                                obj, depsgraph, scene)

                            lateral_area_cm2 = 0.0
                            dorsal_area_cm2 = 0.0
                            lateral_img = ""
                            dorsal_img = ""
                            lateral_mat = ""
                            dorsal_mat = ""

                            if do_render:
                                slug = f"{safe_name(from_key)}_to_{safe_name(to_key)}_step{step:04d}"
                                
                                # Render Silhouettes
                                lateral_base = os.path.join(image_dir, f"{slug}_lateral")
                                dorsal_base = os.path.join(image_dir, f"{slug}_dorsal")
                                lateral_img = render_camera_to_path(scene, lateral_cam, lateral_base, obj, use_matcap=False)
                                dorsal_img = render_camera_to_path(scene, dorsal_cam, dorsal_base, obj, use_matcap=False)

                                lateral_area_cm2 = silhouette_area_cm2(lateral_img, lateral_cam, scene, 0.5)
                                dorsal_area_cm2 = silhouette_area_cm2(dorsal_img, dorsal_cam, scene, 0.5)

                                # Render Matcaps
                                if scene.conform_save_matcap:
                                    lateral_mat_base = os.path.join(matcap_dir, f"{slug}_lateral_matcap")
                                    dorsal_mat_base = os.path.join(matcap_dir, f"{slug}_dorsal_matcap")
                                    lateral_mat = render_camera_to_path(scene, lateral_cam, lateral_mat_base, obj, use_matcap=True)
                                    dorsal_mat = render_camera_to_path(scene, dorsal_cam, dorsal_mat_base, obj, use_matcap=True)

                                if not scene.conform_save_images:
                                    for path in (lateral_img, dorsal_img):
                                        if path and os.path.exists(path):
                                            os.remove(path)
                                    lateral_img = ""
                                    dorsal_img = ""

                            if scene.conform_export_obj:
                                slug = f"{safe_name(from_key)}_to_{safe_name(to_key)}_step{step:04d}"
                                obj_path = os.path.join(obj_dir, f"{slug}.obj")
                                export_obj(obj, obj_path, context)

                            sequence_progress = (
                                global_step / float(total_rows - 1)
                                if total_rows > 1 else 0.0
                            )

                            sample = {
                                "sequence_progress": sequence_progress,
                                "blend_factor": t,
                                "bcs": score,
                                "volume_cm3": volume_cm3,
                                "area3d_cm2": area3d_cm2,
                                "lateral_area_cm2": lateral_area_cm2,
                                "dorsal_area_cm2": dorsal_area_cm2,
                            }
                            if include_bbox:
                                sample.update({
                                    "width_cm": width_cm,
                                    "height_cm": height_cm,
                                    "length_cm": length_cm,
                                })
                            samples.append(sample)

                            row = [
                                key_idx,
                                step,
                                t,
                                score,
                                obj.name,
                                from_key,
                                to_key,
                            ]
                            if include_bbox:
                                row.extend([
                                    width_cm,
                                    height_cm,
                                    length_cm,
                                ])
                            row.extend([
                                volume_cm3,
                                area3d_cm2,
                                lateral_area_cm2,
                                dorsal_area_cm2,
                                os.path.basename(
                                    lateral_img) if lateral_img else "",
                                os.path.basename(
                                    dorsal_img) if dorsal_img else "",
                                os.path.basename(
                                    lateral_mat) if lateral_mat else "",
                                os.path.basename(
                                    dorsal_mat) if dorsal_mat else "",
                            ])
                            writer.writerow(row)

                            global_step += 1
                            # Keep UI responsive during long exports.
                            bpy.ops.wm.redraw_timer(
                                type="DRAW_WIN_SWAP", iterations=1)

            figure_count = 0
            if should_export_figures:
                figure_paths = export_figures(
                    samples, base_output, include_bbox)
                figure_count = len(figure_paths)

            self.report(
                {"INFO"},
                f"Export complete: {csv_path} ({figure_count} figure files)",
            )
            return {"FINISHED"}

        finally:
            wm.progress_end()
            for kb in key_blocks:
                if kb.name in original_values:
                    kb.value = original_values[kb.name]
            context.view_layer.update()


class CONFORM_OT_autoplace_cameras(bpy.types.Operator):
    bl_idname = "conform.autoplace_cameras"
    bl_label = "Auto-Place Lateral/Dorsal Cameras"
    bl_description = "Create/place orthographic cameras around target mesh for lateral and dorsal projections"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        obj = scene.conform_target_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a target mesh first")
            return {"CANCELLED"}

        depsgraph = context.evaluated_depsgraph_get()
        lateral_cam, dorsal_cam = place_cameras(
            scene, obj, depsgraph)
        if lateral_cam is None or dorsal_cam is None:
            self.report(
                {"ERROR"}, "Could not derive mesh bounds for camera placement")
            return {"CANCELLED"}

        self.report({"INFO"}, "Placed lateral and dorsal orthographic cameras")
        return {"FINISHED"}


OPERATOR_CLASSES = (
    CONFORM_OT_add_shapekey,
    CONFORM_OT_remove_shapekey,
    CONFORM_OT_move_shapekey,
    CONFORM_OT_export_shapekey_steps,
    CONFORM_OT_autoplace_cameras,
)
