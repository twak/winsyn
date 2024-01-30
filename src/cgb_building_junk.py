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
from src import materials
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

from pathlib import Path

import glob

def ensure_signs(self):

    if hasattr(self, 'sign_set'):
        return self.sign_set

    self.sign_set = []

    for folder, scale in [("small", 0.2), ("medium", 0.35), ("large", 1.2)]:
        for f in glob.glob (os.path.join (config.resource_path, "signs", folder, "*.png")):

            c = re.search(r"([0-9]+)_([0-9]+)", Path(f).name)
            if c:
                dim = [ float(c.group(1)), float(c.group(2)) ]
                factor = scale / max (dim[0], dim[1]) # 30 cm on longest side
                dim = [dim[0] * factor, dim[1] * factor]
                self.sign_set.append((dim, f))



    return self.sign_set

def ensure_wall_meshes(self):

    if hasattr(self, 'wall_meshes'):
        return self.wall_meshes

    self.wall_meshes = []

    filepath = os.path.join (config.resource_path, "exterior_clutter", "clutter_wall.blend")

    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):

        for o in data_from.objects:

            if o.startswith("Plane"):
                continue # clutter files have a floor plane

            c = re.search(r"\[\s*([0-9\.]+)\s*\,\s*([0-9\.]+)\s*\,\s*([0-9\.]+)\s*\]", o )
            if c:
                s = [ float(c.group(1)), float(c.group(2)), float(c.group(3)) ]

                self.wall_meshes.append((s, o))

    return self.wall_meshes

def scatter_sign(self, depth_offset, parent):

    def sign(shape):
        shape_size = [shape.width, shape.height]
        choices = []

        if self.r2.weighted_int ([3, 8], f"sign_img_or_mesh_{self.sign_count}") == 0 and shape.normal()[0] > 0.9:
            # use expensive 3D geometry on forward facing walls!
            for size, file in self.ensure_wall_meshes():
                if size[0] < shape_size [0] and size[2] < shape_size[1]:
                    choices.append([size, file])
        else: # cheap 2D signs!
            for size, file in self.ensure_signs():
                if size[0] < shape_size [0] and size[1] < shape_size[1]:
                    choices.append([size, file])

        if len(choices) == 0:
            return {}

        sign_size, file = self.r2.choice(choices, f"sign_choice_{self.sign_count}")
        n = "none"
        xfrac = self.r2.uniform(0, 1, f"sign_xfrac_{self.sign_count}")
        yfrac = self.r2.uniform(0, 1, f"sign_yfrac_{self.sign_count}")


        # mesh = self.curves_to_mesh([sign], f"sign_{self.sign_count}", uv_mode="norm")
        # mesh.parent = parent
        # self.geom["wall_signs"].append(mesh)

        if file.endswith(".png"): # a 2D sign

            shapes = split_x(-xfrac, n, sign_size[0],
                             split_y(-yfrac, n, sign_size[1],
                                     extrude(depth_offset, split_faces(n, n, n, n, "sign", n)), -(1 - yfrac), n), -(1 - xfrac), n)(shape=shape)

            for sign in shapes["sign"]:

                mesh = self.curves_to_mesh([sign], f"sign_{self.sign_count}", uv_mode="norm")
                mesh.parent = parent
                self.geom["wall_signs"].append(mesh)

                mat = materials.copy(bpy.data.materials["wall_sign"])
                mat.node_tree.nodes["do_label"].inputs[0].default_value = 0

                bl_im = bpy.data.images.load(file)
                bl_im.name = "xxx_"+bl_im.name
                mat.node_tree.nodes["sign_texture"].image = bl_im
                mat.node_tree.nodes["Principled BSDF"].inputs[7].default_value = self.r2.uniform(0.4, 0.8, f"sign_specular_{self.sign_count}" )
                mesh.data.materials.append( mat )
                mesh.visible_shadow = False # cycles bug with transparent objects close to shadow receiver

        else: # a 3D mesh

            shapes = split_x(-xfrac, n, sign_size[0],
                             split_y(-yfrac, n, sign_size[2],
                                     "sign", -(1 - yfrac), n), -(1 - xfrac), n)(shape=shape)

            for sign in shapes["sign"]:

                filepath = os.path.join (config.resource_path, "exterior_clutter", "clutter_wall.blend")

                with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                    data_to.objects = [file]

                c = data_to.objects[0]

                bbn = c.bound_box[0][:]
                bbx = c.bound_box[6][:]

                c.matrix_world = Matrix.Translation ( Vector( ( sign.x, sign.y, 0) ) ) @ Matrix.Rotation(math.radians(180), 4, 'Y') @ Matrix.Rotation(math.radians(-90), 4, 'X') @ Matrix.Translation ( Vector((-bbx[0], 0, -bbn[2] ) ) )

                c.matrix_world = sign.to_world @ c.matrix_world

                c.name = "xxx-" + c.name
                bpy.context.scene.collection.objects.link(c)
                c.parent = parent
                self.geom["exterior_junk"].append(c)

        self.sign_count += 1
        return {}

    return sign

