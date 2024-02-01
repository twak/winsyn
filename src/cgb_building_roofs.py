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
from src.cgb import split_lines
from src.cgb import split_faces, split_trif, split_trib, split_tril, split_trir, split_lines, extrude, split_tri_c, rot, spin, chance
from src import surround
from src import shutter

import bmesh
from mathutils import Vector, Matrix
from bmesh.types import BMVert


def roof_rule(self, ww, wh, roof_height, facade_height, eaves=True):
    wall = self.bxwall()
    roof = "roof"
    x = self.x
    skirt = "roof_skirt"
    sskirt = spin("roof_skirt")
    gutter = "roof_gutter"
    eave_width = rantom.uniform(0.1, 0.6, "eave_overhang", "Horizontal distance of eave overhang")
    eave_height = rantom.uniform(0.1, 0.6, "eave_height", "Vertical distance of eave overhang")

    # functions which allow us to alter eave height in below roof-match statement...
    def eh(shape):
        return eave_height

    def fh_eh(shape):
        return facade_height - eave_height

    proof = parallel(roof, split_lines(  gutter, x, x, x))
    proot = parallel(roof, split_lines(x, gutter, x))

    roof_eave_a = split_x(-1, x, eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(2, proof), -1, x))
    roof_eave_b = split_x(eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(3, proof), -1, x), -1, x)
    roof_eave_c = split_y(-1, x, eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(0, proof), -1, x))
    roof_eave_d = split_y(eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(1, proof), -1, x), -1, x)

    roof_eave_1 = split_x(-1, x, eave_width, split_y(-1, x, eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(4, proot), -1, x)))
    roof_eave_2 = split_x(eave_width, split_y(eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(6, proot), -1, x), -1, x), -1, x)
    roof_eave_3 = split_x(-1, x, eave_width, split_y(eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(7, proot), -1, x), -1, x))
    roof_eave_4 = split_x(eave_width, split_y(-1, x, eave_width, split_z(fh_eh, x, eh, cgb.split_tri_c(5, proot))), -1, x)

    if not eaves or rantom.weighted_int([1, 4], "no_eaves") == 0:
        roof_eave_1 = roof_eave_2 = roof_eave_3 = roof_eave_4 = roof_eave_a = roof_eave_b = roof_eave_c = roof_eave_d = x

    match 2: # self.r2.weighted_int([2, 2, 2, 1], "roof_type", "type of roof structure we create - hip, shed, gable"):
        case 0:  # hip roof
            if wh > ww:  # + self.r2.uniform(-1,1, "noise_on_hip_roof_split_dir")
                pointy = parallel(split_y(
                    -1, split_x(
                        -1, cgb.split_tri_c(4, roof),
                        -1, cgb.split_tri_c(5, roof)),
                    -1, split_x(
                        -1, cgb.split_tri_c(2, roof),
                        -1, cgb.split_tri_c(3, roof)),
                    -1, split_x(
                        -1, cgb.split_tri_c(7, roof),
                        -1, cgb.split_tri_c(6, roof))),
                    split_faces(split_lines(sskirt, x, x, x), x))
                eave_height = eave_width * roof_height / (ww / 2)
            else:
                pointy = parallel(split_x(
                    -1, split_y(
                        -1, cgb.split_tri_c(4, roof),
                        -1, cgb.split_tri_c(7, roof)),
                    -1, split_y(
                        -1, cgb.split_tri_c(0, roof),
                        -1, cgb.split_tri_c(1, roof)),
                    -1, split_y(
                        -1, cgb.split_tri_c(5, roof),
                        -1, cgb.split_tri_c(6, roof))),
                    split_faces(split_lines(sskirt, x, x, x), x))
                eave_height = eave_width * roof_height / (wh / 2)
        case 1:  # shed roof
            proof =parallel ( roof, split_lines(sskirt, sskirt, sskirt, sskirt) )
            match self.r2.randrange(4, "shed_roof_dir", "type of roof structure we create"):
                case 0:
                    pointy = cgb.split_tri_c(0, proof, wall, wall),
                    roof_eave_1 = roof_eave_2 = roof_eave_3 = roof_eave_4 = roof_eave_a = roof_eave_b = roof_eave_d = x
                    eave_height = eave_width * roof_height / wh
                case 1:
                    pointy = cgb.split_tri_c(1, proof, wall, wall)
                    roof_eave_1 = roof_eave_2 = roof_eave_3 = roof_eave_4 = roof_eave_a = roof_eave_b = roof_eave_c = x
                    eave_height = eave_width * roof_height / wh
                case 2:
                    pointy = cgb.split_tri_c(2, proof, wall, wall)
                    roof_eave_1 = roof_eave_2 = roof_eave_3 = roof_eave_4 = roof_eave_d = roof_eave_b = roof_eave_c = x
                    eave_height = eave_width * roof_height / ww
                case 3:
                    pointy = cgb.split_tri_c(3, proof, wall, wall)
                    roof_eave_1 = roof_eave_2 = roof_eave_3 = roof_eave_4 = roof_eave_d = roof_eave_a = roof_eave_c = x
                    eave_height = eave_width * roof_height / ww
        case 2:  # gable
            proof = parallel(roof, split_lines(sskirt, sskirt, x, sskirt))

            match self.r2.randrange(2, "gable_roof_dir", "direction of gable roof split"):
                case 0:
                    pointy = split_y(
                        -1, cgb.split_tri_c(0, proof, wall),
                        -1, cgb.split_tri_c(1, proof, wall))
                    roof_eave_1 = roof_eave_2 = roof_eave_3 = roof_eave_4 = roof_eave_a = roof_eave_b = x
                    eave_height = eave_width * roof_height / (wh / 2)
                case 1:
                    pointy = split_x(
                        -1, cgb.split_tri_c(2, proof, wall),
                        -1, cgb.split_tri_c(3, proof, wall))
                    roof_eave_1 = roof_eave_2 = roof_eave_3 = roof_eave_4 = roof_eave_c = roof_eave_d = x
                    eave_height = eave_width * roof_height / (ww / 2)
        case 3:  # flat roof+
            pointy = split_faces(x, x, x, x, x, parallel(rot(roof, 3.141, 0, 0), split_lines(skirt, skirt, skirt, skirt)))

    return split_x(
        -1, split_y(-1, roof_eave_1, wh, roof_eave_a, -1, roof_eave_3),
        ww, split_y(-1, roof_eave_c,
                    wh, split_z(facade_height, x, roof_height, pointy, -1, x),
                    -1, roof_eave_d),
        -1, split_y(-1, roof_eave_4, wh, roof_eave_b, -1, roof_eave_2))




