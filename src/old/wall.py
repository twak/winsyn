from re import S
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

def create_wall( geom, width, name):

    shapeOB = geom['shapeOB']

    # print(bpy.context.copy()) 
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[0]

    mesh = shapeOB.to_mesh()
    meshOB = bpy.data.objects.new("xxx_border_mesh", mesh.copy())
    bpy.context.scene.collection.objects.link( meshOB )

    bpy.context.view_layer.objects.active = meshOB

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.extrude_region_move(MESH_OT_extrude_region={"use_normal_flip":False, "use_dissolve_ortho_edges":False, "mirror":False},
       TRANSFORM_OT_translate={"value":(0, 0, width * 2 + 1 )})

    secondary_mat = bpy.data.materials.new(name="xxx-wall-frame")
    geom[name + "_mat_2"] = secondary_mat
    meshOB.data.materials.append(secondary_mat)

    bpy.ops.object.mode_set(mode='OBJECT')

    meshOB.rotation_euler[0] = 1.5708
    meshOB.location[1] = width + 0.5

    bpy.ops.mesh.primitive_cube_add(size=2, enter_editmode=False, align='WORLD', location=(0,0,0), scale=(10, width, 10))
    wall = bpy.data.objects[bpy.context.active_object.name]
    wall.name = "xxx-wall"
    
    primary_material = bpy.data.materials.new(name="xxx-wall")
    geom[name + "_mat_1"] = primary_material
    wall.data.materials.append( primary_material )
    wall.data.materials.append( secondary_mat )

    bpy.ops.object.modifier_add(type='BOOLEAN')
    bpy.context.object.modifiers["Boolean"].object = meshOB
    bpy.ops.object.modifier_apply(modifier="Boolean")
    
    # bpy.ops.object.modifier_add(type='EDGE_SPLIT')
    # bpy.context.object.modifiers["EdgeSplit"].split_angle = 0.3
    # bpy.ops.object.modifier_apply(modifier="EdgeSplit")
    # bpy.ops.object.shade_smooth()

    
#    wall.data.use_auto_smooth = True
#    wall.data.auto_smooth_angle = 0.349066
    
    bpy.data.objects.remove(meshOB, do_unlink=True)

    geom[name+"OB"] = wall
    
    
    
def create_glass(shapeOB, width):
    
    mesh = shapeOB.to_mesh()
    meshOB = bpy.data.objects.new("xxx-glass", mesh.copy())

    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(meshOB, depsgraph)
    bm.faces.ensure_lookup_table()

    r = bmesh.ops.extrude_face_region(bm, geom=bm.faces)
    verts = [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0,0,width), verts=verts)
    
    bm.to_mesh(mesh)
    meshOB2 = bpy.data.objects.new("xxx-glass", mesh.copy())
    bpy.context.scene.collection.objects.link( meshOB2 )
    
    bm.free()
    
    return meshOB2
    
#    bpy.ops.object.mode_set(mode='OBJECT')


