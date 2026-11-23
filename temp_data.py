# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

"""中转目录统计与临时文件清理（面板子面板「临时数据管理」）。

GoB 的中转数据全部落在两个位置：

* ``交换目录``（GoZProjects/Default）：Blender 与 ZBrush 互传的 ``.GoZ``、
  纹理 ``.bmp`` 以及 ``.ztn`` 记录，导出越多堆得越大。
* ``GoZBrush`` 目录：ZBrush 自己写回的 ``.GoZ`` 副本与残留的 ``.ztl``。

清理只针对 ``TEMP_SUFFIXES`` 白名单（.goz/.ztl/.ztn/.bmp），
GoZ_*.txt、GoZ_Config.bak、GoZ*.exe 等配置与可执行文件一律不动。
默认还会跳过最近修改过的文件，避免删掉 ZBrush/Blender 正在使用的中转文件。
"""

import os
import time

import bpy
from bpy.props import EnumProperty, IntProperty
from bpy.types import Operator, Panel

from . import utils

# 允许清理的后缀白名单：中转产生的数据文件
TEMP_SUFFIXES = (".goz", ".ztl", ".ztn", ".bmp")

# 清理范围选项
SCOPE_ITEMS = [
    ("BOTH", "交换目录 + GoZBrush", "同时清理两个中转位置"),
    ("EXCHANGE", "仅交换目录", "只清理 GoZProjects/Default 里的中转文件"),
    ("GOZBRUSH", "仅 GoZBrush", "只清理 GoZBrush 里的中转文件"),
]

# 扫描结果缓存：面板每次重绘直接读这里，避免反复扫描磁盘
_scan_cache = {"timestamp": 0.0, "targets": []}


# --------------------------------------------------------------------------- #
# 路径与工具
# --------------------------------------------------------------------------- #


