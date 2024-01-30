#from random import random

import bpy
import random
import time
import os
import sys
import importlib
from random import randrange, uniform, gauss, choice

from src import rantom
from src import config
from src import shape
from src import utils
from src.old import wall
from src import surround
from src import profile   as prof
from src import materials as mat
from src import subframe  as sub
from src import curtains  as curt



def build_scene():

    geom = cleanup_last_scene()
    
    wall_w = rantom.uniform (0.1, 0.4, "half_wall_width", "Wall width / 2") # half wall width
    window_offset = rantom.other ( lambda: utils.bounce_clamp ( gauss (-wall_w + 0.2, wall_w), -wall_w+0.01, wall_w), "glass_offset", "Distance between front of wall and first frame location (clamped)") # y pos of frame (-ve)
    
    shape.Shape (geom).go()
    geom['shapeOB'].rotation_euler[0] = 1.5708

    sub.Subframe(geom).go("frame")

    # return geom 
    
    geom['frameOB'].rotation_euler[0] = 1.5708
    geom['frameOB'].location      [1] = window_offset

    wall.create_wall(geom, (wall_w + window_offset) * 0.5, "external_wall") # exterior wall
    geom['external_wallOB'].location[1] = (-wall_w + window_offset) * 0.5
    geom['external_wallOB'].name = "xxx-external-wall"
    wall.create_wall(geom, (wall_w - window_offset) * 0.5, "internal_wall") # interior wall
    geom['internal_wallOB'].location[1] = (wall_w - window_offset) * 0.5 + window_offset
    geom['internal_wallOB'].name = "xxx-interior-wall"

    curt.Curtains().go(geom, wall_w, window_offset)

    utils.urban_canyon_go(geom)

    geom['surroundOBs'] = surround.Surround(geom, -window_offset - wall_w ).go()
    for surroundOB in geom['surroundOBs']:
        surroundOB.rotation_euler[0] = 1.5708
        surroundOB.location[1] = surroundOB.location[1] -wall_w

    wall.Wall().go(geom, wall_w)

    geom['shapeOB'].hide_set(True)
    geom['shapeOB'].hide_render = True

    mat.Materials(geom).go()

    return geom