def scatter_junk(self, ww, wh, wall):

    x = "none"

    junk_count = 0

    def exterior_junk(shape):
        nonlocal junk_count
        junk_count += 1
        return self.exterior_junk(shape = shape, position="ymax_random", n=junk_count)

    def bollards(shape):
        nonlocal junk_count
        junk_count += 1
        return self.bollard(shape = shape, n = junk_count)

    def exclude_bays(shape):
        return self.max_bay_front # kludge

    junk_area = self.r2.choice( [
        repeat_x( self.r2.uniform(2, 7, "junk_spacing"), exterior_junk),
        repeat_x( self.r2.uniform(1, 2, "bollard_spacing"), bollards) ], "junk_or_bollards" )


    w = 3
    return split_y (
        -1, x,
        w, split_x(-1, x,
            ww * 1.5, split_faces( x,x,x,x,x, junk_area ),
            -1, x),
        exclude_bays, x,
        wh, x,
        exclude_bays, x,
        w, x,
        -1, x )

def exterior_junk(self, shape=None, position="random", n=0):

    if not hasattr(self, 'junk_set'):
        self.junk_set = rantom.choice(["clutter_shops", "clutter_bins", "clutter_boxes", "clutter_streets"], "ext_junk_style")

    filepath = os.path.join (config.resource_path, "exterior_clutter", self.junk_set + ".blend")

    # in collections any_rotate or against_walls

    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):

        choices = []

        for o in data_from.objects:

            if o.startswith("Plane"):
                continue # clutter files have a floor plane

            c = re.search(r"\[\s*([0-9\.]+)\s*\,\s*([0-9\.]+)\s*\,\s*([0-9\.]+)\s*\]", o )
            if c:
                s = [ float(c.group(1)), float(c.group(2)), float(c.group(3)) ]

                if s[0] < shape.width and s[1] < shape.height:
                    choices.append(o)

        data_to.objects = [rantom.choice ( choices, f"junk_selection_{n}" )]

    for c in data_to.objects:
        if c is not None:
            if position == "centre":
                v = Vector ((shape.x + shape.width/2, shape.y + shape.height/2, 0))
            elif position == "random":
                bbn = c.bound_box[0][:]
                bbx = c.bound_box[6][:]

                v = Vector( (
                    self.r2.uniform ( shape.x - bbn[0], shape.x + shape.width  - bbx[0], f"junk_scatter_{self.junk_count}_x" ),
                    self.r2.uniform ( shape.y - bbn[1], shape.y + shape.height - bbx[1], f"junk_scatter_{self.junk_count}_y" ),
                    0 ))
            elif position == "ymax_random":
                bbn = c.bound_box[0][:]
                bbx = c.bound_box[6][:]

                v = Vector( (
                    self.r2.uniform ( shape.x - bbn[0], shape.x + shape.width - bbx[0], f"junk_scatter_{self.junk_count}_x" ),
                    # shape.y + shape.height - bbx[1],
                    shape.y + bbx[1], # +shape.height - bbn[1],
                    0 ))


            v = shape.to_world @ v
            c.location = v
            c.name = "xxx-" + c.name
            bpy.context.scene.collection.objects.link(c)
            self.geom["exterior_junk"].append(c)

    self.junk_count += 1

    return {}

def load_bollard_set(self):

    if hasattr(self, 'bollard_set'):
        return

    filepath = os.path.join (config.resource_path, "exterior_clutter", "clutter_bollards.blend")

    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        #data_to.collections = [random.choice ( data_from.collections ) ]
        data_to.collections = [rantom.choice ( data_from.collections, "street_bollard_type" )]
        # data_to.objects = [name for name in data_from.objects if name.startswith(obj_name)]

    self.bollard_set = data_to.collections
    for c in self.bollard_set:
        if c is not None:
            for i, o in enumerate ( c.all_objects ):
                o.name = f"xxx-bollard_{i}"

    self.bollard_root = bpy.data.objects.new( f"xxx-bollards", None )
    bpy.context.scene.collection.objects.link(self.bollard_root)

def bollard (self, shape=None, n=0):

    self.load_bollard_set()

    v = Vector ((shape.x + shape.width/2, shape.y + shape.height/2, 0))
    v = shape.to_world @ v

    i = rantom.choice ( self.bollard_set[0].all_objects, f"street_bollard_instance_{n}" )

    i = i.copy()
    bpy.context.collection.objects.link(i)
    i.location = v
    i.parent = self.bollard_root
    self.geom["exterior_junk"].append(i)

    return {}


def create_ground(self, shapes):

    ground ="ground"
    ground_ob = self.curves_to_mesh(shapes[ground], ground)
    self.geom['exterior_floor'] = [ground_ob]
    ground_ob.parent = self.walls_root
    trasho = bpy.data.node_groups['trash-o-matic'].copy()
    trasho.name = f"xxx-{trasho.name}"

    material = bpy.data.materials["trash_mat"].copy()
    material.name = f"xxx-{material.name}"
    trasho.nodes["setmat"].inputs[2].default_value = material

    leaves_or_trash = self.r2.uniform(0,1, "trash_is_leaves", "do we have leaves or garbage on the floor?")
    trasho.nodes["Collection Info"].inputs[0].default_value = bpy.data.collections["trash" if leaves_or_trash < 0.5 else "leaves"]
    trasho.nodes["seed"].outputs[0].default_value = self.r2.uniform(0,100, "trash_random_seed", "Random seed for scatter trash")
    trasho.nodes["density"].outputs[0].default_value = self.r2.uniform_mostly(0.2, 0, 0,100, "trash_density", "Density of trash on the floor")
    material.node_tree.nodes["leaf_or_trash"].outputs[0].default_value = leaves_or_trash
    geom_nodes = ground_ob.modifiers.new('tiles', 'NODES')
    geom_nodes.node_group = trasho

