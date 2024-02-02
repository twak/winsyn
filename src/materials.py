import bpy

import src.monomat_cache
from . import rantom, config, utils
from glob import glob
import colorsys, os, shutil
import random

from . import profile as prof
from . import cgb_building
from . import monomat_cache as mm

import numpy as np
from mathutils import Vector, Matrix, Euler

"""
Adds most of the materials to geometry and does styles.
"""

def copy(material):
    out = material.copy()
    out.name = 'xxx-'+material.name
    return out

class Materials:

    def __init__(self, geom):
        self.geom = geom
        self.dtd_textures = None
        self.cam_lookup = {}

    def go(s, override_r=None):

        # undo fullbright config changes
        bpy.context.scene.cycles.samples = config.samples
        bpy.context.scene.cycles.time_limit = 0
        bpy.data.worlds["World"].node_tree.nodes["fullbright"].inputs[0].default_value = 0
        bpy.data.worlds["World"].node_tree.nodes["simple_lighting"].inputs[0].default_value = 0
        bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[1].default_value = 0
        bpy.context.scene.cycles.use_preview_denoising = True
        bpy.context.scene.cycles.use_denoising = True
        bpy.context.scene.view_settings.view_transform = 'Filmic' # blender default
        bpy.context.scene.camera = bpy.data.objects['camera']
        bpy.context.scene.render.use_freestyle = False
        bpy.context.scene.render.film_transparent = False
        bpy.data.objects["Sun"].hide_render = False
        bpy.data.objects["Sun"].hide_set(False)

        # env maps, lights, camera
        s.env()

        wall_shaders = []
        stucco_wall_shaders = []
        timber_frame_mat = None
        max_volume = -1
        wall_is_texture = "wall_is_texture" in s.geom # not procedural walls, but from texture library

        def sa(ob, mat):
            if ob.data.materials:
                ob.data.materials[0] = mat
            else:
                ob.data.materials.append(mat)

        for idx, walls in enumerate ( s.geom['exterior_wallOBs'] + s.geom['exterior_wallframeOBs'] ):

            wr2 = override_r if override_r else rantom.RantomCache(0.1, name=f"wall_material_{idx}")

            if "timber" in walls[0].name:
                mode = 0
                if hasattr(s.geom, "wall_is_texture"): # don't use procedurals
                    timber_frame_mat = s.got_wall(wr2, "timber_frame")
                elif wr2.weighted_int([2,1], "timber_frame_material") == 0: # kinda black-ish
                    c = wr2.uniform(0.01, 0.1, "timber_frame_color")
                    timber_frame_mat = s.got_stucco("timber_frame", wr2, color=(c,c,c,1))
                else: # metal
                    timber_frame_mat = s.got_metal(wr2)
                    mode = 1

                ex_wall_shader = timber_frame_mat
                use_subdiv = False
            else:
                ex_wall_shader, use_subdiv, mode = s.got_wall(wr2, str(idx))
                mode = 1

            wall_shaders.append(ex_wall_shader)
            if mode == 0:
                stucco_wall_shaders.append (ex_wall_shader)

            volume = 0
            for wall in walls:

                if len ( wall.data.vertices ) == 0:
                    continue

                if wall_is_texture: # do uv-remapping for many-textures...
                    bpy.context.view_layer.objects.active = wall
                    bpy.ops.object.mode_set(mode="EDIT")
                    bpy.ops.mesh.select_all(action="SELECT")
                    # bpy.ops.object.material_slot_select()
                    bpy.ops.uv.cube_project(cube_size=1, correct_aspect=False)
                    bpy.ops.object.mode_set(mode="OBJECT")

                sa (wall, ex_wall_shader ) # wall.data.materials.append( ex_wall_shader )

                if use_subdiv:
                    if ("force_no_subdiv" in s.geom and s.geom["force_no_subdiv"]):
                        _          =  wall.modifiers.new('tri', 'TRIANGULATE')
                        mod_subdiv =  wall.modifiers.new('tri', 'SUBSURF')
                        wall.cycles.use_adaptive_subdivision = True
                        mod_subdiv.subdivision_type = 'SIMPLE'
                        mod_subdiv.levels = 3

                volume += wall.dimensions[0] * wall.dimensions[1] * wall.dimensions[2]

            if volume > max_volume:
                s.geom["biggest_wall_shader"] = ex_wall_shader
                max_volume = volume

        r2 = override_r if override_r else rantom.RantomCache(0.1, name="materials")

        if 'ext_side_wallOBs' in s.geom: # the side may have been merged with the main wall mesh!
            
            count = 0

            for wall in s.geom['ext_side_wallOBs']:
                match r2.weighted_int ([1,1,2], f"merge_win_side_{count}", "do we merge the meshes for walls and walls-edges-around windows") == 0:
                    case 0:
                        key = f"ext_side_wall_{count}"
                        if wall_is_texture:
                            sa ( wall, s.got_wall(r2, key)[0] )
                        else:
                            sa ( wall, s.got_stucco(key, r2) )
                    case 1:
                        key = "ext_side_wall"
                        if wall_is_texture:
                            sa ( wall, s.got_wall(r2,key )[0] )
                        else:
                            sa ( wall, s.got_stucco(key, r2) )
                    case 2:
                        sa ( wall, r2.choice (wall_shaders, "ext_mat_for_int" ))

                count += 1

        if rantom.weighted_int( [3,1], "int_wall_mat_choice", "Interior wall material choice (< 3: plaster else exterior wall material)") == 0:
            int_shader = bpy.data.materials["interior_wall"]
            c = colorsys.hsv_to_rgb(
                r2.uniform(0, 1, "int_wall_plaster_col_h"   ),
                r2.uniform(0, 0.2, "int_wall_plaster_col_s" ),
                r2.uniform(0.7, 1, "int_wall_plaster_col_v" ) )
            int_shader.node_tree.nodes["Diffuse BSDF"].inputs[0].default_value = (c[0], c[1], c[2], 1)
        else:
            int_shader = r2.choice (wall_shaders, "ext_mat_for_int" )

        for ob in s.geom['internal_wallOBs']:
            sa ( ob, int_shader )

        if 'wires' in s.geom:

            match r2.weighted_int([1,1 if len(stucco_wall_shaders) > 0 else 0, 1], "wire_material"):
                case 0:
                    wire_mat = s.got_pvc("wires", r2, col_range=[0.0, 0.2], spec_range=[0, 0.1])
                case 1:
                    wire_mat = r2.choice(stucco_wall_shaders, "pipe_mat_choice_wall_shaders")
                case 2:
                    wire_mat = bpy.data.materials["multi_coloured_wire"]

            for ob in s.geom['wires']:
                sa ( ob, wire_mat )

        match r2.weighted_int([3,1,1,1 if len(stucco_wall_shaders) > 0 else 0], "pipe_material"):
            case 0:
                pipe_mat = s.got_pvc("pipe", r2, col_range=[0, 0.05], spec_range=[0, 0.1])
            case 1:
                pipe_mat = bpy.data.materials["zinc"]
            case 2:
                pipe_mat = s.got_metal(r2, "pipes")
            case 3:
                pipe_mat = r2.choice(stucco_wall_shaders, "pipe_mat_choice_wall_shaders")

        for name in ["drain_pipes", "small_pipes", "gutter"]:
            if name in s.geom:
                for ob in s.geom[name]:
                    sa ( ob, pipe_mat )

        ground_shader = s.got_ground(r2)
        if 'exterior_floor' in s.geom:
            for ob in s.geom['exterior_floor']:
                sa ( ob, ground_shader )

        if 'roof_skirt' in s.geom:
            s.setmat_geonodes(s.geom['roof_skirt'], s.frame_shader(r2).name)

        if 'interior_box' in s.geom:
            for ob in s.geom['interior_box']:
                sa (ob, s.got_interior(r2) )

        for rect in s.geom['windows']:

            wdict = s.geom['windows'][rect]
            wr2 = override_r if override_r else wdict["r2"]
            frame_shader = s.frame_shader(r2)

            if 'frameOBs' in wdict:
                for o in wdict['frameOBs']:
                    sa ( o, frame_shader )

            glass_shader = s.got_glass(r2)
        
            if 'frameGlassOBs' in wdict:
                for o in wdict['frameGlassOBs']:
                    sa ( o, glass_shader )

            if 'blind_fill' in wdict:
                for o in wdict['blind_fill']:
                    sa (o, ex_wall_shader ) # .data.materials.append(ex_wall_shader)

            # lintel/sill/frame:
            if 'surroundOBs' in wdict:
                for idx, surroundOB in enumerate(wdict['surroundOBs']):
                    surround_material_choice = wr2.randrange(3, "surround_material_choice_%d" % idx,
                                                                "Surround (lintel/sill/frame) material choice ( frame, stucco, wood)")
                    match surround_material_choice:
                        # case 0:
                        #     surroundOB.data.materials.append(s.got_brick(f"surround_{idx}_brick"))
                        case 0:
                            sm = frame_shader
                        case 1:
                            sm = s.got_stucco(f"surround_{idx}_stucco", wr2)
                        case 2:
                            sm = s.got_wood(f"surround_{idx}_wood", wr2)

                    sa ( surroundOB, sm )

            if "blinds" in wdict:
                blind_ws = wall_shaders + [frame_shader]

                blind_ws = [w for w in blind_ws if "brick" not in w.name and "wood" not in w.name]

                match wr2.weighted_int([1, 2, 1], "blinds_mat_type"):
                    case 0:
                        blinds_mat = bpy.data.materials["zinc"]
                    case 1:
                        blinds_mat = s.got_metal(wr2, f"blinds_metal")
                    case 2:
                        blinds_mat = s.got_stucco("blinds", wr2)

                match wr2.weighted_int([1, 2 if len(blind_ws) > 0 else 0, 1, 1], "blinds_frame_mat"):
                    case 0:
                        frame_mat = blinds_mat
                    case 1:
                        frame_mat = r2.choice(blind_ws, "blinds_frame_choice_existing_mats")
                    case 2:
                        frame_mat = s.got_metal(wr2, f"blinds_frame_metal")
                    case 3:
                        frame_mat = s.got_stucco("blinds_frame", wr2)

                for obj in wdict["blinds"]:
                    s.setmat_geonodes(obj, frame_mat)
                    s.setmat_geonodes(obj, blinds_mat, key="mat_frame")


            if "balconies_bases" in wdict: # if there is any balcony

                bal_ws = [w for w in wall_shaders if "brick" not in w.name] + [frame_shader]

                sa ( wall, r2.choice(wall_shaders, "ext_mat_for_int"))

                match wr2.weighted_int([4 if len(bal_ws) > 0 else 0, 1, 1], "balcony_mat_type"):
                    case 0:
                        blinds_mat = r2.choice ( bal_ws, "balcony_choice_existing_mats")
                    case 1:
                        blinds_mat = s.got_metal(wr2, f"balcony_metal")
                    case 2:
                        blinds_mat = s.got_stucco("balcony", wr2)


                if "balcony_glass" in wdict:
                    match wr2.weighted_int([1, 2], "balcony_glass_type"):
                        case 0:
                            glass_mat = blinds_mat
                        case 1:
                            glass_mat = s.got_glass(wr2, "balcony", types=[0, 5, 1])
                else:
                    glass_mat = None

                match wr2.weighted_int([2, 2, 1], "balcony_hold_is_wood"):
                    case 0:
                        hold_mat = r2.choice ( bal_ws, "balcony_hold_choice_existing_mats")
                    case 1:
                        hold_mat = frame_shader
                    case 2:
                        hold_mat = s.got_wood("balcony_hold", wr2)

                match wr2.weighted_int([4, 1, 1], "balcony_base_mat_choice"):
                    case 0:
                        base_mat = blinds_mat
                    case 1:
                        base_mat = s.got_stucco("balconies_bases", wr2)
                    case 2:
                        base_mat = s.got_metal(wr2, "balcony_base_metal")

                match wr2.weighted_int([1, 1, 1], "balcony_pillar_mat_choice") == 1:
                    case 0:
                        pillar_mat = blinds_mat
                    case 1:
                        pillar_mat = base_mat
                    case 2:
                        pillar_mat = hold_mat


                for name, mat in [
                    ("balcony_railing_bars", blinds_mat),
                    ("balcony_glass", glass_mat),
                    ("balconies_bases", blinds_mat),
                    ("balcony_hold", hold_mat),
                    ("balcony_hold_line", hold_mat),
                    ("balcony_pillar", pillar_mat),
                    ("balcony_pins", hold_mat),
                    ("balcony_glass", glass_mat),
                ]:
                    if name in wdict:
                        for o in wdict[name]:
                            if not s.setmat_geonodes(o, mat):
                                if len(o.data.materials) == 0:
                                    sa ( o, mat)

    def got_wall(s, r2, name):

        # load wall textures from file
        if "wall_is_texture" in s.geom:

            filepath = os.path.join(config.resource_path, "wall_materials", "walls.blend")
            n = s.geom["wall_is_texture"]

            count = 0
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                for o in data_from.objects:
                    if str(o).startswith("Cube."):
                        count += 1

            x = [y for y in range(count)]
            random.Random(911).shuffle(x)
            x = x[:n]

            target = f"Cube.{format(r2.choice(x, f'wall_texture_{name}'), '03d')}"

            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                for o in data_from.objects:
                    if o == target:
                        data_to.objects = [o]
                        break

            ex_wall_shader = data_to.objects[0].data.materials[0]
            ex_wall_shader.name=f"xxx-{ex_wall_shader.name}"

            use_subdiv = False
            mode = 1
        else:
            # procedural exterior wall texture
            mode = r2.weighted_int([1, 1, 1], f"ext_wall_mat_choice_{name}", "Exterior wall material (Stucco, Brick, Wood-planks)")
            match mode:
                case 0:
                    # stucco
                    ex_wall_shader = s.got_stucco("exterior_wall", r2)
                    use_subdiv = False
                case 1:
                    # brick
                    ex_wall_shader = s.got_brick("exterior_wall", r2)
                    use_subdiv = True
                case 2:
                    # wood
                    ex_wall_shader = bpy.data.materials["wood-plank"].copy()
                    ex_wall_shader.name = "xxx-wood-plank"
                    s.set_params_wood ( ex_wall_shader, "exterior_wall", r2 )
                    ex_wall_shader.node_tree.nodes["Group"].inputs[1].default_value = r2.uniform(0.2, 0.8, f"wood_groove_{name}", "Groove vs. wood ratio")
                    ex_wall_shader.node_tree.nodes["Group"].inputs[12].default_value = r2.uniform(4, 10, "wood_groove_scale", "Scale of frame grooves")
                    bpy.data.node_groups["NodeGroup.002"].nodes["Math.008"].inputs[1].default_value = 1 / r2.uniform(2,4, "wood_grain_horiz_scale")
                    ex_wall_shader.node_tree.nodes["Group"].inputs[22].default_value = r2.randrange(3, "wood_groove_profile")
                    use_subdiv = True

        return ex_wall_shader, use_subdiv, mode

    def env(self, force=False, is_really_night=None):

        is_night = rantom.weighted_int( [19,1],"is_night" ) == 1
        key = ""

        if force:
            is_night = is_really_night
            key="forced_"+str(is_night)

        print (f"is_night: {is_night}")

        sun = bpy.data.objects["Sun"]

        # match random.randrange(4):
        # match rantom.weighted_int( [3,1,1], "sun_distribution_choice" ):
        match rantom.randrange(4, "sun_distribution_choice"):
            # case 0 | 1:
            #     sun.rotation_euler[2] = rantom.gauss(0, 0.5, "sun_z", "Sun rotation around z axis (rads)")
            case 0 | 1 | 2:
                sun.rotation_euler[2] = rantom.uniform(-1.57, 1.57, "sun_z", "Sun rotation around z axis (rads)")
            case 3:
                sun.rotation_euler[2] = rantom.uniform(1.37, 1.57, "sun_z", "Sun rotation around z axis (rads)")
            case 4:
                sun.rotation_euler[2] = rantom.uniform(-1.57, -1.37, "sun_z", "Sun rotation around z axis (rads)")

        # sun.rotation_euler[2] = 0
        sun.rotation_euler[1] = 0
        sun.rotation_euler[0] = rantom.gauss_clamped(0.7, 0.5, 0, 2, "sun_x", "Sun rotation around x axis (rads)")

        if is_night:
            sun.data.energy = rantom.uniform(0.001, 0.5, f"sun_energy_night_{key}")
        else:
            sun.data.energy = max(2, 3 ** rantom.uniform(0.01, 6, f"sun_energy_day_{key}", "Sun brightness"))

        rantom.store("sun_energy", sun.data.energy)

        if random.randrange(5) == 1:
            sun.data.angle = rantom.uniform(0, 1, "sun_angle", "Sun size/shadow sharpness")
        else:
            sun.data.angle = max(0.003, rantom.gauss(0.03, 0.03, "sun_angle", "Sun size/shadow sharpness"))

        rantom.store("sun_size", sun.data.angle)

        # outside texture
        environments = sorted ( glob(f'{config.resource_path}/outside/*.jpg') )
        env_image = bpy.data.images.load(rantom.choice(environments, "ext_skybox", "Exterior environment texture map"))
        env_image.name = "xxx_" + env_image.name
        bpy.data.worlds["World"].node_tree.nodes["Environment Texture"].image = env_image
        bpy.data.worlds["World"].node_tree.nodes["Vector Rotate"].inputs[3].default_value = rantom.uniform(0, 6.2, "ext_z_rot", "Rotation of exterior texture map")  # rotate around z

        if is_night:
            ext_brightness = rantom.uniform(0.01, 0.3, f"ext_brightness_{key}", "Brightness of exterior texture map")  # brightness
        else:
            ext_brightness = rantom.uniform(0.2, 6, f"ext_brightness_{key}", "Brightness of exterior texture map")  # brightness

        bpy.data.worlds["World"].node_tree.nodes["Emission"].inputs[1].default_value = ext_brightness  # brightness

        if is_night:
            int_brightness = rantom.uniform(1, 5, f"interior_brightness_{key}", "Brightness of the interior panorama")
        else:
            int_brightness = rantom.uniform(0.01, 0.1, f"interior_brightness_{key}", "Brightness of the interior panorama")

        bpy.data.materials["interior_pano_shader"].node_tree.nodes["Emission"].inputs[1].default_value = int_brightness

    def got_interior(self, r2):

        # inside texture
        mat = copy ( bpy.data.materials["interior_pano_shader"] )

        internals = sorted ( glob(f'{config.resource_path}/inside/*.jpg') )
        internal_image = bpy.data.images.load(
            rantom.choice(internals, "interior_skybox", "Interior panorama background image"))
        internal_image.name = "xxx_" + internal_image.name
        mat.node_tree.nodes["Environment Texture"].image = internal_image
        mat.node_tree.nodes["Value.001"].outputs[
            0].default_value = rantom.uniform(0, 6.2, "interior_rot",
                                              "Horizontal rotation of interior panorama")  # rotate around z
        mat.node_tree.nodes["Value"].outputs[0].default_value = 0 # rantom.gauss(0,0.03,"interior_blur", "Blur of interior panorama")  # blurryness (0 = none

        return mat

    def got_roof(self, r2):

        mat = bpy.data.materials["roof"].copy()
        mat.name = "xxx-roof"

        mat.node_tree.nodes["hue"].outputs[0].default_value        = rantom.uniform( 0, 1, "roof_colour_hue", "Colour (hue) of roof tiles")
        mat.node_tree.nodes["saturation"].outputs[0].default_value = rantom.uniform_mostly( 0.5, 0.2, 0, 3, "roof_colour_saturation", "Colour (sat) of roof tiles")
        mat.node_tree.nodes["dirt"].outputs[0].default_value       = rantom.uniform( 0, 8, "roof_dirt", "Colour (hue) of roof tiles")
        mat.node_tree.nodes["wet"].outputs[0].default_value        = rantom.uniform_mostly( 0.5, 0.1, 0, 1, "roof_shiny", "How wet is the roof?")

        return mat

    def got_ground(self, r2):
        mat = bpy.data.materials["ground"].copy()
        mat.name = "xxx-ground"

        mat.node_tree.nodes["brightness"].outputs[0].default_value = rantom.uniform( 0.001, 0.02, "concrete_brightness")
        mat.node_tree.nodes["flecks"].outputs[0].default_value = rantom.uniform( 0.6, 0.75, "concrete_flecks")
        mat.node_tree.nodes["cracks"].outputs[0].default_value = rantom.uniform( 0, 0.8, "concrete_cracks")
        mat.node_tree.nodes["Noise Texture"].inputs[2].default_value = rantom.uniform( 140, 200, "concrete_lump_scale")

        return mat

    def got_glass(self, r2, name="win", types=[1,2,8]):

          r, g, b = r2.uniform(0.8, 1, f"glass_color_r_{name}"), r2.uniform(0.95, 1, f"glass_color_g_{name}"), r2.uniform(0.95, 1, f"glass_color_b_{name}")

          match r2.weighted_int(types, f"glass_type_choice_{name}", "Frame material ( Wood)"):
            case 0:  # leaded glass
                mat = bpy.data.materials["leaded_glass"].copy()
            

                if r2.randrange(3, f"leaded_angle_2_{name}", "Diamond/square rotation") == 0:
                    mat.node_tree.nodes["Value"].outputs[0].default_value = np.pi/4. # square vertical lead
                    mat.node_tree.nodes["Value.004"].outputs[0].default_value = np.pi/4.
                else:
                    mat.node_tree.nodes["Value"].outputs[0].default_value = r2.gauss(np.pi/4, np.pi/8, f"leaded_glass_angle_{name}") # diangonal.diamond angle of lead
                    mat.node_tree.nodes["Value.004"].outputs[0].default_value = 0

                mat.node_tree.nodes["Value.002"].outputs[0].default_value = r2.uniform(100, 240, f"leaded_glass_scale_{name}")
                mat.node_tree.nodes["Value.001"].outputs[0].default_value = r2.uniform(0.8, 1.10, f"leaded_glass_thickness_{name}")
                mat.node_tree.nodes["Value.003"].outputs[0].default_value = r2.uniform(0, 0.04, f"leaded_glass_wobble_{name}")


                mat.node_tree.nodes["Glass BSDF"].inputs[1].default_value = 0


                mat.node_tree.nodes["Glass BSDF"].inputs[0].default_value = (r,g,b,1)
                mat.node_tree.nodes["Normal Map"].inputs[0].default_value = r2.gauss(0, 0.01, f"glass_noise_strength_{name}", "Amount of distortion to glass normal")
                mat.node_tree.nodes["Noise Texture"].inputs[2].default_value = max(0, r2.uniform(3, 6, f"glass_noise_scale_{name}", "Spatial extend of glass normal wobble (wobble)"))  # noise scale

                return mat
            case 1: # privacy glass
                glass_shader = bpy.data.materials["glass"].copy()

                glass_shader.node_tree.nodes["Glass BSDF"].inputs[1].default_value = r2.uniform(0, 0.5, f"glass_roughness_{name}", "Roughness of glass pane")

                glass_shader.node_tree.nodes["Glass BSDF"].inputs[0].default_value = (r,g,b,1)
                glass_shader.node_tree.nodes["Normal Map"].inputs[0].default_value = r2.gauss(0, 0.01, f"glass_noise_strength_{name}", "Amount of distortion to glass normal")
                glass_shader.node_tree.nodes["Noise Texture"].inputs[2].default_value = max(0, r2.uniform(-3, 5, f"glass_noise_scale_{name}", "Scale distortion to glass normal"))  # noise scale

                return glass_shader
            case 2: # clear glass
                glass_shader = bpy.data.materials["glass"].copy()

                glass_shader.node_tree.nodes["Glass BSDF"].inputs[1].default_value = 0
                glass_shader.node_tree.nodes["Glass BSDF"].inputs[0].default_value = (r,g,b,1)
                glass_shader.node_tree.nodes["Normal Map"].inputs[0].default_value = r2.gauss(0, 0.01, f"glass_noise_strength_{name}", "Amount of distortion to glass normal")
                glass_shader.node_tree.nodes["Noise Texture"].inputs[2].default_value = max(0, r2.uniform(2, 6, f"glass_noise_scale_{name}", "Spatial extend of glass normal wobble (wobble)"))  # noise scale

                return glass_shader

    def got_metal(self, r2, name="metal"):

        mat = bpy.data.materials["frame_metal"].copy()
        mat.name = "xxx-"+mat.name
        mtn = mat.node_tree.nodes

        match r2.weighted_int([6,2,1], f"metal_color_distribution_{name}", f"color for {name}"):
            case 0: # metalic grey
                col = r2.uniform(0.001, 0.03, f"grey_color_{name}" )
                color = (col, col, col, 1)
            case 1: # black/grey/white paint
                col = r2.uniform(0, 0.7, f"grey_color_{name}")
                color =  (col, col, col, 1)
            case 2: # bright paint
                color = utils.hsv_to_rgb(
                    r2.uniform(0, 1, f"{name}_paint_hue"),
                    r2.uniform(0, 0.7, f"{name}_paint_sat"),
                    0.2 )

        if r2.weighted_int([3,1], f"paint_over_rust_{name}") == 1:  # rust etc... under paint
            mtn["painted_rust"].outputs[0].default_value = 0
            mtn["paint_col"].inputs[1].default_value = color
        else:
            mtn["painted_rust"].outputs[0].default_value = 1
            mtn["ColorRamp.001"].color_ramp.elements[4].color = color   # paint color

        mtn["rust_edges"].outputs[0].default_value = r2.uniform_mostly(0.3, 1.8, 0.4, 1.8, f"{name}_edge_rust")
        mtn["edge_rust_scale"].outputs[0].default_value = 3 ** r2.uniform(1, 4, f"{name}_edge_rust_scale" )
        mtn["rust_everywhere"].outputs[0].default_value = r2.uniform(2.5,6 , f"{name}_rust_everywhere" )
        mtn["specular"].outputs[0].default_value = r2.uniform_mostly(0.3, 0.5, 0.5, 0.9, f"{name}_specular")

        mtn["random_offset"].inputs[0].default_value = ( r2.uniform(-1e2, 1e2, f"{name}_texture_offset_x" ),
                                                         r2.uniform(-1e2, 1e2, f"{name}_texture_offset_y" ),
                                                         r2.uniform(-1e2, 1e2, f"{name}_texture_offset_z" ) )

        return mat

    def frame_shader(self, r2):

        r = r2.weighted_int( [3,2], "frame_mat_choice", "Frame material (Stucco, Wood)" )
           
        if r == 0:
            return self.got_wood("frame", r2)
        else:
            return self.got_pvc ("frame", r2)

    def got_pvc(s, name, r2, col_range=[0.1, 0.5], spec_range=[0, 0.5]  ):

        mat = bpy.data.materials["pvc"].copy()
        grey = r2.uniform(col_range[0], col_range[1], f"pvc_grey_{name}", "Color of PVC")
        mat.node_tree.nodes["RGB"].outputs[0].default_value = (grey, grey, grey, 1) # color
        mat.node_tree.nodes["Value"].outputs[0].default_value = r2.uniform(0.4, 0.8, f"pvc_dirt_{name}", f"PVC {name} frame dirt amount") # dirt
        mat.node_tree.nodes["Principled BSDF"].inputs[7].default_value = r2.uniform(spec_range[0], spec_range[1], f"pvc_specular_{name}")

        mat.name="xxx-pvc"
        return mat

    def got_brick(s, name, r2):

        brick_shader = copy ( bpy.data.materials["brick"] )

        match r2.weighted_int( [6,2,1], "brick_shape_type"):
            case 0:
                width = 1.7  # uk brick sizes
                height = 0.32
            case 1:
                width = 3.4  # breeze block
                height = 1.7
            case 2:
                width = r2.uniform(1, 4, "brick_width", "Brick material brick width")  # width
                height = r2.uniform(0.3, 2, "brick_height", "Brick material brick height")  # height

        brick_shader.node_tree.nodes["Group"].inputs[2].default_value = width
        brick_shader.node_tree.nodes["Group"].inputs[3].default_value = height

        brick_shader.node_tree.nodes["Group"].inputs[5].default_value = max (0, r2.uniform(0, 0.04, "brick_bevel","Brick material brick bevel") )  # bevel
        brick_shader.node_tree.nodes["Group"].inputs[6].default_value = r2.uniform(0, 0.05, "brick_round","Brick material rounded brick corner amount")  # round corner
        brick_shader.node_tree.nodes["Group"].inputs[7].default_value = abs(r2.gauss(0, 0.8, "brick_rot", "Brick material brick rotation "))  # rotation
        
        if r2.randrange(8, "brick_use_random_offset") == 0:
            brick_shader.node_tree.nodes["Group"].inputs[8].default_value = r2.uniform(0.1, 0.4,"brick_rand_offset","Brick material random brick offset per row")  # random offset
        else:
            brick_shader.node_tree.nodes["Group"].inputs[8].default_value = 0

        offset = 0
        match r2.weighted_int( [5,1,0,1], "brick_regular_offset_type"):
            case 0:
                offset = 0.5
            case 1:
                offset = 0.250
            case 2:
                offset = 0.
            case 3:
                offset = r2.uniform(0.3, 0.7,"brick_regular_offset","Brick material constant brick offset per row")

        brick_shader.node_tree.nodes["Group"].inputs[9].default_value = offset

        wall_col_1_v = r2.uniform(0.1, 0.3, "brick_col1_value")

        h = r2.uniform(0.0, 0.13, "brick_col_hue")

        bs1 = r2.uniform(0.0, 0.85, "brick_sat_1")
        c = utils.hsv_to_rgb(h, bs1, wall_col_1_v / 2)
        brick_shader.node_tree.nodes["ColorRamp.002"].color_ramp.elements[1].color = c  # brick color 1 dark

        c = utils.hsv_to_rgb(h, r2.uniform(0.5, 0.85, "brick_col_sat_2"), wall_col_1_v)
        brick_shader.node_tree.nodes["ColorRamp.002"].color_ramp.elements[2].color =c  # brick color 1 light

        wall_col_1_v = r2.uniform(0.1, 0.3, "brick_col2_value")

        c = utils.hsv_to_rgb(r2.uniform(0.0, 0.06, "brick_mat_c2_d_hue"), r2.uniform(0.0, 0.85, "brick_mat_c2_d_value"), wall_col_1_v / 2)
        brick_shader.node_tree.nodes["ColorRamp.003"].color_ramp.elements[3].color = c  # brick color 2 dark
        c = utils.hsv_to_rgb(r2.uniform(0.0, 0.06, "brick_mat_c2_l_hue"), r2.uniform(0.0, 0.85, "brick_mat_c2_l_sat"), wall_col_1_v)
        brick_shader.node_tree.nodes["ColorRamp.003"].color_ramp.elements[4].color = c  # brick color 2 light
        brick_shader.node_tree.nodes["Group"].inputs[2].default_value = 1.7  # width

        brick_shader.node_tree.nodes["tilt"].outputs[0].default_value = r2.gauss_clamped(3, 2, 0.5, 10, "brick_tilt")
        if height > 1.4:
            mortar_width = r2.uniform(0.00,0.015, "brick_mortar_width") # big bricks = less mortar
        else:
            mortar_width = r2.uniform(0.02, 0.05, "brick_mortar_width")

        brick_shader.node_tree.nodes["mortar_width"].outputs[0].default_value = mortar_width
        brick_shader.node_tree.nodes["Value.005"].outputs[0].default_value = r2.uniform(0,10000, "brick_random_seed", "Random seed for brick shader noise materials")
        brick_shader.node_tree.nodes["Group"].inputs[11].default_value = r2.uniform_mostly(0.5, 0, 0,1, "how_much_to_split_bricks") ## split bricks

        return brick_shader


    def got_stucco(s, name, r2, color=None):

            stucco = copy ( bpy.data.materials["stucco"] )

            if color == None:
                if r2.randrange(3, "stucco_colored_wall") == 0:
                    color = utils.hsv_to_rgb(
                        r2.uniform(0, 1, "wall_col_h"),
                        r2.gauss_clamped(0.7, 0.1, 0,1, "wall_col_s"),
                            r2.gauss_clamped(0.2, 0.1, 0.05, 1, "wall_col_v")
                            if random.random() < 0.4 else
                            r2.gauss_clamped(0.9, 0.3, 0,1, "wall_col_v"))
                else:
                    c = r2.gauss(0.4, 0.2, "stucco_grey_color", "Shade of grey for chipped areas under stucco")
                    color = (c,c,c * r2.uniform(0.7, 1, "stucco_yellow_greys"),1)
                    
            stucco.node_tree.nodes["RGB"].outputs[0].default_value = color

            # color of concrete chips
            if r2.weighted_int([1,1], "chip_colors") == 0:
                c = r2.gauss_clamped(0.2, 0.2, 0.15, 0.5, "stucco_chip_grey", "Shade of grey for chipped areas under stucco")
                stucco.node_tree.nodes["RGB.001"].outputs[0].default_value = (c, c, c*0.8, 1)
            else:
                h,s,v = utils.rgb_to_hsv(color[0], color[1], color[2])
                v *= r2.uniform(0.2, 0.8, "chip_color_vmul")
                s *= r2.uniform(0.3, 1, "chip_color_smul")
                rgb = utils.hsv_to_rgb(h,s,v)
                stucco.node_tree.nodes["RGB.001"].outputs[0].default_value = (rgb[0], rgb[1], rgb[2], 1)


            if r2.weighted_int([1,1], "stucco_clean_or_dirty") == 0: # dirty stucco
                # dirt ammount
                stucco.node_tree.nodes["Value.002"].outputs[0].default_value = r2.uniform(0.5, 1.2, "stucco_dirt", "Stucco material dirt")
                # edge_cracks on geometry corners
                stucco.node_tree.nodes["edge_cracks"].outputs[0].default_value = r2.gauss_clamped(0.3, 1, 0, 0.3, "stucco_c_cracks", "Stucco chips on geometry corners")
                # size of cracks. 0.26 = some.
                stucco.node_tree.nodes["Value"].outputs[0].default_value = r2.uniform(0.1, 0.22, "stucco_crack_size", "Size of stucco cracks")
                stucco.node_tree.nodes["chip_height"].outputs[0].default_value = r2.uniform(0.28, 2.5, "stucco_crack_height", "How height do the chips run?")
                stucco.node_tree.nodes["damage_mask_rough"].outputs[0].default_value = r2.uniform(7, 15, "stucco_damage_mask_detail", "shape of the damaged areas")
            else: # clean stucco
                # dirt ammount
                stucco.node_tree.nodes["Value.002"].outputs[0].default_value = r2.uniform(0.0, 0.4, "stucco_dirt", "Stucco material dirt")
                # edge_cracks on geometry corners
                stucco.node_tree.nodes["edge_cracks"].outputs[0].default_value = r2.uniform(0, 0.1, "stucco_c_cracks", "Stucco chips on geometry corners")
                # size of cracks. 0.26 = some.
                stucco.node_tree.nodes["Value"].outputs[0].default_value = r2.uniform(-0.1, 0.05, "stucco_crack_size", "Size of stucco cracks")
                stucco.node_tree.nodes["chip_height"].outputs[0].default_value = r2.uniform(0, 0.1, "stucco_crack_height", "How height do the chips run?")


            stucco.node_tree.nodes["Value.003"].outputs[0].default_value = r2.uniform(-10000,10000, "stucco_random_seed", "Random seed for stucco noise materials")
            stucco.node_tree.nodes["Noise Texture.004"].inputs[2].default_value = r2.uniform(20,60, "stucco_small_bump_size", "Size of smaller wobbles in stucco")

            return stucco

    def got_wood(s, name, r2):

        return s.set_params_wood ( copy ( bpy.data.materials["wood"] ), name, r2 )


    def set_params_wood(s, wm, name, r2):

        match r2.weighted_int([1,1,1], name+"wood_mat_choice", "Frame material ( Wood)"):
           
            case 0:  # bare wood

                h = r2.gauss(0.06, 0.015, f"bare_wood_hue_{name}")
                s = r2.uniform(0.5, 0.95, f"bare_wood_sat_{name}")
                v = r2.uniform(0.05, 1, f"bare_wood_value_{name}")

                s2 = s + r2.gauss_clamped(0, 0.1, 0,1, f"bare_wood_sat_2_offset_{name}")
                v2 = v + r2.gauss_clamped(0, 0.2, 0,1, f"bare_wood_value_2_offset_{name}")

                s3 = s + r2.gauss_clamped(0, 0.1, 0,1, f"bare_wood_sat_3_offset_{name}")
                v3 = v + r2.gauss_clamped(0, 0.2, 0,1, f"bare_wood_value_3_offset_{name}")


                wm.node_tree.nodes["Group"].inputs[0].default_value = 0.80  # stains
                wm.node_tree.nodes["Group"].inputs[1].default_value = 1#r2.uniform(0.2, 0.8, f"wood_groove_{name}", "Groove vs. wood ratio")
                wm.node_tree.nodes["Group"].inputs[2].default_value = 0.0  # dust
                wm.node_tree.nodes["Group"].inputs[3].default_value = 0.0  # dust (groove)
                wm.node_tree.nodes["Group"].inputs[4].default_value = utils.hsv_to_rgb(h, s ,v ) # (1, 0.53595, 0.151237, 1) # Base 1
                wm.node_tree.nodes["Group"].inputs[5].default_value = utils.hsv_to_rgb(h, s2 ,v2 )#(0.623961, 0.254152, 0.0822827, 1) # Base 2
                wm.node_tree.nodes["Group"].inputs[6].default_value = utils.hsv_to_rgb(h, s3 ,v3 ) #(0.603828, 0.291834, 0.107023, 1)  # Base 3
                wm.node_tree.nodes["Group"].inputs[7].default_value = utils.hsv_to_rgb(h, s ,v/2 )#(0.259571, 0.127618, 0.0767914, 1)  # Accentuation
                wm.node_tree.nodes["Group"].inputs[8].default_value = (0.59733, 0.552792, 0.379261, 1)  # Dust color
                wm.node_tree.nodes["Group"].inputs[9].default_value = (0.00543223, 0.00445329, 0, 1)  # Stains color
                wm.node_tree.nodes["Group"].inputs[10].default_value = r2.uniform(20, 60, f"wood_scale_{name}", "Scale of frame wood texture ") # 21  # wood scale
                wm.node_tree.nodes["Group"].inputs[11].default_value = 110  # wood grain scale
                wm.node_tree.nodes["Group"].inputs[12].default_value = 0  # groove scale
                wm.node_tree.nodes["Group"].inputs[13].default_value = r2.uniform(1, 3, f"wood_stains_scale_{name}", "Scale of frame wood texture stains ")  # stains scale
                wm.node_tree.nodes["Group"].inputs[14].default_value = 1.3  # bump strength
                wm.node_tree.nodes["Group"].inputs[15].default_value = 0.250  # wood bump
                wm.node_tree.nodes["Group"].inputs[16].default_value = 0.188  # groove bump
                wm.node_tree.nodes["Group"].inputs[17].default_value = 0.1 # clearcoat bump
                wm.node_tree.nodes["Group"].inputs[18].default_value = 1.0  # wood roughness
                wm.node_tree.nodes["Group"].inputs[19].default_value = 1.3  # groove roughness
                wm.node_tree.nodes["Group"].inputs[20].default_value = 0.864  # stains roughness
                wm.node_tree.nodes["Group"].inputs[21].default_value = 0.1  # displacement

                wm.node_tree.nodes["Principled BSDF"].inputs[14].default_value = 0  # clearcoat


            case 1:  # painted wood

                h = s.less_pink_hue ( f"painted_wood_hue_{name}", r2 )

                s = r2.gauss_clamped(0.8, 0.1, 0,1, f"painted_wood_sat_{name}") \
                    if random.randrange(3) == 0 else \
                    r2.gauss_clamped(0.0, 0.1, 0,1, f"painted_wood_sat_{name}")

                v = r2.gauss_clamped(0.8, 0.3, 0,1, f"painted_wood_value_{name}")

                c =  utils.hsv_to_rgb(h,s,v)
                s2 = s + r2.gauss_clamped(0, 0.3, 0,1, f"painted_sat_2_offset_{name}")
                v2 = v + r2.gauss_clamped(0, 0.3, 0,1, f"painted_value_2_offset_{name}")

                wm.node_tree.nodes["Group"].inputs[0].default_value = r2.uniform(0.5, 1, f"wood_stains_{name}", "Frame wood texture stains")  # stains
                wm.node_tree.nodes["Group"].inputs[1].default_value = 1#r2.uniform(0.2, 0.8, f"wood_groove_{name}", "Groove vs. wood ratio") # groove
                wm.node_tree.nodes["Group"].inputs[2].default_value = 0.9  # dust
                wm.node_tree.nodes["Group"].inputs[3].default_value = 0.0  # dust (groove)
                wm.node_tree.nodes["Group"].inputs[4].default_value = utils.hsv_to_rgb(h,s2,v2) # (1, 0.53595, 0.151237, 1) # Base 1
                wm.node_tree.nodes["Group"].inputs[5].default_value = c # (0.623961, 0.254152, 0.0822827, 1) # Base 2
                wm.node_tree.nodes["Group"].inputs[6].default_value = c # (0.603828, 0.291834, 0.107023, 1)  # Base 3
                wm.node_tree.nodes["Group"].inputs[7].default_value = c# (0.259571, 0.127618, 0.0767914, 1)  # Accentuation
                wm.node_tree.nodes["Group"].inputs[8].default_value = utils.hsv_to_rgb( r2.gauss(0.06, 0.015, f"painted_wood_dust_hue_{name}"), r2.uniform(0.5, 0.95, f"painted_wood_dust_sat_{name}") ,r2.uniform(0.05, 1, f"painted_wood_dust_value_{name}") ) # (0.59733, 0.552792, 0.379261, 1)  # Dust color
                wm.node_tree.nodes["Group"].inputs[9].default_value = utils.hsv_to_rgb( r2.uniform(0, 1, f"wood_frame_stains_col_h_{name}"), r2.gauss_clamped(0.7, 0.1, 0,1, f"wood_frame_stains_col_s_{name}"), r2.gauss_clamped(0.8, 0.3, 0,1, f"wood_frame_stains_col_v_{name}") )
                wm.node_tree.nodes["Group"].inputs[10].default_value = r2.uniform(20, 60, f"wood_scale_{name}", "Scale of frame wood texture") # 21  # wood scale
                wm.node_tree.nodes["Group"].inputs[11].default_value = 110  # wood grain scale
                wm.node_tree.nodes["Group"].inputs[12].default_value =  r2.uniform(2, 8, f"wood_frame_groove_scale_{name}", "Scale of wood planks in frame") # groove scale
                wm.node_tree.nodes["Group"].inputs[13].default_value =  r2.uniform(1, 4, f"wood_stains_scale_{name}", "Scale of frame wood texture stains ")  # stains scale
                wm.node_tree.nodes["Group"].inputs[14].default_value = 1.0  # bump strength
                wm.node_tree.nodes["Group"].inputs[15].default_value = 0.4  # wood bump
                wm.node_tree.nodes["Group"].inputs[16].default_value = 0.006  # groove bump
                wm.node_tree.nodes["Group"].inputs[17].default_value = 0.01 # clearcoat bump
                wm.node_tree.nodes["Group"].inputs[18].default_value = 2  # wood roughness
                wm.node_tree.nodes["Group"].inputs[19].default_value = 0  # groove roughness
                wm.node_tree.nodes["Group"].inputs[20].default_value = 0  # stains roughness
                wm.node_tree.nodes["Group"].inputs[21].default_value = 0.1  # displacement

                wm.node_tree.nodes["Principled BSDF"].inputs[14].default_value = 0  # clearcoat

            case 2:  # polished wood

                h = r2.gauss(0.06, 0.015, f"polished_wood_hue_{name}")
                s = r2.uniform(0.6, 0.8, f"polished_wood_sat_{name}")
                v = r2.uniform(0.01, 0.1, f"polished_wood_value_{name}")

                s2 = s + r2.gauss_clamped(0, 0.1, 0,1, f"polished_wood_sat_2_offset_{name}")
                v2 = v + r2.gauss_clamped(0, 0.2, 0,1, f"polished_wood_value_2_offset_{name}")

                s3 = s + r2.gauss_clamped(0, 0.1, 0,1, f"polished_wood_sat_3_offset_{name}")
                v3 = v + r2.gauss_clamped(0, 0.2, 0,1, f"polished_wood_value_3_offset_{name}")

                wm.node_tree.nodes["Group"].inputs[0].default_value = r2.uniform(0, 0.2, f"wood_stains_{name}", "Frame wood texture stains")  # stains
                wm.node_tree.nodes["Group"].inputs[1].default_value = 1#r2.uniform(0.2, 0.8, f"wood_groove_{name}", "Groove vs. wood ratio")
                wm.node_tree.nodes["Group"].inputs[2].default_value = 0.0  # dust
                wm.node_tree.nodes["Group"].inputs[3].default_value = 0.0  # dust (groove)
                wm.node_tree.nodes["Group"].inputs[4].default_value = utils.hsv_to_rgb(h, s ,v ) # (1, 0.53595, 0.151237, 1) # Base 1
                wm.node_tree.nodes["Group"].inputs[5].default_value = utils.hsv_to_rgb(h, s2 ,v2 )#(0.623961, 0.254152, 0.0822827, 1) # Base 2
                wm.node_tree.nodes["Group"].inputs[6].default_value = utils.hsv_to_rgb(h, s3 ,v3 ) #(0.603828, 0.291834, 0.107023, 1)  # Base 3
                wm.node_tree.nodes["Group"].inputs[7].default_value =(0.001, 0.00102126, 0.00121405, 1)#(0.259571, 0.127618, 0.0767914, 1)  # Accentuation
                wm.node_tree.nodes["Group"].inputs[8].default_value = (0.59733, 0.552792, 0.379261, 1)  # Dust color
                wm.node_tree.nodes["Group"].inputs[9].default_value = (0.00543223, 0.00445329, 0, 1)  # Stains color
                wm.node_tree.nodes["Group"].inputs[10].default_value = r2.uniform(30, 80, f"wood_scale_{name}", "Scale of frame wood texture ") # 21  # wood scale
                wm.node_tree.nodes["Group"].inputs[11].default_value = r2.uniform(60, 120, f"wood_grain_scale_{name}", "Scale of frame wood grain  ") # 21  # wood scale
                wm.node_tree.nodes["Group"].inputs[12].default_value =  r2.uniform(2, 8, f"wood_frame_groove_scale_{name}", "Scale of wood planks in frame") # groove scale
                wm.node_tree.nodes["Group"].inputs[13].default_value = 2.4
                wm.node_tree.nodes["Group"].inputs[14].default_value = 1.3  # bump strength
                wm.node_tree.nodes["Group"].inputs[15].default_value = 0.05  # wood bump
                wm.node_tree.nodes["Group"].inputs[16].default_value = 0.0188  # groove bump
                wm.node_tree.nodes["Group"].inputs[17].default_value = 0.01 # clearcoat bump
                wm.node_tree.nodes["Group"].inputs[18].default_value = 1.0  # wood roughness
                wm.node_tree.nodes["Group"].inputs[19].default_value = 0.3  # groove roughness
                wm.node_tree.nodes["Group"].inputs[20].default_value = 0.63  # stains roughness
                wm.node_tree.nodes["Group"].inputs[21].default_value = 0.1  # displacement

                wm.node_tree.nodes["Principled BSDF"].inputs[14].default_value =  r2.uniform(0.6, 1, f"clear_coat_{name}", "Wood frame clearcoat") # clearcoat
        
        return wm

    def less_pink_hue(s, name, r2):
        # hue in {0..0.15} or {0.6...0.7}
        match random.randrange(2):
            case 0:
                return r2.uniform(0, 0.15, f"less_pink_distribution_{name}")
            case 1:
                return r2.uniform(0.5, 0.65, f"less_pink_distribution_{name}")

    def vienna_distribution(s, r2, name, sat_low = 0.2, sat_high=0.8):

        col = r2.uniform(0.3, 0.8, f"color_distribution_grey_{name}")

        match r2.randrange(4, f"color_distribution_{name}", f"color for {name}"):
            case 0:
                return (col, col, col, 1)
            case 1:
                return (col, col, col*0.8, 1)
            case 2:
                return (col, col, col*1.2, 1)
            case 3:
                return utils.hsv_to_rgb(
                    s.less_pink_hue(name, r2),
                    r2.uniform(sat_low, sat_high, f"color_distribution_highsat_{name}_s"),
                    r2.uniform(0.2, 0.8, f"color_distribution_highsat_{name}_v"))

    def got_blinds(s, r2, use_wood = False):

        match r2.randrange(2 + (1 if use_wood else 0), "blinds_mat_choice", "material for slats/blinds"):
            case 0:
                # pvc
                return s.got_pvc ("frame", r2)
            case 1:
                # painted metal
                mat = bpy.data.materials["venetian"].copy()
                mat.name = "xxx-venetian"
                mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value = s.vienna_distribution(r2, "blinds_metal_color", sat_low=0.8, sat_high=0.8)
                return mat
            case 2:
                # wood
                slat_shader = bpy.data.materials["wood"].copy()
                slat_shader.name = "xxx-blinds-wood"
                s.set_params_wood ( slat_shader, "blind_slats", r2 )
                return slat_shader

    def got_ext_shutters(s, r2):

        match r2.randrange(3, "external_shutters_mat_choice", "material for external shutters"):
            case 0:
                # pvc
                return s.got_pvc ("frame", r2)
            case 1:
                # wood
                mat = bpy.data.materials["wood"].copy()
                mat.name = "xxx-wood"
                s.set_params_wood ( mat, "shutter", r2 )
                # mat.node_tree.nodes["Group"].inputs[12].default_value = rantom.uniform(4, 10, "wood_groove_scale", "Scale of frame grooves")
                # bpy.data.node_groups["NodeGroup.002"].nodes["Math.008"].inputs[1].default_value = 1 / rantom.uniform(2,4, "wood_grain_horiz_scale")

                return mat
            case 2:
                # stucco
                mat = s.got_stucco("extn-shutters", r2)
                return mat

    def curtain_colors(s, r2):

        h1 = r2.uniform(0, 1, "curtain_color_hue")
        s1 = r2.uniform(0, 1, "curtain_color_sat")
        v1 = r2.uniform(0.4, 1, "curtain_color_value")

        match r2.randrange(5, "curtain_color_mech"):
            case 0:
                h2 = h1 + r2.gauss(0, 0.1, "curtain_color_h2_offset")
                s2 = s1
                v2 = v1

                h3 = h1 + r2.gauss(0, 0.1, "curtain_color_h3_offset")
                s3 = s1
                v3 = v1
            case 1:
                h2 = h1
                s2 = s1
                v2 = v1 + r2.uniform(0.2, 0.4, "curtain_color_v2_offset")

                h3 = h1 
                s3 = s1
                v3 = v1 - r2.uniform(0.2, 0.4, "curtain_color_v3_offset")
            case 2:
                h2 = h1 + 1.51
                s2 = s1
                v2 = v1

                h3 = h1 
                s3 = s1
                v3 = v1 * 0.4
            case 3: 
                h2 = 0 # white
                s2 = 0
                v2 = r2.uniform(0.5, 0.9, "curtain_color_v2_range")

                h3 = h1 
                s3 = s1
                v3 = v1 * r2.uniform(0, 1, "curtain_color_v3_factor")

            case 4: 
                h2 = h1 
                s2 = s1
                v2 = v1

                h1 = 0 # white
                s2 = 0
                v1 = r2.uniform(0.5, 0.9, "curtain_color_v1_range")

                h3 = h1 
                s3 = s1
                v3 = v1 * r2.uniform(0, 1, "curtain_color_v3_factor")

        return utils.hsv_to_rgb(h1,s1,v1),utils.hsv_to_rgb(h2,s2,v2),utils.hsv_to_rgb(h3,s3,v3),


    def got_curtain(s, r2):

        match r2.randrange(3, "curtain_mat_choice", "material for curtains"):
            case 0:
                # two sided curtain
                mat = bpy.data.materials["curtain_two_sided"].copy()
                 # front of curtain
                mat.node_tree.nodes["front_color"].inputs[0].default_value = utils.hsv_to_rgb(
                    r2.uniform(0, 1, "curtain_bright_front_v"),
                    r2.uniform(0.8, 1, "curtain_bright_front_s"),
                    r2.uniform(0.1, 0.9, "curtain_bright_front_v"))
                # back of curtain
                col = r2.uniform(0.6, 0.9, f"color_distribution_grey_curtains")
                mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value = (col, col, col * r2.uniform(0.9,1, "cream_curtain_back"), 1) 
                mat.node_tree.nodes["Principled BSDF"].inputs[21].default_value =  r2.uniform(0.95, 1, "curtain_two_sided_transparency" )

            case 1:
                mat = bpy.data.materials["curtain_ugly_pattern"].copy()
                
                mat.node_tree.nodes["pattern_select"].outputs[0].default_value = r2.randrange(4, "curtain_pattern_type")

                # parameterize all the patterns:
                # stripes
                mat.node_tree.nodes["Wave Texture.001"].bands_direction = 'X' if r2.randrange(2, "curtain_stripe_direction") ==0 else 'Y'
                mat.node_tree.nodes["Wave Texture.001"].inputs[1].default_value = r2.uniform(1, 6, "stripe_scale")
                s_width = r2.uniform(0.2, 0.8, "curtain_stripe_pattern")
                mat.node_tree.nodes["Map Range.002"].inputs[1].default_value = s_width
                mat.node_tree.nodes["Map Range.002"].inputs[2].default_value = s_width + 0.001

                # checkers
                mat.node_tree.nodes["Vector Rotate"].inputs[3].default_value = r2.randrange(2, "curtain_checker_rotation") * 1.51
                mat.node_tree.nodes["Checker Texture"].inputs[3].default_value = r2.uniform(16, 60, "curtain_checker_scale")

                # dots
                mat.node_tree.nodes["Voronoi Texture"].inputs[5].default_value = r2.uniform_mostly(0.3, 0, 0,1, "curtain_polka_rand" )
                mat.node_tree.nodes["Voronoi Texture"].inputs[2].default_value = r2.uniform(3, 20, "curtain_polka_scale" )
                d_width = r2.uniform(0.2, 0.8, "curtain_polka_dot_distance")
                mat.node_tree.nodes["Map Range.001"].inputs[1].default_value = d_width
                mat.node_tree.nodes["Map Range.001"].inputs[2].default_value = d_width + r2.uniform_mostly(0.5, 0.001, 0,0.3, "curtain_polka_fuzzy_radius" )

                # tile/brick texture
                mat.node_tree.nodes["Brick Texture"].offset = r2.uniform(0, 1, "curtain_tile_offset" )
                mat.node_tree.nodes["Brick Texture"].inputs[4].default_value = r2.uniform(0.2, 2.5, "curtain_tile_scale" )
                mat.node_tree.nodes["Brick Texture"].inputs[9].default_value = r2.uniform(0.01, 0.3, "curtain_tile_vert" )
                mat.node_tree.nodes["Brick Texture"].squash = r2.uniform(0.2, 0.4, "curtain_tile_horiz" )

                c1, c2, c3 = s.curtain_colors(r2)                
                mat.node_tree.nodes["col_a"].outputs[0].default_value = c1
                mat.node_tree.nodes["col_b"].outputs[0].default_value = c2
                mat.node_tree.nodes["stripe_col"].outputs[0].default_value = c3

                mat.node_tree.nodes["Principled BSDF"].inputs[21].default_value =  r2.uniform(0.95, 1, "curtain_pattern_transparency" )

                mat.node_tree.nodes["stripe_width"].outputs[0].default_value = r2.uniform_mostly(0.5, 0, 0.01,0.3, "curtain_ugly_stripe_width" )

            case 2:
                mat = bpy.data.materials["curtain_lace"].copy()
                mat.node_tree.nodes["Map Range"].inputs[3].default_value = r2.uniform(0, 0.1, "lace_transparency" )
        
        mat.name = "xxx-curtain"
        return mat

    def set_shader_all_objs(s, shader):
        s.all_objs( lambda s, obj: bpy.data.materials[shader] )

    def all_objs(s, f):
        a = []

        for cat in ['exterior_wallOBs', 'exterior_wallframeOBs']:
            if cat in s.geom:
                for walls in s.geom[cat]:
                    a.extend ( walls )

        for cat in ['roofses',
            'exterior_junk', 'exterior_floor', 'internal_wallOBs', 'ext_side_wallOBs', 'interior_box', 'wall_signs', 'wires', 'drain_pipes', 'small_pipes', 'gutter']:
            if cat in s.geom:
                a.extend(s.geom[cat])

        if 'roofses' in s.geom:
            for o in s.geom['roofses']:
                s.setmat_geonodes(o, f)

        if 'roof_skirt' in s.geom:
            s.setmat_geonodes(s.geom['roof_skirt'], f(s, s.geom['roof_skirt']))


        for cat, node_name in [('roofses', 'setmat'), ('roof_skirt', 'setmat'), ('extShutterGlassOBs', 'setmat')]:
            if cat in s.geom:
                things = s.geom[cat]
                if type ( things ) is list:
                    for thing in things:
                        s.setmat_geonodes(thing, f, key=node_name)
                else:
                    s.setmat_geonodes(things, f, key=node_name)

        for rect in s.geom['windows']:

            wdict = s.geom['windows'][rect]
            for cat in ['frameOBs', 'frameGlassOBs', 'surroundOBs', 'mouldingOBs',
                        'blind', 'blind_fill', 'wires']:
                if cat in wdict:
                    a.extend(wdict[cat])

            def set(thing, node_name):
                if thing.data == None:
                    return # empty shape?
                if not s.setmat_geonodes(thing, f, key=node_name):
                    if len(thing.data.materials) == 0:
                        thing.data.materials.append(f(s, o))
                    else:
                        thing.data.materials[0] = f(s, o)

            for cat, node_name in [
                ('blinds'              , 'setmat'),
                ('blinds'              , 'mat_frame'),
                ('curtainOBs'          , 'setmat'),
                ("balcony_railing_bars", 'setmat'),
                ("balcony_glass"       , 'setmat'),
                ("balcony_hold"        , 'setmat'),
                ("balcony_hold_line"   , 'setmat'),
                ("balcony_pillar"      , 'setmat'),
                ("balcony_glass"       , 'setmat'),
                ("balcony_pins"        , 'setmat'),
                ('barOBs'              , 'setmat'),
                ("balconies_bases"     , 'setmat'),
                ("extShutterOBs"       , 'setmat'),
                ("extShutterGlassOBs"  , 'setmat'),
            ]:
                if cat in wdict:
                    things = wdict[cat]
                    if type(things) is list:
                        for thing in things:
                            set(thing, node_name)
                    else:
                        set(things, node_name)

        for obj in a:
            if len(obj.data.materials) == 0:
                obj.data.materials.append (f(s, obj))
            for i in range (len(obj.data.materials)):
                obj.data.materials[i] = f(s, obj)

    def set_fullbright(s):

        bpy.context.scene.cycles.samples = 1
        bpy.context.scene.cycles.use_preview_denoising = False
        bpy.context.scene.cycles.use_denoising = False
        bpy.context.scene.view_settings.view_transform = 'Standard'

        # white background
        bpy.data.worlds["World"].node_tree.nodes["fullbright"].inputs[0].default_value = 1
        bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[1].default_value = 500

        if 'exterior_wallOBs' in s.geom:
            for walls in s.geom['exterior_wallOBs']:
                for wall in walls:
                    if len(wall.data.materials) > 0:
                        wall.data.materials[0] = bpy.data.materials["wall"]
                        wall.cycles.use_adaptive_subdivision = False

        if 'exterior_wallframeOBs' in s.geom:
            for walls in s.geom['exterior_wallframeOBs']:
                for wall in walls:
                    if len(wall.data.materials) > 0:
                        wall.data.materials[0] = bpy.data.materials["wall-frame"]
        # s.geom['external_wallOB'].data.materials[0] = bpy.data.materials["wall-frame"]

        if 'internal_wallOBs' in s.geom:
            for o in s.geom['internal_wallOBs']:
                o.data.materials[0] = bpy.data.materials["interior"]

        if 'interior_box' in s.geom:
            for o in s.geom['interior_box']:
                o.data.materials[0] = bpy.data.materials["interior"]

        if 'ext_side_wallOBs' in s.geom: # the side may not have been merged with the main wall mesh
            for o in s.geom['ext_side_wallOBs']:
                o.data.materials[0] = bpy.data.materials["wall-frame"]
                # o.data.materials.append( s.got_stucco("window_frame", r2) )

        if 'roofses' in s.geom:
            for o in s.geom['roofses']:
                s.setmat_geonodes(o, "unlabelled")

        if 'roof_skirt' in s.geom:
                s.setmat_geonodes(s.geom['roof_skirt'], "unlabelled")

        if 'wall_signs' in s.geom:
            for o in s.geom['wall_signs']:
                o.data.materials[0].node_tree.nodes["do_label"].inputs[0].default_value = 1

        for name in ['exterior_junk', 'wires', 'drain_pipes', 'small_pipes', 'gutter']:
            if name in s.geom:
                for o in s.geom[name]:
                    if len(o.data.materials) == 0:
                        o.data.materials.append(bpy.data.materials["misc-obj"])
                    else:
                        o.data.materials[0] = bpy.data.materials["misc-obj"]

        if 'exterior_floor' in s.geom:
            for o in s.geom['exterior_floor']:
                o.data.materials[0] = bpy.data.materials["unlabelled"]
                s.setmat_geonodes(o, "unlabelled")

        for rect in s.geom['windows']:
            wgeom = s.geom['windows'][rect]

            if "blinds" in wgeom:
                mat = bpy.data.materials["blinds"]
                for obj in wgeom["blinds"]:
                    s.setmat_geonodes(obj, mat)
                    s.setmat_geonodes(obj, mat, key="mat_frame")

            for name in [
                "balcony_railing_bars",
                "balcony_glass",
                "balcony_hold",
                "balcony_hold_line",
                "balcony_pillar",
                "balcony_glass",
                "balcony_pins",
            ]:
                if name in wgeom:
                    for o in wgeom[name]:
                        mat = bpy.data.materials["balcony"]
                        if not s.setmat_geonodes(o, mat):
                            if len(o.data.materials) == 0:
                                o.data.materials.append(mat)

            if 'balconies_bases' in wgeom:
                for h in wgeom['balconies_bases']:
                    if not s.setmat_geonodes(h, "wall-frame"): # balcony-base should be wall-frame.
                        h.data.materials[0] = bpy.data.materials["wall-frame"]

            if 'frameOBs' in wgeom:
                for o in wgeom['frameOBs']: o.data.materials[0] = bpy.data.materials["window-frame"]

            if 'frameGlassOBs' in wgeom:
                for o in wgeom['frameGlassOBs']: o.data.materials[0] = bpy.data.materials["window-pane"]

            if 'blind_fill' in wgeom: # windows without glass
                for o in wgeom['blind_fill']: o.data.materials[0] = bpy.data.materials["window-pane"]

            if 'blind' in wgeom:
                for o in wgeom['blind']:
                    o.data.materials[0] = bpy.data.materials["blinds"]

            # lintel/sill/frame:
            if 'surroundOBs' in wgeom:
                for surroundOB in wgeom['surroundOBs']:
                    surroundOB.data.materials[0] = bpy.data.materials["wall-frame"]

            if 'mouldingOBs' in wgeom:
                for m in wgeom['mouldingOBs']:
                    m.data.materials[0] = bpy.data.materials["wall"]

            if 'barOBs' in wgeom:
                for c in wgeom["barOBs"]:
                    s.setmat_geonodes(c, "bars")

            if 'curtainOBs' in wgeom:
                for c in wgeom["curtainOBs"]:
                    s.setmat_geonodes(c, "interior")


                    if c.data is not None and len (c.data.materials) > 0:
                        c.data.materials[0] = bpy.data.materials["interior"]
                    for q in c.modifiers:
                        if q.type == "NODES":
                            if "setmat" in q.node_group.nodes:
                                q.node_group.nodes["setmat"].inputs[2].default_value = bpy.data.materials["interior"]

            # for all objs, for all modifiers, if geom shader
            if 'extShutterOBs' in wgeom:
                for h in wgeom['extShutterOBs']:
                    h.data.materials[0] = bpy.data.materials["shutter"]

            if 'extShutterGlassOBs' in wgeom:
                for h in wgeom['extShutterGlassOBs']:
                    s.setmat_geonodes(h, "shutter")



        # set background colors
        bpy.data.worlds["World"].node_tree.nodes["fullbright"].inputs[0].default_value = 1

    def setmat_geonodes(s, o, material, key="setmat"):

        if material.__class__ is str:
            material = bpy.data.materials[material]
        elif callable(material):
            material = material(s, o)

        if o.data is not None and len (o.data.materials) > 0:
            o.data.materials[0] = material

        for q in o.modifiers:
            if q.type == "NODES":
                if key in q.node_group.nodes:
                    q.node_group.nodes[key].inputs[2].default_value = material
                    return True

        return False

    def set_simple_lighting(s, on):

        # lit by emission
        if on:
            bpy.data.objects["Sun"].hide_render = True
            bpy.data.objects["Sun"].hide_set(True)

            bpy.data.worlds["World"].node_tree.nodes["simple_lighting"].inputs[0].default_value = 1
            bpy.context.scene.view_settings.view_transform = 'Raw'
            # bpy.context.scene.render.film_transparent = True
        else:
            bpy.data.objects["Sun"].hide_render = False
            bpy.data.objects["Sun"].hide_set(False)
            bpy.data.worlds["World"].node_tree.nodes["simple_lighting"].inputs[0].default_value = 0
            bpy.context.scene.view_settings.view_transform = 'Filmic'
            # bpy.context.scene.render.film_transparent = False

    def set_texture_rot(s):

        if s.dtd_textures is None:
            s.dtd_textures = sorted ( glob(f'{config.resource_path}/dtd/*.jpg') )

        def get(s, obj):
            mat = bpy.data.materials["texture_rot"].copy()
            mat.name = "xxx-texture_rot"
            img = bpy.data.images.load( random.choice(s.dtd_textures ) )
            img.name = "xxx-"+img.name
            mat.node_tree.nodes["tex"].image = img

            return mat

        s.all_objs(get)

    def set_circle_camera(s, style):

        r = int(style[:-3])

        cam_data = bpy.data.cameras.new(f'xxx-camera_circle_{r}m')
        cam = bpy.data.objects.new('camera', cam_data)
        bpy.context.collection.objects.link(cam)
        cons = cam.constraints.new(type='TRACK_TO')
        cons.target = bpy.data.objects['cen_target']

        s.cam_lookup[style] = cam
        bpy.context.scene.camera = cam

        pos = (1e4, 1e4, -1e4)  # sample...
        cam.location = bpy.data.objects['cen_camera'].location.copy()
        while prof.length(prof.sub(pos, cam.location)) > r + 0.0001 or pos[2] < 0.1:  # ...for in circle, above ground
            pos = (cam.location.x + random.uniform(-r, r), cam.location.y, cam.location.z + random.uniform(-r, r))

        cam.location = pos

        try:
            pw = None
            for w in s.geom["windows"]:

                if w.get_value("wdict")["name"] == "win_primary":
                    pw = w

            if pw:
                window_shape = pw.get_value("wdict")['shapeOB']
                bl = np.array(window_shape.bound_box[0][:])
                tl = np.array(window_shape.bound_box[2][:])
                br = np.array(window_shape.bound_box[5][:])
                tr = np.array(window_shape.bound_box[6][:])
                fov = float( max (
                    abs(prof.angle_twixt(pw.to_world @ Vector(bl), cam.location, pw.to_world @ Vector(tr))),
                    abs(prof.angle_twixt(pw.to_world @ Vector(br), cam.location, pw.to_world @ Vector(tl)))
                ) )
                cam.data.angle = fov * 1.1
            else:
                cam.data.angle = 0.5
        except:
            print("something went wrong with setting the camera angle")
            cam.data.angle = 0.5

    def set_label_level(s, level, do_hide):


        def hide(c):
            c.hide_render = do_hide
            c.hide_viewport = do_hide

        def show(c):
            c.hide_render = not do_hide
            c.hide_viewport = not do_hide

        for rect in s.geom['windows']:
            wgeom = s.geom['windows'][rect]

            # level 9 also done during creation.
            if level <= 9: # open-window

                if "dummy_wall" in wgeom:
                    dps = wgeom["dummy_wall"]
                    for dp in dps:
                        dp.hide_render = True
                        dp.hide_viewport = True

                if 'curtainOBs' in wgeom:
                    for c in wgeom["curtainOBs"]:
                        hide(c)

            if level <= 8: # bars
                if 'barOBs' in wgeom:
                    for c in wgeom["barOBs"]:
                        hide(c)

            if level <= 7: # blinds
                if "blinds" in wgeom:
                    for obj in wgeom["blinds"]:
                        hide(obj)

            if level <= 6: # junk
                if 'wall_signs' in s.geom:
                    for o in s.geom['wall_signs']:
                        hide(o)

                for name in ['exterior_junk', 'wires', 'drain_pipes', 'small_pipes', 'gutter']:
                    if name in s.geom:
                        for o in s.geom[name]:
                            hide(o)

            if level <=5: # balcony
                for name in [
                    "balcony_railing_bars",
                    "balcony_glass",
                    "balcony_hold",
                    "balcony_hold_line",
                    "balcony_pillar",
                    "balcony_glass",
                    "balcony_pins",
                    "balconies_bases"
                ]:
                    if name in wgeom:
                        for o in wgeom[name]:
                            hide(o)

            if level <= 4: # shutters
                for name in ['extShutterOBs', 'extShutterGlassOBs']:
                    if name in wgeom:
                        for h in wgeom[name]:
                            hide(h)

            # hide all dummy glass
            for i in [2, 3]:
                if f"dummy_pane_lvl{i}" in wgeom:
                    dps = wgeom[f"dummy_pane_lvl{i}"]
                    for dp in dps:
                        dp.hide_render = True
                        dp.hide_viewport = True

            if level <= 3: # window frame

                # hide the glass and frame
                for name in ['frameOBs','frameGlassOBs']:
                    if name in wgeom:
                        for h in wgeom[name]:
                            hide(h)

                # add in dummy-glass
                if "dummy_pane_lvl3" in wgeom and level ==3:
                    dps = wgeom["dummy_pane_lvl3"]
                    for dp in dps:
                        show (dp)

            if level <=2: # window surround

                if 'surroundOBs' in wgeom:
                    for surroundOB in wgeom['surroundOBs']:
                        hide(surroundOB)

                if 'int_wall_side' in wgeom:
                    o = wgeom['int_wall_side']
                    hide(o)

                # add in dummy-glass
                if level == 2:
                    if "dummy_pane_lvl2" in wgeom:
                        dps = wgeom["dummy_pane_lvl2"]
                        for dp in dps:
                            show (dp)

            if level <=1: # window panes

                if "dummy_wall" in wgeom:
                    dps = wgeom["dummy_wall"]

                    for dp in dps:

                        show(dp)

                        if do_hide and "biggest_wall_shader" in s.geom: # patch shader, now we've added materials.
                            mat = s.geom["biggest_wall_shader"]
                            if dp.data.materials:
                                dp.data.materials[0] = mat
                            else:
                                dp.data.materials.append(mat)

                    if dps not in s.geom["exterior_wallOBs"]: # so that we update the labels.
                        s.geom["exterior_wallOBs"].append(dps)



    def create_geometry(style, seed, old_geom=None, force_no_subdiv=False, param_override={}):

        print (f"creating geometry with seed {int(seed)}")

        if "root/_seed" in param_override:
            seed = param_override["root/_seed"]
            print (f"seed overriden by parameter file to: {seed}")

        if style == "rgb" or style.endswith("nwall"):

            geom = utils.cleanup_last_scene()
            geom["force_no_subdiv"] = force_no_subdiv

            rantom.set_param_override(param_override)
            rantom.reset()
            rantom.store("seed", seed)
            rantom.seed(seed)
            cgb_building.CGA_Building(geom).go()

            materials = geom["materials"] = Materials(geom)
            return geom, materials

        elif style in ["nosplitz","mono_profile","only_rectangles","no_rectangles","only_squares","single_window","wide_windows"]:

            geom = utils.cleanup_last_scene(geom=old_geom)
            geom["force_no_subdiv"] = force_no_subdiv

            rantom.set_param_override(param_override)
            rantom.reset() # reset all - will remove timings, etc...
            rantom.store("seed", seed)
            rantom.seed(seed)

            geom["mode"] = style
            cgb_building.CGA_Building(geom).go()

            materials = geom["materials"] = Materials(geom)
            return geom, materials

        elif style == "lvl9":

            geom = utils.cleanup_last_scene()
            geom["force_no_subdiv"] = force_no_subdiv
            rantom.set_param_override(param_override)
            rantom.reset()
            rantom.store("seed", seed)
            rantom.seed(seed)
            geom["lvl"] = 9
            cgb_building.CGA_Building(geom).go()

            materials = geom["materials"] = Materials(geom)
            return geom, materials

        else: # assume geometry already exists

            geom = old_geom
            geom["force_no_subdiv"] = force_no_subdiv
            materials = geom["materials"]
            return geom, materials


    passes_rgb       = [["png", "exposed"], ["png", "albedo"], ["exr", "depth"]]
    passes_canonical = [["png", "albedo"], ["png", "transcol"]]
    passes_light = [["png", "exposed"]]
    styles_with_passes = ["rgb", "canonical", "nightonly", "dayonly", "notransparency", "nobounce", "nosun", "fixedsun"]

    def get_passes_for_style(s, style):

        if style == "rgb":
            passes = Materials.passes_rgb
        elif style == "canonical":
            passes = Materials.passes_canonical
        else:
            passes = Materials.passes_light
        return passes

    def pre_render(s, style, passes=False):

        # configure compositor
        if passes and style in Materials.styles_with_passes:
            
            bpy.context.scene.use_nodes = True
            bpy.context.scene.view_layers["ViewLayer"].use_pass_diffuse_color = True
            bpy.context.scene.view_layers["ViewLayer"].use_pass_z = True
            bpy.context.scene.view_layers["ViewLayer"].use_pass_transmission_color = True

            # configure output locations for files from compositor
            for _, pazz in s.get_passes_for_style(style):
                bpy.data.scenes["Scene"].node_tree.nodes[f"{pazz}_file"].base_path = os.path.join(config.render_path, f"tmp{config.jobid}_{style}_{pazz}")
                os.makedirs(f'{config.render_path}/{style}_{pazz}/', exist_ok=True)

        # setup scene materials
        if style == "rgb":
            s.go()

        elif  style[0].isdigit() and style[-2:] == "ms": # 100ms, 1000ms etc...
            bpy.context.scene.cycles.time_limit = int(style[:-2])/1000 # ms -> seconds
            bpy.context.scene.cycles.use_denoising = False

        elif  style[0].isdigit() and style[-3:] == "cen": # 0cen, 4cen...

            s.set_circle_camera(style)

        elif style[0].isdigit() and style[-6:] == "cenlab":

            s.set_fullbright()
            bpy.context.scene.camera = s.cam_lookup[style[:-3]]

        elif  style[0].isdigit() and style[-3:] == "spp": # 100ms, 1000ms etc...

            bpy.context.scene.cycles.samples = int(style[:-3])
            bpy.context.scene.cycles.time_limit = 0
            bpy.context.scene.cycles.use_denoising = False

        elif style == "nosun":

            bpy.data.objects["Sun"].hide_render = True
            bpy.data.worlds["World"].node_tree.nodes["simple_lighting"].inputs[0].default_value = 1

        elif style == "nobounce":

            bpy.context.scene.cycles.sample_clamp_indirect = 0.0001

        elif style == "fixedsun":

            bpy.data.objects["Sun"].hide_render = True
            bpy.data.objects["boring_sun"].hide_render = False

        elif style == "nightonly":
            s.env(True, True)

        elif style == "dayonly":
            s.env(True, False)

        elif style == "notransmission":
            bpy.context.scene.cycles.transmission_bounces = 0

        elif style == "canonical":
            bpy.context.scene.camera = bpy.data.objects['canonical_camera']
            bpy.context.scene.render.film_transparent = True

        elif style == "labels":
            s.set_fullbright()

        elif style == "texture_rot":
            s.set_simple_lighting(True)
            s.set_texture_rot()

        elif style == "col_per_obj":
            s.set_simple_lighting(True)
            bpy.data.materials["col_per_obj"].node_tree.nodes["script_random"].inputs[1].default_value = random.uniform(0,7)
            s.set_shader_all_objs(style)

        elif style == "edges":
            s.set_shader_all_objs(style)
            s.set_simple_lighting(True)
            bpy.context.scene.render.use_freestyle = True

        elif style.startswith("lvl") and style[-1].isdigit():

            level = int(style[3:])
            s.set_label_level(level, True)

        elif style.startswith("lvl") and style.endswith("labels"):

            lvl = int(style[3:-7])

            if lvl == 9:
                # show everything at start of label run.
                # for lvl in range (1, 10):
                s.set_label_level(1, False)

            s.set_label_level(lvl, True)

            # render labels
            s.set_fullbright()

        elif style in ["nosplitz","mono_profile","only_rectangles","no_rectangles","only_squares","single_window","wide_windows"]:

            pass

        elif style.endswith("_labels"):

            s.set_fullbright()

        elif style == "all_brick":
            mat = s.got_brick("all_is_brick", r2=mm.MonoMatCache(name="monomat", monomat=True))
            def all_is_brick(s, obj):
                return mat
            s.all_objs( all_is_brick )
        elif style == "monomat":
            s.go(override_r=mm.MonoMatCache(name="monomat"))
        elif style.endswith("monomat"):
            sigma = float ( style[:-7] )
            s.go(override_r=mm.MonoMatCache(name="monomat", monomat=True, sigma=sigma))
        elif style.endswith("multimat"):
            tau = float ( style[:-8] )
            s.go(override_r=mm.MonoMatCache(name="multimat", monomat=False, sigma=tau))
        elif style.endswith("nwall"):
            n = int ( style[:-5] )
            s.geom["wall_is_texture"] = n # not procedural materials, textures from disk.
            s.go()

        elif style is not None and style != "none":
            if not "complex" in style:
                s.set_simple_lighting(True)
            s.set_shader_all_objs(style)

    def recover_composite(self, ext, name, render_name):

        tmp_dir = os.path.join(config.render_path, f"tmp{config.jobid}_{name}")
        for f in os.listdir(tmp_dir):
            if os.path.splitext(f)[1] == ext:
                shutil.move(os.path.join(tmp_dir, f), f'{config.render_path}/{name}/{render_name}{ext}')

        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

    def post_render(s, style, render_name, passes):

        if passes and style in Materials.styles_with_passes:

            bpy.context.scene.use_nodes = False
            bpy.context.scene.view_layers["ViewLayer"].use_pass_diffuse_color      = False
            bpy.context.scene.view_layers["ViewLayer"].use_pass_z                  = False
            bpy.context.scene.view_layers["ViewLayer"].use_pass_transmission_color = False

            for ext, pazz in s.get_passes_for_style(style):
                s.recover_composite(f".{ext}", f"{style}_{pazz}", render_name)

        if  style[0].isdigit() and style[-3:] == "cen":

            bpy.context.scene.camera = bpy.data.objects['camera']

        elif style == "labels" or (style[0].isdigit() and style[-6:] == "cenlab"):

            bpy.context.scene.camera = bpy.data.objects['camera']
            bpy.context.scene.cycles.samples = config.samples
            bpy.data.worlds["World"].node_tree.nodes["fullbright"].inputs[0].default_value = 0
            bpy.context.scene.cycles.use_preview_denoising = True
            bpy.context.scene.cycles.use_denoising = True

        elif style[1].isdigit() and style[-2] == "ms":

            bpy.context.scene.cycles.time_limit = 0
            bpy.context.scene.cycles.use_denoising = True

        elif  style[0].isdigit() and style[-3:] == "spp": # 100ms, 1000ms etc...

            bpy.context.scene.cycles.samples = config.samples
            bpy.context.scene.cycles.time_limit = 0
            bpy.context.scene.cycles.use_denoising = True

        elif style == "nosun":

            bpy.data.objects["Sun"].hide_render = False
            bpy.data.worlds["World"].node_tree.nodes["simple_lighting"].inputs[0].default_value = 0

        elif style == "nobounce":

            bpy.context.scene.cycles.sample_clamp_indirect = 10

        elif style == "fixedsun":

            bpy.data.objects["Sun"].hide_render = False
            bpy.data.objects["boring_sun"].hide_render = True

        elif style == "nightonly" or style == "dayonly":
            s.env(False)

        elif style == "notransmission":

            bpy.context.scene.cycles.transmission_bounces = 12

        elif style == "canonical":
            bpy.context.scene.camera = bpy.data.objects['camera']
            bpy.context.scene.render.film_transparent = False

        elif style == "edges":
            bpy.context.scene.render.use_freestyle = False

        s.set_simple_lighting(False)

        # regular textured background
        bpy.data.worlds["World"].node_tree.nodes["fullbright"].inputs[0].default_value = 0
        bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[1].default_value = 500
