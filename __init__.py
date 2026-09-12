bl_info = {
    "name": "More Nif Input",
    "author": "Codex",
    "version": (0, 5, 0),
    "blender": (5, 0, 0),
    "location": "3D Viewport > Sidebar > MoreNifInput",
    "description": "Batch-import NIF files with selectable grouping modes and cleanup options.",
    "category": "Import-Export",
}

import math
import os
import re

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup


def _library_root(settings):
    if not settings.library_path:
        return ""
    return os.path.abspath(bpy.path.abspath(settings.library_path))


def _find_meshes_dir(mod_dir):
    for candidate in os.listdir(mod_dir):
        candidate_path = os.path.join(mod_dir, candidate)
        if os.path.isdir(candidate_path) and candidate.lower() == "meshes":
            return candidate_path
    return None


def _prefix_of_filename(filename):
    stem = os.path.splitext(filename)[0]
    match = re.match(r"^(.+?)_", stem)
    return (match.group(1) if match else stem).lower()


def _deduplicate_files(files):
    kept = []
    seen_prefixes = set()
    for file_path in files:
        prefix = _prefix_of_filename(os.path.basename(file_path))
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        kept.append(file_path)
    return kept


def _nif_files_under(directory):
    files = []
    for current_root, _dirs, filenames in os.walk(directory):
        for filename in filenames:
            if filename.lower().endswith(".nif"):
                files.append(os.path.join(current_root, filename))
    files.sort(key=lambda path: path.lower())
    return files


def _mod_level_groups(root):
    groups = []
    for mod_name in sorted(os.listdir(root)):
        mod_dir = os.path.join(root, mod_name)
        if not os.path.isdir(mod_dir):
            continue
        meshes_dir = _find_meshes_dir(mod_dir)
        if meshes_dir is None:
            continue

        kept_files = _deduplicate_files(_nif_files_under(meshes_dir))
        if kept_files:
            groups.append(
                {
                    "name": mod_name,
                    "mod_name": mod_name,
                    "relative_path": "",
                    "files": kept_files,
                }
            )
    return groups


def _minimum_layer_groups(root):
    groups = []
    for mod_name in sorted(os.listdir(root)):
        mod_dir = os.path.join(root, mod_name)
        if not os.path.isdir(mod_dir):
            continue
        meshes_dir = _find_meshes_dir(mod_dir)
        if meshes_dir is None:
            continue

        direct_files = sorted(
            os.path.join(meshes_dir, filename)
            for filename in os.listdir(meshes_dir)
            if filename.lower().endswith(".nif")
            and os.path.isfile(os.path.join(meshes_dir, filename))
        )
        kept_direct = _deduplicate_files(direct_files)
        if kept_direct:
            groups.append(
                {
                    "name": mod_name,
                    "mod_name": mod_name,
                    "relative_path": "",
                    "files": kept_direct,
                }
            )

        for current_root, dirs, filenames in os.walk(meshes_dir):
            dirs.sort(key=lambda name: name.lower())
            if os.path.abspath(current_root) == os.path.abspath(meshes_dir):
                continue

            nif_files = sorted(
                os.path.join(current_root, filename)
                for filename in filenames
                if filename.lower().endswith(".nif")
            )
            kept_files = _deduplicate_files(nif_files)
            if not kept_files:
                continue

            relative_dir = os.path.relpath(current_root, meshes_dir)
            relative_parts = [part for part in relative_dir.split(os.sep) if part]
            relative_path = "/".join(relative_parts)
            groups.append(
                {
                    "name": f"{mod_name}/{relative_path}",
                    "mod_name": mod_name,
                    "relative_path": relative_path,
                    "files": kept_files,
                }
            )
    return groups


def scan_library(root, mode):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []
    if mode == "MOD_LEVEL":
        return _mod_level_groups(root)
    return _minimum_layer_groups(root)


def populate_settings(settings, groups):
    settings.groups.clear()
    for group in groups:
        group_item = settings.groups.add()
        group_item.name = group["name"]
        group_item.mod_name = group["mod_name"]
        group_item.relative_path = group["relative_path"]
        for file_path in group["files"]:
            file_item = group_item.files.add()
            file_item.file_path = file_path
            file_item.display_name = os.path.basename(file_path)


