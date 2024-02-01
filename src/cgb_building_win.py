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
from src import materials as mat
from src import subframe as sub
from src.cgb import shp, rect, tri, cuboid, parallel, repeat_x, repeat_y, split_x, split_y, split_z
from src.cgb import split_lines, set_value
from src.cgb import split_faces, split_trif, split_trib, split_tril, split_trir, split_lines, extrude, split_tri_c, rot, spin, chance
from src import surround
from src import shutter
from src.materials import Materials

import bmesh
from mathutils import Vector, Matrix, Euler
from bmesh.types import BMVert
from collections import defaultdict


def group(shapes, names):  # groups by r2 (e.g., separate balconies).
    r2shapes = defaultdict(lambda: defaultdict(lambda: []))
    for name in names:
        for s in shapes[name]:
            wdict = s.get_value("wdict")
            r2shapes[wdict["r2"].name][name].append(s)

    return r2shapes

def create_balcony_geometry(self, shapes):

    for name, s2 in group(shapes, [
        "balcony_railing_bars",
        "balcony_glass",
        "balcony_pins",
        "balcony_base",
        "balcony_base_line",
        "balcony_hold",
        "balcony_pillar",
        "balcony_hold_line"
                ]).items():

        eg = s2["balcony_base"][0]
        wdict = eg.get_value("wdict") # window-dictionary for material pass
        r2 = wdict["r2"]
        parent = wdict["parent"]

        if "mode" in self.geom and self.geom["mode"] == "single_window":
            if not "name" in eg.get_value('wdict') or eg.get_value('wdict')["name"] != "win_primary":
                continue


        if "balcony_railing_bars" in s2:
            wdict["balcony_railing_bars"] = []
            for s in s2["balcony_railing_bars"]:
                obj = utils.to_mesh(s.to_curve())
                obj.matrix_basis = s.to_world
                obj.parent = parent
                self.create_baromatic(obj, False, r2, "balcony" )
                wdict["balcony_railing_bars"].append(obj)
                # self.geom['balconies'].append(obj)

        if "balcony_glass" in s2:
            glass = self.curves_to_mesh( s2["balcony_glass"], "balcony_glass" )
            glass.parent = parent
            wdict["balcony_glass"] = [glass]

        if "balcony_pins" in s2:
            pins = self.curves_to_mesh (s2["balcony_pins"], "balcony_pins" )
            pins.parent = parent
            wdict["balcony_pins"] = [pins]

        base_shapes = []
        base_geom = []

        if "balcony_base" in s2:
            base_shapes.extend(s2["balcony_base"])

        if "balcony_base_line" in s2:
            prof = r2.choice(bpy.data.collections["ornament_profiles"].all_objects, "balcony_base_line_profile")
            obj = self.line_extrude( prof, s2["balcony_base_line"], "balcony_profile", reverse=True)
            base_geom.append(obj)

        if len (base_shapes) + len (base_geom) > 0:
            obj = self.curves_to_mesh(base_shapes, "balcony_base2", extra_meshes=base_geom, remove_interior=True)
            obj.parent = parent
            for g in base_geom:
                bpy.data.objects.remove(g, do_unlink=True)

            wdict['balconies_bases'] = [obj]

        if "balcony_hold" in s2:
            obj = self.curves_to_mesh (s2["balcony_hold"], "balcony_hold" )
            obj.parent = parent
            wdict['balcony_hold'] = [obj]

        if "balcony_pillar" in s2:

            geom = r2.choice(bpy.data.collections["pillar_meshes"].all_objects, "balcony_pillar_mesh") # bpy.data.objects["Icosphere"]
            single_instance = geom.copy() # single copy with no-materials
            single_instance.name = "xxx"+single_instance.name
            single_instance.data = single_instance.data.copy()

            faces = []
            meshes = []

            for c in s2["balcony_pillar"]:
                if c.__class__ == cgb.cuboid: # instance pillar within cube
                    duplicate = single_instance.copy() # shallow copy - use material as above
                    duplicate.name = "xxx-"+duplicate.name
                    bpy.context.scene.collection.objects.link(duplicate)
                    pi2 = 1.570796
                    duplicate.matrix_basis =  c.to_world @ Matrix.Translation(c.centre()) @ Matrix.LocRotScale(None,None,(c.coords[3], c.coords[4], c.coords[5])) @ Matrix.Rotation(-pi2, 4, 'X')

                    duplicate.parent = parent
                    meshes.append(duplicate)

                else: # just take each face as geometry
                    faces.append(c)

            obj = self.curves_to_mesh (faces, "balcony_pillar" )
            obj.parent = parent
            wdict['balcony_pillar']=meshes + [obj]

        if "balcony_hold_line" in s2:
            prof = r2.choice(bpy.data.collections["hold_profiles"].all_objects, f"balcony_hold_profile")

            if "mode" in self.geom and self.geom["mode"] == "mono_profile":
                prof = bpy.data.collections["hold_profiles"].all_objects[0]

            obj = self.line_extrude( prof, s2["balcony_hold_line"], "balcony_hold_line")
            obj.parent = parent
            wdict["balcony_hold_line"] = [obj]


