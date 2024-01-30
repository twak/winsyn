import bpy, bmesh
from src import utils   as utils
import math
import time
import bpy
from functools import partial
from mathutils import Vector
import random
from src import rantom, splittable
from src import utils
from src import splittable as split
from src import profile    as prof
from src import subframe   as sub
from src import curtains   as curtains

from src.materials import Materials


class Shutter:

    def __init__(self) -> None:
        pass

    def go(self, shapeOB, geom, wall_y, r2, left=True, idx=0):
        
        self.geom = geom
        self.r2 = r2

        bounds = prof.curve_xyzwhd(shapeOB)

        to_cover = [shapeOB]

        ab = utils.world_bounds_children(to_cover)

        r = [bounds[0], bounds[1], bounds[3], bounds[4]]
        mat = Materials(self.geom).got_ext_shutters (self.r2)
        open_ammount = self.r2.uniform (-1.51, -1.15, f"ex_shutter_open_amount")
        
        side_string = "left" if left else "right" 


        rect = curtains.ShutterSplittable(rect=r, r2=self.r2)

        utils.get_curve_info( self.geom, rect.shape )['splittable'] = rect

        subf = sub.Subframe(self.geom)
        frame_root = subf.go(f"extShutter", r2=r2, glass_w=-0.01, shape=rect.shape, profile_stacks="shutter_profiles",
            #glass_fn = partial ( Wall.create_exterior_shutters_not_glass, mat, open_ammount), open_windows=False )
            glass_fn = partial ( r2.choice([Shutter.create_exterior_shutters_not_glass, Shutter.create_panel_not_glass], "ex_shutters_slats_or_solid" ),
                    mat, open_ammount, self.r2), open_windows=False, root_hinges_left=left )

        frame_root.name= f"xxx-ext_shutter_{side_string}"

        for o in self.geom['extShutterOBs']: 
            o.data.materials.append(mat)

        shutter_parent = bpy.data.objects.new( f"xxx-ex-shutter-{idx}-{side_string}", None )
        bpy.context.scene.collection.objects.link(shutter_parent)
        shutter_parent.location[0] = r[0] if left else r[0] + r[2]

        # frame_root
        frame_root.parent = shutter_parent

        max_angle = 0

        match r2.weighted_int([1,1], "external_shutter_{idx}_open_or_close"):
            case 0:
                angle = r2.uniform(0, 0.2, f"shutter_angle_{idx}")
            case 1:
                angle = r2.uniform(3.135, 3.141, f"shutter_angle_{idx}")
            # case 2:
            #     angle = r2.uniform(max_angle, 3.141, f"flapping_shutter_angle_{idx}")

        shutter_parent.rotation_euler[1] = -angle if left else angle
        shutter_parent.location[2] += wall_y
        return shutter_parent

    def create_panel_not_glass(mat, open_ammount, r2, bez_curve_int, glass_w, out_glass_objs):

        #meshOB = bez_curve_int.copy() # utils.to_mesh(bez_curve_int)
        meshOB = utils.to_mesh(bez_curve_int)

        me = meshOB.data

        vert_loops = {}
        for l in me.loops:
            vert_loops.setdefault(l.vertex_index, []).append(l.index)

        uv_layer = me.uv_layers[0]

        for face in me.polygons:
            for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                uv_layer.data[loop_idx].uv = me.vertices [vert_idx ].co.xy #  uvs[vert_idx]

        name = "exterior-shutter"

        meshOB.hide_set(False)
        meshOB.hide_render = False
        meshOB.name = f"xxx-{name}"

        mat.name = f"xxx-{name}-material"
        meshOB.data.materials.append(mat)
        out_glass_objs.append(meshOB)

        return meshOB

    def create_exterior_shutters_not_glass(mat, open_ammount, r2, bez_curve_int, glass_w, out_glass_objs):

        # curtainOBs.append ( blind_ob )
        bez = bez_curve_int.copy()
        bpy.context.scene.collection.objects.link( bez )

        name = "exterior-shutter"

        bez.hide_set(False)
        bez.hide_render = False
        bez.name = f"xxx-{name}"

        blind_geom_mod = bez.modifiers.new('blinds', 'NODES')
        slato = bpy.data.node_groups['slat-o-matic'].copy()
        slato.name = f"xxx-{name}"
        blind_geom_mod.node_group = slato
        slato.nodes["Object Info.001"].inputs[0].default_value = bpy.data.objects["chunky-slat"]
        slato.nodes["setmat"].inputs[2].default_value = mat
        mat.name = f"xxx-{name}-material"
        bez.data.materials.append(mat)

        slato.nodes["Value.002"].outputs[0].default_value = open_ammount
        slato.nodes["Value"].outputs[0].default_value = 0.03  # vertical distance between each slat

        slato.nodes["Value.001"].outputs[0].default_value = r2.gauss (0, 0.0005, f"{name}_angle_jitter")

        # converting to mesh crashes blender 3.2:
        # bez.to_mesh_clear()
        # dg = bpy.context.evaluated_depsgraph_get() 
        # ob = bez.evaluated_get(dg) 
        # mesh_from_eval = ob.to_mesh()
        # meshOB = bpy.data.objects.new("xxx-"+bez.name, mesh_from_eval.copy())
        # bpy.context.scene.collection.objects.link( meshOB )
        # dg = bpy.context.evaluated_depsgraph_get() 
        # ob = bez.evaluated_get(dg) 
        # b_mesh = ob.to_mesh()
        # meshOB = bpy.data.objects.new("xxx-slates-"+bez_curve_int.name, ob.copy())
        #utils.to_mesh(bez, delete=True)

        out_glass_objs.append(bez)

        return bez