def _suggest_grid(group_count):
    if group_count <= 0:
        return 1, 1
    rows = max(1, math.ceil(math.sqrt(group_count)))
    columns = max(1, math.ceil(group_count / rows))
    return rows, columns


def _unique_child_name(parent, preferred):
    if parent.children.find(preferred) == -1:
        return preferred
    suffix = 1
    while parent.children.find(f"{preferred}.{suffix:03d}") != -1:
        suffix += 1
    return f"{preferred}.{suffix:03d}"


def _ensure_child_collection(parent, preferred):
    if parent.children.find(preferred) != -1:
        return parent.children[preferred]
    child = bpy.data.collections.new(_unique_child_name(parent, preferred))
    parent.children.link(child)
    return child


def _ensure_group_collection(base, mod_name, relative_path):
    mod_collection = _ensure_child_collection(base, mod_name)
    current = mod_collection
    if relative_path:
        for component in relative_path.split("/"):
            if not component:
                continue
            current = _ensure_child_collection(current, component)
    return current


def _set_active_layer_collection(name):
    view_layer = bpy.context.view_layer

    def visit(layer_collection):
        if layer_collection.name == name:
            view_layer.active_layer_collection = layer_collection
            return True
        for child in layer_collection.children:
            if visit(child):
                return True
        return False

    return visit(view_layer.layer_collection)


def _ensure_base_collection():
    base = bpy.data.collections.get("Collection")
    if base is None:
        base = bpy.data.collections.new("Collection")
        bpy.context.scene.collection.children.link(base)
    return base


def _transform_group_roots(new_objects, center, scale):
    roots = [
        obj
        for obj in new_objects
        if obj.parent is None or obj.parent not in new_objects
    ]
    if not roots:
        return

    bpy.ops.object.select_all(action="DESELECT")
    for obj in roots:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        obj.location = center
        obj.scale = (scale, scale, scale)


def _english_part(name):
    return "".join(ch for ch in name if ch.isascii() and ch.isalpha()).lower()


def _deduplicate_meshes_by_prefix_and_vertex_count(mesh_objects):
    sorted_meshes = sorted(mesh_objects, key=lambda obj: obj.name)
    index = 0
    while index < len(sorted_meshes):
        group_key = _english_part(sorted_meshes[index].name)
        group = [sorted_meshes[index]]
        cursor = index + 1
        while cursor < len(sorted_meshes):
            candidate = sorted_meshes[cursor]
            if _english_part(candidate.name) != group_key:
                break
            group.append(candidate)
            cursor += 1

        if len(group) > 1:
            vertex_counts = [len(obj.data.vertices) for obj in group]
            if len(set(vertex_counts)) == 1:
                for obj in group[1:]:
                    if obj.name in bpy.data.objects:
                        bpy.data.objects.remove(obj, do_unlink=True)

        index = cursor


def _meshes_with_numbered_suffixes(mesh_objects):
    suffixes = [f".{number:03d}" for number in range(1, 10)]
    return [
        obj
        for obj in mesh_objects
        if any(suffix in obj.name for suffix in suffixes)
    ]


def _delete_all_camera_objects():
    for obj in [obj for obj in bpy.data.objects if obj.type == "CAMERA"]:
        bpy.data.objects.remove(obj, do_unlink=True)


def _clear_all_animation():
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)

    for obj in bpy.data.objects:
        if obj.animation_data is None:
            continue
        for track in list(obj.animation_data.nla_tracks):
            obj.animation_data.nla_tracks.remove(track)
        obj.animation_data_clear()

    for scene in bpy.data.scenes:
        if scene.animation_data is not None:
            scene.animation_data_clear()


def _cleanup_group(group_object_names, settings):
    def remaining():
        return [
            bpy.data.objects[name]
            for name in group_object_names
            if name in bpy.data.objects
        ]

    if settings.remove_armature_empty:
        for obj in [obj for obj in remaining() if obj.type == "MESH"]:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj

            if bpy.ops.object.transform_apply.poll():
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            if obj.parent is not None and bpy.ops.object.parent_clear.poll():
                bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
            obj.modifiers.clear()

        for obj in [obj for obj in remaining() if obj.type in {"EMPTY", "ARMATURE"}]:
            bpy.data.objects.remove(obj, do_unlink=True)

    _delete_all_camera_objects()

    if settings.remove_collision_meshes:
        for obj in [obj for obj in remaining() if obj.type == "MESH"]:
            if len(obj.data.materials) == 0:
                bpy.data.objects.remove(obj, do_unlink=True)

    for obj in [obj for obj in remaining() if obj.type == "MESH" and "3BA" in obj.name]:
        bpy.data.objects.remove(obj, do_unlink=True)

    _deduplicate_meshes_by_prefix_and_vertex_count(
        [obj for obj in remaining() if obj.type == "MESH"]
    )

    bpy.ops.file.pack_all()
    bpy.ops.outliner.orphans_purge(
        do_local_ids=True,
        do_linked_ids=True,
        do_recursive=True,
    )