def format_size(num_bytes):
    """把字节数格式化成便于阅读的字符串。"""
    value = float(max(0, num_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.2f} {unit}"
        value /= 1024.0


def get_targets():
    """返回需要统计的两个中转目录：[(标签, 路径), ...]。"""
    targets = []

    try:
        exchange_path = bpy.path.abspath(utils.get_project_path())
    except Exception:
        exchange_path = ""
    targets.append(("交换目录", exchange_path))

    try:
        gozbrush_path = os.path.join(utils.get_pixologic_path(), "GoZBrush")
    except Exception:
        gozbrush_path = ""
    targets.append(("GoZBrush", gozbrush_path))

    return targets


def _scan_target(label, path):
    """统计单个目录的总大小与可清理临时文件大小。"""
    info = {
        "label": label,
        "path": path,
        "exists": bool(path) and os.path.isdir(path),
        "files": 0,
        "bytes": 0,
        "temp_files": 0,
        "temp_bytes": 0,
        "suffixes": {},
        "error": "",
    }
    if not info["exists"]:
        info["error"] = "目录不存在"
        return info

    try:
        entries = list(os.scandir(path))
    except OSError as error:
        info["error"] = str(error)
        return info

    for entry in entries:
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            size = entry.stat().st_size
        except OSError:
            continue

        suffix = os.path.splitext(entry.name)[1].lower()
        info["files"] += 1
        info["bytes"] += size
        info["suffixes"][suffix] = info["suffixes"].get(suffix, 0) + size
        if suffix in TEMP_SUFFIXES:
            info["temp_files"] += 1
            info["temp_bytes"] += size

    return info


def scan_all():
    """扫描全部中转目录，写入缓存并返回结果列表。"""
    targets = [_scan_target(label, path) for label, path in get_targets()]
    _scan_cache["targets"] = targets
    _scan_cache["timestamp"] = time.time()
    return targets


def get_cached_scan():
    return _scan_cache


def _scope_selected(scope, label):
    if scope == "BOTH":
        return True
    if scope == "EXCHANGE":
        return label == "交换目录"
    return label == "GoZBrush"


def clean_all(min_age_hours=1, scope="BOTH"):
    """删除白名单后缀、且修改时间早于 ``min_age_hours`` 的中转文件。

    Returns:
        dict: removed/skipped/freed/errors 统计。
    """
    cutoff = time.time() - max(0.0, float(min_age_hours)) * 3600.0
    result = {"removed": 0, "skipped": 0, "freed": 0, "errors": []}

    for label, path in get_targets():
        if not path or not os.path.isdir(path):
            continue
        if not _scope_selected(scope, label):
            continue

        try:
            entries = list(os.scandir(path))
        except OSError as error:
            result["errors"].append(f"{label}: {error}")
            continue

        for entry in entries:
            suffix = os.path.splitext(entry.name)[1].lower()
            if suffix not in TEMP_SUFFIXES:
                continue
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat()
            except OSError as error:
                result["errors"].append(f"{entry.name}: {error}")
                continue

            # 最近仍可能被 ZBrush/Blender 使用的文件先跳过
            if stat.st_mtime > cutoff:
                result["skipped"] += 1
                continue

            try:
                os.remove(entry.path)
            except OSError as error:
                result["errors"].append(f"{entry.name}: {error}")
                continue

            result["removed"] += 1
            result["freed"] += stat.st_size

    return result


# --------------------------------------------------------------------------- #
# 场景属性
# --------------------------------------------------------------------------- #


def register_properties():
    bpy.types.Scene.gob_temp_min_age = IntProperty(
        name="保留时长",
        description="只清理修改时间早于该时长的临时文件，避免删除正在使用的中转文件",
        default=1,
        min=0,
        soft_max=168,
        subtype="UNSIGNED",
    )
    bpy.types.Scene.gob_temp_scope = EnumProperty(
        name="清理范围",
        description="选择要清理的中转目录",
        items=SCOPE_ITEMS,
        default="BOTH",
    )


def unregister_properties():
    for name in ("gob_temp_min_age", "gob_temp_scope"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)


# --------------------------------------------------------------------------- #
# 操作符
# --------------------------------------------------------------------------- #


class GOB_OT_temp_scan(Operator):
    bl_idname = "gob.temp_scan"
    bl_label = "统计中转目录"
    bl_description = "统计交换目录与 GoZBrush 的占用大小，以及其中可清理的临时文件"

    def execute(self, context):
        targets = scan_all()
        messages = []
        for info in targets:
            if info["error"]:
                messages.append(f"{info['label']}: {info['error']}")
                continue
            messages.append(
                f"{info['label']}: {format_size(info['bytes'])} / "
                f"{info['files']} 个文件，可清理 "
                f"{format_size(info['temp_bytes'])}（{info['temp_files']} 个）"
            )
        for message in messages:
            self.report({"INFO"}, message)
        return {"FINISHED"}


def pending_summary(context):
    """当前清理设置下会被删除的文件数量与总大小（用于确认对话框与自检）。"""
    min_age = getattr(context.scene, "gob_temp_min_age", 1)
    scope = getattr(context.scene, "gob_temp_scope", "BOTH")
    cutoff = time.time() - max(0.0, float(min_age)) * 3600.0

    count = 0
    total = 0
    for label, path in get_targets():
        if not path or not os.path.isdir(path):
            continue
        if not _scope_selected(scope, label):
            continue
        try:
            entries = list(os.scandir(path))
        except OSError:
            continue
        for entry in entries:
            if os.path.splitext(entry.name)[1].lower() not in TEMP_SUFFIXES:
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            if stat.st_mtime <= cutoff:
                count += 1
                total += stat.st_size
    return count, total


class GOB_OT_temp_clean(Operator):
    bl_idname = "gob.temp_clean"
    bl_label = "清理临时文件"
    bl_description = "删除中转目录中的 .GoZ/.ztl/.ztn/.bmp 临时文件（保留配置与可执行文件）"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        count, total = pending_summary(context)
        if not count:
            self.report({"INFO"}, "GoB: 没有符合条件的中转文件需要清理")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        count, total = pending_summary(context)
        layout.label(text=f"将删除 {count} 个文件，释放 {format_size(total)}", icon="TRASH")
        layout.label(text="只删除 .GoZ / .ztl / .ztn / .bmp")
        layout.label(text="GoZ 配置、GoZ_Config.bak 与可执行文件不受影响")

    def execute(self, context):
        min_age = getattr(context.scene, "gob_temp_min_age", 1)
        scope = getattr(context.scene, "gob_temp_scope", "BOTH")
        result = clean_all(min_age_hours=min_age, scope=scope)

        scan_all()

        skipped_note = (
            f"，跳过 {result['skipped']} 个最近修改的文件" if result["skipped"] else ""
        )
        self.report(
            {"INFO"},
            f"GoB: 已删除 {result['removed']} 个文件，释放 "
            f"{format_size(result['freed'])}{skipped_note}",
        )
        for error in result["errors"]:
            self.report({"WARNING"}, f"GoB: {error}")
        return {"FINISHED"}


class GOB_OT_temp_open_folder(Operator):
    bl_idname = "gob.temp_open_folder"
    bl_label = "打开目录"
    bl_description = "在系统文件管理器中打开该中转目录"

    target: EnumProperty(
        name="目录",
        items=[
            ("EXCHANGE", "交换目录", "GoZProjects/Default"),
            ("GOZBRUSH", "GoZBrush", "ZBrush 的 GoZBrush 目录"),
        ],
        default="EXCHANGE",
    )

    def execute(self, context):
        for label, path in get_targets():
            wanted = "交换目录" if self.target == "EXCHANGE" else "GoZBrush"
            if label != wanted:
                continue
            if not path or not os.path.isdir(path):
                self.report({"WARNING"}, f"GoB: 目录不存在：{path}")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=path)
            return {"FINISHED"}
        return {"CANCELLED"}


