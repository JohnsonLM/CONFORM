import bpy
from .operators import OPERATOR_CLASSES, update_shape_age_slider
from .ui import CONFORM_ShapeKeyItem, UI_CLASSES

CLASSES = UI_CLASSES + OPERATOR_CLASSES


def camera_poll(_self, obj):
    return obj is not None and obj.type == "CAMERA"


def mesh_object_poll(_self, obj):
    return obj is not None and obj.type == "MESH"


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.conform_target_object = bpy.props.PointerProperty(
        name="Target Object",
        type=bpy.types.Object,
        poll=mesh_object_poll,
    )
    bpy.types.Scene.conform_shapekey_sequence = bpy.props.CollectionProperty(
        type=CONFORM_ShapeKeyItem,
    )
    bpy.types.Scene.conform_shapekey_sequence_index = bpy.props.IntProperty(
        default=0,
    )
    bpy.types.Scene.conform_steps = bpy.props.IntProperty(
        name="Steps",
        default=11,
        min=2,
        description="Number of interpolation samples including endpoints",
    )
    bpy.types.Scene.conform_mode = bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("BCS", "BCS", "Body condition score mode"),
            ("AGE", "Age", "Age mode for day-labeled shape keys"),
        ),
        default="BCS",
        description="Choose whether to use BCS blending or age-based shape key playback",
    )
    bpy.types.Scene.shape_age_slider = bpy.props.FloatProperty(
        name="Age",
        description="Normalized slider (left=young, right=old).",
        default=0.0,
        min=0.0,
        max=1.0,
        precision=3,
        update=update_shape_age_slider,
    )
    bpy.types.Scene.shape_age_step_days = bpy.props.IntProperty(
        name="Age Step (days)",
        default=30,
        min=1,
        description="Step interval in days across the full age range",
    )
    bpy.types.Scene.conform_output_dir = bpy.props.StringProperty(
        name="Output Directory",
        subtype="DIR_PATH",
        default="//conform/",
    )
    bpy.types.Scene.conform_ortho_padding = bpy.props.FloatProperty(
        name="Ortho Padding",
        default=2,
        min=1.0,
        soft_max=10.0,
        description="Orthographic framing scale multiplier",
    )
    bpy.types.Scene.conform_save_images = bpy.props.BoolProperty(
        name="Include Silhouette Images",
        default=True,
        description="Include rendered silhouette images in the export",
    )
    bpy.types.Scene.conform_export_obj = bpy.props.BoolProperty(
        name="Include .obj per Step",
        default=False,
        description="Include a .obj file for the mesh at each interpolation step",
    )
    bpy.types.Scene.conform_include_bbox = bpy.props.BoolProperty(
        name="Include Object Dimensions",
        default=True,
        description="Include width, height, and length columns in CSV output",
    )
    bpy.types.Scene.conform_export_figures = bpy.props.BoolProperty(
        name="Include Figures",
        default=True,
        description="Generate SVG line plots from exported measurements",
    )
    bpy.types.Scene.conform_lateral_camera = bpy.props.PointerProperty(
        name="Lateral Camera",
        type=bpy.types.Object,
        poll=camera_poll,
    )
    bpy.types.Scene.conform_dorsal_camera = bpy.props.PointerProperty(
        name="Dorsal Camera",
        type=bpy.types.Object,
        poll=camera_poll,
    )


def unregister():
    scene_props = (
        "conform_target_object",
        "conform_shapekey_sequence",
        "conform_shapekey_sequence_index",
        "conform_steps",
        "conform_mode",
        "shape_age_slider",
        "shape_age_step_days",
        "conform_output_dir",
        "conform_save_images",
        "conform_export_obj",
        "conform_include_bbox",
        "conform_export_figures",
        "conform_ortho_padding",
        "conform_lateral_camera",
        "conform_dorsal_camera",
    )

    for prop_name in scene_props:
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


__all__ = ("register", "unregister")
