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

"""S导入（快速导入）

与原版 gob_import.py 并存的高速 GoZ 导入器：
- 一次性读取整个 .GoZ 文件到内存，使用 numpy.frombuffer 向量化解析
  顶点/面/UV/顶点色/蒙版/多边形组，避免逐元素 struct.unpack 的 Python 循环；
- 使用 vertices/loops/polygons/属性的 foreach_set 批量写入网格数据，
  避免 from_pydata 的 tuple 列表与逐顶点 RNA 写入；
- 蒙版与多边形组按取值分组后批量加入顶点组，避免逐顶点 add 调用。

注意：bpy 数据写入仍必须在主线程完成，因此本模块是"单线程但向量化"的方案，
解析阶段由 numpy/C 层执行，可显著降低主线程占用并大幅缩短导入时间。
原版导入器（scene.gob_import）保持不变。
"""

import os
import time
from struct import unpack_from

import bpy
import numpy as np
from bpy.props import BoolProperty
from bpy.types import Operator

from . import geometry, paths, utils, nodes


# ---------------------------------------------------------------------------
# GoZ 二进制块标识（小端 4 字节标签）
# ---------------------------------------------------------------------------
TAG_NAME = b'\x89\x13\x00\x00'        # 对象名
TAG_SUBDIV = b'\x8a\x13\x00\x00'      # 细分级别（当前不导入，仅跳过）
TAG_VERTS = b'\x11\x27\x00\x00'       # 顶点坐标
TAG_FACES = b'\x21\x4e\x00\x00'       # 面索引
TAG_UVS = b'\xa9\x61\x00\x00'         # UV 坐标
TAG_POLYPAINT = b'\xb9\x88\x00\x00'   # 多边形绘制（顶点色）
TAG_MASK = b'\x32\x75\x00\x00'        # 蒙版
TAG_POLYGROUPS = b'\x41\x9c\x00\x00'  # 多边形组
TAG_END = b'\x00\x00\x00\x00'         # 结束
TAG_DIFF = b'\xc9\xaf\x00\x00'        # 漫反射贴图
TAG_DISP = b'\xd9\xd6\x00\x00'        # 置换贴图
TAG_NORM = b'\x51\xc3\x00\x00'        # 法线贴图


