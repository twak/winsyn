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

# modified from p2or's https://blender.stackexchange.com/questions/57306/how-to-create-a-custom-ui/57332#57332 by twak


bl_info = {
    "name": "WinSyn",
    "description": "A synthetic data tool for creating windows",
    "author": "twak",
    "version": (0, 1),
    "blender": (3, 3, 0),
    "location": "3D View > WinSyn",
    "warning": "",  # used for warning icon and text in addons panel
    "doc_url": "https://github.com/twak/winsyn",
    "support": "COMMUNITY",
    "category": "Research"
}
import time
import os
from os.path import expanduser
import sys
import importlib
import pathlib

import bpy

from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       FloatVectorProperty,
                       EnumProperty,
                       PointerProperty,
                       )
from bpy.types import (Panel,
                       Menu,
                       Operator,
                       PropertyGroup,
                       )


from datetime import datetime
from pathlib import Path
from bpy.app import handlers


dir = os.path.dirname(bpy.data.filepath)
if not dir in sys.path:
    sys.path.append(dir)
sys.path.append(pathlib.Path(__file__).parent.resolve() ) # needed for vs code development with https://github.com/JacquesLucke/blender_vscode

from src import pipes
from src import adjacent
from src import rantom
from src import config
from src import shape
from src import utils
from src import cgb_building
from src import cgb_building_walls
from src import cgb_building_junk
from src import cgb_building_roofs
from src import cgb_building_win
from src import cgb
from src import surround
from src import shutter
from src import profile    as prof
from src import materials  as mat
from src import subframe   as sub
from src import splittable as split
from src import curtains   as curt

#import pydevd_pycharm
#pydevd_pycharm.settrace('localhost', port=10912, stdoutToServer=True, stderrToServer=True)

# ------------------------------------------------------------------------
#    Scene Properties
# ------------------------------------------------------------------------

class MY_PG_SceneProperties(PropertyGroup):

    generate_seed: IntProperty(
        name="seed",
        description="Random seed used to generate parameters",
        default=17066429,
        min=-100000000,
        max=100000000
    )

    param_file_path : StringProperty(
        name="param file:",
        description="Choose a parameter file:",
        default="winsyn_params.txt",
        maxlen=1024,
        subtype='FILE_PATH'
    )

    resource_path : StringProperty(
        name="resources:",
        description="Choose a resource folder (`resource` to use built-in)",
        default="resources",
        maxlen=1024,
        subtype='DIR_PATH'  # FILE_PATH
    )

    seed_or_file: EnumProperty(
        name="parameters:",
        description="Enum Property",
        items=[('SEED', "seed", ""),
               ('FILE', "file", ""),
               ],
    )

    style : EnumProperty(
        name="styles",
        description="Enum Property",
        items=[('rgb', "colour", "regular colo(u)r render"),
               ('labels', "labels", "per-part semantic labels"),
               ('col_per_obj', "col_per_obj", "every object has a different colour"),
               ('voronoi_chaos', "Voronoi", "crazy shader with scaled brightly coloured Voronoi "),
               ('texture_rot', "texture_rot", "rotated textures on every object"),
               ('phong_diffuse', "Phong", "grey old-school Phong"),
               ('diffuse', "Diffuse", "grey diffuse shader"),
               ('1nwall', "1 wall mat", "the wall always has a single material"),
               ('only_squares', "square windows", "all windows are square"),
               ('no_rectangles', "no rectangles", "no windows are rectangles"),
               ]
    )

    do_physics: BoolProperty(
        name="physics",
        description="do we run the (slow) physics simulator?",
        default = True
        )



# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class WM_OT_OpenParams(Operator):

    bl_label = "edit params"
    bl_idname = "wm.openparams"

    @classmethod
    def poll(self, context):
        scene = context.scene
        mytool = scene.winsyn
        return mytool.seed_or_file == "SEED" or os.path.exists(mytool.param_file_path)

    def execute(self, context):

        scene = context.scene
        mytool = scene.winsyn

        text = bpy.data.texts.load(str ( Path(mytool.param_file_path).resolve() ))
        for area in bpy.context.screen.areas:

            if area.type == 'TEXT_EDITOR':
                area.spaces[0].text = text # make loaded text file visible
                mytool.seed_or_file = "FILE"
                return {'FINISHED'}

        self.report({"WARNING"}, "Open a text editor to use that button")
        return {'CANCELLED'}