class MoreNifInputFileItem(PropertyGroup):
    file_path: StringProperty()
    display_name: StringProperty()


class MoreNifInputGroupItem(PropertyGroup):
    name: StringProperty()
    mod_name: StringProperty()
    relative_path: StringProperty()
    files: CollectionProperty(type=MoreNifInputFileItem)


class MoreNifInputSettings(PropertyGroup):
    library_path: StringProperty(
        name="库地址",
        description="NIF 文件库根目录（main）",
        subtype="DIR_PATH",
    )
    mode: EnumProperty(
        name="输出模式",
        items=[
            ("MOD_LEVEL", "按 mod 文件层输出", "每个 mod 的 meshes 内全部 NIF 作为一组"),
            ("MIN_LAYER", "最小文件层输出", "按 meshes 下每个直接包含 NIF 的目录分别成组"),
        ],
        default="MIN_LAYER",
    )
    detected_group_count: IntProperty(
        name="检测到的组数",
        default=0,
        min=0,
    )
    remove_armature_empty: BoolProperty(
        name="移除骨骼和空物体的影响",
        description="应用旋转+缩放，清除父级和修改器，并删除空物体与骨架",
        default=True,
    )
    remove_collision_meshes: BoolProperty(
        name="移除碰撞网格",
        description="删除不含材质的网格体",
        default=True,
    )
    split_secondary_parts: BoolProperty(
        name="拆分次级部件",
        description="将名称含 .001-.009 的网格体向 -Y 方向拆分移动",
        default=True,
    )
    rows: IntProperty(
        name="行数",
        description="导入网格的行数",
        default=2,
        min=1,
    )
    columns: IntProperty(
        name="列数",
        description="导入网格的列数",
        default=2,
        min=1,
    )
    spacing: FloatProperty(
        name="间距",
        description="相邻组之间的间距（米）",
        default=1.0,
        min=0.000001,
        subtype="DISTANCE",
    )
    scale: FloatProperty(
        name="Scale",
        description="导入物体的统一缩放",
        default=0.01,
        min=0.000001,
        precision=6,
    )
    groups: CollectionProperty(type=MoreNifInputGroupItem)


class MoreNifInputOT_detect_count(Operator):
    bl_idname = "morenifinput.detect_count"
    bl_label = "检测数量"
    bl_description = "检测当前模式下 NIF 组数，并填入建议的行列数"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.morenifinput
        root = _library_root(settings)

        if not root:
            self.report({"ERROR"}, "请先填写库地址")
            return {"CANCELLED"}
        if not os.path.isdir(root):
            self.report({"ERROR"}, "库地址无效，请检查路径")
            return {"CANCELLED"}

        groups = scan_library(root, settings.mode)
        settings.detected_group_count = len(groups)
        populate_settings(settings, groups)

        if not groups:
            self.report({"ERROR"}, "库中没有找到 NIF 文件")
            return {"CANCELLED"}

        rows, columns = _suggest_grid(len(groups))
        settings.rows = rows
        settings.columns = columns
        self.report(
            {"INFO"},
            f"检测到 {len(groups)} 组，建议 {rows} 行 x {columns} 列",
        )
        return {"FINISHED"}