class GoB_OT_s_import(Operator):
    """S导入：基于 numpy 向量化解析的高速 GoZ 导入器"""
    bl_idname = "scene.gob_s_import"
    bl_label = "S导入"
    bl_description = "S导入：使用向量化解析的高速 GoZ 导入（保留原版导入不变）"

    # 操作符自身属性（F3 搜索执行/脚本调用时可用）；
    # 面板复选框勾选后由 ui.py 在调用前从 Scene.gob_s_import_* 同步
    import_overwrite: BoolProperty(
        name="导入覆盖",
        description="勾选：场景中存在同名对象时覆盖当前对象\n"
                    "不勾选：自动添加 .001 等后缀，作为新对象添加到场景",
        default=True,
    )

    hide_modifiers: BoolProperty(
        name="隐藏修改器",
        description="导入时关闭对象全部修改器的视图显示，避免修改器重求值卡顿\n"
                    "（导入后保持隐藏，可在修改器面板手动恢复）\n"
                    "与是否覆盖无关，任何情况下都生效",
        default=False,
    )

    recover_multires: BoolProperty(
        name="找回细分",
        description="导入时对对象已有的多级细分（Multires）修改器执行\n"
                    "“重建细分”找回丢失的较低层级，并把视图层级降为 2 以防卡顿\n"
                    "任何情况下都可用；没有 Multires 修改器则忽略；\n"
                    "是否同时隐藏 Multires 由“隐藏修改器”决定",
        default=False,
    )

    # ------------------------------------------------------------------
    # 找回细分
    # ------------------------------------------------------------------
    @staticmethod
    def recover_object_multires(obj, view_levels=2,
                                create_if_missing=False, keep_visible=False):
        """对对象找回多级细分并降低视图层级。

        “重建细分”的官方语义（关键）：在一个 *还没有任何细分级别的*
        Multires 修改器上，依据当前网格（高模）反推出尽可能多的较低
        细分级别。因此只有 ``total_levels == 0`` 时才能执行重建；
        已经有细分级别时该操作会报“找不到有效细分”，直接跳过。

        Args:
            obj (bpy.types.Object): 目标网格对象。
            view_levels (int): 找回后设置的视图显示层级，默认 2。
            create_if_missing (bool): 没有 Multires 时是否新建一个空
                修改器再重建。导入流程与独立命令都需要（True），这样
                GoZ 覆盖进来的高模才能反推出低级别。
            keep_visible (bool): 是否保留修改器原有视图显示状态。
                导入流程按“隐藏修改器”决定；独立命令保持显示（True）。

        Returns:
            int: 成功重建或降层的 Multires 修改器数量。
        """
        if obj is None or obj.type != 'MESH':
            return 0

        multires = next((m for m in obj.modifiers if m.type == 'MULTIRES'), None)
        if multires is None:
            if not create_if_missing:
                return 0
            multires = obj.modifiers.new(name='Multires', type='MULTIRES')

        view_layer = bpy.context.view_layer
        # rebuild 是需要“活动对象 + OBJECT 模式”的轮询操作符
        prev_active = view_layer.objects.active
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        obj.select_set(True)
        view_layer.objects.active = obj

        handled = 0
        for mod in obj.modifiers:
            if mod.type != 'MULTIRES':
                continue
            obj.modifiers.active = mod
            if not keep_visible:
                # 隐藏视图显示，避免重建/写层级时视口对高细分求值造成卡顿
                mod.show_viewport = False

            # 仅当尚无细分级别时，依据当前高模重建较低级别；
            # 已有级别时重建会安全报错，忽略即可
            if mod.total_levels == 0:
                try:
                    bpy.ops.object.multires_rebuild_subdiv(modifier=mod.name)
                except RuntimeError:
                    pass

            # 视图层级降为 view_levels，防止开启显示时直接上最高级导致卡顿
            if mod.total_levels >= view_levels:
                mod.levels = view_levels
                handled += 1

        view_layer.objects.active = prev_active
        return handled

    # ------------------------------------------------------------------
    # 命名
    # ------------------------------------------------------------------
    @staticmethod
    def _unique_object_name(base_name):
        """场景中已存在同名对象时，生成 .001 / .002 ... 形式的唯一名。

        Args:
            base_name (str): 文件内部对象名。

        Returns:
            str: 场景中不与现有对象冲突的名称。
        """
        if bpy.data.objects.get(base_name) is None:
            return base_name
        index = 1
        while bpy.data.objects.get(f"{base_name}.{index:03d}") is not None:
            index += 1
        return f"{base_name}.{index:03d}"

    # ------------------------------------------------------------------
    # 面合法性过滤
    # ------------------------------------------------------------------
    @staticmethod
    def _valid_face_mask(face_idx, num_verts):
        """标记可成面的面：槽位内无重复顶点（非退化）且索引不越界。

        规则与原版 from_pydata 丢弃面的行为一致：
        - 三角形第 4 分量为 0xFFFFFFFF，需先还原为槽位表示再比较；
        - 第 4 索引为 0 的四边形按原版规则重排为 (v4, v1, v2, v3)。

        Args:
            face_idx (np.ndarray): 形状 (F, 4) 的 uint32 原始面索引。
            num_verts (int): 顶点总数，用于越界判断。

        Returns:
            np.ndarray: 形状 (F,) 的布尔数组，True 表示该面有效。
        """
        tri_mask = face_idx[:, 3] == 0xFFFFFFFF
        slots = face_idx.astype(np.int64, copy=True)
        slots[tri_mask, 3] = slots[tri_mask, 0]
        zero_w = (~tri_mask) & (face_idx[:, 3] == 0)
        if zero_w.any():
            slots[zero_w] = slots[zero_w][:, (3, 0, 1, 2)]

        in_range = (slots >= 0).all(axis=1) & (slots < num_verts).all(axis=1)

        # 逐对比较 4 个槽位是否有重复顶点
        dup = np.zeros(len(slots), dtype=bool)
        for i in range(4):
            for j in range(i + 1, 4):
                dup |= slots[:, i] == slots[:, j]
        # 三角形的第 4 槽位是第 1 槽位的填充副本，不参与重复判定
        dup &= ~tri_mask
        # 三角形自身前 3 个顶点仍需检查重复
        for i in range(3):
            for j in range(i + 1, 3):
                dup |= tri_mask & (slots[:, i] == slots[:, j])

        return in_range & ~dup

    # ------------------------------------------------------------------
    # 网格构建
    # ------------------------------------------------------------------
    def _make_mesh(self, obj_name, verts, face_idx, overwrite=True,
                   hide_modifiers=False, validate=True):
        """使用 foreach_set 批量创建或更新网格。

        Args:
            obj_name (str): 文件内部对象名。
            verts (np.ndarray | None): 顶点坐标，形状 (N, 3)，float32。
            face_idx (np.ndarray | None): 面索引，形状 (F, 4)，uint32，
                三角形第 4 分量为 0xFFFFFFFF，四边形第 1 分量为 0。
            overwrite (bool): True 时覆盖场景中的同名对象；
                False 时自动加后缀创建新对象。
            hide_modifiers (bool): 写入前关闭已有对象全部修改器的视图
                显示。与是否覆盖无关，任何情况下都生效（新建对象此时
                尚无修改器，实际作用于其后续找回细分新建的 Multires）。
            validate (bool): 是否在本方法内执行 me.validate()。
                S导入传 False，把校验推迟到 UV/顶点色/蒙版/多边形组等
                逐面属性写入之后（否则被删掉的面会让面序号错位）。

        Returns:
            tuple: (对象, 网格数据, 三角形掩码, 是否为覆盖已有对象)。
        """
        if not overwrite:
            # 不覆盖：解析出唯一名，作为全新对象添加到场景
            obj_name = self._unique_object_name(obj_name)

        obj = bpy.data.objects.get(obj_name)
        reused = obj is not None
        if obj:
            # 覆盖已有对象：写入新几何前先关闭修改器视图显示，
            # 避免覆盖瞬间旧修改器重求值卡顿（保持隐藏，由用户手动恢复）。
            # 找回细分不能在此执行——必须等新的最高级几何写入后再重建。
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj

            if hide_modifiers:
                for mod in obj.modifiers:
                    mod.show_viewport = False

            me = obj.data
        else:
            me = bpy.data.meshes.new(obj_name)
            obj = bpy.data.objects.new(obj_name, me)
            layer_collection = bpy.context.view_layer.active_layer_collection
            if layer_collection:
                layer_collection.collection.objects.link(obj)
            else:
                print("错误：活动层集合无效，对象无法链接到场景")
            # 新建对象没有任何修改器，找回细分自然无 Multires 可处理

        # 后续变换依赖活动对象（ZUNITS 缩放等），先选中并激活
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        # 清空旧几何（保留对象本身，便于从 ZBrush 重复发送时更新）
        me.clear_geometry()

        num_verts = len(verts) if verts is not None else 0
        num_faces = len(face_idx) if face_idx is not None else 0
        # 无面时也要返回合法的三角形掩码，供 UV 应用阶段使用
        tri_mask = np.zeros(num_faces, dtype=bool)

        if num_verts:
            # 批量写入顶点坐标
            me.vertices.add(num_verts)
            me.vertices.foreach_set("co", verts.astype(np.float32, copy=False).ravel())

        if num_faces:
            # 判断三角形：第 4 个索引为 0xFFFFFFFF（与原版规则一致）
            tri_mask = face_idx[:, 3] == 0xFFFFFFFF

            # 统一转为四边形槽位（(F,4)），三角形占用前 3 个槽位；
            # 原版规则：当第 4 索引为 0 时四边形面为 (v4, v1, v2, v3)
            slots = face_idx.astype(np.int64, copy=True)
            slots[tri_mask, 3] = slots[tri_mask, 0]
            zero_w = (~tri_mask) & (face_idx[:, 3] == 0)
            if zero_w.any():
                slots[zero_w] = slots[zero_w][:, (3, 0, 1, 2)]
            slots = slots.astype(np.int32)

            # 多边形槽位保持原始面顺序，每面 loop 连续存放，
            # loop_start 按面循环数（三角形 3 / 四边形 4）前缀累加
            loop_counts = np.where(tri_mask, 3, 4).astype(np.int32)
            loop_total = int(loop_counts.sum())
            poly_loop_start = np.zeros(num_faces, dtype=np.int32)
            np.cumsum(loop_counts[:-1], out=poly_loop_start[1:])

            # 按槽位顺序展开逐 loop 顶点索引：三角形丢弃第 4 个填充槽位
            keep = np.ones((num_faces, 4), dtype=bool)
            keep[tri_mask, 3] = False
            loop_verts = slots[keep]

            me.loops.add(loop_total)
            me.loops.foreach_set("vertex_index", loop_verts)
            me.polygons.add(num_faces)
            # loop_total 为只读派生属性，按面顺序连续存放时由 loop_start 自动推导
            me.polygons.foreach_set("loop_start", poly_loop_start)

        # 更新边、法线等派生数据
        if bpy.app.version >= (4, 0, 0):
            me.update()
        else:  # 兼容旧版本签名
            me.update(calc_edges=True, calc_edges_loose=True)

        # 应用导入变换（轴向、缩放），与原版保持一致
        me, _ = geometry.apply_transformation(me, is_import=True)
        me.transform(obj.matrix_world.inverted())
        if validate:
            me.validate(verbose=utils.prefs().debug_output)

        bpy.context.view_layer.update()
        return obj, me, tri_mask, reused

    # ------------------------------------------------------------------
    # UV
    # ------------------------------------------------------------------
    def _apply_uvs(self, me, uv_raw, tri_mask):
        """将每面 4 组 UV 批量写入 UV 层。

        Args:
            me (bpy.types.Mesh): 网格数据。
            uv_raw (np.ndarray): 形状 (F, 4, 2) 的 float32 UV（原始 u/v）。
            tri_mask (np.ndarray): 形状 (F,) 的布尔数组，标记三角形面。
        """
        prefs = utils.prefs()
        num_faces = uv_raw.shape[0]
        flip_x = prefs.import_uv_flip_x
        flip_y = prefs.import_uv_flip_y

        # 尽量零拷贝：
        # - 含三角形时 boolean 索引本身会生成一份连续副本，直接在该副本上翻转；
        # - 纯四边网格（最常见）直接 reshape 成视图，仅在需要翻转时才拷贝。
        if tri_mask.any():
            # 三角形面丢弃第 4 组 UV，与构建 loop 时的槽位规则一致
            keep = np.ones((num_faces, 4), dtype=bool)
            keep[tri_mask, 3] = False
            loop_uv = uv_raw[keep].reshape(-1, 2)
            if flip_x:
                loop_uv[:, 0] = 1.0 - loop_uv[:, 0]
            if flip_y:
                loop_uv[:, 1] = 1.0 - loop_uv[:, 1]
        else:
            loop_uv = uv_raw.reshape(-1, 2)
            if flip_x or flip_y:
                loop_uv = loop_uv.copy()
                if flip_x:
                    loop_uv[:, 0] = 1.0 - loop_uv[:, 0]
                if flip_y:
                    loop_uv[:, 1] = 1.0 - loop_uv[:, 1]

        uv_layers = me.uv_layers
        if prefs.import_uv_name in uv_layers:
            uv_layers.active = uv_layers[prefs.import_uv_name]
        else:
            uv_layers.new(name=prefs.import_uv_name)

        # 防御：UV 组数必须与网格 loop 数严格一致，否则 foreach_set 会
        # 报 “internal error setting the array”。不一致时按较小长度对齐。
        total_loops = len(me.loops)
        loop_uv = np.ascontiguousarray(loop_uv).reshape(-1, 2)
        if loop_uv.shape[0] != total_loops:
            if prefs.debug_output:
                print(f"S导入：UV 数（{loop_uv.shape[0]}）与 loop 数（{total_loops}）不一致，已对齐")
            fixed = np.zeros((total_loops, 2), dtype=np.float32)
            n = min(total_loops, loop_uv.shape[0])
            fixed[:n] = loop_uv[:n]
            loop_uv = fixed

        uv_layers.active.data.foreach_set("uv", loop_uv.ravel())

    # ------------------------------------------------------------------
    # 顶点色（多边形绘制）
    # ------------------------------------------------------------------
    def _apply_polypaint(self, me, pp_raw):
        """将 BGRA 字节流批量转换为 RGBA 浮点顶点色。

        Args:
            me (bpy.types.Mesh): 网格数据。
            pp_raw (np.ndarray): 形状 (N, 4) 的 uint8（B,G,R,A）。
        """
        prefs = utils.prefs()
        rgba = np.empty((pp_raw.shape[0], 4), dtype=np.float32)
        # GoZ 字节序为 B,G,R,A，翻转为 R,G,B；Alpha 固定为 1
        rgba[:, 0] = pp_raw[:, 2] / 255.0
        rgba[:, 1] = pp_raw[:, 1] / 255.0
        rgba[:, 2] = pp_raw[:, 0] / 255.0
        rgba[:, 3] = 1.0

        if prefs.import_polypaint_name not in me.color_attributes:
            me.color_attributes.new(prefs.import_polypaint_name, 'BYTE_COLOR', 'POINT')
        color_data = me.color_attributes[prefs.import_polypaint_name].data

        # 注意：属性集合切片会返回 Python list（无 foreach_set），
        # 因此直接对整个属性集合批量写入；长度不一致时截断颜色数组
        count = min(len(rgba), len(color_data))
        if count == len(color_data):
            color_data.foreach_set("color_srgb", rgba[:count].ravel())
        elif count:
            # 顶点多于颜色属性时回退为逐点写入（正常不会发生）
            for i in range(count):
                color_data[i].color_srgb = rgba[i]

    # ------------------------------------------------------------------
    # 蒙版 -> 顶点组
    # ------------------------------------------------------------------
    def _apply_mask(self, obj, mask_raw):
        """将 uint16 蒙版权重按取值分组批量写入名为 mask 的顶点组。

        Args:
            obj (bpy.types.Object): 目标对象。
            mask_raw (np.ndarray): 形状 (N,) 的 uint16 蒙版权重。
        """
        old = obj.vertex_groups.get('mask')
        if old:
            obj.vertex_groups.remove(old)
        group = obj.vertex_groups.new(name='mask')

        # 防御：蒙版数量应与顶点数一致，多出的部分直接忽略
        num_verts = min(len(mask_raw), len(obj.data.vertices))
        # 快速路径：蒙版数据全 0（ZBrush 未绘制蒙版，最常见），
        # 所有权重均为 1，一次 add 即可，省去 argsort 与分组开销
        if not np.any(mask_raw):
            group.add(list(range(num_verts)), 1.0, 'REPLACE')
            return

        weights = 1.0 - mask_raw[:num_verts].astype(np.float32) / 65535.0

        # 按权重排序后分组，一次性 add 相同权重的所有顶点，
        # 将逐顶点调用降为"不同权重数量"次调用
        order = np.argsort(weights, kind='stable')
        sorted_w = weights[order]
        boundaries = np.flatnonzero(np.diff(sorted_w)) + 1
        for start, end in zip(np.r_[0, boundaries], np.r_[boundaries, len(sorted_w)]):
            value = float(sorted_w[start])
            indices = order[start:end].astype(np.int32).tolist()
            if indices:
                group.add(indices, value, 'REPLACE')

    # ------------------------------------------------------------------
    # 多边形组
    # ------------------------------------------------------------------
    def _apply_polygroups(self, obj, me, pg_raw):
        """将 uint16 多边形组数据写入材质/顶点组/面集。

        Args:
            obj (bpy.types.Object): 目标对象。
            me (bpy.types.Mesh): 网格数据。
            pg_raw (np.ndarray): 形状 (F,) 的 uint16 多边形组编号。
        """
        prefs = utils.prefs()
        # 多边形槽位与 .GoZ 面顺序一致（材质索引/面集均按多边形槽位索引）
        pg = pg_raw.astype(np.int32)

        # 防御：面组数量需与网格面数严格一致，否则 foreach_set 报
        # “internal error setting the array”；不一致时按较小长度对齐
        num_polys = len(me.polygons)
        if len(pg) != num_polys:
            if prefs.debug_output:
                print(f"S导入：面组数（{len(pg)}）与网格面数（{num_polys}）不一致，已对齐")
            aligned = np.zeros(num_polys, dtype=np.int32)
            n = min(num_polys, len(pg))
            aligned[:n] = pg[:n]
            pg = aligned

        # 多边形组 -> 材质槽
        if prefs.import_material == 'POLYGROUPS':
            unique_groups = np.unique(pg)
            slot_index = {}
            for g in unique_groups:
                name = str(int(g))
                obj_mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
                nodes.create_base_nodes(obj_mat)
                if name not in obj.material_slots:
                    obj.data.materials.append(obj_mat)
                    obj_mat.use_nodes = True
                    rgba = (np.random.random(), np.random.random(), np.random.random(), 1)
                    obj_mat.diffuse_color = rgba
                    obj_mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value = rgba
                slot_index[int(g)] = obj.material_slots[name].slot_index

            mat_indices = np.fromiter(
                (slot_index[int(g)] for g in pg), dtype=np.int32, count=len(pg))
            me.polygons.foreach_set("material_index", mat_indices)

        # 多边形组 -> 顶点组（按组收集去重顶点后批量加入）
        if prefs.import_polygroups_to_vertexgroups:
            loop_verts = np.empty(len(me.loops), dtype=np.int32)
            me.loops.foreach_get("vertex_index", loop_verts)
            poly_start = np.empty(len(me.polygons), dtype=np.int32)
            me.polygons.foreach_get("loop_start", poly_start)
            poly_total = np.empty(len(me.polygons), dtype=np.int32)
            me.polygons.foreach_get("loop_total", poly_total)

            unique_groups = np.unique(pg)
            for g in unique_groups:
                name = str(int(g))
                group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
                face_indices = np.flatnonzero(pg == g)
                vert_set = set()
                for fi in face_indices:
                    s = int(poly_start[fi])
                    vert_set.update(loop_verts[s:s + int(poly_total[fi])].tolist())
                if vert_set:
                    group.add(list(vert_set), 1.0, 'ADD')

        # 多边形组 -> 雕塑面集
        if prefs.import_polygroups_to_facesets:
            if '.sculpt_face_set' not in obj.data.attributes:
                obj.data.attributes.new('.sculpt_face_set', 'INT', 'FACE')
            obj.data.attributes['.sculpt_face_set'].data.foreach_set('value', pg)

    # ------------------------------------------------------------------
    # 单个 .GoZ 文件解析与导入
    # ------------------------------------------------------------------
    def GoZit(self, path_file, overwrite=True,
              hide_modifiers=False, recover_multires=False):
        """解析并导入单个 .GoZ 文件。

        Args:
            path_file (str): .GoZ 文件绝对路径。
            overwrite (bool): 同名对象是否覆盖当前对象；
                False 时加后缀创建新对象。
            hide_modifiers (bool): 覆盖前隐藏同名对象全部修改器。
            recover_multires (bool): 覆盖前为同名对象找回 Multires 细分。
        """
        prefs = utils.prefs()
        if prefs.performance_profiling:
            start_time = time.perf_counter()
            start_total = start_time

        if not os.path.isfile(path_file):
            if prefs.debug_output:
                print(f'无法读取网格文件：{path_file}，已跳过')
            return

        with open(path_file, 'rb') as f:
            data = f.read()
        buf = np.frombuffer(data, dtype=np.uint8)
        total = len(buf)
        pos = 0

        def tag_at(offset):
            # 标签为 4 字节定长标识，直接切片即可
            return bytes(buf[offset:offset + 4])

        def u32_at(offset):
            return unpack_from('<I', data, offset)[0]

        def arr(start, count, dtype):
            # 对 bytes 切片（生成对齐的新字节对象）后构建数组，
            # 避免 frombuffer 在任意非对齐 offset 上的限制
            return np.frombuffer(data[start:start + count], dtype=dtype)

        # ---- 文件头（36 字节）+ 对象名块 -----------------------------
        # 真实 GoZ 布局（与原版解析器一致）：
        #   offset 36 : u32 名称块总长度（此位置没有 4 字节标签）
        #   offset 40 : 8 字节子头
        #   offset 48 : 名称字节（前 8 字节为 "GoZMesh_" 子标签，需丢弃）
        pos = 36
        if pos + 12 > total:
            print(f"S导入：文件过小，无法解析文件头：{path_file}")
            return
        # 与原版一致：offset36 处直接是 u32 名称长度，随后跳过 8 字节子头
        # （seek(36) 读 len，再 seek(+8) 到 offset48）读取 name_len 字节名称
        name_len = u32_at(pos) - 16
        name_start = pos + 12
        if name_len <= 0 or name_start + name_len > total:
            print(f"S导入：名称块长度异常：{path_file}")
            return
        name_bytes = bytes(buf[name_start:name_start + name_len])
        # 前 8 字节是 "GoZMesh_" 子标签，直接丢弃；
        # 只剔除控制字符与 NUL，保留中文等非 ASCII 字符（原实现用
        # string.printable 过滤，会把中文名整段丢掉，如“中模体型5”→ “5”）
        obj_name = ''.join(c for c in name_bytes[8:].decode('utf-8', 'ignore')
                           if c.isprintable() and c != '\x00')
        if not obj_name:
            obj_name = 'GoZ_Mesh'
        # 名称块结构：4(u32) + 8(子头) + name_len，下一标签紧随其后
        pos = name_start + name_len

        if prefs.debug_output:
            print(f"\nS导入：\n{path_file, obj_name}")

        # 名称块之后紧跟一个 0x1389 名称数据块，直接跳过
        if tag_at(pos) == TAG_NAME:
            name_chunk_len = u32_at(pos + 4) - 8
            pos += 8 + name_chunk_len

        # ---- 解析数据块 ---------------------------------------------
        verts = None
        face_idx = None
        uv_raw = None
        pp_raw = None
        mask_raw = None
        pg_raw = None
        diff_texture = disp_texture = norm_texture = None

        # 数据块统一按“块总长度”推进，而不是依赖 +8 处的计数字段：
        #   offset +0: 4 字节块标识
        #   offset +4: 4 字节块总长度（含 16 字节块头，即 16 + 载荷字节数）
        #   offset +8: 计数/标志（不同块、不同 ZBrush 版本宽度不一致）
        #   offset +16: 载荷起点
        # 关键兼容点：ZBrush 2026 写出的 POLYPAINT 块把计数写成 u32，其后
        # 紧跟一个恒为 1.0 的 float32。若仍按 u64 读计数，会得到
        # 0x3F800000_XXXXXXXX 这种天文数字，进而触发
        # “cannot reshape array of size N into shape (4575657221408603884,4)”
        # 的崩溃（普通导入不崩，是因为它读到异常 count 后直接放弃该块）。
        # 因此这里一律由“块总长 - 16”反推载荷长度与元素个数。
        def block_payload(block_pos):
            """返回 (载荷起点, 载荷字节数, 块总长)；块头非法时返回 (None, 0, 0)。"""
            if block_pos + 8 > total:
                return None, 0, 0
            block_len = u32_at(block_pos + 4)
            if block_len < 16 or block_pos + block_len > total:
                return None, 0, block_len
            return block_pos + 16, block_len - 16, block_len

        tag = tag_at(pos)
        while tag and tag != TAG_END:
            if tag == TAG_NAME:
                # 名称数据块（通常在进入循环前已跳过，这里做防御性处理）
                name_chunk_len = u32_at(pos + 4) - 8
                pos += 8 + name_chunk_len

            elif tag in (TAG_VERTS, TAG_FACES, TAG_UVS,
                         TAG_POLYPAINT, TAG_MASK, TAG_POLYGROUPS):
                start, payload, block_len = block_payload(pos)
                if start is None:
                    print(f"S导入：块 {tag!r} 长度异常（{block_len}），终止解析：{path_file}")
                    break

                if tag == TAG_VERTS:
                    count = payload // 12
                    verts = arr(start, count * 12, '<f4').reshape(count, 3)

                elif tag == TAG_FACES:
                    count = payload // 16
                    face_idx = arr(start, count * 16, '<u4').reshape(count, 4)

                elif tag == TAG_UVS:
                    # 保持只读零拷贝视图；翻转/含三角形时由 _apply_uvs 内部按需拷贝
                    if prefs.import_uv:
                        count = payload // 32
                        uv_raw = arr(start, count * 32, '<f4').reshape(count, 4, 2)

                elif tag == TAG_POLYPAINT:
                    if prefs.import_polypaint:
                        count = payload // 4
                        pp_raw = arr(start, count * 4, np.uint8).reshape(count, 4)

                elif tag == TAG_MASK:
                    if prefs.import_mask:
                        count = payload // 2
                        mask_raw = arr(start, count * 2, '<u2')

                else:  # TAG_POLYGROUPS
                    # 该块始终读取（用于材质/顶点组/面集）
                    count = payload // 2
                    pg_raw = arr(start, count * 2, '<u2')

                pos += block_len

            elif tag == TAG_SUBDIV:
                # 细分级别块：仅跳过，块长已包含块头
                start, payload, block_len = block_payload(pos)
                if start is None:
                    print(f"S导入：细分块长度异常（{block_len}），终止解析：{path_file}")
                    break
                pos += block_len

            elif tag in (TAG_DIFF, TAG_DISP, TAG_NORM):
                # 贴图路径字符串块
                str_len = u32_at(pos + 4) - 16
                path_bytes = bytes(buf[pos + 16:pos + 16 + str_len])
                pos = pos + 16 + str_len
                image_path = path_bytes.strip(b'\x00').decode('utf-8', 'ignore').strip()

                if tag == TAG_DIFF:
                    texture_name = obj_name + prefs.import_diffuse_suffix
                elif tag == TAG_DISP:
                    texture_name = obj_name + prefs.import_displace_suffix
                else:
                    texture_name = obj_name + prefs.import_normal_suffix

                try:
                    img = bpy.data.images.load(image_path, check_existing=True)
                    img.name = texture_name
                    img.reload()
                    if tag == TAG_DIFF:
                        diff_texture = img
                    elif tag == TAG_DISP:
                        disp_texture = img
                    else:
                        norm_texture = img
                except Exception as e:
                    print(f"S导入：贴图加载失败 {image_path}: {e}")

            else:
                # 未知块：第二个 u32 为块总长度（含 8 字节头），据此安全跳过
                # 例：ZBrush 2026 在 POLYGROUPS 之后还会写一个 0x9c42 块
                # （每面 1 字节的多边形组色索引），按块长跳过即可
                if pos + 8 > total:
                    break
                block_len = u32_at(pos + 4)
                if block_len < 8 or pos + block_len > total:
                    if prefs.debug_output:
                        print(f"S导入：遇到无法跳过的块 {tag!r}（{block_len} 字节），终止解析")
                    break
                if prefs.debug_output:
                    print(f"S导入：跳过未知块 {tag!r}，{block_len} 字节")
                pos += block_len
                tag = tag_at(pos) if pos + 4 <= total else b''
                continue

            if prefs.performance_profiling:
                start_time = utils.profiler(start_time, f"解析块 {tag!r}")

            tag = tag_at(pos) if pos + 4 <= total else b''

        if verts is None:
            print(f"S导入：文件中没有顶点数据：{path_file}")
            return

        # ---- 预过滤非法面 -------------------------------------------
        # 与原版 from_pydata 的行为保持一致：
        #   1) 槽位内存在重复顶点的退化面会被丢弃（from_pydata 静默跳过）；
        #   2) 索引越界的面同样无法成面，一并丢弃。
        # 必须在构建网格前过滤，并同步过滤 UV/多边形组等逐面数据，
        # 否则后续 foreach_set 会出现"阵列长度不匹配/internal error"
        # （原版在含退化面的文件上会因此崩溃）。
        if face_idx is None:
            face_idx = np.zeros((0, 4), dtype=np.uint32)

        # 逐面/逐顶点数据的数量必须与几何一致，否则 foreach_set 会报
        # “array length mismatch / internal error”；数量不符时安全放弃该属性
        num_faces_raw = len(face_idx)
        if uv_raw is not None and uv_raw.shape[0] != num_faces_raw:
            print(f"S导入：UV 组数（{uv_raw.shape[0]}）与面数（{num_faces_raw}）不一致，跳过 UV")
            uv_raw = None
        if pg_raw is not None and len(pg_raw) != num_faces_raw:
            print(f"S导入：多边形组数（{len(pg_raw)}）与面数（{num_faces_raw}）不一致，跳过多边形组")
            pg_raw = None
        if pp_raw is not None and len(pp_raw) != len(verts):
            print(f"S导入：顶点色数（{len(pp_raw)}）与顶点数（{len(verts)}）不一致，跳过顶点色")
            pp_raw = None
        if mask_raw is not None and len(mask_raw) != len(verts):
            print(f"S导入：蒙版数（{len(mask_raw)}）与顶点数（{len(verts)}）不一致，跳过蒙版")
            mask_raw = None

        if len(face_idx):
            face_valid = self._valid_face_mask(face_idx, len(verts))
            dropped = int((~face_valid).sum())
            if dropped:
                if prefs.debug_output:
                    print(f"S导入：丢弃 {dropped} 个退化/非法面")
                face_idx = face_idx[face_valid]
                if uv_raw is not None:
                    uv_raw = uv_raw[face_valid]
                if pg_raw is not None:
                    pg_raw = pg_raw[face_valid]

        # ---- 构建网格 -----------------------------------------------
        # validate=False：网格校验推迟到所有逐面/逐顶点属性写完之后，
        # 详见下方“收尾校验”说明
        obj, me, tri_mask, reused = self._make_mesh(
            obj_name, verts, face_idx, overwrite,
            hide_modifiers=hide_modifiers, validate=False)
        if prefs.performance_profiling:
            start_time = utils.profiler(start_time, "构建网格")

        # ---- 可选属性数据 -------------------------------------------
        if uv_raw is not None and len(face_idx):
            self._apply_uvs(me, uv_raw, tri_mask)
            if prefs.performance_profiling:
                start_time = utils.profiler(start_time, "UV")

        if pp_raw is not None:
            self._apply_polypaint(me, pp_raw)
            if prefs.performance_profiling:
                start_time = utils.profiler(start_time, "多边形绘制")

        if mask_raw is not None:
            self._apply_mask(obj, mask_raw)
            if prefs.performance_profiling:
                start_time = utils.profiler(start_time, "蒙版")

        if pg_raw is not None and len(face_idx):
            self._apply_polygroups(obj, me, pg_raw)
            if prefs.performance_profiling:
                start_time = utils.profiler(start_time, "多边形组")

        # ---- 收尾校验（必须在逐面/逐顶点属性写入之后）----------------
        # me.validate() 会删除重复面、非法面等。若在属性写入前执行，
        # 网格面数会少于 .GoZ 里的面组/UV 数量，后续按 .GoZ 面序做
        # foreach_set 就会报 “internal error setting the array”
        # （合并模型这类含重复面的文件必然触发）。
        # 放到最后：删面时其 loop 与对应属性数据会被一并裁剪，索引保持同步。
        if me.validate(verbose=prefs.debug_output) and prefs.debug_output:
            print(f"S导入：网格校验修正了非法数据，当前面数 {len(me.polygons)}")

        # ---- 材质 ---------------------------------------------------
        if prefs.import_material == 'POLYPAINT':
            if prefs.import_polypaint_name in me.color_attributes:
                if obj.material_slots and obj.material_slots[0].material is not None:
                    obj_mat = obj.material_slots[0].material
                else:
                    # 使用实际对象名（非覆盖导入时可能带 .001 后缀）
                    obj_mat = bpy.data.materials.new(obj.name)
                    obj.data.materials.append(obj_mat)
                nodes.materail_from_polypaint(obj_mat)

        elif prefs.import_material == 'TEXTURES':
            if obj.material_slots and obj.material_slots[0].material is not None:
                obj_mat = obj.material_slots[0].material
            else:
                obj_mat = bpy.data.materials.new(obj.name)
                obj.data.materials.append(obj_mat)
            nodes.material_fromm_texture(obj_mat, diff_texture, norm_texture, disp_texture)

        # ---- 找回细分（必须在最终最高级几何写入完成后执行）--------------
        # multires_rebuild_subdiv 在一个尚无细分级别的空 Multires 上，
        # 依据当前网格（高模）反推尽可能多的较低级别；因此必须等几何/
        # 属性全部写入后再调用，与是否覆盖无关（任何情况都可用）。
        # 是否隐藏新 Multires 由“隐藏修改器”决定（覆盖时才会隐藏）。
        if recover_multires:
            self.recover_object_multires(
                obj, create_if_missing=True,
                keep_visible=not hide_modifiers)
            if prefs.performance_profiling:
                start_time = utils.profiler(start_time, "找回细分")

        if prefs.performance_profiling:
            print(30 * "-")
            utils.profiler(start_total, f"S导入对象耗时：{obj_name}")
            print(30 * "-")

    # ------------------------------------------------------------------
    # 操作符入口
    # ------------------------------------------------------------------
    def execute(self, context):
        # 与上游一致：按当前平台的首选项刷新 GoZ 根路径
        # （直接改 paths.PATH_GOZ 不会同步 PATH_OBJLIST / PATH_CONFIG 等派生路径）
        paths.set_goz_path_from_preferences()

        goz_obj_paths = []
        try:
            list_path = paths.PATH_OBJLIST
            with open(list_path, 'rt') as goz_objs_list:
                goz_obj_paths.extend(f'{line.strip()}.GoZ' for line in goz_objs_list)
        except PermissionError:
            self.report({'WARNING'}, "GoZ_ObjectList 正被占用，请稍后重试")
            return {'CANCELLED'}
        except Exception as e:
            print(e)

        if not goz_obj_paths:
            self.report({'INFO'}, "GoZ_ObjectList 中没有 GoZ 文件")
            return {'CANCELLED'}

        # 非对象模式下先切回对象模式，导入后恢复
        current_mode = None
        if context.object:
            current_mode = context.object.mode
            if current_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

        prefs = utils.prefs()
        if prefs.performance_profiling:
            print("\n", 100 * "=")
            total_start = utils.profiler(time.perf_counter(), "S导入：开始")
            print(100 * "-")

        # 面板复选框会写入 Scene 持久属性；优先采用它，其次用操作符属性默认值
        scene = context.scene
        overwrite = getattr(scene, "gob_s_import_overwrite",
                            self.import_overwrite)
        # “隐藏修改器”与“找回细分”都和覆盖无关，任何情况下都按勾选执行；
        # 新建对象通常无修改器，找回细分新建的 Multires 也会据此决定是否隐藏
        hide_modifiers = getattr(
            scene, "gob_s_import_hide_modifiers", self.hide_modifiers)
        recover_multires = getattr(
            scene, "gob_s_import_recover_multires", self.recover_multires)

        wm = context.window_manager
        wm.progress_begin(0, 100)
        step = 100 / len(goz_obj_paths)
        # S导入不使用原版的导入缓存，每次强制重新导入全部对象
        for i, ztool_path in enumerate(goz_obj_paths):
            try:
                self.GoZit(ztool_path, overwrite,
                           hide_modifiers, recover_multires)
            except Exception as e:
                # 单个对象失败不影响其余对象导入
                import traceback
                traceback.print_exc()
                self.report({'WARNING'}, f"S导入失败：{os.path.basename(ztool_path)}: {e}")
            wm.progress_update(step * i)
        wm.progress_end()

        if context.object and current_mode:
            bpy.ops.object.mode_set(mode=current_mode)

        if prefs.performance_profiling:
            utils.profiler(total_start, "S导入：总耗时")
            print("=" * 100)

        self.report({'INFO'}, "S导入完成")
        return {'FINISHED'}


