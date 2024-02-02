import math
import time
import bpy
import random
from functools import partial
from mathutils import Vector
from src import rantom, splittable, config
from src import utils
from src import splittable as split
from src import profile    as prof
from src import subframe   as sub
from src.materials import Materials
from mathutils import Matrix, Euler, Vector

class ShutterSplittable(split.Rect): # create window split-shapes for rectangles
    def split(s, profile_width, prof_idx, r2, key=None):

        out = []
        opts = [4] # don't split

        if s.rect[3] > 4 * profile_width + 2 * s.min_to_split: # split horizontal if tall
            opts.append(3)

        if s.rect[2] > 4 * profile_width + 2 * s.min_to_split: # split vert if wide
            opts.append(2)

        s.do_split( r2.choice(opts, "split_type", "Type of split at current level: H, V, H*, V*, None") , profile_width, out, r2, key=key)

        for o in out:
            o.subterminal = True
            o.terminal = True

        return out

# generates cloth curtains, blinds, and internal shutters
class Curtains:
    def __init__(self) -> None:
        pass

    def go( self, geom, wall_thickness, int_wall_thickness, frame_bounds, r2, expand=True ):

        steps = 10
        self.geom = geom
        self.r2 = r2
        self.wall_thickness = wall_thickness

        cloth_settings = self.cloth_settings("curtain")

        shapeOB = self.geom['shapeOB']

        blind_ob = shapeOB.copy()
        blind_ob.data = blind_ob.data.copy()
        blind_ob.hide_set(False)
        blind_ob.hide_render = False
        
        blind_ob.name = "xxx-curtain-marker"

        r = prof.curve_xyzwhd(blind_ob)

        geom["curtains_z_offset"] = 0 # depth offset from inside of wall (applied in facade)
        
        if type ( utils.get_curve_info(geom, shapeOB)['splittable']) is split.Rect:

            geom["curtains_z_offset"] = self.r2.uniform ( 0, int_wall_thickness + frame_bounds[2][0], "depth offset for curtains" ) 

            expand = 0

        else: # otherwise they have to go behind
            
            expand = self.r2.uniform(0.05, max(min (r[3] * 0.1, 0.6), 0.06), "curtains_expansion", "how much are the curtains wider/taller than the window?") if expand else 0
            zoffset = min ( frame_bounds[2][0], -int_wall_thickness ) - 0.03
            blind_ob.matrix_basis = blind_ob.matrix_basis @ Matrix().Translation(( 0, 0, zoffset ) )

        curtainOBs = []
        geom["curtainOBs"] = curtainOBs
        geom["do_physics"] = False


        match self.r2.weighted_int([2,1,1,1,3], "curtain_type", "Curtains, blinds, internal shutters, or none"):

            case 0: # curtains
                if config.physics:
                    ideal_width=self.r2.uniform(0.4, 1, "per_curtain_width")

                    if r[3] > 2.5 * ideal_width and self.r2.uniform(0, r[3], "curtains_many") > 3: # many curtains
                        c_count =  math.ceil( r[3] / ideal_width )
                    else: # one or two curtains usually
                        c_count = 1 if r[3] < ideal_width else 2

                    c_width = (r[3]+2*expand)/c_count

                    mat = Materials(geom).got_curtain(self.r2)

                    for c in range (c_count):

                        bunch_type = self.r2.randrange(4, "curtain_bunch_direction", "Do curtains bunch vertically, horizontally, drape etc...?")

                        height = r[4]
                        no_support = False

                        # lowered height, not at top of frame
                        if c_count == 1 and (bunch_type == 3 or bunch_type == 1) and height > 0.5 and self.r2.randrange(4, "curtain_reduced_height_chance") == 0:
                            height *= self.r2.uniform(0.4, 0.8, "reduced_height_curtain")
                            no_support = True

                        left = None

                        if c == 0:
                            left = False
                        elif c == c_count -1:
                            left = True

                        if left == None or c_count == 1:
                            left = self.r2.randrange(2, f"curtain_side_{c}") == 0

                        curtain = self.cloth_curtains ( [r[0] + c * c_width - expand, r[1] - expand, r[2]], c_width, height + 2 * expand,
                                            cloth_settings=cloth_settings, steps=steps, left=left, bunch_type=bunch_type, no_support=no_support)

                        curtain.location = blind_ob.location
                        curtain.location.y += 0.03
                        curtain.rotation_euler = blind_ob.rotation_euler

                        if self.r2.randrange(10, "different_curtain_material") == 0:
                            mat = Materials(geom).got_curtain(self.r2)

                        curtain.data.materials.append(mat)

                        curtainOBs.append ( curtain )

                    for window_comp in geom["frameOBs"] + geom["frameGlassOBs"] + [geom['int_wall_side']]: # collide against whole window
                        mod = window_comp.modifiers.new('wc', 'COLLISION')
                        mod.settings.use_culling = False


                    geom["do_physics"] = True

            case 1: # venetian blinds
                Curtains.slat_o_matic(blind_ob, "venetian", curtainOBs, r, Materials(geom).got_blinds(self.r2))
            case 2: # slat blinds
                Curtains.slat_o_matic(blind_ob, "slat", curtainOBs, r, Materials(geom).got_blinds(self.r2, use_wood=True))
            case 3: # framed slat blinds
                                
                utils.apply_transfrom(blind_ob, use_scale = True, use_location = True )

                # create rectangular shutter
                blind_ob.name = "xxx-blind_obb"

                xywh = prof.curve_xywh(blind_ob)
                rect = ShutterSplittable(rect=xywh, r2=self.r2)
                rect.shape.name = "xxx-curtain-maker"
                rect.shape.matrix_local = blind_ob.matrix_local
                rect.shape.matrix_basis = blind_ob.matrix_basis


                curtainOBs.append (rect.shape)
                bpy.context.scene.collection.objects.link(rect.shape)

                utils.get_curve_info( self.geom, rect.shape )['splittable'] = rect
                
                mat = Materials(geom).got_blinds(self.r2, use_wood=True)

                frame_root = sub.Subframe(geom).go(
                    "intShutters",
                    r2 = self.r2,
                    glass_w       = -0.01,
                    shape         = rect.shape,
                    profile_stacks= "shutter_profiles",
                    glass_fn      = partial ( Curtains.create_shutters_not_glass, mat, r2) )

                utils.apply_transfrom(frame_root, use_location = True, use_rotation=True)

                for o in self.geom['intShuttersOBs']: # slats material set above for use by geometry shader
                    o.data.materials.append(mat)

                curtainOBs.append(frame_root)
                curtainOBs.extend(self.geom['intShuttersOBs'])
                curtainOBs.extend(self.geom['intShuttersGlassOBs'])

                rect.shape.hide_set(True)
                rect.shape.hide_render = True

            case 4: # nothing
                pass


    def create_shutters_not_glass(mat, r2, bez_curve_int, glass_w, out_glass_objs):

        # curtainOBs.append ( blind_ob )
        bez = bez_curve_int.copy()
        bpy.context.scene.collection.objects.link( bez )

        name = "shutter"

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

        slato.nodes["Value.002"].outputs[0].default_value = r2.uniform (0.1, 1.5, f"{name}_open_amount")
        slato.nodes["Value"].outputs[0].default_value = 0.035 # vertical distance between each slat

        slato.nodes["Value.001"].outputs[0].default_value = r2.gauss (0, 0.0005, f"{name}_angle_jitter")

        out_glass_objs.append(bez)

        return bez


    def slat_o_matic( blind_ob, name, curtainOBs, r, mat, spacing_up=0.008, spacing_down=0.025 ):

        bpy.context.scene.collection.objects.link(blind_ob)
        curtainOBs.append ( blind_ob )

        blind_geom_mod = blind_ob.modifiers.new('blinds', 'NODES')
        slato = bpy.data.node_groups['slat-o-matic'].copy()
        slato.name = f"xxx-{name}"
        blind_geom_mod.node_group = slato
        slato.nodes["Object Info.001"].inputs[0].default_value = bpy.data.objects[name]
        slato.nodes["setmat"].inputs[2].default_value = mat
        mat.name = f"xxx-{name}-material"
        blind_ob.data.materials.append(mat)

        if rantom.randrange(3, f"{name}_drawn_up")  == 0: # rolled up

            blind_height = rantom.uniform (0.1, r[4]*0.4, f"{name}_drawn_up_size")
            # blind_ob.scale.z = blind_ob.scale.y * blind_height  / r[4] 
            # utils.apply_transfrom(blind_ob, use_location=True, use_scale = True )

            # blind_ob.location[1] += r[4]  #- blind_height/2
            

            slato.nodes["Value.002"].outputs[0].default_value = 0
            slato.nodes["Value"].outputs[0].default_value = spacing_up # vertical distance between each slat

            slato.nodes["Value.001"].outputs[0].default_value = rantom.gauss (0, 0.015, f"{name}_angle_jitter")

        else: # pulled down open
            slato.nodes["Value.002"].outputs[0].default_value = rantom.uniform (-1.4, 1.4, f"{name}_open_amount")
            slato.nodes["Value"].outputs[0].default_value = spacing_down # vertical distance between each slat

            slato.nodes["Value.001"].outputs[0].default_value = rantom.gauss (0, 0.005, f"{name}_angle_jitter")

    def cloth_curtains(self,
            location,
            width,
            height,
            bunch_type = 0,
            cloth_settings = None,
            left=True, # which side do we open on?
            steps = 100,
            no_support = False
        ):

        if cloth_settings == None or self.r2.randrange(8, "ignore_shared_cloth_settings") == 0:
            cloth_settings = self.cloth_settings("left" if left else "right")

        # vertex resolution
        resolution = 0.05

        x_count = math.ceil (width/resolution)
        x_delta = width/x_count
        y_count = math.ceil (height/resolution)
        y_delta = height/y_count

        x_select = []
        y_select = []

        if bunch_type == 0: # gather to one side
            
            x_select=[int(y_count * self.r2.uniform(0.2,0.6, "curtain_bunch_point"))]
            slide_top = True #self.r2.randrange(5, "drape_slides") != 0 

        elif bunch_type == 1: # pull up to top of curtain
            
            if no_support:
                y_select = []
            else:
                x_skip = int ( (x_count+1) / (self.r2.randrange(3, "curtain_vertical_bunch_points")+2) )
                y_select = list ( range(x_skip, x_count-int (x_skip/2))[::x_skip] )

            if no_support or self.r2.randrange(4, "curtain_vertical_end_bunches")> 0:
                y_select.append(x_count)
                y_select.append(0)
                
            slide_top = False

        elif bunch_type ==2: # pin whole top
            slide_top = True #self.r2.randrange(5, "drape_slides") != 0 

        elif bunch_type == 3: # "student's bedsheet" - pin several along the top
            
            if no_support:
                y_select = []
            else:
                x_skip = max(1,int ( (x_count+1) / (self.r2.randrange(4, "curtain_vertical_bunch_points")+2) ))
                y_select = list ( range(x_skip, x_count-int (x_skip/2))[::x_skip] )

            y_select.append(x_count)
            y_select.append(0)

            slide_top = not no_support #False if no_support else self.r2.randrange(5, "drape_slides") != 0 

        group_top  = []
        group_rows = []
        group_cols = []

        vertices = []
        uvs = []

        noise = x_delta * 0.05

        for x in range (x_count+1):
            for y in range (y_count+1):

                vertices.append(Vector((x_delta * x + location[0] + random.gauss(0,noise ), y_delta * y + location[1] + random.gauss(0,noise), random.gauss(0,noise) )) )
                uvs.append((x * x_delta, y * y_delta ))
                ta = (len(vertices)-1, x, y)

                if y == y_count:
                    if bunch_type != 3:
                        group_top .append(ta)
                    else:
                        if x in y_select:
                            group_top .append(ta)
                if y in x_select:
                    group_rows.append(ta)
                if x in y_select and bunch_type != 3:
                    group_cols.append(ta)

        faces = []
        for x in range (x_count):
            for y in range (y_count):
                faces.append( [
                    y + x * (y_count + 1),
                    y + (x+1) * (y_count + 1),
                    y + 1 + (x+1) * (y_count + 1),
                    y + 1 + x * (y_count + 1) 
                ] )


        me = bpy.data.meshes.new("xxx-cube")
        me.from_pydata(vertices, [], faces)
        # me.validate(verbose = True)  # useful for development when the mesh may be invalid.
        
        uv_layer = me.uv_layers.new(name="uvs")

        for face in me.polygons:
            for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                uv_layer.data[loop_idx].uv = uvs[vert_idx]

        meshOB = bpy.data.objects.new("xxx-mesh", me)
        bpy.context.scene.collection.objects.link(meshOB)

        group = meshOB.vertex_groups.new(name="animated")

        for g in [group_top, group_rows, group_cols]:
            group.add(index=list(map(lambda x: x[0], g)), weight=1, type="ADD")

        _ = meshOB.shape_key_add(name='Base')

        sk = meshOB.shape_key_add(name='Deform')
        sk.interpolation = 'KEY_LINEAR'

        if slide_top:
            close_fraction = self.r2.uniform(0.1, 0.7, f"curtain_top_offset", f"how open are the curtains?")
            for t_idx, x_idx, y_idx in group_top:
                sk.data[t_idx].co.x = x_delta * close_fraction * x_idx + location[0] + ( ((1-close_fraction) * width) if left else 0 )

            if len (group_rows) > 0:
                bunch_fraction = self.r2.uniform(0.02, close_fraction - 0.1, f"curtain__bunch_fraction", f"how bunched is middle of the curtain?")
                for t_idx, x_idx, y_idx in group_rows:
                    sk.data[t_idx].co.x = x_delta * bunch_fraction * x_idx + location[0] + ( ((1-bunch_fraction) * width) if left else 0 )
        
        if bunch_type == 1:

            bunch_height = self.r2.uniform(0.01, height * 0.4, f"curtain_bunch_height", f"closed-height of middle of the curtain?")
            for t_idx, x_idx, y_idx in group_cols:
                sk.data[t_idx].co.y = location[1] + height - bunch_height + (bunch_height * y_idx/y_count )

        # animate shape key
        sk.value = 0
        sk.keyframe_insert("value", frame=0)
        sk.value = 1
        sk.keyframe_insert("value", frame=steps)

        # collide with glass + interior frame - not very reliable        
        # for ob in self.geom['glassOBs']:
        #     ob.modifiers.new('collision', 'COLLISION')
        # for ob in self.geom['frameOBs']:
        #     ob.modifiers.new('collision', 'COLLISION')

        # cloth simulator
        modifier = meshOB.modifiers.new(name="Cloth", type='CLOTH')
        self.apply_cloth_settings(modifier, cloth_settings)

        # subdiv surfaces
        subsurf = meshOB.modifiers.new(name="Subsurf", type='SUBSURF')
        subsurf.levels = 2
        subsurf.render_levels = 3

        meshOB.name = "xxx-curtain"

        return meshOB

    def cloth_settings(self, name):
        return dict(
                mass = self.r2.uniform(2, 6,  f"curtain_vertex_mass_{name}"),
                compression_stiffness = 2,
                bending_stiffness = self.r2.uniform(0.05, 2,  f"curtain_bending_stiffness_{name}" ),
                shear_stiffness = self.r2.uniform(0.2, 1,  f"curtain_shear_stiffness_{name}")
            )

    def apply_cloth_settings(self, modifier, cloth):
        modifier.collision_settings.use_self_collision = True
        modifier.settings.vertex_group_mass = "animated" # pin group
        modifier.settings.mass = cloth["mass"]
        modifier.settings.compression_stiffness = cloth["compression_stiffness"]
        modifier.settings.bending_stiffness = cloth["bending_stiffness"]
        modifier.settings.shear_stiffness = cloth["shear_stiffness"]
        modifier.settings.time_scale = 5
        # modifier.settings.shear_damping = 50
        # modifier.settings.compression_damping = 50
        # modifier.settings.tension_damping = 50
        # modifier.settings.bending_damping = 5

