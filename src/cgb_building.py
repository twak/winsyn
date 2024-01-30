import functools
import random
import bpy
from . import rantom
import time
from copy import copy
import os
import re
from functools import partial
import math
import numpy as np
from src import utils, config, profile
from src import materials as mat
from src import curtains as curt
from src.shape import Shape
from src import cgb
from src import subframe as sub
from src.cgb import shp, rect, tri, cuboid, parallel, repeat_x, repeat_y, split_x, split_y, split_z
from src.cgb import split_lines, trans
from src.cgb import split_faces, split_trif, split_trib, split_tril, split_trir, split_lines, extrude, split_tri_c, rot, spin, chance
from src import surround
from src import shutter

import bmesh
from mathutils import Vector, Matrix
from bmesh.types import BMVert

from collections import defaultdict
from src import pipes

class CGA_Building:

    def __init__(self, geom) -> None:
        self.geom = geom
        self.geom["windows"] = {}

        self.wall_curve = None # whole outer wall
        self.windows = [] # list of windows
        
        self.roof_curves = [] # top/gutter roof line
        self.floor_curves = [] # bottom/street roof line

        self.shutter_count = 0

        self.tiles = [] # subdivision of wall
        
        self.do_physics = False

    from .cgb_building_roofs import roof_rule, create_roof, create_skirt
    from .cgb_building_junk  import scatter_junk, bollard, load_bollard_set, create_ground, exterior_junk, ensure_signs, scatter_sign, ensure_wall_meshes
    from .cgb_building_win   import create_win, create_shutter, create_bars, win_cluster, balcony_split, create_balcony_geometry, create_baromatic, blind_split, create_blind_geometry, dummy_pane
    from .cgb_building_walls import create_wall, create_timber_frame, w, merge_walls, bay_windows

    def go(self):

        self.r2 = rantom.RantomCache(rantom.uniform_mostly(0.3, 0, 0, 0.5, "facade_random_spread", "meta-random: width of facade distribution" ), name="facade" )

        self.facade_root = bpy.data.objects.new( f"xxx-facade", None )
        bpy.context.scene.collection.objects.link(self.facade_root)
        self.walls_root = bpy.data.objects.new( f"xxx-wall", None )
        bpy.context.scene.collection.objects.link(self.walls_root)
        self.walls_root.parent = self.facade_root

        self.junk_count = 1
        self.geom["exterior_junk"] = []
        self.sign_count = 0
        self.geom["wall_signs"] = []
        self.geom['roofses'] = []
        self.win_count = 0
        self.ext_curves = []
        self.roof_curves = []
        self.wall_names = {"w"}
        self.geom['internal_wallOBs'] = []
        # self.wallframes = []
        self.geom['ext_side_wallOBs'] = [] # around the windows, perpendicular to main wall, outside
        self.geom['exterior_wallOBs'] = []
        self.geom['exterior_wallframeOBs'] = []
        self.bay_wins = []
        self.max_bay_front = 0
        self.bay_window_count = 0

        self.chance_blind = 5 # n:1 chance for not having a blind
        # self.geom['int_fill_wallOBs'] = [] # around the windows, perpendicular to main wall, inside

        self.bay_wall_width = 0.07
        self.ext_wall_thickness = rantom.uniform (0.02, 0.3, "ext_wall_width", "Exterior wall thickness")
        self.int_wall_thickness = rantom.uniform (0.02, 0.3, "int_wall_width", "Interior wall thickness")

        self.dg = bpy.context.evaluated_depsgraph_get() 

        self.setup_cgb()

        utils.urban_canyon_go(self.geom)

    # def wall2(self, shape=None, name=None):
    #     return self.wall(shape = shape, name = name)


    def setup_cgb(self):

        def wall(shape):
            return self.create_wall(shape=shape, ext_wall_thickness=self.ext_wall_thickness, int_wall_thickness=self.int_wall_thickness)
        self.wall = wall

        def nwall(name):
            return partial(self.w, name=name)
        self.nwall = nwall

        def bxwall(name="w"):
            return partial(self.w, name=name, interior=False)
        self.bxwall = bxwall

        def bwall(name = "w"):
            return partial(self.w, name=name, interior=True, ext_wall_thickness=self.bay_wall_width, int_wall_thickness=self.bay_wall_width)
        self.bwall=bwall

        win_r2_failure=random.uniform(0,1)
        def win_dict(shape):

            parent = bpy.data.objects.new(f"xxx-parent", None)
            bpy.context.scene.collection.objects.link(parent)
            out = { "r2": rantom.RantomCache(failure_rate=win_r2_failure, parent=self.r2), "parent": parent }

            if "mode" in self.geom:
                out["mode"] = self.geom["mode"]

            self.geom["windows"][shape] = out
            return out
        self.win_dict = win_dict

        #######################################

        self.count_u = 0
        def u (min, max, key=None):
            
            v = self.count_u
            self.count_u += 1
            key = key if key else f"cga_u_{v}"
            return lambda shape : rantom.uniform(min, max, key, f"CGA variable {key}")
        self.u = u

        self.timber_framed = rantom.weighted_int([8, 1], "do_timber_frame") == 1
        self.timber_frame_width = rantom.uniform( 0.01, 0.10, f"timber_width") # width of the timbers
        timber_max_inset = min( self.bay_wall_width, self.ext_wall_thickness + self.int_wall_thickness) # stop interior wall going through recessed panels...
        self.timber_frame_depth = self.r2.uniform_mostly(0.2, 0.005, 0, min(timber_max_inset, 0.2), "timber_depth") # setback of panel between timbers

        self.roof_skirt_height = self.r2.uniform(0.01, 0.3, "roof_skirt_height")
        if self.timber_framed:
            self.roof_skirt_height = min(self.roof_skirt_height, self.timber_frame_width)

        self.x         = "none"
        self.ground    = "ground"
        win = self.win = "win1" # front window - candidate for primary
        self.roof      = "roof"

        shapes = self.run_cgb()

        camera = bpy.data.objects["camera"]
        if "camera_box" in shapes:
            camera.location = shapes["camera_box"][0].random_point(self.r2, "camera_location")

        if "debug" in shapes:
            self.curves_to_mesh(shapes["debug"], f"xxx-debug")

        primary_win = None
        if len (shapes[win]) > 0:
            primary_win = p = rantom.choice(shapes[win], "p_win", "which window is the primary?" )
            pv = p.world_verts()

            north, south, east, west = None, None, None, None
            n_dist = s_dist = e_dist = w_dist = 1e6

            for s in shapes[win]:
                if s == primary_win:
                    continue

                # bl, br, tl, tr
                sv = s.world_verts()
                dist = (s.world_center() - p.world_center()).magnitude

                if utils.overlap(sv[0][0], sv[1][0], pv[0][0], pv[1][0]):
                    if sv[0][2] > pv[0][2]:
                        if dist < n_dist:
                            n_dist = dist
                            north = s
                    else:
                        if dist < s_dist:
                            s_dist = dist
                            south = s

                if utils.overlap(sv[0][2], sv[3][2], pv[0][2], pv[3][2]):
                    if sv[0][0] >  pv[0][0]:
                        if dist < e_dist:
                            e_dist = dist
                            east = s
                    else:
                        if dist < w_dist:
                            w_dist = dist
                            west = s

            win2 = "win2" # windows that we won't choose to be primary (side of bay windows etc...)
            for win_category in [win, win2]:
                for shape in shapes[win_category]:

                    name = f"win_{self.win_count}"
                    for target, a_name in [[primary_win, "win_primary"], [north, "win_north"], [south, "win_south"], [west, "win_west"], [east, "win_east"] ]:
                        if shape == target:
                            name = a_name
                            shape.get_value("wdict")["name"] =name

                    if "mode" in self.geom and self.geom["mode"] == "single_window" and name != "win_primary":
                        shapes["wa"].append(shape) # be a wall pls
                        wdict = shape.get_value("wdict")

                        for sn in ["extShutterOBs", "extShutterGlassOBs"]:
                            if sn in wdict:
                                for o in wdict[sn]:
                                    o.hide_render = o.hide_viewport = True

                        continue

                    is_bay = shape in self.bay_wins

                    if is_bay:
                        iwt = ewt = self.bay_wall_width
                    else:
                        iwt = self.int_wall_thickness
                        ewt = self.ext_wall_thickness

                    for k, v in self.create_win(
                            name=name,
                            shape=shape,
                            primary=primary_win==shape,
                            do_surround=not (self.timber_framed or is_bay),
                            expand_curtains=not is_bay,
                            blinds=not self.timber_framed,
                            ext_wall_thickness=ewt,
                            int_wall_thickness=iwt,
                            camera=camera).items():
                        shapes[k].extend(v)

        else: # something went wrong...no windows?
            print("didn't find a window to look at :(")
            if "backup_camera_target" in shapes:
                bpy.data.objects["cen_target"].location = bpy.data.objects["camera_target"].location = shapes["backup_camera_target"][0].random_point(self.r2, name="camera_target")

            bpy.data.objects["cen_camera"].location = camera.location

            if config.ortho:
                camera.data.ortho_scale = self.r2.uniform(0.5, 3, "ortho_scale")
            else:
                camera.data.lens = self.r2.uniform( 20, 200, "backup_camera_fov", "Camera focal length / field of view (mm lens equivalent)")

        namestring = ""
        if camera and not config.ortho:  # store window corners in camera space
            bpy.context.view_layer.update()
            for shape in self.geom["windows"]:
                wdict = shape.get_value("wdict")
                if 'shapeOB' in wdict:
                    window_shape = wdict['shapeOB']
                    xyz = sum(profile.curve_bounds(window_shape), [])
                    pts = []
                    for xi, yi, name in [(0, 2, "bl"), (1, 2, "br"), (1, 3, "tr"), (0, 3, "tl")]:
                        v = Vector((xyz[xi], xyz[yi], 0))
                        v = shape.to_world @ v
                        pts.append(v)
                    cam = utils.project_3d_point(camera, pts)
                    for name, coord in zip(["bl", "br", "tr", "tl"], cam):
                        wdict["r2"].store_v(f"{name}_screen", coord)

                    namestring = namestring +"," + wdict['name']
        rantom.store("window_names", f'"{namestring[1:]}"' ) # store all window names in attribs
        target = self.store_cam_params()

        if not (config.ortho and target.location[2] > camera.location[2]):
            self.create_ground( shapes ) # camera intersects ground in orthomode if looking down.

        pipes.max_subdivide(shapes, self, include_others = False)

        self.merge_walls( shapes, self.timber_framed )

        if self.timber_framed:
            self.create_timber_frame(shapes, self.timber_frame_width, self.timber_frame_depth )

        for idx, wall_name in enumerate ( self.wall_names ):

            sign_chance=self.r2.uniform_mostly(0.05, 0.99, -1,0.5,"sign_chance_per_rect")
            if not self.timber_framed:
                n =0
                for s in shapes[wall_name]:
                    if isinstance(s, rect) and self.r2.random(f"sign_{wall_name}_{n}") > sign_chance:
                        n += 1
                        self.scatter_sign(0.005, self.walls_root)(shape=s)

            ext_obj = self.curves_to_mesh(shapes[wall_name], f"ext-wall-{wall_name}", autosmooth=False)
            self.geom['exterior_wallOBs'].append ([ext_obj])
            ext_obj.parent = self.walls_root

        self.create_roof(shapes)
        self.create_skirt(shapes, self.roof_skirt_height )
        self.create_balcony_geometry(shapes)
        self.create_blind_geometry(shapes)

        self.remove_obstructing_junk(primary_win, camera)


        if "interior_box" in shapes:
            obj = self.curves_to_mesh(shapes["interior_box"], "interior_box")
            self.geom["interior_box"] = [obj]

        if self.do_physics and config.physics: # run for cloth curtains
            
            # self.geom['internal_wallOB'].modifiers.new('collision', 'COLLISION')
            last_time = time.time()

            print("starting physics")
            for i in range(10+40):
                bpy.context.scene.frame_set(i)
                new_time = time.time()
                if new_time - last_time > 5:
                    print(f"overly long simulation step {i}, aborting remainder")
                    break
            print("starting physics")

    def run_cgb( self ):

        # d = rantom.uniform(0.5, 2, "foo")
        # e = rantom.uniform(0.5, 2, "foo1")
        # f = rantom.uniform(0.5, 2, "foo2")
        # g = rantom.uniform(0.5, 2, "foo3")
        #
        # faces =  split_faces(
        #     repeat_x (-g, "w", 1,
        #               repeat_y( -d,
        #                         split_y(e, "w", -f, "none"), -d, "w" ), -g, "w" ), "w", "none" )  (shape=cuboid((-5,-5, 0, 3, 3, 6)) )

        ib = "interior_box"
        x = self.x
        u = self.u
        wall = self.wall
        nwall = self.nwall

        ww = rantom.uniform (3, 9, "facade_width", "Rectangular facade shape width")
        wh = rantom.uniform (3, 5, "facade_depth", "Rectangular building shape depth")
        wt = self.ext_wall_thickness + self.int_wall_thickness

        roof_height   = rantom.uniform( 0.1 * wh, 0.3 * wh, "roof_peak_height") 
        
        floor_height  = rantom.uniform(1.8, 3, "floor_height", "")
        number_floors = rantom.randrange(3, "number_of_floors", "") +1
        facade_height = floor_height * number_floors

        window_panel = self.win_cluster ()

        interior_box = extrude( 1, trans ( (0,0,-1 - self.timber_frame_depth -0.001), split_faces( ib, ib, ib, ib, x, ib ) ) )

        min_panel_width = (ww-wt-wt)/6 # stop many-small-windows chewing out my cpu
        max_panel_width = max(min_panel_width, 4)

        if "mode" in self.geom and self.geom["mode"] == "wide_windows":
            max_panel_width = 6
            min_panel_width = (ww - wt - wt) / 3

        floor  = split_x (
                wt, self.bxwall("wa"),
                -1, parallel ( interior_box, repeat_x( self.r2.uniform(-max_panel_width, -max(1,min_panel_width), "window_panel_width" ), window_panel ) ),
                wt, self.bxwall("wf") )

        pad = self.r2.uniform(0.2, 1, "bay_window_padding" )
        bays = split_x( pad * 0.5, self.bxwall("wa"),
                # -1, twall,
                -1, repeat_x ( pad * 0.5, self.nwall("wm"),
                    -2, chance("win_or_bay",
                         0.6, self.bay_windows ( self.bwall("wp"), self.bxwall("wq"), interior_box, x, self.roof ),
                         0.4, parallel ( interior_box,  window_panel ) ),
                    pad * 0.5, self.nwall("wn") ),
                pad * 0.5, self.bxwall("wf")  )

        if number_floors <= 2 : #2.5: # short buildings with bay windows
            fac = split_y ( floor_height, chance("bays_on_wins_ground", 0.5, bays, 0.5, floor), -1, repeat_y (-floor_height, floor ) )
        else: # tall building
            fac = split_y ( -1, nwall("wg"), floor_height, floor, floor_height, floor)

        if self.timber_framed: # add frame around the border of the facade to even out the thicknesses
            fac = split_x(self.timber_frame_width, "frame", -1, split_y( -1, fac, self.timber_frame_width, "frame"), self.timber_frame_width, "frame")

        wings = self.bay_windows ( self.bwall("wbw"), self.bxwall("wbw"), interior_box, x, self.roof, wing=True )

        outcrop = chance("wing_prob",
            0.3, repeat_x( u(-2,-1), self.bxwall(), u(-2,-1), split_y(u(2, facade_height), wings, -1, self.bxwall()), u(-2,-1), self.bxwall()) ,
            0.7, self.bxwall() )

        # building = split_faces(wall,  wall,  wall, wall, x)
        building = split_faces(fac,  outcrop,  outcrop, self.bxwall(name="back_wall"), x)

        exterior = split_faces(x,x,x,x,x, self.ground ) # floor around builing
        camera_box = split_y ( -2, x, 8, split_z(0.5, x, 1, "camera_box", -1, x), 2, x )

        shapes = parallel ( split_x (
            -1, exterior,
            ww, split_y(-1, parallel (exterior, camera_box),
                        wh, split_z(facade_height, parallel("backup_camera_target", building), 
                                    -1, x ),
                        -1, exterior),
            -1, exterior ),

            self.scatter_junk( ww, wh, wall ) if number_floors <= 2 else None,
            self.roof_rule(ww, wh, roof_height, facade_height, eaves=not self.timber_framed) ,

            ) (shape=cuboid((-64,-64, 0, 128, 128, 128))) 

        return shapes

    def remove_obstructing_junk(self, primary_win, camera):

        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        removed = []

        if primary_win:
            cl = camera.location
            if 'exterior_junk' in self.geom:
                for j in self.geom["exterior_junk"]:

                    jwi = j.matrix_world.inverted()
                    clw = jwi @ cl
                    hits = 0
                    for pt in primary_win.world_verts() + [primary_win.world_center()]:
