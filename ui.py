import bpy
from .core import map_slider_to_days_linear


def get_age_sequence(scene, obj):
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return []
    keys = []
    for item in scene.conform_shapekey_sequence:
        if item.key_name in obj.data.shape_keys.key_blocks:
            keys.append((item.bcs_score, item.key_name))
    keys.sort(key=lambda x: x[0])
    return keys


class CONFORM_ShapeKeyItem(bpy.types.PropertyGroup):
    key_name: bpy.props.StringProperty(name="Shape Key")
    bcs_score: bpy.props.FloatProperty(
        name="BCS",
        default=5.0,
        min=0.0,
        soft_min=1.0,
        soft_max=9.0,
        precision=2,
        description="Body condition score or age in days mapped to this shape key",
    )


class CONFORM_UL_shapekey_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.key_name, icon="SHAPEKEY_DATA")
            score_label = "BCS"
            if getattr(context.scene, "conform_mode", "BCS") == "AGE":
                score_label = "Age"
            row.prop(item, "bcs_score", text=score_label)
        else:
            layout.alignment = "CENTER"
            layout.label(text="", icon="SHAPEKEY_DATA")


class CONFORM_PT_panel(bpy.types.Panel):
    bl_label = "CONFORM"
    bl_idname = "CONFORM_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CONFORM"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "conform_target_object", text="Object")
        layout.prop(scene, "conform_mode", expand=True)


class CONFORM_PT_shapekey_blending(bpy.types.Panel):
    bl_label = "Shape Key Blending"
    bl_idname = "CONFORM_PT_shapekey_blending"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CONFORM"
    bl_parent_id = "CONFORM_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = scene.conform_target_object
        if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
            layout.label(
                text="Select a mesh with a target object and shape keys.")
            return

        row = layout.row()
        row.template_list(
            "CONFORM_UL_shapekey_list", "",
            scene, "conform_shapekey_sequence",
            scene, "conform_shapekey_sequence_index",
            rows=3,
        )
        col = row.column(align=True)
        col.operator("conform.add_shapekey", icon="ADD", text="")
        col.operator("conform.remove_shapekey", icon="REMOVE", text="")
        col.separator()
        col.operator("conform.move_shapekey", icon="TRIA_UP",
                     text="").direction = "UP"
        col.operator("conform.move_shapekey", icon="TRIA_DOWN",
                     text="").direction = "DOWN"

        sequence = get_age_sequence(scene, obj)
        if len(sequence) > 1:
            if scene.conform_mode == "AGE":
                min_age, max_age = sequence[0][0], sequence[-1][0]
                mapped_days = map_slider_to_days_linear(
                    scene.shape_age_slider, min_age, max_age
                )
                label = f"Age: {int(round(mapped_days))} d"
            else:
                label = "Preview"
            layout.row(align=True).prop(
                scene, "shape_age_slider", slider=True, text=label)
        else:
            layout.label(text="Add at least two shape keys to preview.")

        if scene.conform_mode == "AGE":
            step_days = max(1, scene.shape_age_step_days)
            min_age, max_age = int(round(sequence[0][0])), int(round(sequence[-1][0]))
            age_days = list(range(min_age, max_age + 1, step_days))
            if not age_days or age_days[-1] != max_age:
                age_days.append(max_age)
            layout.prop(scene, "shape_age_step_days", text="Age Step (days)")
            total = len(age_days)
        else:
            layout.prop(scene, "conform_steps", text="Steps per Key")
            pairs = max(0, len(scene.conform_shapekey_sequence) - 1)
            steps = max(2, scene.conform_steps)
            total = (pairs * steps) - max(0, pairs - 1)
        row = layout.row()
        row.enabled = False
        row.label(text=f"Total steps: {total}")


class CONFORM_PT_2d_surface_area(bpy.types.Panel):
    bl_label = "2D Surface Area"
    bl_idname = "CONFORM_PT_2d_surface_area"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CONFORM"
    bl_parent_id = "CONFORM_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        col = layout.column(align=True)
        col.prop(scene, "conform_ortho_padding", text="Camera Zoom")
        col.separator(factor=0.5)
        cam_col = col.column(align=True)
        cam_col.prop(scene, "conform_lateral_camera", text="Lateral")
        cam_col.prop(scene, "conform_dorsal_camera", text="Dorsal")
        col.separator(factor=0.5)
        col.operator("conform.autoplace_cameras",
                     text="Place Cameras", icon="OUTLINER_OB_CAMERA")


class CONFORM_PT_output(bpy.types.Panel):
    bl_label = "Output"
    bl_idname = "CONFORM_PT_output"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CONFORM"
    bl_parent_id = "CONFORM_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "conform_output_dir", text="Output")
        layout.separator(factor=0.2)
        col = layout.column(align=True)
        col.prop(scene, "conform_save_images",
                 text="Include Silhouette Images")
        col.prop(scene, "conform_save_matcap",
                 text="Include Matcap Renders")
        col.prop(scene, "conform_export_obj", text="Include .obj per Step")
        col.prop(scene, "conform_include_bbox",
                 text="Include Object Dimensions")
        col.prop(scene, "conform_export_figures",
                 text="Include Figures")
        layout.separator(factor=0.2)
        layout.operator(
            "conform.export_shapekey_steps",
            text="Generate .CSV",
            icon="EXPORT")


UI_CLASSES = (
    CONFORM_ShapeKeyItem,
    CONFORM_UL_shapekey_list,
    CONFORM_PT_panel,
    CONFORM_PT_shapekey_blending,
    CONFORM_PT_2d_surface_area,
    CONFORM_PT_output,
)