class GoB_OT_s_recover_multires(Operator):
    """找回细分：对选中对象的多级细分级修改器重建较低层级并降低视图层级"""
    bl_idname = "scene.gob_s_recover_multires"
    bl_label = "找回细分"
    bl_description = ("为选中网格对象的 Multires 修改器找回丢失的细分层级，"
                      "并把视图显示层级设为 2 以防卡顿")

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'WARNING'}, "没有选中的网格对象")
            return {'CANCELLED'}

        recovered = 0
        for obj in targets:
            # 独立命令：无 Multires 时新建；保留修改器当前显示状态
            recovered += GoB_OT_s_import.recover_object_multires(
                obj, view_levels=2,
                create_if_missing=True, keep_visible=True)

        self.report({'INFO'}, f"找回细分完成，处理 {len(targets)} 个对象")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Scene 持久属性：供面板复选框绑定（操作符属性本身无法直接在面板勾选）
# ---------------------------------------------------------------------------
def register():
    bpy.types.Scene.gob_s_import_overwrite = BoolProperty(
        name="导入覆盖",
        description="勾选：S导入时若场景中存在同名对象则覆盖当前对象\n"
                    "不勾选：自动添加 .001 等后缀，作为新对象添加到场景",
        default=True,
    )
    bpy.types.Scene.gob_s_import_hide_modifiers = BoolProperty(
        name="隐藏修改器",
        description="导入时关闭对象全部修改器的视图显示，避免修改器重求值卡顿\n"
                    "导入后保持隐藏，可在修改器面板手动恢复\n"
                    "与是否覆盖无关，任何情况下都生效",
        default=False,
    )
    bpy.types.Scene.gob_s_import_recover_multires = BoolProperty(
        name="找回细分",
        description="导入时为对象已有的多级细分级修改器重建丢失的较低层级，"
                    "并把视图层级降为 2 以防卡顿\n"
                    "任何情况下都可用，无 Multires 时自动忽略；\n"
                    "是否同时隐藏 Multires 由“隐藏修改器”决定",
        default=False,
    )


def unregister():
    for attr in ("gob_s_import_overwrite",
                 "gob_s_import_hide_modifiers",
                 "gob_s_import_recover_multires"):
        try:
            delattr(bpy.types.Scene, attr)
        except AttributeError:
            pass