class WM_OT_OpenMyBlend(Operator):

    bl_label = "open correct blend"
    bl_idname = "wm.openblend"

    def execute(self, context):
        bpy.ops.wm.open_mainfile(filepath=str(pathlib.Path(__file__).parent.parent.joinpath("winsyn.blend").resolve()))
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

class WM_OT_Generate(Operator):

    bl_label = "generate"
    bl_idname = "wm.generate"
    bl_description = "run winsyn to create a scene"

    @classmethod
    def poll(self, context):
        scene = context.scene
        mytool = scene.winsyn
        return (mytool.seed_or_file == "SEED" or os.path.exists(mytool.param_file_path)) and bpy.data.filepath.endswith("/winsyn.blend")

    def execute(self, context):

        # bit of a hack: we need our blend file open before we do anything...
        if not bpy.data.filepath.endswith ("/winsyn.blend"):
            context.operator_context = 'INVOKE_DEFAULT'
            bpy.ops.wm.open_mainfile(filepath=str ( pathlib.Path(__file__).parent.parent.joinpath("winsyn.blend").resolve() ))
            return {'CANCELLED'}

        scene = context.scene
        mytool = scene.winsyn

        print("gui generating...")
        print("seed:", mytool.generate_seed)
        print("param path:", mytool.param_file_path)
        print("resource path:", mytool.resource_path)
        print("enum selection:", mytool.seed_or_file)

        config.resource_path = mytool.resource_path if mytool.resource_path != "resources" else pathlib.Path(__file__).parent.parent.resolve().joinpath("resources")
        config.physics = mytool.do_physics

        if mytool.seed_or_file == "SEED":
            params = {}
        else:
            params = rantom.read_params(mytool.param_file_path)

        self.report({"INFO"}, "Generating. Please wait...")

        if mytool.style in ["only_squares", "no_rectangles"]:
            geom_style = mytool.style
            material_style = "rgb"
        else:
            geom_style = "rgb"
            material_style = mytool.style

        geom, m = mat.Materials.create_geometry(geom_style, seed=mytool.generate_seed, param_override=params)

        m.pre_render(material_style)

        rantom.write_file(mytool.param_file_path)

        return {'FINISHED'}


# ------------------------------------------------------------------------
#    Panel in Object Mode
# ------------------------------------------------------------------------

class OBJECT_PT_WinSynPanel(Panel):
    bl_label = "WinSyn"
    bl_idname = "OBJECT_PT_custom_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "WinSyn"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return context.mode == "OBJECT"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        scene = context.scene
        mytool = scene.winsyn

        # layout.prop(mytool, "my_bool")
        layout.prop(mytool, "seed_or_file", expand=True)
        if context.scene.winsyn.seed_or_file == "SEED":
            layout.prop(mytool, "generate_seed")
        # else:
        layout.prop(mytool, "param_file_path")
        layout.operator("wm.openparams")


        layout.prop(mytool, "resource_path")

        layout.prop(mytool, "style")
        layout.prop(mytool, "do_physics")
        # layout.prop(mytool, "my_string")
        # layout.prop(mytool, "my_path")

        layout.separator(factor=1.5)
        if not bpy.data.filepath.endswith("/winsyn.blend"):
            layout.operator("wm.openblend")
        else:
            layout.operator("wm.generate")
        layout.separator()


# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    WM_OT_Generate,
    WM_OT_OpenParams,
    MY_PG_SceneProperties,
    OBJECT_PT_WinSynPanel,
    WM_OT_OpenMyBlend
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.winsyn = PointerProperty(type=MY_PG_SceneProperties)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.Scene.winsyn


if __name__ == "__main__":
    register()