class Wall:

    def __init__(self) -> None:
        pass

    def go(s, geom, wall_y):
        s.geom = geom

        # moulding around everything else
        s.create_mouldings(wall_y)

    def create_mouldings(s, wall_y):

        mouldings = s.geom['mouldingOBs'] = []

        avoid =[]

        shapeOB = s.geom['shapeOB']
        avoid.append(shapeOB)

        if 'extShutterOBs' in s.geom:
            avoid.extend(s.geom['extShutterOBs'])

        if 'balconyOBs' in s.geom:
            avoid.extend(s.geom['balconyOBs'])

        if 'surroundOBs' in s.geom:
            avoid.extend(s.geom['surroundOBs'])

        ab = utils.world_bounds_children(avoid)
        avoid2d = [ab[0][0], ab[0][1], ab[2][0], ab[2][1]] # x1y1x2y2 in world-space

        profiles = bpy.data.collections["moulding_profiles"].objects
        
        line_blocks = [(0,0)]

        moulding_curves = []

        match rantom.randrange(5, "mouldings_placement_algorithm" ):
            case 0:
                s.complex_moulds( profiles, avoid2d, line_blocks, -wall_y, moulding_curves )
            case 1 | 2:
                s.simple_moulds ( profiles, avoid2d, line_blocks, -wall_y, moulding_curves )
            case _:
                return

        for curveOB, profile in moulding_curves: # range(rantom.randrange(5, "number of mouldings") + 5):
    
            # pwh = prof.curve_wh(profile)

            if curveOB is not None:
                curveOB.data.bevel_object = profile
                curveOB.data.bevel_mode = 'OBJECT'
                curveOB.data.use_fill_caps = True

                bpy.context.scene.collection.objects.link(curveOB)
                ob = curveOB.evaluated_get(bpy.context.evaluated_depsgraph_get())

                mesh_curveOB = bpy.data.objects.new( f"xxx-moulding", ob.to_mesh().copy())
                bpy.context.scene.collection.objects.link(mesh_curveOB)

                bpy.data.objects.remove(curveOB, do_unlink=True)

                utils.set_auto_smooth(mesh_curveOB)
                mouldings.append(mesh_curveOB)


    def complex_moulds(s, profiles, avoid2d, line_blocks, wall_y, moulding_curves ):
        '''
        Creates patterns of art-deco-ish mouldings over and under the window.
        '''

        incr_offset_width = True

        count = rantom.randrange( 5, "number_complex_moulds") + 1
        
        r2 = rantom.RantomCache(0.3/count)

        al_incr = -1 if r2.randrange(2, f"moulding_complex_al_seq") == 0 else 1

        match rantom.randrange(5, f"moulding_complex_loop_choice"):
            case 0:
                fns = [s.loop_under, s.loop_over]
            case 1:
                fns = [s.loop_over]
            case 2:
                fns = [s.loop_under]
            case 3: 
                fns = [s.straight_through]
                incr_offset_width = False
            case 4: 
                fns = [s.straight_through, s.loop_under, s.loop_over]
                incr_offset_width = False
                count = 3
                al_incr = 1
        
        fn_idx = 0
        r2 = rantom.RantomCache(0.3/count)

        fn_incr = r2.randrange(2, f"moulding_complex_swap_dir") 
        flipped_h = r2.randrange(2, f"moulding_complex_flipped_stagger") == 0


        #moulding y-height before window
        al = s.find_h_within_window(avoid2d, 0.3, line_blocks)
        if al == None:
            return []

        al_incr = -1 if r2.randrange(2, f"moulding_complex_al_seq") == 0 else 1

        # offsets for loops over or under window
        offset_w = 0 # rantom.uniform_mostly(0.2, 0, 0.2, 0.3 )
        offset_h = (count) * 0.4 if flipped_h else 0 #rantom.uniform_mostly(0.3, offset_w, 0.2, 0.3 )

        for i in range(count):

            profile = profiles[r2.randrange(len(profiles), "moulding_profile_curve", "moulding wall-frame profile")]
            ph = prof.curve_wh(profile)[1]
            spacing = ph + r2.uniform_mostly( 0.2, 0, 0, 2* ph, "moulding_complex_spacing")

            if i > 0 and offset_h < ph: # might cover window
                break

            fn_idx = (fn_idx + 1) % len (fns) #r2.randrange(len(fns), "moulding_complex_fn_type")
                    
            f = fns[fn_idx]

            if i == 0 and r2.randrange(2, f"moulding_complex_center_straight") == 0:
                f = s.straight_through

            # print (f" >>>>{i} >>>> {offset_w} ")

            moulding_curves.append ( ( f ( al, offset_w, offset_h,  avoid2d, line_blocks, ph, wall_y=wall_y + rantom.uniform(-0.001, 0.001, "complex_moulding_depth_jitter") ), profile ) )
            al += al_incr * spacing

            if incr_offset_width:
                offset_w += spacing

            offset_h += -1 * spacing if flipped_h else spacing
            
            


    def straight_through(s, al, offset_w, offset_h, avoid2d, line_blocks, ph, wall_y= 1, far = 10 ):
        
        '''
        Horizontal moulding, stopping at the window
        '''
        
        line_blocks.append((al, al+ph))

        if al > avoid2d[3] or al + ph < avoid2d[2]:
            return prof.build_curve(1,  [
                    (-far, wall_y, al),
                    (far, wall_y, al) ],
                    d='3D', cyclic=False)
        else:
            return prof.build_curve(1, 
            [ [ (-far, wall_y       , al ),  ( avoid2d[0]-offset_w, wall_y, al ) ],
                [ ( avoid2d[1] + offset_w, wall_y, al ),  ( far       , wall_y, al ) ] ],
                d='3D', cyclic=False)    


    def loop_under (s, al, offset_w, offset_h, avoid2d, line_blocks, ph, wall_y= 1, far = 10 ):

        # offset_w = spacing #rantom.uniform_mostly(0.3, ph, 2 * ph, max_offset+2*ph, "arched_moulding_offset_width")
        offset_h += ph # rantom.uniform_mostly(0.7, offset_w, 2* ph, max_offset+2*ph, "arched_moulding_offset_height")
        offset_w += ph

        line_blocks.append((avoid2d[2] - offset_h, al+ph ))

        return prof.build_curve(1, 
            [ (-far, wall_y       , al ),  
            ( avoid2d[0] - offset_w, wall_y, al ), 
            ( avoid2d[0] - offset_w, wall_y, avoid2d[2] - offset_h ), 
            ( avoid2d[1] + offset_w, wall_y, avoid2d[2] - offset_h ), 
            ( avoid2d[1] + offset_w, wall_y, al ), 
            ( far                , wall_y, al ) ], d='3D', cyclic=False)

    def loop_over(s, al, offset_w, offset_h, avoid2d, line_blocks, ph, wall_y= 1, far = 10 ):

        # offset_w = spacing # rantom.uniform_mostly(0.3, ph, 2 * ph, max_offset+2*ph, "arched_moulding_offset_width")
        # offset_h = spacing # rantom.uniform_mostly(0.7, offset_w, 2* ph, max_offset+2*ph, "arched_moulding_offset_height")
        
        line_blocks.append((al-ph, avoid2d[3] + offset_h ))

        return prof.build_curve(1, 
            [ (-far, wall_y       , al ),  
            ( avoid2d[0] - offset_w, wall_y, al ), 
            ( avoid2d[0] - offset_w, wall_y, avoid2d[3] + offset_h ), 
            ( avoid2d[1] + offset_w, wall_y, avoid2d[3] + offset_h ), 
            ( avoid2d[1] + offset_w, wall_y, al ), 
            ( far                , wall_y, al ) ], d='3D', cyclic=False) 

    
    def simple_moulds(s, profiles, avoid2d, line_blocks, wall_y, moulding_curves, far = 10 ):
        '''
        Adds a chaotic simple mouldings
        '''
        r2 = rantom.RantomCache(0.3)

        for i in range (rantom.randrange(4, f"simple_moulding_count")+1):

            profile = profiles[r2.randrange(len(profiles), f"moulding_profile_curve_{i}", "moulding wall-frame profile")]
            ph = prof.curve_wh(profile)[1]
            wyj = wall_y + rantom.uniform(-0.001, 0.001, "simple_moulding_depth_jitter")

            match rantom.randrange(3, f"simple_moulding_pattern_{i}"):

                # case 0: # loop over window
                    
                #     al = s.find_h_within_window(avoid2d, ph, line_blocks)
                #     if al is None: return

                #     max_offset = 0.5

                #     offset_w = rantom.uniform_mostly(0.3, 0, ph * 0.5, max_offset+ph, "arched_moulding_offset_width")
                #     offset_h = rantom.uniform_mostly(0.7, offset_w, ph, max_offset+ph, "arched_moulding_offset_height")
                    
                #     moulding_curves.append ( ( s.loop_over(al, offset_w, offset_h, avoid2d, line_blocks, ph, wyj ), profile ) )

                # case 1: # loop under the window
                    
                #     al = s.find_h_within_window(avoid2d, ph, line_blocks)
                #     if al is None: return

                #     max_offset = 0.5

                #     offset_w = rantom.uniform_mostly(0.3, ph, 2 * ph, max_offset+2*ph, "arched_moulding_offset_width")
                #     offset_h = rantom.uniform_mostly(0.7, offset_w, 2* ph, max_offset+2*ph, "arched_moulding_offset_height")
                    
                #     moulding_curves.append ( (  s.loop_under(al, offset_w, offset_h, avoid2d, line_blocks, ph, wyj ), profile ) )


                case 0: # above the window

                    max_h = max ( avoid2d[3] , max ( [maxx for (minn,maxx) in line_blocks] ) )
                    h = max_h + rantom.uniform_mostly( 0.33, 0, 0.01, 0.5, "moulding_above_window")

                    verts = [
                        (-far, wyj, h),
                        (far, wyj, h),
                    ]
                    
                    line_blocks.append((h, h+ph))

                    moulding_curves.append ( ( prof.build_curve(1, verts, d='3D', cyclic=False), profile ) ) 

                case 1: # below the window

                    min_h = min ( avoid2d[2] , min ( [minn for (minn,maxx) in line_blocks] ) )
                    h = min_h - rantom.uniform_mostly( 0.33, 0, 0.01, 0.5, "moulding_distance_under_window") - ph

                    verts = [
                        (-far, wyj, h ),
                        ( far, wyj, h ),
                    ]
                    
                    line_blocks.append((h-ph, h))

                    moulding_curves.append ( ( prof.build_curve(1, verts, d='3D', cyclic=False), profile ) )

                case 2: # through the window
                
                    al = s.find_h_within_window(avoid2d, ph, line_blocks, i)
                    if al is None: return

                    line_blocks.append((al, al+ph))

                    moulding_curves.append ( ( prof.build_curve(1, 
                        [ [ (-far, wyj       , al ),  ( avoid2d[0], wyj, al ) ],
                            [ ( avoid2d[1], wyj, al ),  ( far       , wyj, al ) ] ],
                            d='3D', cyclic=False), profile ) )


    def find_h_within_window(s, avoid2d, ph, line_blocks, i = -1):

        for i in range (10): # lazy programmer
            
            al = rantom.uniform (avoid2d[2], avoid2d[3] - ph, f"moulding_h_within_window_{i}")
            ah = al + ph

            overlap = False

            for (bl, bh) in line_blocks:
                if ah > bl and al < bh: # then bad
                    overlap = True
                    break

            if overlap: continue

            return al

        return None


            

        

