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
from src.cgb import split_lines, set_value, gt, lt, trans
from src.cgb import split_faces, split_trif, split_trib, split_tril, split_trir, split_lines, extrude, split_tri_c, rot, spin, chance
from src import surround
from src import shutter
from src import adjacent

import bmesh
from mathutils import Vector, Matrix
from bmesh.types import BMVert

def bay_windows(self, wall, twall, interior_box, x, roof, wing=False, name="none"):

    if self.timber_framed:
        wall = twall # stop interior wall intersecting through timber frame

    name = self.bay_window_count
    self.bay_window_count += 1
    skirt = "roof_skirt"

    fw_min, fw_max = 0.07, 0.3
    bf_min, bf_max = 0.3, 1

    if "mode" in self.geom and self.geom["mode"] == "wide_windows":
        fw_min, fw_max = 0.03, 0.1
        bf_min, bf_max = 0.2, 1.5
    frame_width = max(self.bay_wall_width * 2, self.r2.uniform(fw_min, fw_max, f"bay_frame_width_{name}"))
    bottom_frame_width = self.r2.uniform_mostly(0.2, frame_width, bf_min, bf_max, f"bay_bottom_frame_width_{name}")
    wwidth = self.r2.uniform_mostly(0.1, 0.2, 0.5, 2, f"bay_win_width_{name}")

    def bay_win(shape):
        self.bay_wins.append(shape)

        if not wing:
            self.max_bay_front = max(self.max_bay_front, depth)

        if (shape.normal() - Vector((1,0,0))).magnitude > 0.01: # not pointing forwards
            return {"win2": [shape]}
        else:
            return {self.win: [shape]}

    if not wing:
        bay_windows = set_value("is_bay", True,
                split_y(bottom_frame_width, wall,
                              -1, split_x(0.5 * frame_width, wall,
                                          -1, repeat_x(0.5 * frame_width, wall,
                                                       -wwidth,
                                                            lt (lambda shape : shape.size_(0), 0.2, wall,
                                                            set_value( "wdict", self.win_dict,
                                                                           chance("add_blind_to_bay_window",
                                                                                  self.chance_blind, bay_win,
                                                                                  1, set_value("has_blind", True, parallel(self.blind_split, bay_win)))
                                                                           ) ),
                                                       0.5 * frame_width, wall),
                                          frame_width * 0.5, wall),
                              max (self.roof_skirt_height + 0.02, frame_width), wall) )
    else:
        bay_windows = wall

    if self.timber_framed: # add frame around the border of the facade to even out the thicknesses
        frame = "frame"
        bay_windows = split_x(self.timber_frame_width, frame, -1, split_y( self.timber_frame_width, frame,-1, bay_windows, self.timber_frame_width, frame), self.timber_frame_width, frame)

    if wing or self.r2.randrange(2, f"bay_windowhape_{name}") == 0:  # square walls on sides of bay window

        depth = self.r2.uniform(0.5, 5 if wing else 2, f"bay_width_{name}")
        sr = parallel ( roof, split_lines( spin(skirt), spin(skirt), x, spin(skirt) ) )

        if self.r2.randrange(3, f"bay_roof_type_{name}") == 0:
            # # bay_roof = split_faces( roof, x, x, x, x, x)
            # bay_roof = split_faces( roof, roof, roof, roof, roof, roof)
            bay_roof = split_faces(rot(sr, math.pi, 0, 0), x, x, x, x, x)
            roof_height = 0.001
        else:
            bay_roof = split_tri_c(1, spin( sr, 2), twall, x)
            roof_height = self.r2.uniform(0.2, 1, f"bay_shed_roof_height_{name}")

        # bay_base = split_faces(x, spin ( bay_windows, 1), spin ( wall, 1), x, spin ( bay_windows,2), x)
        bay_base = split_faces(x, spin(bay_windows, 1), spin(bay_windows, 3), x, bay_windows, x)

        bay = parallel(extrude(depth, split_y(-1, bay_base, roof_height, bay_roof)), interior_box)

    else:  # sloped walls on sides of bay window

        depth = self.r2.uniform(0.3, 1, f"bay_window_sloped_corner_width_{name}")

        if self.r2.weighted_int([1, 3], f"bay_roof_type_{name}") == 0:
            roof_height = 0.001
        else:
            roof_height = depth * self.r2.uniform_mostly(0.5, 0.5, 0.2, 0.7, f"bay_roof_slope_{name}")

        br = split_x(
            depth, split_tri_c(8, roof),
            -1, split_tri_c(1, spin(roof, 2)),
            depth, split_tri_c(10, roof))
        bay_roof = parallel(br, split_faces(x, x, x, x, x, rot(wall, 0, math.pi, 0)))  # patch wall in facade

        bws = parallel(bay_windows, split_lines(x, x, skirt, x))

        bay_base = split_x(
            depth, split_tri_c(2, spin(bws, 1)),
            -1, split_faces(x, x, x, x, bws, x),
            depth, split_tri_c(3, spin(bws, 3)))

        bay = parallel(extrude(depth, split_y(-1, bay_base, roof_height, bay_roof)), interior_box)

    return bay


