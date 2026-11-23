# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####


"""Addon preferences"""

import os
import platform

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import AddonPreferences

from . import paths, ui, utils

preferences_tabs = [
    ("OPTIONS", "选项", ""),
    ("IMPORT", "导入", ""),
    ("EXPORT", "导出", ""),
    ("DEBUG", "调试", ""),
    ("HELP", "故障排除", ""),
]

MACOS_PIXOLOGIC_PATH = "/Users/Shared/Pixologic"
WINDOWS_PIXOLOGIC_PATH = os.path.join(
    os.environ.get("PUBLIC", "C:/Users/Public"), "Pixologic"
).replace("\\", "/")
MACOS_PROJECT_PATH = f"{MACOS_PIXOLOGIC_PATH}/GoZProjects/Default/"
WINDOWS_PROJECT_PATH = f"{WINDOWS_PIXOLOGIC_PATH}/GoZProjects/Default/"


def branch_version_string():
    """当前插件版本字符串（含分支标识），统一从 utils.gob_version() 取。"""

    return utils.gob_version()


class GoB_Preferences(AddonPreferences):
    bl_idname = __package__
    tabs: EnumProperty(name="Tabs", items=preferences_tabs, default="OPTIONS")

    def on_x_axis_remap_change(self, context):
        x_axis = self.remap_x_axis
        if x_axis == self.remap_y_axis:
            if x_axis != "X":
                self.remap_y_axis = "X"
            else:
                self.remap_y_axis = "Y"
        if x_axis == self.remap_z_axis:
            if x_axis != "X":
                self.remap_z_axis = "X"
            else:
                self.remap_z_axis = "Z"
        else:
            pass

    def on_y_axis_remap_change(self, context):
        y_axis = self.remap_y_axis
        if y_axis == self.remap_x_axis:
            if y_axis != "Y":
                self.remap_x_axis = "Y"
            else:
                self.remap_x_axis = "X"
        if y_axis == self.remap_z_axis:
            if y_axis != "Y":
                self.remap_z_axis = "Y"
            else:
                self.remap_z_axis = "Z"
        else:
            pass

    def on_z_axis_remap_change(self, context):
        z_axis = self.remap_z_axis
        if z_axis == self.remap_x_axis:
            if z_axis != "Z":
                self.remap_x_axis = "Z"
            else:
                self.remap_x_axis = "X"
        if z_axis == self.remap_y_axis:
            if z_axis != "Z":
                self.remap_y_axis = "Z"
            else:
                self.remap_y_axis = "Y"
        else:
            pass

    # GLOBAL
    zbrush_exec: StringProperty(
        name="ZBrush 路径",
        description="选择当前系统的 ZBrush 程序。"
        "\n未指定时将使用系统默认的 .zsc 文件关联程序",
        subtype="FILE_PATH",
        default="",
    )

    zbrush_exec_macos: StringProperty(
        name="macOS ZBrush 路径",
        description="选择 macOS 上的 ZBrush 程序",
        subtype="FILE_PATH",
        default="",
    )
    zbrush_exec_windows: StringProperty(
        name="Windows ZBrush 路径",
        description="选择 Windows 上的 ZBrush 可执行文件",
        subtype="FILE_PATH",
        default="",
    )

    show_macos_paths: BoolProperty(
        name="显示 macOS 路径",
        default=False,
        options={"SKIP_SAVE"},
    )
    show_windows_paths: BoolProperty(
        name="显示 Windows 路径",
        default=True,
        options={"SKIP_SAVE"},
    )

    use_pixologic_path: BoolProperty(
        name="查找 Pixologic 版本",
        description="启用时优先搜索 Pixologic 版 ZBrush，而不是 Maxon 版，"
        "\n安装的是 Pixologic 版 ZBrush 时很有用。"
        "\n如果安装的是 Maxon 版 ZBrush，请关闭此选项",
        default=False,
    )  # Default: False

    custom_pixologoc_path: BoolProperty(
        name="自定义 Pixologic 公共路径",
        description="自定义 Pixologic 公共路径，ZBrush 在这里存放 GoZ 配置",
        default=False,
    )  # Default: False

    if platform.system() == "Windows":
        PATH_GOZ = os.path.join(os.environ["PUBLIC"], "Pixologic")
    elif platform.system() == "Darwin":  # osx
        PATH_GOZ = os.path.join("/", "Users", "Shared", "Pixologic")
    else:
        PATH_GOZ = False

    pixologoc_path: StringProperty(
        name="Pixologic 公共路径",
        description="设置 Pixologic 公共路径，必须是 ZBrush 可访问的有效文件夹。"
        "默认位于系统盘 C:\\Users\\Public\\Pixologic",
        subtype="DIR_PATH",
        default=PATH_GOZ,
    )  # Default: PATH_GOZ

    pixologoc_path_macos: StringProperty(
        name="macOS Pixologic 公共路径",
        description="macOS 上 ZBrush 使用的 Pixologic 公共文件夹",
        subtype="DIR_PATH",
        default=MACOS_PIXOLOGIC_PATH,
    )
    pixologoc_path_windows: StringProperty(
        name="Windows Pixologic 公共路径",
        description="Windows 上 ZBrush 使用的 Pixologic 公共文件夹",
        subtype="DIR_PATH",
        default=WINDOWS_PIXOLOGIC_PATH,
    )

    project_path: StringProperty(
        name="项目路径",
        description="ZBrush 与 Blender 存放导出内容的文件夹",
        subtype="DIR_PATH",
        default=os.path.join(paths.PATH_GOZ, "GoZProjects", "Default/").replace(
            "\\", "/"
        ),
    )

    project_path_macos: StringProperty(
        name="macOS 项目路径",
        description="macOS 上 ZBrush 与 Blender 交换文件的文件夹",
        subtype="DIR_PATH",
        default=MACOS_PROJECT_PATH,
    )
    project_path_windows: StringProperty(
        name="Windows 项目路径",
        description="Windows 上 ZBrush 与 Blender 交换文件的文件夹",
        subtype="DIR_PATH",
        default=WINDOWS_PROJECT_PATH,
    )

    clean_project_path: BoolProperty(
        name="清理项目文件",
        description="导出前清空项目路径中的中转文件，保持 GoZ 桥接干净、少占 SSD",
        default=False,
    )  # Default: False

    use_scale: EnumProperty(
        name="缩放",
        description="选择 Blender 与 ZBrush 之间的缩放换算方式",
        items=[
            ("MANUAL", "手动", "使用手动因子缩放"),
            (
                "BUNITS",
                "Blender 单位",
                "按 Blender 的单位缩放换算",
            ),
            ("ZUNITS", "ZBrush 单位", "把单个对象缩放到 ZBrush 单位"),
        ],
        default="BUNITS",
    )  # Default: BUNITS
    zbrush_scale: FloatProperty(
        name="ZBrush 缩放",
        description="目标 ZBrush 缩放",
        default=2.0,
        soft_min=0.01,
        min=0.000001,
        soft_max=10,
        step=0.01,
        precision=2,
        subtype="FACTOR",
    )
    manual_scale: FloatProperty(
        name="缩放因子",
        description="在 ZBrush 中改变缩放",
        default=1.0,
        soft_min=0.01,
        min=0.000001,
        soft_max=10,
        step=0.01,
        precision=2,
        subtype="FACTOR",
    )
    flip_x_axis: BoolProperty(
        name="翻转 X 轴",
        description="翻转 X 轴（在重映射之前）",
        default=False,
    )  # Default: False
    flip_y_axis: BoolProperty(
        name="翻转 Y 轴",
        description="翻转 Y 轴（在重映射之前）",
        default=False,
    )  # Default: False
    flip_z_axis: BoolProperty(
        name="翻转 Z 轴",
        description="翻转 Z 轴（在重映射之前）",
        default=False,
    )  # Default: False

    # Axis Remapping
    remap_x_axis: EnumProperty(
        name="重映射 X 轴",
        description="把 X 轴重映射到其他轴",
        items=[
            ("X", "X", "保持 X 为 X"),
            ("Y", "Y", "把 X 映射到 Y"),
            ("Z", "Z", "把 X 映射到 Z"),
        ],
        default="X",
        update=on_x_axis_remap_change
    )  # Default: X

    remap_y_axis: EnumProperty(
        name="重映射 Y 轴",
        description="把 Y 轴重映射到其他轴",
        items=[
            ("X", "X", "把 Y 映射到 X"),
            ("Y", "Y", "保持 Y 为 Y"),
            ("Z", "Z", "把 Y 映射到 Z"),
        ],
        default="Y",
        update=on_y_axis_remap_change
    )  # Default: Y

    remap_z_axis: EnumProperty(
        name="重映射 Z 轴",
        description="把 Z 轴重映射到其他轴",
        items=[
            ("X", "X", "把 Z 映射到 X"),
            ("Y", "Y", "把 Z 映射到 Y"),
            ("Z", "Z", "保持 Z 为 Z"),
        ],
        default="Z",
        update=on_z_axis_remap_change
    )  # Default: Z
    show_button_text: BoolProperty(
        name="显示按钮文本",
        description="在导入/导出按钮上显示文字",
        default=True,
    )  # Default: True
    flat_icons: BoolProperty(
        name="使用扁平图标", description="使用不带颜色的扁平图标", default=True
    )  # Default: True

    export_uv_flip_x: BoolProperty(
        name="UV 翻转 X", default=False
    )  # Default: False
    export_uv_flip_y: BoolProperty(name="UV 翻转 Y", default=True)  # Default: True

    """
    texture_format: EnumProperty(
        name="Image Format",
        description=" Output image format",
        items=[ ('TIFF', '.tif', ' Output image in TIFF format'),
                ('BMP', '.bmp', ' Output image in BMP format'),
                ('JPEG', '.jpg', ' Output image in JPEG format'),
                ('PNG', '.png', ' Output image in PNG format'),
               ],
        default='BMP')  # Default: BMP           """

    # EXPORT
    export_modifiers: EnumProperty(
        name="修改器",
        description="修改器处理方式",
        items=[
            (
                "APPLY_EXPORT",
                "导出并应用",
                "在 Blender 中应用修改器后导出到 ZBrush",
            ),
            (
                "ONLY_EXPORT",
                "仅导出",
                "把修改器结果导出到 ZBrush，但不在 Blender 中应用",
            ),
            ("IGNORE", "忽略", "不导出修改器"),
        ],
        default="ONLY_EXPORT",
    )  # Default: ONLY_EXPORT

    export_polygroups: EnumProperty(
        name="多边形组",
        description="创建多边形组",
        items=[
            ("FACE_SETS", "来自面集", "从面集创建多边形组"),
            ("MATERIALS", "来自材质", "从材质创建多边形组"),
            (
                "VERTEX_GROUPS",
                "来自顶点组",
                "从顶点组创建多边形组",
            ),
            ("NONE", "无", "不创建多边形组"),
        ],
        default="FACE_SETS",
    )  # Default: FACE_SETS

    export_weight_threshold: FloatProperty(
        name="权重阈值",
        description="只有高于阈值的顶点权重才会转换为多边形组",
        default=0.1,
        soft_min=0.01,
        min=0,
        max=1.0,
        step=0.01,
        precision=2,
        subtype="FACTOR",
    )

    export_mask: EnumProperty(
        name="蒙版",
        description="蒙版导出方式",
        items=[
            (
                "SCULPT_MASK",
                "来自雕刻模式蒙版",
                "使用雕刻模式的蒙版",
            ),
            ("VERTEX_GROUP_MASK", "来自顶点组", "使用顶点组作为蒙版"),
            ("NONE", "无", "不导出蒙版"),
        ],
        default="SCULPT_MASK",
    )

    export_remove_internal_faces: BoolProperty(
        name="删除内部面",
        description="删除所有边都被 2 个以上面使用的内部面",
        default=True,
    )  # Default: True

    export_merge: BoolProperty(
        name="合并曲线、曲面、文字与元对象顶点",
        description="合并 SURFACE、CURVE、FONT、META 类型对象中距离在阈值内的顶点",
        default=False,
    )  # Default: False

    export_merge_distance: FloatProperty(
        name="顶点合并阈值",
        description="顶点合并阈值",
        default=0.0001,
        min=0,
        soft_min=0.0001,
        soft_max=0.01,
        step=0.0001,
        precision=4,
        subtype="DISTANCE",
    )

    export_run_zbrush: BoolProperty(
        name="运行 ZBrush",
        description="从 Blender 导出后启动 ZBrush",
        default=True,
    )  # Default:True

    # IMPORT
    import_timer: FloatProperty(
        name="更新间隔",
        description="检测 GoZ_ObjectList.txt 变化的时间间隔（秒）",
        default=0.5,
        min=0.1,
        soft_max=2.0,
        step=0.1,
        precision=2,
        subtype="FACTOR",
    )

    import_material: EnumProperty(
        name="材质",
        description="材质创建方式",
        items=[
            ("TEXTURES", "来自纹理", "从纹理创建材质输入"),
            ("POLYPAINT", "来自多边形绘制", "从多边形绘制创建材质"),
            ("POLYGROUPS", "来自多边形组", "从多边形组创建材质"),
            ("NONE", "无", "不创建额外的材质输入"),
        ],
        default="POLYPAINT",
    )  # Default: POLYPAINT

    import_method: EnumProperty(
        name="导入按钮方式",
        description="手动模式：每次从 ZBrush 发送模型后都要按一次导入按钮",
        items=[
            (
                "MANUAL",
                "手动",
                "手动模式：每次从 ZBrush 发送模型后都要按一次导入按钮",
            ),
            ("AUTOMATIC", "自动", "自动模式"),
        ],
        default="AUTOMATIC",
    )  # Default: AUTOMATIC

    import_mask: BoolProperty(
        name="蒙版", description="把蒙版导入为顶点组", default=True
    )  # Default: True

    import_uv: BoolProperty(
        name="UV 贴图", description="从 ZBrush 导入 UV 贴图", default=True
    )  # Default: True
    import_uv_name: StringProperty(
        name="UV 贴图", description="设置 UV 贴图名称", default="UVMap"
    )  # Default: UVMap

    import_uv_flip_x: BoolProperty(
        name="UV 翻转 X", default=False
    )  # Default: False
    import_uv_flip_y: BoolProperty(name="UV 翻转 Y", default=True)  # Default: True

    import_subdiv: BoolProperty(
        name="细分", description="导入细分级别", default=True
    )  # Default: True

    import_polypaint: BoolProperty(
        name="多边形绘制", description="把多边形绘制导入为顶点颜色", default=True
    )  # Default: True
    import_polypaint_name: StringProperty(
        name="顶点颜色",
        description="设置顶点颜色图层名称",
        default="Col",
    )  # Default: Col

    import_polygroups: BoolProperty(
        name="多边形组", description="导入多边形组数据", default=True
    )  # Default: True
    import_polygroups_to_vertexgroups: BoolProperty(
        name="多边形组转顶点组",
        description="把多边形组导入为顶点组",
        default=False,
    )  # Default: False
    import_polygroups_to_facesets: BoolProperty(
        name="多边形组转面集",
        description="把多边形组导入为面集",
        default=True,
    )  # Default: True

    import_diffuse_suffix: StringProperty(
        name="基础颜色", description="设置基础颜色贴图后缀", default="_diff"
    )  # Default: _diff
    import_diffuse_colorspace: EnumProperty(
        name="",
        description="diffuse_colorspace",
        items=[
            (item.identifier, item.name, item.description)
            for item in bpy.types.ColorManagedInputColorspaceSettings.bl_rna.properties[
                "name"
            ].enum_items
        ],
        default="sRGB",
    )  # Default: sRGB

    import_displace_suffix: StringProperty(
        name="置换贴图",
        description="设置置换贴图后缀",
        default="_disp",
    )  # Default: _disp

    import_displace_colorspace: EnumProperty(
        name="",
        description="displace_colorspace",
        items=[
            (item.identifier, item.name, item.description)
            for item in bpy.types.ColorManagedInputColorspaceSettings.bl_rna.properties[
                "name"
            ].enum_items
        ],
        default="Linear Rec.709",
    )  # Default: Linear

    import_normal_suffix: StringProperty(
        name="法线贴图", description="设置法线贴图后缀", default="_norm"
    )  # Default: _norm

    import_normal_colorspace: EnumProperty(
        name="",
        description="normal_colorspace",
        items=[
            (item.identifier, item.name, item.description)
            for item in bpy.types.ColorManagedInputColorspaceSettings.bl_rna.properties[
                "name"
            ].enum_items
        ],
        default="Non-Color",
    )  # Default: Non-Color

    # DEBUG
    performance_profiling: BoolProperty(
        name="调试：性能分析",
        description="在控制台输出计时信息，启用后会减慢 GoZ 传输速度！",
        default=False,
    )  # Default:False
    debug_output: BoolProperty(
        name="调试：输出",
        description="在控制台输出调试信息，启用后会减慢 GoZ 传输速度！",
        default=False,
    )  # Default:False

    def draw_options(self, box):
        # GoB General Options
        box.use_property_split = True
        box.label(text="GoB 通用选项", icon="PREFERENCES")
        col = box.column(align=False)

        utils.migrate_legacy_zbrush_exec(self)
        utils.migrate_legacy_project_path(self)
        if self.custom_pixologoc_path:
            utils.migrate_legacy_pixologic_path(self)

        paths_box = col.box()
        paths_box.label(text="系统路径", icon="FILE_FOLDER")

        windows_box = paths_box.box()
        windows_header = windows_box.row(align=True)
        windows_header.use_property_split = False
        windows_header.prop(
            self,
            "show_windows_paths",
            text="",
            icon="TRIA_DOWN" if self.show_windows_paths else "TRIA_RIGHT",
            icon_only=True,
            emboss=False,
        )
        windows_header.label(text="Windows", translate=False)
        if self.show_windows_paths:
            windows_col = windows_box.column(align=True)
            windows_col.prop(self, "use_pixologic_path", text="优先使用 Pixologic 安装版")
            windows_col.prop(
                self, "zbrush_exec_windows", text="ZBrush 路径", translate=False
            )
            windows_col.prop(
                self, "project_path_windows", text="项目路径", translate=False
            )
            if self.custom_pixologoc_path:
                windows_col.prop(
                    self,
                    "pixologoc_path_windows",
                    text="Pixologic 公共路径",
                    translate=False,
                )

        macos_box = paths_box.box()
        macos_header = macos_box.row(align=True)
        macos_header.use_property_split = False
        macos_header.prop(
            self,
            "show_macos_paths",
            text="",
            icon="TRIA_DOWN" if self.show_macos_paths else "TRIA_RIGHT",
            icon_only=True,
            emboss=False,
        )
        macos_header.label(text="macOS", translate=False)
        if self.show_macos_paths:
            macos_col = macos_box.column(align=True)
            macos_col.prop(
                self, "zbrush_exec_macos", text="ZBrush 路径", translate=False
            )
            macos_col.prop(
                self, "project_path_macos", text="项目路径", translate=False
            )
            if self.custom_pixologoc_path:
                macos_col.prop(
                    self,
                    "pixologoc_path_macos",
                    text="Pixologic 公共路径",
                    translate=False,
                )

        paths_box.prop(self, "custom_pixologoc_path")
        paths_box.prop(self, "clean_project_path")

        col.separator()
        col.prop(self, "remap_x_axis")
        col.prop(self, "flip_x_axis")
        col.prop(self, "remap_y_axis")
        col.prop(self, "flip_y_axis")
        col.prop(self, "remap_z_axis")
        col.prop(self, "flip_z_axis")
        col.prop(self, "use_scale")
        if self.use_scale == "MANUAL":
            col.prop(self, "manual_scale")
        if self.use_scale == "ZUNITS":
            col.prop(self, "zbrush_scale")
        col.prop(self, "show_button_text")
        col.prop(self, "flat_icons")
        # col.prop(self, 'texture_format')

    def draw_import(self, box):
        # GoB Import Options
        box.use_property_split = True
        # box = layout.box()
        box.label(text="GoB 导入选项", icon="IMPORT")
        col = box.column(align=False)
        # box.prop(self, 'import_method') #TODO: disabled: some bugs when switching import method
        col.prop(self, "import_timer")
        col.prop(self, "import_material")
        col.prop(self, "import_mask")

        uv_row = col.row()
        uv_row.prop(self, "import_uv")
        if self.import_uv:
            uv_row.prop(self, "import_uv_name", text="")
            col.prop(self, "import_uv_flip_x")
            col.prop(self, "import_uv_flip_y")

        pp_row = col.row()
        pp_row.prop(self, "import_polypaint")
        if self.import_polypaint:
            pp_row.prop(self, "import_polypaint_name", text="")

        pg_col = col.column()
        pg_col.prop(self, "import_polygroups_to_vertexgroups")
        pg_col.prop(self, "import_polygroups_to_facesets")

        if self.import_material == "TEXTURES":
            row = box.row(align=True)
            row.prop(self, "import_diffuse_suffix")
            row.prop(self, "import_diffuse_colorspace")
            row = box.row(align=True)
            row.prop(self, "import_normal_suffix")
            row.prop(self, "import_normal_colorspace")
            row = box.row(align=True)
            row.prop(self, "import_displace_suffix")
            row.prop(self, "import_displace_colorspace")

    def draw_export(self, box):
        # GoB Export Options
        box.use_property_split = True
        box.label(text="GoB 导出选项", icon="EXPORT")
        col = box.column(align=False)
        col.prop(self, "export_modifiers")
        col.prop(self, "export_polygroups")
        if self.export_polygroups == "VERTEX_GROUPS":
            col.prop(self, "export_weight_threshold")
        col.prop(self, "export_mask")
        col.prop(self, "export_uv_flip_x")
        col.prop(self, "export_uv_flip_y")

        col.prop(self, "export_merge")
        if self.export_merge:
            col.prop(self, "export_merge_distance")
        col.prop(self, "export_remove_internal_faces")
        col.prop(self, "export_run_zbrush")

    def draw_debug(self, box):
        box.use_property_split = True
        col = box.column(align=True)
        col.prop(self, "performance_profiling")
        col.prop(self, "debug_output")

    def draw_help(self, box):
        # GoB Troubleshooting
        box.use_property_split = True
        # box = layout.box()
        box.label(text="GoB 故障排除", icon="QUESTION")

        if platform.system() == "Windows":
            icons = ui.preview_collections["main"]
            box.operator(
                "gob.install_goz",
                text="安装 GoZ",
                icon_value=icons["GOZ_SEND"].icon_id,
            )

    def draw(self, context):

        layout = self.layout
        # 版本标识：分支版显示为 “4.5.3-Speed”
        version_row = layout.row()
        version_row.alignment = "RIGHT"
        version_row.label(text=f"GoB {branch_version_string()}")
        # TAB BAR
        layout.use_property_split = False
        column = layout.column(align=True)
        row = column.row()
        row.prop(self, "tabs", expand=True)
        box = column.box()
        if self.tabs == "OPTIONS":
            self.draw_options(box)
        elif self.tabs == "EXPORT":
            self.draw_export(box)
        elif self.tabs == "IMPORT":
            self.draw_import(box)
        elif self.tabs == "HELP":
            self.draw_help(box)
        elif self.tabs == "DEBUG":
            self.draw_debug(box)