#[Vector((-1.0463764667510986, -1.9372276067733765, 0.8622647523880005)), Vector((-0.5758798122406006, -1.9372276067733765, 0.8622647523880005)), Vector((-0.5758798122406006, -1.9372276067733765, 1.7305623292922974)), Vector((-1.0463764667510986, -1.9372276067733765, 1.7305623292922974)), Vector((-0.8111281394958496, -1.9372276067733765, 1.296413540840149))]
                        result, location, normal, index = j.ray_cast(clw, jwi @ pt - clw, distance=30, depsgraph=dg )
                        if result:
                            hits += 1

                    if hits >= 2:
                        print ("removing junk-in-the-way: " + j.name)
                        bpy.data.objects.remove(j, do_unlink=True)
                        removed.append(j)

        for j in removed:
            self.geom["exterior_junk"].remove(j)

    def build_uvs(self, me, uv_mode):

        bm = bmesh.new()
        bm.from_mesh(me)

        uv_layer = bm.loops.layers.uv.verify()

        if uv_mode == "norm":

            big = 1e6
            lims = [big, -big, big, -big]

            for face in bm.faces:
                for loop in face.loops:
                    lims[0] = min(lims[0], loop.vert.co.x)
                    lims[1] = max(lims[1], loop.vert.co.x)
                    lims[2] = min(lims[2], loop.vert.co.y)
                    lims[3] = max(lims[3], loop.vert.co.y)

            for face in bm.faces:
                for loop in face.loops:
                    loop_uv = loop[uv_layer]
                    loop_uv.uv[0] = (loop.vert.co.x- lims[0]) / (lims[1] - lims[0])
                    loop_uv.uv[1] = (loop.vert.co.y- lims[2]) / (lims[3] - lims[2])

        elif uv_mode == "xy":
            for face in bm.faces:
                for loop in face.loops:
                    loop_uv = loop[uv_layer]
                    loop_uv.uv = loop.vert.co.xy

        bm.to_mesh(me)

    def curves_to_mesh(self, shapes, name, extra_meshes=[], uv_mode="xy", clean = True, remove_interior=False, object_transform_is_identity=True, autosmooth=True):
        bm = bmesh.new()
        dg = bpy.context.evaluated_depsgraph_get()

        if not object_transform_is_identity:
            assert len(shapes) == 1

        for mesh in extra_meshes:
            if len ( mesh.modifiers ) > 0: #  geometry nodes (?!)
                m2 = mesh.evaluated_get(dg)
                mesh = bpy.data.meshes.new_from_object(m2, depsgraph=dg)
            elif mesh.__class__ == bpy.types.Object: # i said mesh!
                mesh = mesh.data
            bm.from_mesh(mesh)

        for shape in shapes:
            ob = shape.to_curve().evaluated_get(dg)
            me2 = ob.to_mesh()

            self.build_uvs(me2, uv_mode)

            if object_transform_is_identity:
                for v in me2.vertices:
                    v.co = shape.to_world @ v.co

            bm.from_mesh(me2)

        ext_mesh = bpy.data.meshes.new(f"Mesh_{name}")

        if clean:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist = 0.001 )
            bmesh.ops.dissolve_limit(bm, angle_limit=0.1, verts=bm.verts, edges=bm.edges)

        if remove_interior:
            self.bmesh_remove_interior_faces(bm)

        bm.to_mesh(ext_mesh)

        ext_mesh.update()
        ext_obj = bpy.data.objects.new(f"xxx-{name}", ext_mesh)

        ext_obj.data.use_auto_smooth = autosmooth

        if not object_transform_is_identity:
            ext_obj.matrix_basis = shapes[0].to_world

        bpy.context.scene.collection.objects.link(ext_obj)

        bm.free()

        return ext_obj

    def line_extrude(self, prof, shps, name, mat=None, reverse=False):

        eg = shps[0]

        obj = self.curves_to_mesh(shps, name)  # fuse end points
        mod = obj.modifiers.new('hand_rail', 'NODES')
        matic = bpy.data.node_groups['extrude-o-matic'].copy()
        matic.name = "xxx-" + matic.name
        mod.node_group = matic
        mod["Input_5"] = eg.get_value("radius")
        mod["Input_6"] = eg.get_value("height")
        mod["Input_8"] = reverse

        matic.nodes["profile"].inputs[0].default_value = prof

        if mat is not None:
            matic.nodes["setmat"].inputs[2].default_value = mat

        return obj

    def remove_interior_faces (self, mesh):
        bm = bmesh.new()  # create an empty BMesh
        bm.from_mesh(mesh.data)
        self.bmesh_remove_interior_faces(bm)
        bm.to_mesh(mesh.data)
        bm.free()

    def bmesh_remove_interior_faces(self, bm):
        togo_list = set()
        for f in bm.faces:
            togo = True
            for e in f.edges:  # interior edges have only one
                if len(list(e.link_faces)) <= 2:
                    togo = False
                    break
            if togo:
                togo_list.add(f)

        for f in togo_list:
            bm.faces.remove(f)

    def store_cam_params(self):

        camera = bpy.data.objects["camera"]

        target = bpy.data.objects["camera_target"]
        view_dir = target.location - camera.location
        rantom.store("cam_dist", view_dir.length)
        view_dir = view_dir / view_dir.length
        rantom.store_v("cam_dir", view_dir)

        azimuth = profile.angle_twixt(Vector((target.location[0], target.location[1], 0)),
                                      Vector((camera.location[0], camera.location[1], 0)),
                                      Vector((0, 1, 0)))

        elevation = profile.angle_twixt(Vector((0, target.location[1], target.location[2])),
                                        Vector((0, camera.location[1], camera.location[2])),
                                        Vector((0, 1, 0)))

        if target.location[0] < camera.location[0]:
            azimuth = -azimuth
        if target.location[2] < camera.location[2]:
            elevation = - elevation

        rantom.store("cam_azimuth", azimuth)
        rantom.store("cam_elevation", elevation)

        if config.ortho:
            camera.data.type = 'ORTHO'
            bpy.data.worlds["World"].node_tree.nodes["ortho_scale"].outputs[0].default_value = self.r2.uniform(0.2, 0.4, "ortho_background_scale")
            rantom.store("ortho_scale", camera.data.ortho_scale)
        else:
            camera.data.type = 'PERSP'
            bpy.data.worlds["World"].node_tree.nodes["ortho_scale"].outputs[0].default_value = 0
            rantom.store("camera_fov", camera.data.angle)
        return target