# --------------------------------------------------------------------------- #
# 子面板
# --------------------------------------------------------------------------- #


class VIEW3D_PT_goB_temp_data(Panel):
    """GoB 面板下的子面板：中转目录统计与临时文件清理"""

    bl_parent_id = "VIEW3D_PT_goB"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GoB"
    bl_label = "临时数据管理"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        cache = get_cached_scan()

        if not cache["timestamp"]:
            layout.label(text="尚未统计中转目录", icon="INFO")
        else:
            box = layout.box()
            for info in cache["targets"]:
                col = box.column(align=True)
                header = col.row()
                header.label(text=info["label"], icon="FILE_FOLDER")
                if info["error"]:
                    col.label(text=f"  {info['error']}", icon="ERROR")
                    continue
                size_row = col.row()
                size_row.label(text=f"  总计 {format_size(info['bytes'])} / {info['files']} 个文件")
                if info["temp_bytes"]:
                    size_row.label(
                        text=f"可清理 {format_size(info['temp_bytes'])}",
                        icon="TRASH",
                    )
                else:
                    size_row.label(text="无临时文件")
                open_row = col.row()
                open_row.operator(
                    "gob.temp_open_folder",
                    text="打开",
                    icon="FILEBROWSER",
                ).target = "EXCHANGE" if info["label"] == "交换目录" else "GOZBRUSH"

            if cache["timestamp"]:
                scanned = time.strftime("%H:%M:%S", time.localtime(cache["timestamp"]))
                layout.label(text=f"统计时间 {scanned}", icon="TIME")

        row = layout.row(align=True)
        row.operator("gob.temp_scan", text="统计大小", icon="FILE_REFRESH")

        clean_box = layout.box()
        clean_box.use_property_split = True
        clean_col = clean_box.column(align=True)
        clean_col.label(text="清理选项：")
        clean_col.prop(scene, "gob_temp_scope", text="范围")
        clean_col.prop(scene, "gob_temp_min_age", text="保留时长（小时）")
        clean_box.operator("gob.temp_clean", text="清理临时文件", icon="TRASH")


classes = (
    GOB_OT_temp_scan,
    GOB_OT_temp_clean,
    GOB_OT_temp_open_folder,
    VIEW3D_PT_goB_temp_data,
)



# 说明：类的注册由包的 __init__ 统一完成（classes 元组），
# 这里只负责场景属性的注册/注销。
