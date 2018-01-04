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

import itertools

import bpy
from bpy.props import (
    BoolProperty,
    StringProperty,
    FloatProperty,
    IntProperty)

from mathutils import Matrix, Vector

from sverchok.utils.sv_bmesh_utils import bmesh_from_pydata
from sverchok.node_tree import SverchCustomTreeNode
from sverchok.data_structure import (
    dataCorrect,
    fullList,
    updateNode)

from sverchok.utils.sv_viewer_utils import (
    matrix_sanitizer,
    natural_plus_one,
    get_random_init,
    greek_alphabet)


# -- DUPLICATES --
def make_duplicates_live_curve(node, object_index, verts, edges, matrices):
    # curves = bpy.data.curves
    # objects = bpy.data.objects
    # scene = bpy.context.scene

    # # if curve data exists, pick it up else make new curve
    # # this curve is then used as a data.curve for all objects.
    # # objects still have slow creation time, but storage is very good due to
    # # reuse of curve data and applying matrices to objects instead.

    # just make the curve data.
    curve_name = self.basedata_name + '.' + str("%04d" % obj_index)
    cu = curves.get(curve_name)
    if not cu:
        cu = curves.new(name=curve_name, type='CURVE')

    # wipe!
    if cu.splines:
        cu.splines.clear()

    cu.bevel_depth = node.depth
    cu.bevel_resolution = node.resolution
    cu.dimensions = '3D'
    cu.fill_mode = 'FULL'

    # rebuild!
    for edge in edges:
        v0, v1 = verts[edge[0]], verts[edge[1]]
        full_flat = [v0[0], v0[1], v0[2], 0.0, v1[0], v1[1], v1[2], 0.0]

        # each spline has a default first coordinate but we need two.
        segment = cu.splines.new('POLY')
        segment.points.add(1)
        segment.points.foreach_set('co', full_flat)

    # to proceed we need to add or update objects.
    obj_base_name = curve_name[:-1]  <--- nope

    # #### sv_object, cu = self.get_obj_curve(obj_index)

    # if object reference exists, pick it up else make a new one
    # assign the same curve to all Objects.
    for idx, matrix in enumerate(matrices):
        m = matrix_sanitizer(matrix)
        obj_name = obj_base_name + str(idx)
        obj = objects.get(obj_name)
        if not obj:
            obj = objects.new(obj_name, cu)
            scene.objects.link(obj)
        obj.matrix_local = m


# -- MERGE --
def make_merged_live_curve(node, obj_index, verts, edges, matrices):
    cu = node.get_obj_curve(obj_index)

    cu.bevel_depth = node.depth
    cu.bevel_resolution = node.resolution
    cu.dimensions = '3D'
    cu.fill_mode = 'FULL'

    for matrix in matrices:
        m = matrix_sanitizer(matrix)

        # and rebuild
        for edge in edges:
            v0, v1 = m * Vector(verts[edge[0]]), m * Vector(verts[edge[1]])

            full_flat = [v0[0], v0[1], v0[2], 0.0, v1[0], v1[1], v1[2], 0.0]

            # each spline has a default first coordinate but we need two.
            segment = cu.splines.new('POLY')
            segment.points.add(1)
            segment.points.foreach_set('co', full_flat)


# -- UNIQUE --
def live_curve(obj_index, verts, edges, matrix, node):

    cu = node.get_obj_curve(obj_index)

    cu.bevel_depth = node.depth
    cu.bevel_resolution = node.resolution
    cu.dimensions = '3D'
    cu.fill_mode = 'FULL'

    # and rebuild
    for edge in edges:
        v0, v1 = verts[edge[0]], verts[edge[1]]
        full_flat = [v0[0], v0[1], v0[2], 0.0, v1[0], v1[1], v1[2], 0.0]

        # each spline has a default first coordinate but we need two.
        segment = cu.splines.new('POLY')
        segment.points.add(1)
        segment.points.foreach_set('co', full_flat)

    return obj