def balcony_split( self, shape, inner_win_panel=None):
    r2 = shape.get_value("wdict")["r2"]

    h, w = shape.height, shape.width # rectangle to contain the balcony and window
    nwall = self.nwall
    x = self.x

    m_min = max(0.2, h * 0.2)
    rail_height = r2.uniform(m_min, max(m_min + 0.01, min(1.4, h * 0.5)), "bal_rail_height", lookup=False)

    base_height = r2.uniform_mostly(0.2, 0.01, 0.1, min(h * 0.15, 0.4), "bal_base_height", lookup=False)
    rail_width = r2.uniform_mostly(0.2, 0.02, 0.01, min(w / 8, 0.2), "bal_rail_width")
    hold_height = r2.uniform_mostly(0.3, rail_width/2, rail_width/5, rail_width/2, "balcony_handhold_height", lookup=False)

    v_between_base_and_window = r2.uniform_mostly(0.3, 0, 0, rail_height * 0.6, "bal_v_between_base_and_window")

    h_right_window = w - 2*rail_width
    if h_right_window < 0.4:
        h_left_window = h_right_window = 0
    else:
        t = r2.uniform_mostly(0.25, 0, 0, (h_right_window - 0.3) / 2, "bal_h_between_railings_and_window" )
        ratio = r2.uniform_mostly (0.7, 0.5, 0.1, 0.9, "balcony_space_to_win")
        h_left_window = t * ratio
        h_right_window = t * ratio

    depth = r2.uniform (rail_width, max(rail_width * 3, w * 0.3), "balcony_depth")

    pillar_shrink = r2.uniform(min(0.01, rail_width / 3), rail_width / 4, "balcony_pillar_shrink")
    no_side_pins = False
    match r2.weighted_int([1,2,3 if rail_width> 0.05 else 0], "balcony_corner_pillar_type"):
        case 0:
            corner_pillar = split_faces("balcony_pillar") # simple cuboid
            no_side_pins = True
        case 1:
            corner_pillar = split_x(-pillar_shrink, x, -1, split_z(-pillar_shrink, x, -1, split_faces("balcony_pillar"), -pillar_shrink, x), -pillar_shrink, x)  # shrunk cuboid
            no_side_pins = True
        case 2:
            corner_pillar = "balcony_pillar" # instance a pillar in the cube

    #match r2.weighted_int([0,0,1], "balcony_panel_type", "railing, glass, solid..."):
    match r2.weighted_int([ 0 if  corner_pillar == "balcony_pillar" else 2, 1, 2 if rail_width > 0.2 else 0], "balcony_panel_type", "railing, glass, solid..."):
        case 0: # bars
            rail_front = split_faces(x, x, x, x, "balcony_railing_bars")
        case 1: # glass / solid
            glass_width = r2.uniform (0.005, 0.02, "glass_width")
            shrink = r2.uniform_mostly (0.2, 0, 0, min (base_height*0.15, 0.08), "glass_inset")

            pw = 0.005
            pg = r2.uniform (0.2, min(depth, w, rail_height)/2, "balcony_pin_spacing")
            pd = r2.uniform (0.01, 0.05, "balcony_pin_width")
            overlap = 0 if rail_width < 2 * glass_width else r2.uniform (0, 0.05, "balcony_pin_overlap")

            vpins = split_y(shrink + overlap, split_faces("balcony_pins"), -1, x, shrink + overlap, split_faces("balcony_pins"))
            hpins = split_x(shrink + overlap, split_faces("balcony_pins"), -1, x, shrink + overlap, split_faces("balcony_pins"))

            match r2.weighted_int([0,1,0] if no_side_pins else [4,1,3] , "balcony_pin_usage"):
                case 0:
                    pass
                case 1:
                    vpins = x
                case 2:
                    hpins = x

            if shrink == 0:
                hpins = vpins = x

            pins_front = split_z(-1, x, glass_width + 2 * pw, parallel (
                                 split_x(shrink+pg*0.5, x, -1, split_x(pd, vpins, -1, repeat_x(-pg, x, pd, vpins) ), shrink+pg*0.5, x),
                                 split_y(shrink+pg*0.5, x, -1, split_y(pd, hpins, -1, repeat_y(-pg, x, pd, hpins) ), shrink+pg*0.5, x) )
                          , -1, x )

            rail_front = parallel (pins_front, split_z(-1, x, glass_width,
                                 split_x(shrink, x, -1,
                                         split_y(shrink, x, -1, split_faces("balcony_glass"), shrink, x), #
                                         shrink, x), -1, x ) )

        case 2: # pillars along rails

            match r2.weighted_int([1, 2, 3 if rail_width> 0.05 else 0], "balcony_front_pillar_type"):
                case 0:
                    front_pillar = corner_pillar
                case 1:
                    front_pillar = split_x (-pillar_shrink, x, -1, split_z(-pillar_shrink,x, -1, split_faces("balcony_pillar"), -pillar_shrink, x), -pillar_shrink, x)  # shrunk cuboid
                case 2:
                    front_pillar = split_x (-pillar_shrink, x, -1, split_z(-pillar_shrink,x, -1, "balcony_pillar", -pillar_shrink, x), -pillar_shrink, x)  # instance a pillar in the cube

            spacing2 = r2.uniform_mostly( 0.2, rail_width/2, min(0.025, w/3), 0.05, "balcony_rail_spacing" )
            es = r2.uniform_mostly(0.5, spacing2, 0, spacing2, "balcony_extra_end_spacing")
            rail_front = split_x(es, x, -1, repeat_x(-spacing2, x, -rail_width, front_pillar, -spacing2, x), es, x)

    profile_height = r2.uniform( min (base_height/2, 0.01), base_height - 0.01, "balcony_base_extrude_height" )
    profile_depth = r2.uniform ( 0 , depth, "balcony_base_extrude_depth")
    balcony_base_line = set_value("radius", profile_depth / 2, "height", profile_height, "balcony_base_line")
    sfb = split_faces("balcony_base")

    match r2.weighted_int([1,2,2], "balcony_base_type"):
        case 0:  # solid
            base = split_faces("balcony_base")
        case 1:  # single-direction profile
            base = split_y(profile_height, split_z( -1, sfb, profile_depth, split_faces(x,x,x,split_lines(balcony_base_line, x, x, x), x) ),
                           -1, split_z( -1, sfb,profile_depth, sfb ) )
        case 2: # profile around corner
            base = split_y(profile_height,
                           split_z( -1,
                                   split_x(profile_depth, split_faces(x, x, split_lines(x, balcony_base_line, x, x), x, x),
                                           -1, sfb, profile_depth, split_faces(x, split_lines(x, x, x, balcony_base_line ), x, x, x)),
                                   profile_depth, split_x(profile_depth, x, -1, split_faces(x, x, x, split_lines( spin ( balcony_base_line, 1), x, x, x), x), profile_depth, x) ),
                           -1, split_z(-1, sfb, profile_depth, sfb))

    balcony_hold_line = set_value("radius", r2.uniform_mostly(0.5, rail_width*0.5, rail_width*0.5, rail_width*3 if rail_width < 0.02 else rail_width*0.7, "balcony_width_multiplier", lookup=False),
                                  "height", hold_height, "balcony_hold_line" )
    hold_front  = split_z( -1, split_faces( split_lines(x, x, balcony_hold_line, x) ,x,x),-1, x) #
    pillar_hold = split_z(-1, split_x(-1,  split_faces( split_lines(x, balcony_hold_line, balcony_hold_line,  x),x,x,x,x,x), -1, x), -1, x)

    def balcony_rail(spin_amount):
        return split_y (rail_height, parallel ( extrude(depth, spin (spin_amount, split_y(-1, rail_front, hold_height,
                                split_z(-1, x, -1, split_faces(
                                split_lines( balcony_hold_line, x,x, x) , x, x)) ) ) ), nwall("wbb") ), -1, nwall("wbb") )

    balcony_base = parallel ( extrude( depth + rail_width, base ), nwall("wbb") )

    balcony_front = extrude(depth + rail_width, split_z (depth, x,
                                                rail_width, split_y (base_height, x,
                                                -1, split_x(rail_width,
                                                            split_y(-1, corner_pillar, hold_height, spin ( (0,-1,0), pillar_hold) ),
                                                            -1, split_y(-1, rail_front, hold_height, hold_front), rail_width,
                                                            split_y(-1, corner_pillar, hold_height, pillar_hold) ) ) ) )

    return parallel (
            split_y(base_height, balcony_base,
                   -1, split_x (rail_width, balcony_rail ( (0,-1,0) ),
                                -1, split_x(h_left_window, nwall("wbb"), -1, split_y(v_between_base_and_window, nwall("wbb"), -1, inner_win_panel), h_right_window, nwall("wbb") ),
                                rail_width, balcony_rail ( (0, 1,0) ) )  ),
            split_y(base_height + rail_height, balcony_front, -1, x ) ) \
        (shape=shape)