def create_timber_frame(self, shapes, frame_width, frame_depth):
    frame = "frame"
    panel = "waf"
    x = "none"
    fw = frame_width  # = rantom.uniform(0.01, 0.1, f"timber_width_2")

    for n in self.wall_names:
        if n != "wrf":  # there should be a single wall_name left (but ignore rectfills )
            wall_name = n
            break

    sy = rantom.uniform(0.7, 2, "frame_subdiv_y")
    sx = rantom.uniform(0.7, 2, "frame_subdiv_x")

    def fw_const():
        return fw

    def apply_small(dim, thresh, small, big, shape):
        if shape.size_(dim) < thresh:
            return small(shape=shape)
        else:
            return big(shape=shape)

    def if_small(dim, thresh, small, big):
        return functools.partial(apply_small, dim, thresh, small, big)

    # frame_shape = extrude (frame_depth, split_faces(frame))
    frame_shape = frame # extrude (frame_depth, trans((0,0,-frame_depth), split_faces(frame)))

    merged_rects = [x for x in shapes[wall_name] if not isinstance(x, rect)]

    for ss in adjacent.same_to_world(shapes[wall_name]).values(): # merge rectangles into big ones.
        merged_rects.extend ( adjacent.merge_rects(ss) )



    # wall_name = next( iter( self.wall_names ) )
    for ws in merged_rects: # shapes[wall_name]:

        if str ( ws.__class__ ) == str ( rect ):

            recess_panel = extrude(-frame_depth, split_faces(frame, frame, frame, frame, panel, x))

            #recess_panel = extrude(-frame_depth, split_faces(x, x, x, x, panel, x))
            # y_splits =
                # split_x(fw, frame_shape,
                #     -1, if_small(1, frame_width * 4, recess_panel, split_y(fw, frame_shape, -1, recess_panel )),
                #         )
            # frames = recess_panel (shape=ws)
            # if_small(0, frame_width * 4, recess_panel, split_x(fw, frame, -1, y_splits, fw, frame))))(shape=ws)
            # if_small(0, frame_width * 4, y_splits, split_x(fw, frame_shape, -1, y_splits))))(shape=ws)

            frames = repeat_y ( -sy, repeat_x ( -sx, split_x(fw, frame, -1, repeat_y(-sy, split_y(fw, frame, -1, recess_panel, fw, frame)), fw, frame)))(shape=ws)

            # frames = repeat_y(-sy, repeat_x(sx, split_x(fw, frame, -1,
            #                                             repeat_y(sy, split_y(fw, frame, -1, recess_panel, fw, frame)), fw, frame)))(shape=ws)
            shapes[frame].extend(frames[frame])
            shapes[panel].extend(frames[panel])
        elif isinstance(ws, cgb.tri):
            # pass
            shapes[panel].append(ws)
        else:
            shapes[panel].append(ws)

    del shapes[wall_name]

    self.wall_names.add(panel)

    frame_wall = list(shapes[frame])

    # for all shapes[frame] adjacent to some shape[win], remove from list of frames
    togo = set()

    rectfill_obj = self.curves_to_mesh(shapes["wrf"], f"timber-wall-frame-rectfill")

    if False: # find wall-frame components to be wall-frames too buggy for now...
        for r in [x for x in frame_wall if isinstance(x, rect)]:
            for w in [x for x in shapes[self.win] if isinstance(x, rect)]:
                if w.to_world == r.to_world:
                    my, mx = r.y + r.height / 2, r.x + r.width / 2
                    if (r.x + r.width == w.x or w.x + w.width == r.x) and w.y < my < w.y + w.height:
                        togo.add(r)  # vertical
                    if (r.y + r.height == w.y or w.y + w.height == r.y) and w.x < mx < w.x + w.width:
                        togo.add(r)  # horizontal

        frame_wall = [x for x in frame_wall if x not in togo]

        wallframe_obj = self.curves_to_mesh(togo, f"timber-wall-frame")
        self.geom['exterior_wallframeOBs'] = [[wallframe_obj], [rectfill_obj]]
    else: # no wall-frame on timber-frames
        self.geom['exterior_wallOBs'].append([rectfill_obj])

    frame_obj = self.curves_to_mesh(frame_wall, f"timber-frame")
    self.geom['exterior_wallOBs'].append([frame_obj])

    del shapes["wrf"]

    # mydict[k_new] = mydict.pop(k_old)

    frame_obj.parent = self.walls_root

    sign_chance = self.r2.uniform(-0.8, 1.1, "chance_of_sign_per_rect")
    n = 0
    for s in shapes[panel]:
        n += 1
        if isinstance(s, rect) and self.r2.random(f"add_sign_{wall_name}_{n}") > sign_chance:
            self.scatter_sign(0.005, self.walls_root)(shape=s)

    return frame_obj