def make_curve_geometry(node, context, obj_index, verts, *topology):
    edges, matrix = topology
    
    sv_object = live_curve(obj_index, verts, edges, matrix, node)
    sv_object.hide_select = False
    self.push_custom_matrix_if_present(sv_object, matrix)


class SvCurveViewerNodeMK2(bpy.types.Node, SverchCustomTreeNode, SvObjHelper):
    """
    Triggers: CV object curves
    Tooltip: Advanced 2d/3d curve outputting into scene
    """

    bl_idname = 'SvCurveViewerNode'
    bl_label = 'Curve Viewer'
    bl_icon = 'MOD_CURVE'

    mode_options = [
        ("Merge", "Merge", "", 0),
        ("Duplicate", "Duplicate", "", 1),
        ("Unique", "Unique", "", 2)
    ]

    selected_mode = bpy.props.EnumProperty(
        items=mode_options,
        description="merge or use duplicates",
        default="Unique",
        update=updateNode
    )

    data_kind = StringProperty(default='CURVE')
    grouping = BoolProperty(default=False)

    depth = FloatProperty(min=0.0, default=0.2, update=updateNode)
    resolution = IntProperty(min=0, default=3, update=updateNode)

    def sv_init(self, context):
        self.sv_init_helper_basedata_name()

        self.inputs.new('VerticesSocket', 'vertices')
        self.inputs.new('StringsSocket', 'edges')
        self.inputs.new('MatrixSocket', 'matrix')

    def draw_buttons(self, context, layout):
        view_icon = 'RESTRICT_VIEW_' + ('OFF' if self.activate else 'ON')
        sh = 'node.sv_callback_curve_viewer'

        def icons(button_type):
            icon = 'WARNING'
            if button_type == 'v':
                icon = 'RESTRICT_VIEW_' + ['ON', 'OFF'][self.state_view]
            elif button_type == 'r':
                icon = 'RESTRICT_RENDER_' + ['ON', 'OFF'][self.state_render]
            elif button_type == 's':
                icon = 'RESTRICT_SELECT_' + ['ON', 'OFF'][self.state_select]
            return icon

        col = layout.column(align=True)
        row = col.row(align=True)
        row.column().prop(self, "activate", text="UPD", toggle=True, icon=view_icon)

        row.operator(sh, text='', icon=icons('v')).fn_name = 'hide_view'
        row.operator(sh, text='', icon=icons('s')).fn_name = 'hide_select'
        row.operator(sh, text='', icon=icons('r')).fn_name = 'hide_render'

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "grouping", text="Group", toggle=True)
        row.separator()
        row.prop(self, "selected_mode", expand=True)

        row = col.row(align=True)
        row.scale_y = 1
        row.prop(self, "basemesh_name", text="", icon='OUTLINER_OB_MESH')

        row = col.row(align=True)
        row.scale_y = 2
        row.operator(sh, text='Select / Deselect').fn_name = 'mesh_select'
        row = col.row(align=True)
        row.scale_y = 1

        row.prop_search(
            self, 'material', bpy.data, 'materials', text='',
            icon='MATERIAL_DATA')

        col = layout.column()
        col.prop(self, 'depth', text='depth radius')
        col.prop(self, 'resolution', text='surface resolution')

    def draw_buttons_ext(self, context, layout):
        self.draw_buttons(context, layout)
        self.draw_ext_object_buttons(context, layout)

    def get_geometry_from_sockets(self):

        def get(socket_name):
            data = self.inputs[socket_name].sv_get(default=[])
            return dataCorrect(data)

        mverts = get('vertices')
        medges = get('edges')
        mmtrix = get('matrix')
        return mverts, medges, mmtrix

    def get_structure(self, stype, sindex):
        if not stype:
            return []

        try:
            j = stype[sindex]
        except IndexError:
            j = []
        finally:
            return j

    def process(self):
        if not (self.inputs['vertices'].is_linked and self.inputs['edges'].is_linked):
            # possible remove any potential existing geometry here too
            return

        # perhaps if any of mverts is [] this should already fail.
        mverts, *mrest = self.get_geometry_from_sockets()

        mode = self.selected_mode
        single_set = (len(mverts) == 1) and (len(mrest[-1]) > 1)
        has_matrices = self.inputs['matrix'].is_linked

        if single_set and (mode in {'Merge', 'Duplicate'}) and has_matrices:
            obj_index = 0
            self.output_dupe_or_merged_geometry(mode, mverts, *mrest)

            if mode == "Duplicate":
                obj_index = len(mrest[1]) - 1

        else:

            def get_edges_matrices(obj_index):
                for geom in mrest:
                    yield self.get_structure(geom, obj_index)

            # extend all non empty lists to longest of mverts or *mrest
            maxlen = max(len(mverts), *(map(len, mrest)))
            fullList(mverts, maxlen)
            for idx in range(2):
                if mrest[idx]:
                    fullList(mrest[idx], maxlen)

            for obj_index, Verts in enumerate(mverts):
                if not Verts:
                    continue

                data = get_edges_matrices(obj_index)
                make_curve_geometry(self, bpy.context, obj_index, Verts, *data)

            # we must be explicit
            obj_index = len(mverts) - 1

        self.remove_non_updated_objects(obj_index)
        objs = self.get_children()

        if self.grouping:
            self.to_group(objs)

        self.set_corresponding_materials(objs)

    def output_dupe_or_merged_geometry(self, TYPE, mverts, *mrest):
        '''
        this should probably be shared in the main process function but
        for prototyping convenience and logistics i will keep this separate
        for the time-being. Upon further consideration, i might suggest keeping this
        entirely separate to keep function length shorter.
        '''
        verts = mverts[0]
        edges = mrest[0][0]
        matrices = mrest[1]

        # object index = 0 because these modes will output only one object.
        if TYPE == 'Merge':
            make_merged_live_curve(self, 0, verts, edges, matrices)
        elif TYPE == 'Duplicate':
            make_duplicates_live_curve(self, 0, verts, edges, matrices)

    # def get_children(self):
    #     objects = bpy.data.objects
    #     objs = [obj for obj in objects if obj.type == 'CURVE']
    #     return [o for o in objs if o.name.startswith(self.basemesh_name + "_")]

    # def remove_non_updated_objects(self, obj_index):
    #     objs = self.get_children()
    #     # print('found', [o.name for o in objs])

    #     objs = [obj.name for obj in objs if int(obj.name.split("_")[-1]) > obj_index]
    #     # print('want to remove:', objs)

    #     if not objs:
    #         return

    #     curves = bpy.data.curves
    #     objects = bpy.data.objects
    #     scene = bpy.context.scene

    #     # remove excess objects
    #     for object_name in objs:
    #         obj = objects[object_name]
    #         obj.hide_select = False
    #         scene.objects.unlink(obj)
    #         objects.remove(obj)

    #     # delete associated meshes
    #     if (self.selected_mode == 'Duplicate'):
    #         objs = self.get_children()
    #         objs = [obj.name for obj in objs if int(obj.name.split("_")[-1]) > 0]
    #         # in Duplicate mode it's necessary to remove existing curves above index 0.
    #         # A previous mode may have generated such curves.

    #         for object_name in objs:
    #             if curves.get(object_name):
    #                 curves.remove(curves[object_name])
    #     else:
    #         for object_name in objs:
    #             curves.remove(curves[object_name])




def register():
    bpy.utils.register_class(SvCurveViewerNode)
    bpy.utils.register_class(SvCurveViewOp)


def unregister():
    bpy.utils.unregister_class(SvCurveViewerNode)
    bpy.utils.unregister_class(SvCurveViewOp)