def create_blind_geometry(self, shapes):

    for name, s2 in group(shapes, [
        "blind_frame"
                ]).items():

        eg = s2["blind_frame"][0]
        wdict = eg.get_value("wdict") # window-dictionary for material pass
        r2 = wdict["r2"]
        parent = wdict["parent"]

        if "mode" in self.geom and self.geom["mode"] == "single_window":
            if not "name" in eg.get_value('wdict') or eg.get_value('wdict')["name"] != "win_primary":
                continue

        if "blind_frame" in s2:

            if not "frameBounds" in wdict:
                frame_bounds = 0 # no frame! (hole in the wall/blind?)
            else:
                frame_bounds = wdict["frameBounds"][2][1]#frame_bounds[2][0]
            wall_thickness = self.ext_wall_thickness

            only_over = wall_thickness - frame_bounds < 0.10 or eg.get_value("is_bay") is not None # too thin to go under external wall
            cant_over = "surroundOBs" in wdict   # too much clutter to go over external wall

            if only_over and cant_over:
                return # panic! no space for blind
            elif only_over:
                over = True
            elif cant_over:
                over = False
            else:
                over = r2.weighted_int([1,1], "blind_goes_over") == 0

            setback = 0 if over else r2.uniform ( min(wall_thickness - frame_bounds, 0.10), wall_thickness - frame_bounds, "blind_setback" )

            obj = self.curves_to_mesh(s2["blind_frame"], "blinds", object_transform_is_identity=False)  # fuse end points

            mod = obj.modifiers.new('blind-o-matic', 'NODES')
            matic = bpy.data.node_groups['blind-o-matic'].copy()
            matic.name = "xxx-" + matic.name
            mod.node_group = matic
            mod["Input_2"] = r2.gauss_clamped(0.7, 0.3, 0 , 1, "blinds_open_amount") #open amount
            mod["Input_3"] = r2.uniform ( 0   , 0.5, "blind_handle_length" )
            mod["Input_4"] = r2.uniform ( 0.02, 0.1, "blinds_extra_roller_width" )
            mod["Input_5"] = r2.uniform_mostly (0.1, 0.02, 0, 0.004, "blinds_jitter" )
            mod["Input_6"] = r2.uniform( 0.5, 1.1, "blinds_profile_scale" )
            mod["Input_7"] = r2.uniform( 1, 1.5, "blinds_roller_scale" )

            mod["Input_8"] = 1 if over else 0 # do we add a roller above?
            mod["Input_10"] = float ( setback )

            matic.nodes["blind_profile"] .inputs[0].default_value = r2.choice(bpy.data.collections["blinds_blind_profiles"].all_objects, "blinds_blind_profiles")
            matic.nodes["roller_profile"].inputs[0].default_value = r2.choice(bpy.data.collections["blinds_roller_profiles"].all_objects, "blinds_roller_profiles")
            matic.nodes["frame_profile"].inputs[0].default_value = r2.choice(bpy.data.collections["blinds_frame_profiles"].all_objects, "blinds_frame_profiles")

            if "mode" in self.geom and self.geom["mode"] == "mono_profile":
                matic.nodes["blind_profile"].inputs[0].default_value = bpy.data.collections["blinds_blind_profiles"].all_objects[0]
                matic.nodes["roller_profile"].inputs[0].default_value = bpy.data.collections["blinds_roller_profiles"].all_objects[0]
                matic.nodes["frame_profile"].inputs[0].default_value = bpy.data.collections["blinds_frame_profiles"].all_objects[0]


            wdict["blinds"] = [obj]

            obj.parent = parent