def merge_walls(self, shapes, single_material):
    number_wall_mats = 1
    names = self.wall_names.copy()
    add_wrf = False

    if single_material:
        number_wall_mats = 1
        if "wrf" in names:  # just ignore the rect-fill
            names.remove("wrf")
            add_wrf = True
    elif rantom.random("single_wall_mat") < 0.33 and len(names) > 1:
        number_wall_mats = rantom.randrange(min(2, int(len(names) - 1)), "wall_mat_count") + 1

    tmp = 0
    while len(names) > number_wall_mats:  # for i in range(rantom.randrange(len(self.wall_names) * 2, "merge_walls")):
        a = rantom.choice(names, f"merge_walls_a_{tmp}")
        b = rantom.choice(names, f"merge_walls_b_{tmp}")

        tmp += 1

        if a == b:
            continue

        shapes[a].extend(shapes[b])
        names.remove(b)
        del shapes[b]

    if add_wrf:
        names.add("wrf")

    self.wall_names = names


def w(self, shape=None, name="w", ext_wall_thickness=None, int_wall_thickness=None, interior=True):
    # wrapper for lambdas above
    if ext_wall_thickness is None:
        ext_wall_thickness = self.ext_wall_thickness
    if int_wall_thickness is None:
        int_wall_thickness = self.int_wall_thickness

    return self.create_wall(shape=shape, ext_wall_thickness=ext_wall_thickness, int_wall_thickness=int_wall_thickness, name=name, interior=interior)


def create_wall(self, shape=None, interior=True, name="w", ext_wall_thickness=0.1, int_wall_thickness=0.1):
    self.ext_curves.append(shape)
    self.wall_names.add(name)

    if interior:
        # do interior wall
        mesh = utils.to_mesh(shape.to_curve(z=-(ext_wall_thickness + int_wall_thickness)))
        mesh.parent = self.walls_root
        mesh.name = f"xxx-internal-wall"
        mesh.matrix_basis = shape.to_world
        # utils.apply_transform_to_obj(shape.to_world(), mesh)
        self.geom['internal_wallOBs'].append(mesh)

    return {name: [shape]}