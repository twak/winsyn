##### BEGIN GPL LICENSE BLOCK #####
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


bl_info = {
    "name": "Add-on Template",
    "description": "A demo that adds a custom panel to the 'Tool Shelf' of the '3d View'",
    "author": "p2or",
    "version": (0, 4),
    "blender": (3, 0, 0),
    "location": "3D View > Tools",
    "warning": "",  # used for warning icon and text in addons panel
    "doc_url": "https://blender.stackexchange.com/a/57332",
    "tracker_url": "https://gist.github.com/p2or/2947b1aa89141caae182526a8fc2bc5a",
    "support": "COMMUNITY",
    "category": "Development"
}

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


# ------------------------------------------------------------------------
#    Scene Properties
# ------------------------------------------------------------------------

class MY_PG_SceneProperties(PropertyGroup):
    my_bool: BoolProperty(
        name="Bool",
        description="A bool property",
        default=False
    )

    my_int: IntProperty(
        name="Int",
        description="Integer property",
        default=23,
        min=10,
        max=100
    )

    my_float: FloatProperty(
        name="Float",
        description="Float Property",
        default=23.7,
        min=0.01,
        max=30.0
    )

    my_float_vector: FloatVectorProperty(
        name="Float Vector",
        description="Float Vector Property",
        default=(0.0, 0.0, 0.0),
        # subtype='COLOR',
        min=0.0,  # float
        max=0.1
    )

    my_string: StringProperty(
        name="String",
        description="String Property",
        default="",
        maxlen=1024,
    )

    my_path: StringProperty(
        name="Directory",
        description="Choose a Directory:",
        default="",
        maxlen=1024,
        subtype='DIR_PATH'  # FILE_PATH
    )

    my_enum: EnumProperty(
        name="Enum",
        description="Enum Property",
        items=[('OP1', "Option 1", ""),
               ('OP2', "Option 2", ""),
               ]
    )


# ------------------------------------------------------------------------
#    Operators
# ------------------------------------------------------------------------

class WM_OT_HelloWorld(Operator):
    bl_label = "Print Values to the Console"
    bl_idname = "wm.hello_world"

    # WindowManager namespace (wm.hello...) serves as example,
    # You could also use a custom one like: my_category.hello_world

    def execute(self, context):
        scene = context.scene
        mytool = scene.my_tool

        # print the values to the console
        print("Hello World")
        print("bool state:", mytool.my_bool)
        print("int value:", mytool.my_int)
        print("float value:", mytool.my_float)
        print("string value:", mytool.my_string)
        print("enum selection:", mytool.my_enum)

        return {'FINISHED'}


# ------------------------------------------------------------------------
#    Menus
# ------------------------------------------------------------------------

class OBJECT_MT_CustomMenu(Menu):
    bl_label = "Select"
    bl_idname = "OBJECT_MT_custom_menu"

    def draw(self, context):
        layout = self.layout

        # Built-in operators
        layout.operator("object.select_all", text="Select/Deselect All").action = 'TOGGLE'
        layout.operator("object.select_all", text="Inverse").action = 'INVERT'
        layout.operator("object.select_random", text="Random")


# ------------------------------------------------------------------------
#    Panel in Object Mode
# ------------------------------------------------------------------------

class OBJECT_PT_CustomPanel(Panel):
    bl_label = "My Panel"
    bl_idname = "OBJECT_PT_custom_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tools"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        scene = context.scene
        mytool = scene.my_tool

        layout.prop(mytool, "my_bool")
        layout.prop(mytool, "my_enum", expand=True)
        layout.prop(mytool, "my_int")
        layout.prop(mytool, "my_float")
        layout.prop(mytool, "my_float_vector")
        layout.prop(mytool, "my_string")
        layout.prop(mytool, "my_path")

        layout.separator(factor=1.5)
        layout.menu(OBJECT_MT_CustomMenu.bl_idname, text="Presets", icon="SCENE")
        layout.operator("wm.hello_world")
        layout.separator()


# ------------------------------------------------------------------------
#    Registration
# ------------------------------------------------------------------------

classes = (
    WM_OT_HelloWorld,
    MY_PG_SceneProperties,
    OBJECT_MT_CustomMenu,
    OBJECT_PT_CustomPanel
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.my_tool = PointerProperty(type=MY_PG_SceneProperties)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.Scene.my_tool


if __name__ == "__main__":
    register()