def blind_split (self, shape):

    x = self.x
    r2 = shape.get_value("wdict")["r2"]


    wdict = shape.get_value("wdict")
    if "mode" in wdict and wdict["mode"] == "only_squares":  # hack to make a square blind
        ww = min(shape.width, shape.height)
        s2 = cgb.rect(shape.x + (shape.width - ww) / 2, shape.y + (shape.height - ww) / 2, ww, ww, to_world=shape.to_world, name=shape.name + "_square_patch")
        s2.parent = shape.parent
        s2.lookup = shape.lookup
        shape = s2


    return parallel ( "blind_frame" )(shape=shape)
        #,  ) (shape=shape)

def win_cluster(self):

    u = self.u
    win = self.win
    nwall = self.nwall

    def shutter_l(shape):
        return self.create_shutter(shape=shape, left=True)

    def shutter_r(shape):
        return self.create_shutter(shape=shape, left=False)

    if self.timber_framed:
        win = split_x(self.timber_frame_width, "frame", -1, split_y(self.timber_frame_width, "frame", -1, self.win, self.timber_frame_width, "frame"), self.timber_frame_width, "frame")

    shutters = set_value( "has_shutters", True, chance(
        "shutters_both",
                      lambda shape: 10 if shape.width > 1 else 0, split_x(
            -0.5, nwall("wss"),
            -1,
            parallel(win,
                     split_x(-1, shutter_l, -1, shutter_r)),
            -0.5, nwall("wss")),
                      0.25, split_x(-1, nwall("wss"), -1, split_x (-1, parallel(win, shutter_l)) ), # we rely on the total window size being shutter.parent....
                      0.25, split_x(-1, split_x (-1, parallel(win, shutter_r) ), -1, nwall("wss")))
                          )

    win_or_shutter_or_blind = chance("add_shutters_to_window",
                                     4, shutters,
                                     2, set_value ("has_blind", True, parallel (self.blind_split, win ) ),
                                     10, win)

    left, y_bottom, y_win_height, y_top, right = -0.5, u(-1, -0.3), u(-3, -0.6), u(-1, -0.3), -0.5
    if "mode" in self.geom and self.geom["mode"] == "wide_windows":
        left, y_win_height, right = -0.1, u(-1.5, -0.6), -0.1

    inner_win_panel = split_x(left, nwall("wb"), -1, split_y(y_bottom, nwall("wc"), y_win_height, win_or_shutter_or_blind, y_top, nwall("wd")), right, nwall("we"))

    maybe_balcony = split_x( u(-0.4, -0.1, key="win_cluster_pad"), nwall("wb"), -1, chance("balcony", \
            lambda shape: 1 if shape.y > 1 and shape.width > 0.5 and shape.height > 0.5 else 0,
                           set_value( "has_balcony", True, split_y(-0.3, nwall("wc"), u(1, 2, key="balcony_win_height"),
                                                                   partial ( self.balcony_split, inner_win_panel=win_or_shutter_or_blind ), -1, nwall("wd") ) ), \
            self.chance_blind, inner_win_panel ), u(-0.4, -0.1, key="win_cluster_pad"), nwall("we"))

    return set_value( "wdict", self.win_dict, maybe_balcony )