class MoreNifInputOT_import(Operator):
    bl_idname = "morenifinput.import_groups"
    bl_label = "开始导入"
    bl_description = "按当前模式和参数批量导入所有 NIF 组"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.morenifinput
        root = _library_root(settings)

        if not root:
            self.report({"ERROR"}, "请先填写库地址")
            return {"CANCELLED"}
        if not os.path.isdir(root):
            self.report({"ERROR"}, "库地址无效，请检查路径")
            return {"CANCELLED"}

        groups = scan_library(root, settings.mode)
        if not groups:
            self.report({"ERROR"}, "库中没有找到 NIF 文件")
            return {"CANCELLED"}
        populate_settings(settings, groups)
        settings.detected_group_count = len(groups)

        if settings.rows < 1 or settings.columns < 1:
            self.report({"ERROR"}, "行数和列数必须为正整数")
            return {"CANCELLED"}
        if settings.spacing <= 0:
            self.report({"ERROR"}, "间距必须大于 0")
            return {"CANCELLED"}
        if settings.scale <= 0:
            self.report({"ERROR"}, "Scale 必须大于 0")
            return {"CANCELLED"}
        if settings.rows * settings.columns < len(groups):
            self.report(
                {"ERROR"},
                f"行列之积({settings.rows} x {settings.columns})小于 NIF 组数({len(groups)})",
            )
            return {"CANCELLED"}

        if not hasattr(bpy.ops.import_scene, "pynifly"):
            self.report({"ERROR"}, "请先安装并启用 io_scene_nifly 插件")
            return {"CANCELLED"}

        base = _ensure_base_collection()
        columns = settings.columns
        spacing = settings.spacing
        scale = settings.scale

        for index, group in enumerate(settings.groups):
            row = index // columns
            column = index % columns
            center = (
                column * spacing,
                (settings.rows - row) * spacing,
                0.0,
            )

            collection = _ensure_group_collection(
                base,
                group.mod_name,
                group.relative_path,
            )
            bpy.context.view_layer.update()

            if not _set_active_layer_collection(collection.name):
                self.report({"ERROR"}, f"无法激活集合：{collection.name}")
                return {"CANCELLED"}

            before = set(bpy.data.objects)
            for file_item in group.files:
                result = bpy.ops.import_scene.pynifly(filepath=file_item.file_path)
                if result != {"FINISHED"}:
                    self.report({"ERROR"}, f"导入失败：{file_item.file_path}")
                    return {"CANCELLED"}
            after = set(bpy.data.objects)

            new_objects = [obj for obj in (after - before)]
            new_object_names = [obj.name for obj in new_objects]
            _transform_group_roots(new_objects, center, scale)
            _cleanup_group(new_object_names, settings)

        if settings.split_secondary_parts:
            numbered_meshes = _meshes_with_numbered_suffixes(
                [obj for obj in bpy.data.objects if obj.type == "MESH"]
            )
            if numbered_meshes:
                bpy.ops.object.select_all(action="DESELECT")
                for obj in numbered_meshes:
                    obj.select_set(True)
                bpy.context.view_layer.objects.active = numbered_meshes[0]

                distance = (settings.rows + 1) * settings.spacing
                if bpy.ops.transform.translate.poll():
                    bpy.ops.transform.translate(value=(0.0, -distance, 0.0))
                else:
                    for obj in numbered_meshes:
                        obj.location.y -= distance

        _clear_all_animation()

        self.report({"INFO"}, "NIF 批量导入完成")
        return {"FINISHED"}


class MoreNifInputPT_panel(Panel):
    bl_label = "More Nif Input"
    bl_idname = "MORENIFINPUT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MoreNifInput"

    def draw(self, context):
        settings = context.scene.morenifinput
        layout = self.layout

        layout.label(text="导入准备")
        layout.prop(settings, "library_path")
        layout.prop(settings, "mode", expand=True)

        row = layout.row(align=True)
        row.operator("morenifinput.detect_count", text="检测数量")
        row.label(text=str(settings.detected_group_count))

        layout.separator()
        layout.label(text="导入设置")
        layout.prop(settings, "remove_armature_empty")
        layout.prop(settings, "remove_collision_meshes")
        layout.prop(settings, "split_secondary_parts")

        box = layout.box()
        box.label(text="网格布局")
        box.prop(settings, "rows")
        box.prop(settings, "columns")
        box.prop(settings, "spacing")
        box.prop(settings, "scale")

        layout.operator("morenifinput.import_groups", text="开始导入")


classes = (
    MoreNifInputFileItem,
    MoreNifInputGroupItem,
    MoreNifInputSettings,
    MoreNifInputOT_detect_count,
    MoreNifInputOT_import,
    MoreNifInputPT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.morenifinput = PointerProperty(type=MoreNifInputSettings)


def unregister():
    if hasattr(bpy.types.Scene, "morenifinput"):
        del bpy.types.Scene.morenifinput
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