def create_roof(self, shapes):
    if self.r2.weighted_int([1, 2], "roof_felt_or_tiles") == 0:  # do stucco!

        object = self.curves_to_mesh(shapes["roof"], "roof")
        object.data.materials.append(mat.Materials(self.geom).got_stucco("roof", rantom.RantomCache(0, name="roof")))
        object.name = "xxx-roof"
        self.geom['roofses'].append(object)

        thick = object.modifiers.new('tiles', 'SOLIDIFY')
        thick.thickness = -self.r2.uniform(0.01, 0.04, "felt_roof_depth")

        return object

    roof_group = bpy.data.objects.new(f"xxx-roofses", None)
    material = mat.Materials(self.geom).got_roof(rantom.RantomCache(0, name="roof"))

    tilo = bpy.data.node_groups['tile-o-matic'].copy()
    tilo.name = f"xxx-roof-tile-o-matic"
    tilo.nodes["setmat"].inputs[2].default_value = material

    type = tilo.nodes["tile_type"].integer = self.r2.randrange(4, "roof_tile_shape", "type of roof tiels used")

    # xs = tilo.nodes["tile_size"].vector[0] = self.r2.uniform(0.05, 0.15, "roof_tile_x")
    xs = tilo.nodes["tile_size"].vector[0] = self.r2.uniform(0.10, 0.20, "roof_tile_x")
    ys = tilo.nodes["tile_size"].vector[1] = self.r2.uniform(0.10, 0.20, "roof_tile_x")
    # ys = tilo.nodes["tile_size"].vector[1] = max (0.04, xs + self.r2.uniform(-0.04, 0.02, "roof_tile_y"))

    if type == 3:
        tile_height = tilo.nodes["tile_size"].vector[2] = self.r2.uniform(0.01, 0.03, "roof_tile_height")  # square tiles -> different heights
    else:
        tile_height = (xs + ys) / 2

    tilo.nodes["tile_size"].vector[2] = tile_height

    tilo.nodes["pitch"].outputs[0].default_value = self.r2.uniform(-0.1, -0.05, "roof_tile_pitch")
    tilo.nodes["rot_noise"].outputs[0].default_value = self.r2.uniform(0, 0.07, "roof_tile_rot_noise")
    tilo.nodes["pitch_noise"].outputs[0].default_value = self.r2.uniform(0, 0.07, "roof_tile_rot_noise")
    tilo.nodes["use_boolean"].boolean = False  # True too slow for production. a problem.


    done = set() # group roof shapes by normal
    for a in shapes["roof"]:
        similar = [a]
        if a in done:
            continue
        done.add(a)
        for b in shapes["roof"]:
            if a == b or b in done:
                continue

            diff = (Vector(a.to_world.to_euler()[:]) - Vector(b.to_world.to_euler()[:])).magnitude
            if diff < 0.01: # similar normals
                similar.append(b)
                done.add(b)

        bm = bmesh.new()
        for s in similar:
            ob = s.to_curve().evaluated_get(self.dg)
            me2 = ob.to_mesh()

            for v in me2.vertices:
                v.co = s.to_world @ v.co

            bm.from_mesh(me2)
        ext_mesh = bpy.data.meshes.new(f"Mesh_roof")
        bm.to_mesh(ext_mesh)

        for v in ext_mesh.vertices:
            v.co = a.to_world.inverted() @ v.co

        ext_obj = bpy.data.objects.new(f"xxx-roof", ext_mesh)
        bpy.context.scene.collection.objects.link(ext_obj)
        ext_obj.parent = roof_group
        self.geom['roofses'].append(ext_obj)
        ext_obj.matrix_basis = a.to_world
        bm.free()
        geom_nodes = ext_obj.modifiers.new('tiles', 'NODES')
        geom_nodes.node_group = tilo

    roof_group.parent = self.walls_root
    return roof_group


def create_skirt(self, shapes, dropdown):

    if self.r2.weighted_int([1, 5], "create_roof_skirt") == 1:

        mesh = self.curves_to_mesh(shapes["roof_skirt"], "roof_skirt")
        # convert mesh to curve to fix direction bug!
        extrudo = bpy.data.node_groups['extrude-down'].copy()
        extrudo.name = f"xxx-{extrudo.name}"

        material = bpy.data.materials["trash_mat"].copy()
        material.name = f"xxx-{material.name}"
        mesh.data.materials.append(material)
        extrudo.nodes["setmat"].inputs[2].default_value = material

        geom_nodes = mesh.modifiers.new('tiles', 'NODES')
        geom_nodes.node_group = extrudo
        geom_nodes.node_group.nodes["depth"].outputs[0].default_value = -dropdown

        solid = mesh.modifiers.new('extrude-down-solidfy', 'SOLIDIFY')
        solid.nonmanifold_thickness_mode = 'FIXED'
        solid.solidify_mode = 'NON_MANIFOLD'
        solid.thickness = self.r2.uniform(0.001, 0.03, "roof_skirt_depth")

        self.geom['roof_skirt'] = mesh