def create_win(self, name="win_anon", shape=None, primary=False, do_surround=True, expand_curtains=True,
               blinds=True, ext_wall_thickness=0.1, int_wall_thickness=0.1, camera=None):

    wdict = shape.get_value("wdict")
    win_rand = wdict["r2"]
    win_group = wdict["parent"]
    wdict["name"] = name
    win_group.name = f"xxx-{name}"
    has_balcony = shape.get_value("has_balcony") != None
    has_blind = shape.get_value("has_blind") != None
    has_shutters = shape.get_value("has_shutters") != None

    if win_rand is not None:
        pass
        # win_rand.name = name # hack to label primary, nsew... windows. don't change names of randomcaches - it messes up parameters.
    else:
        win_rand = rantom.RantomCache(failure_rate=0.3, parent=self.r2, name=name)

    win_rand.store("name", name, "name of dictionary")

    window_type = win_rand.weighted_int([1, 1, 80], "generate_frame", "do we have a frame and glass?")
    has_bars = win_rand.weighted_int([0 if has_blind or has_shutters else 1,5], "bars_on_window", lookup=False) == 0

    slightly_smaller = copy(shape)
    slightly_smaller.offset(0.01)
    wdict["rect"] = slightly_smaller
    wdict["do_physics"] = False

    window_shape = Shape(wdict).go(shape, wdict, r2=win_rand, circular=not has_balcony)  # what shape is the hole/window?
    window_shape.parent = win_group

    win_rand.store("width", shape.dim[2])
    win_rand.store("height", shape.dim[3])
    win_rand.store("ratio", shape.dim[2]/shape.dim[3])

    wallframe = utils.extrude_edges(window_shape, (0, 0, ext_wall_thickness), name="xxx-ext-side", add=False)  # between the hole/rectfill in the wall and the window-frame
    wallframe.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -ext_wall_thickness)))

    wallframe.parent = win_group
    bpy.context.scene.collection.objects.link(wallframe)

    self.geom['ext_side_wallOBs'].append(wallframe)

    wdict['int_wall_side'] = int_side = utils.extrude_edges(window_shape, (0, 0, int_wall_thickness), name="xxx-int-side")  # between the window and interior wall/rectfill
    int_side.parent = win_group
    self.geom['internal_wallOBs'].append(int_side)
    int_side.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -ext_wall_thickness - int_wall_thickness)))

    rf = shp(curve=wdict["rectfill"], to_world=shape.to_world)
    rf.to_world = shape.to_world
    self.wall_names.add("wrf")

    mesh_rectfill = utils.to_mesh(wdict["rectfill"], add=False)  # between whatever shape window and rectangle wall tile

    mesh_rectfill_int = mesh_rectfill.copy()
    bpy.context.scene.collection.objects.link(mesh_rectfill_int)
    mesh_rectfill_int.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -ext_wall_thickness - int_wall_thickness)))
    mesh_rectfill_int.parent = self.walls_root
    self.geom['internal_wallOBs'].append(mesh_rectfill_int)

    if has_bars:
        self.create_bars(win_rand, wdict, ext_wall_thickness, shape, win_group, window_shape)

    if not blinds:
        window_type = 2

    force_windows_closed = False

    if "lvl" in self.geom:

        # dummy_int_side = utils.extrude_edges(window_shape, (0, 0, int_wall_thickness + ext_wall_thickness), name="xxx-dummy-int-side")  # between the window and interior wall/rectfill
        # dummy_int_side.parent = win_group
        # self.geom['internal_wallOBs'].append(dummy_int_side)
        # wdict['int_wall_side_lvl2'] = dummy_int_side
        # dummy_int_side.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -ext_wall_thickness - int_wall_thickness)))
        # dummy_int_side.hide_viewport = True
        # dummy_int_side.hide_render = True

        wc = wallframe.copy()
        bpy.context.scene.collection.objects.link(wc)
        wc.data = wallframe.data.copy()
        wc.hide_render = True
        wc.hide_viewport = True
        wc.name = "xxx-ext-side-lvl2"
        wdict['ext_side_wallOB_lvl2'] = wc
        self.geom['exterior_wallOBs'].append([wc])

        force_windows_closed = True



        # create a pane of glass that we can show for a window without a frame.

        for name, offset in [("lvl3", ext_wall_thickness), ("lvl2", 0)]:
            dps = self.dummy_pane(shape, wdict, window_shape, offset)

            for dp in dps:
                dp.name = f"xxx-{name}-dummy-glass"
                dp.hide_render = True
                dp.hide_viewport = True
            wdict[f"dummy_pane_{name}"] = dps

        mesh = window_shape.to_mesh()
        meshOB = bpy.data.objects.new("xxx-dummy-wall-lvl1", mesh.copy())
        meshOB.hide_render = True
        meshOB.hide_viewport = True
        bpy.context.scene.collection.objects.link(meshOB)
        wdict["dummy_wall"] = [meshOB]
        meshOB.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, 0)))

    match window_type:
        case 0:  # blind window

            blind_fill = utils.to_mesh(shape.to_curve(), add=True)
            blind_fill.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -ext_wall_thickness)))
            blind_fill.name = "xxx-blind_fill"
            wdict['blind_fill'] = [blind_fill]
            blind_fill.parent = win_group

        case 1:  # just a hole in the facade!

            if "lvl" in self.geom and self.geom["lvl"] <= 9: # panic! add a pane of glass!
                self.dummy_pane(shape, wdict, window_shape, ext_wall_thickness)

        case _:  # regular window with a frame, glass and maybe curtains

            # create frame and glass
            frame_root = sub.Subframe(wdict, force_windows_closed=force_windows_closed).go("frame", r2=win_rand, open_windows=not (has_bars or has_blind or has_balcony) )
            wdict["frameBounds"] = frame_bounds = utils.world_bounds_children(frame_root) # size of window lying on floor at inside/outside line (e.g., z, up).

            # create curtains before we move the window out of facade-space
            if primary:

                curt.Curtains().go(wdict, -(ext_wall_thickness + int_wall_thickness), int_wall_thickness, frame_bounds, win_rand, expand=expand_curtains)
                self.do_physics |= wdict["do_physics"]

                if "curtainOBs" in wdict:
                    for o in wdict["curtainOBs"]:
                        o.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -ext_wall_thickness - int_wall_thickness - 0.03 + wdict["curtains_z_offset"])))
                        o.parent = win_group

            # move all to world space
            frame_root.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -ext_wall_thickness)))
            frame_root.parent = win_group

            win_group.parent = self.facade_root

    if primary:  # we are the main attraction. setup camera location and direction.

        # position camera target within window
        target = bpy.data.objects["camera_target"]
        bl = np.array(window_shape.bound_box[0][:])
        tr = np.array(window_shape.bound_box[6][:])
        cen = bl + (tr - bl) * 0.5

        # use global parameter space
        target_jitter = 0.1 # balcony was 0.2
        pos = [cen[0] + self.r2.uniform(-target_jitter, target_jitter, "cam_target_x_offset"),
               cen[1] + self.r2.uniform(-target_jitter, target_jitter, "cam_target_y_offset"), cen[2]]

        target.location = shape.to_world @ Vector(pos)
        bpy.data.objects["cen_target"].location = shape.to_world @ Vector(cen)

        if config.ortho:

            os = np.linalg.norm(bl - tr) * self.r2.gauss(1.1, 0.2, "camera_fov_spread")
            if target.location.z * 2 < os:
                os = target.location.z * 2 # try not to show below buildings

            camera.data.ortho_scale = os

        else:

            # more camera positions at same level as window pls. see materials.set_circle_camera for an improvement.
            if rantom.weighted_int([2,1], "camera_to_window_height") == 0:
                cen_w =  shape.to_world @ Vector(cen)
                camera.location[2] = max(0.3, cen_w[2] + self.r2.uniform(-2, 2, "cam_extra_z_offset"))
                camera.location[0] = max(0.3, cen_w[0] + self.r2.uniform(-1, 1, "cam_extra_x_offset"))

            fov = float(abs(profile.angle_twixt(shape.to_world @ Vector(bl), camera.location, shape.to_world @ Vector(tr))))
            camera.data.angle = fov * self.r2.gauss(1.1, 0.1, "camera_fov_spread")

        ec = bpy.data.objects["cen_camera"]
        cc = bpy.data.objects["canonical_camera"]
        ec.location = cc.location = Matrix.Translation(Vector((  0, -5,0) ) ) @ shape.to_world @ Vector(cen)

    if do_surround and not has_blind and win_rand.weighted_int([5,1], "create_surround") == 0:

        wdict['surroundOBs'] = surround.Surround(wdict, -ext_wall_thickness).go(r2=win_rand)

        for o in wdict['surroundOBs']:
            o.matrix_basis = shape.to_world
            o.parent = win_group

    return {"window": [shape], "wrf": [rf]}


