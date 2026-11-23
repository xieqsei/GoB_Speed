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


import os

import bpy
import bpy.utils.previews

from . import (gob_export,
               gob_import,
               gob_s_import,
               paths,
               preferences,
               temp_data,
               ui)

# 分支版本标识：分支名为 Gob_Speed，版本号 = 上游版本 + "-Speed" 后缀。
# manifest 里的 version 必须是纯 X.Y.Z，分支标识只体现在 bl_info 名称、
# 版本字符串与面板/首选项显示上。
BRANCH_NAME = "Gob_Speed"
BRANCH_TAG = "Speed"
VERSION = (4, 5, 3)
VERSION_STRING = f"{'.'.join(str(part) for part in VERSION)}-{BRANCH_TAG}"

bl_info = {
    "name": "Gob_Speed (GoB 分支版)",
    "description": """GoB (for GoBlender) is an unofficial GoZ-like extension, providing a seamless bridge between ZBrush and Blender.
          Effortlessly transfer your models between ZBrush and Blender with a single click, streamlining your workflow and maximizing efficiency.""",
    "author": "ODe, JoseConseco, Daniel Grauer (kromar), Jamie Phipps (Boozebeard) / Gob_Speed 分支",
    "version": VERSION,
    "blender": (4, 00, 0),
    "location": "In the info header / 3D Viewport > Sidebar > GoB",
    "doc_url": "https://github.com/JoseConseco/GoB/wiki",
    "tracker_url": "https://github.com/JoseConseco/GoB/issues/new",
    "category": "Import-Export",
}


classes = (
    gob_import.GoB_OT_import,
    gob_s_import.GoB_OT_s_import,
    gob_s_import.GoB_OT_s_recover_multires,
    gob_export.GoB_OT_export,
    ui.VIEW3D_PT_goB,
    temp_data.VIEW3D_PT_goB_temp_data,
    temp_data.GOB_OT_temp_scan,
    temp_data.GOB_OT_temp_clean,
    temp_data.GOB_OT_temp_open_folder,
    ui.GoB_OT_export_button,
    ui.GOB_OT_Popup,
    paths.GoB_OT_GoZ_Installer,
    preferences.GoB_Preferences,
)


def _scan_temp_data_on_startup():
    """启动后延迟统计一次中转目录，供子面板直接显示（只读，不删任何文件）。"""
    try:
        temp_data.scan_all()
    except Exception as error:
        print(f"GoB: 中转目录统计失败：{error}")
    return None


def register():
    [bpy.utils.register_class(c) for c in classes]
    gob_s_import.register()
    temp_data.register_properties()

    global icons
    icons = bpy.utils.previews.new()
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    icons.load("GOZ_SEND", os.path.join(icons_dir, "goz_send.png"), "IMAGE")
    icons.load(
        "GOZ_SYNC_ENABLED", os.path.join(icons_dir, "goz_sync_enabled.png"), "IMAGE"
    )
    icons.load(
        "GOZ_SYNC_DISABLED", os.path.join(icons_dir, "goz_sync_disabled.png"), "IMAGE"
    )

    icons.load("GOZ_SEND_FLAT", os.path.join(icons_dir, "goz_send_flat.png"), "IMAGE")
    icons.load("GOZ_SYNC_FLAT", os.path.join(icons_dir, "goz_sync_flat.png"), "IMAGE")

    ui.preview_collections["main"] = icons
    bpy.types.TOPBAR_HT_upper_bar.prepend(ui.draw_goz_buttons)

    if not bpy.app.timers.is_registered(_scan_temp_data_on_startup):
        bpy.app.timers.register(_scan_temp_data_on_startup, first_interval=1.0)


def unregister():

    if bpy.app.timers.is_registered(_scan_temp_data_on_startup):
        bpy.app.timers.unregister(_scan_temp_data_on_startup)

    for preferences.custom_icons in ui.preview_collections.values():
        bpy.utils.previews.remove(icons)
    ui.preview_collections.clear()

    bpy.types.TOPBAR_HT_upper_bar.remove(ui.draw_goz_buttons)

    temp_data.unregister_properties()
    gob_s_import.unregister()
    [bpy.utils.unregister_class(c) for c in classes]

    if bpy.app.timers.is_registered(gob_import.run_import_periodically):
        bpy.app.timers.unregister(gob_import.run_import_periodically)
