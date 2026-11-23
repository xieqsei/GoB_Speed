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

import bpy
from bpy.types import Operator, Panel
from bpy.app.translations import pgettext_iface as iface_
from . import geometry, utils, gob_import


icons = None
preview_collections = {}


def draw_goz_buttons(self, context):
    """顶栏右侧的导出/导入按钮（上游 4.5.x 的 header 快捷入口，与本地面板并存）。"""

    if context.region.alignment != 'RIGHT':
        return
    layout = self.layout
    row = layout.row(align=True)

    icons = preview_collections["main"]
    if utils.prefs().flat_icons:
        icon_goz_send = 'GOZ_SEND_FLAT'
        icon_goz_disabled = 'GOZ_SYNC_FLAT'
        icon_goz_enabled = 'GOZ_SYNC_FLAT'
    else:
        icon_goz_send = 'GOZ_SEND'
        icon_goz_disabled = 'GOZ_SYNC_DISABLED'
        icon_goz_enabled = 'GOZ_SYNC_ENABLED'

    if utils.prefs().show_button_text:
        row.operator(operator="scene.gob_export_button",
                     text="Export",
                     emboss=True,
                     icon_value=icons[icon_goz_send].icon_id)

        if gob_import.run_background_update:
            row.operator(operator="scene.gob_import",
                         text=iface_("Import", None),
                         emboss=True,
                         depress=True,
                         icon_value=icons[icon_goz_enabled].icon_id).action = 'AUTO'
        else:
            row.operator(operator="scene.gob_import",
                         text=iface_("Import", None),
                         emboss=True,
                         depress=False,
                         icon_value=icons[icon_goz_disabled].icon_id).action = 'AUTO'

        row.operator(operator="scene.gob_import",
                     text="Manual",
                     emboss=True,
                     depress=False,
                     icon='IMPORT').action = 'MANUAL'

    else:
        row.operator(operator="scene.gob_export_button",
                     text="",
                     emboss=True,
                     icon_value=icons[icon_goz_send].icon_id)

        if gob_import.run_background_update:
            row.operator(operator="scene.gob_import",
                         text="",
                         emboss=True,
                         depress=True,
                         icon_value=icons[icon_goz_enabled].icon_id).action = 'AUTO'
        else:
            row.operator(operator="scene.gob_import",
                         text="",
                         emboss=True,
                         depress=False,
                         icon_value=icons[icon_goz_disabled].icon_id).action = 'AUTO'

        row.operator(operator="scene.gob_import",
                     text="",
                     emboss=True,
                     depress=False,
                     icon='IMPORT').action = 'MANUAL'


class VIEW3D_PT_goB(Panel):
    """GoB 操作面板，提供导出/导入到 ZBrush 的快捷按钮"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "GoB"
    bl_label = "GoB"

    def draw(self, context):
        layout = self.layout
        icons = preview_collections["main"]

        if utils.prefs().flat_icons:
            icon_goz_send = 'GOZ_SEND_FLAT'
            icon_goz_disabled = 'GOZ_SYNC_FLAT'
            icon_goz_enabled = 'GOZ_SYNC_FLAT'
        else:
            icon_goz_send = 'GOZ_SEND'
            icon_goz_disabled = 'GOZ_SYNC_DISABLED'
            icon_goz_enabled = 'GOZ_SYNC_ENABLED'

        col = layout.column(align=True)

        # 导出到 ZBrush
        col.operator(operator="scene.gob_export_button",
                     text="Export",
                     emboss=True,
                     icon_value=icons[icon_goz_send].icon_id)

        # 自动导入开关
        if gob_import.run_background_update:
            col.operator(operator="scene.gob_import",
                         text=iface_("Auto", None),
                         emboss=True,
                         depress=True,
                         icon_value=icons[icon_goz_enabled].icon_id).action = 'AUTO'
        else:
            col.operator(operator="scene.gob_import",
                         text=iface_("Auto", None),
                         emboss=True,
                         depress=False,
                         icon_value=icons[icon_goz_disabled].icon_id).action = 'AUTO'

        # 手动导入
        col.operator(operator="scene.gob_import",
                     text="Import",
                     emboss=True,
                     depress=False,
                     icon='IMPORT').action = 'MANUAL'

        # S导入：向量化高速导入（原版导入保持不变）
        col.operator(operator="scene.gob_s_import",
                     text="S导入",
                     emboss=True,
                     depress=False,
                     icon='MOD_DATA_TRANSFER')

        # S导入选项：“隐藏修改器 / 找回细分”均与覆盖无关，任何情况都可用
        box = layout.box()
        box.label(text="s导入选项：")
        opt_col = box.column(align=True)
        opt_col.prop(context.scene, "gob_s_import_overwrite", text="导入覆盖")
        opt_col.prop(context.scene, "gob_s_import_recover_multires", text="找回细分")
        opt_col.prop(context.scene, "gob_s_import_hide_modifiers", text="隐藏修改器")
        

        # 独立命令：对当前选中对象找回 Multires 细分
        layout.operator(operator="scene.gob_s_recover_multires",
                        text="找回细分",
                        icon='MOD_MULTIRES')


class GoB_OT_export_button(Operator):
    bl_idname = "scene.gob_export_button"
    bl_label = "Export to ZBrush"
    bl_description = "将所选对象导出到 ZBrush\n"\
                        "左键：作为子工具\n"\
                        "SHIFT/CTRL/ALT + 左键：作为工具"
    bl_options = {'INTERNAL'}
    
    @classmethod
    def poll(cls, context):              
        return geometry.export_poll(cls, context)
        #return bpy.context.selected_objects

    def invoke(self, context, event):
        as_tool = event.shift or event.ctrl or event.alt
        bpy.ops.scene.gob_export(as_tool=as_tool)
        return {'FINISHED'}
    

class GOB_OT_Popup(Operator):
    bl_label = "GoB: Zbrush Path not found!"
    bl_description ="在指定路径或默认安装目录中查找 ZBrush，"\
                    "如果未找到，则提示用户手动输入路径"
    bl_idname = "gob.search_zbrush"
          
    def draw(self, context):        
        self.layout.label(text='请在插件首选项中设置 ZBrush 路径', icon='COLORSET_01_VEC')
        self.layout.label(text='        在插件首选项中设置 ZBrush 路径')

    def open_addon_prefs(self, context):
        # Open the preferences window and show the add-on settings
        bpy.ops.preferences.addon_show(module=__package__)

    def invoke(self, context, event):       
        wm = context.window_manager
        if bpy.app.version < (4,3,0): 
            font_size_correction = bpy.context.preferences.ui_styles[0].widget_label.points / 10
        else:
            font_size_correction = bpy.context.preferences.ui_styles[0].tooltip.points / 10

        return wm.invoke_props_dialog(self, width = int(200 * font_size_correction))

    def execute(self, context):
        self.open_addon_prefs(context)
        return {'FINISHED'}


def ShowReport(self, message = [], title = "Message Box", icon = 'INFO'):
    def draw(self, context):
        for i in message:
            self.layout.label(text=i)
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