def dummy_pane(self, shape, wdict, window_shape, ext_wall_thickness):
    glist = []
    gwidth = 0.01
    sub.create_glass(window_shape, 0.01, glist)
    for o in glist:
        o.name = "xxx-dummy-glass"
        o.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, -gwidth-ext_wall_thickness)))

    if "frameGlassOBs" in wdict:
        wdict["frameGlassOBs"].extend(glist)
    else:
        wdict["frameGlassOBs"] = [*glist]

    return glist


def create_bars(self, r2, wdict, ext_wall_thickness, shape, win_group, window_shape):

    wall_thickness_limit = 0.10
    # we count bars over just the bottom of the window as balcony
    is_balcony = ext_wall_thickness > wall_thickness_limit and shape.height > 0.6 and r2.weighted_int([1,5], "bars_are_really_balcony") == 0

    if ext_wall_thickness < wall_thickness_limit:
        over = True
    elif is_balcony or shape.get_value("has_shutters") is not None:
        over = False
    else:
        over = r2.weighted_int([1, 1], "bars_over_windows") == 0

    if is_balcony:
        shape = cgb.rect(shape.x, shape.y, shape.width, shape.height, to_world=shape.to_world, name=shape.name+"2")
        shape.height = r2.uniform ( max(shape.height/4, 0.1), min(shape.height/2, 0.4), "bars_as_balcony_height" )

    bar_holder = utils.to_mesh(shape.to_curve())
    # bar_holder = self. utils.to_mesh(window_shape)
    bar_holder.matrix_basis = shape.to_world @ Matrix.Translation(Vector((0, 0, 0 if over else -ext_wall_thickness * r2.uniform(0.2, 0.8, "bars_under_pushback"))))
    bar_holder.name = "xxx-balcony" if is_balcony else "xxx-bars"
    bar_holder.parent = win_group

    dname = 'balconies' if is_balcony else 'barOBs'

    if dname in wdict:
        wdict[dname].append (bar_holder)
    else:
        wdict[dname] = [bar_holder]

    self.create_baromatic(bar_holder, over, r2, horz_only=is_balcony)


def create_baromatic(self, bar_holder, over, r2, name="bars", mat=None, horz_only=False):

    bar_mod = bar_holder.modifiers.new('blinds', 'NODES')
    baro = bpy.data.node_groups['bar-o-matic'].copy()
    baro.name = "xxx-" + baro.name
    bar_mod.node_group = baro
    profs = list(bpy.data.collections["bar_profiles"].all_objects)



    if not over:
        profs = [p for p in profs if '[i]' in p.name]

    baro.nodes["Object Info"].inputs[0].default_value = r2.choice(profs, f"v_bar_profile_{name}")
    baro.nodes["Object Info.002"].inputs[0].default_value = r2.choice([p for p in profs if '[v]' not in p.name], f"h_bar_profile_{name}")
    baro.nodes["Object Info.003"].inputs[0].default_value = r2.choice(bpy.data.collections["bar_cross_sections"].all_objects, f"h_bar_cross_sec_shape_{name}")
    baro.nodes["Object Info.001"].inputs[0].default_value = r2.choice(bpy.data.collections["bar_cross_sections"].all_objects, f"v_bar_cross_sec_shape_{name}")

    if "mode" in self.geom and self.geom["mode"] == "mono_profile":
        baro.nodes["Object Info"].inputs[0].default_value = profs[0]
        baro.nodes["Object Info.002"].inputs[0].default_value = [p for p in profs if '[v]' not in p.name][0]
        baro.nodes["Object Info.003"].inputs[0].default_value = bpy.data.collections["bar_cross_sections"].all_objects[0]
        baro.nodes["Object Info.001"].inputs[0].default_value = bpy.data.collections["bar_cross_sections"].all_objects[0]

    baro.nodes["Value.003"].outputs[0].default_value = r2.uniform(0.01, 0.04, f"h_bar_cross_sec_size_{name}")
    baro.nodes["Value.001"].outputs[0].default_value = r2.uniform(0.01, 0.04, f"v_bar_cross_sec_size_{name}")
    baro.nodes["Value.002"].outputs[0].default_value = r2.uniform(0.1, 0.3, f"bar_depth_scale_{name}")  # how far out the bars come
    baro.nodes["Value.004"].outputs[0].default_value = r2.uniform(0.05, 0.2, f"h_bar_spacing_{name}")
    baro.nodes["Value"].outputs[0].default_value = r2.uniform(0.05, 0.2, f"v_bar_spacing_{name}")
    baro.nodes["Boolean.002"].boolean = r2.weighted_int([1, 2], f"bars_have_bolts_or_welds_{name}") == 1 if over else False
    match r2.weighted_int([0, 0, 1] if horz_only else [2, 1, 1], f"bars_to_show_{name}"):  # do we have horizontal, vertical or both direcitons for bars
        case 0:
            h, v = False, False
        case 1:
            h, v, = True, False
        case 2:
            h, v, = False, True
    baro.nodes["Boolean"].boolean = h
    baro.nodes["Boolean.001"].boolean = v
    if mat is None:
        mat = Materials(self.geom).got_metal(r2, f"window_bars_{name}")
    baro.nodes["setmat"].inputs[2].default_value = mat

    return baro, mat

def create_shutter(self, shape=None, left=False):

    wdict = shape.get_value("wdict")
    if "mode" in wdict and wdict["mode"] == "only_squares": # hack to make a square shutter
        ps = shape.parent
        ww = min (ps.width, ps.height)

        if abs ( ps.width - shape.width ) < 0.05: # there is a single shutter over the whole window
            shape = cgb.rect(shape.x + (shape.width - ww) / 2, shape.y + (shape.height - ww) / 2, ww, ww, to_world=shape.to_world, name=shape.name + "_square_patch")
        else: # we're one of two shutters

            ww2 = ww/2
            if left:
                shape = cgb.rect(shape.x, shape.y + (shape.height - ww) / 2, ww2, ww, to_world=shape.to_world, name=shape.name + "_square_patch")
            else:
                shape = cgb.rect(shape.x + (shape.width-ww2), shape.y + (shape.height - ww) / 2, ww2, ww, to_world=shape.to_world, name=shape.name + "_square_patch")

    shutter_root = shutter.Shutter().go(shape.to_curve(), wdict, 0.05, wdict["r2"], left=left, idx=self.shutter_count)
    shutter_root.matrix_basis = shape.to_world @ shutter_root.matrix_basis
    shutter_root.parent= wdict["parent"]
    self.shutter_count += 1

    return {}
