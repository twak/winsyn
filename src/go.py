import random

import bpy
import time
import os
from os.path import expanduser
import sys
import importlib
import pathlib
from datetime import datetime
from bpy.app import handlers
import bmesh


dir = os.path.dirname(bpy.data.filepath)
if not dir in sys.path:
    sys.path.append(dir)

sys.path.append(pathlib.Path(__file__).parent.resolve() ) # needed for vs code development with https://github.com/JacquesLucke/blender_vscode

from src import pipes
from src import adjacent
from src import rantom
from src import config
from src import shape
from src import utils
from src import cgb_building
from src import cgb_building_walls
from src import cgb_building_junk
from src import cgb_building_roofs
from src import cgb_building_win
from src import cgb
from src import surround
from src import shutter 
from src import profile    as prof
from src import materials  as mat
from src import subframe   as sub
from src import splittable as split
from src import curtains   as curt

# ones at the top are reloaded on first run(?!) lower ones need two runs to flush changes

importlib.reload( pipes  )
importlib.reload( cgb_building_junk )
importlib.reload( cgb_building_roofs )
importlib.reload( cgb_building_walls )
importlib.reload( adjacent )
importlib.reload( cgb      )
importlib.reload( cgb_building )
importlib.reload( mat      )
importlib.reload( cgb_building_win )
importlib.reload( config   )  # re-read these from disk in blender before running code!
importlib.reload( rantom   )
importlib.reload( shape    )
importlib.reload( utils    )
importlib.reload( prof     )
importlib.reload( surround )
importlib.reload( sub      )
importlib.reload( split    )
importlib.reload( curt     )
importlib.reload( cgb_building )
importlib.reload( cgb_building_walls )
importlib.reload( shutter  )

# useful incantation to allow interactive debugging in pycharm as https://code.blender.org/2015/10/debugging-python-code-with-pycharm/
# import pydevd_pycharm
# pydevd_pycharm.settrace('localhost', port=10912, stdoutToServer=True, stderrToServer=True)

if config.interactive: # used for development/one-off renders.

    # hard coded seed/parameters for debugging.
    seed = 1706642979540530925
    # otherwise, random-by-time
    # seed = time.time_ns()

    geom, m = mat.Materials.create_geometry("rgb", seed=seed)
    # create the default materials
    m.pre_render("rgb")
    # alternately, create grey materials
#    m.pre_render("labels")

    # in debug mode, dump to my Downloads folder
    rantom.write_file( os.path.join (expanduser("~"), "Downloads", "params.txt") )

else:  # batch render from console

    if os.environ.get("WINDOWZ_STYLE") is not None:
        config.style = os.environ["WINDOWZ_STYLE"] # allow the environment to override the style we use. (Allows us to fire off slurm jobs with a command line argument)

    todo_list = utils.read_todo_list()

    for step in range (config.render_number):

        if todo_list:
            seed, force_no_subdiv = utils.next_todo(todo_list)
        else:
            seed, force_no_subdiv  = time.time_ns() + config.jobid * 1e6 + step, False

        if seed is None:
            print("todo list empty, ending job!")
            os.system(f"scancel {config.jobid}")
            break

        print("seed %d" % seed)
        render_name = "%020d" % seed

        styles = config.style.split(';')
        passes = True

        if not styles[0] in ["rgb", "lvl9"] and not styles[0].endswith("nwall"):
            # default pass goes first to create geometry, if not explicitly specified, don't do compositor passes
            styles.insert(0, "rgb")
            passes = False

        geom = None
        for style in styles:

            geom_start_time = datetime.now()
            geom, m = mat.Materials.create_geometry(style, seed=seed, old_geom=geom, force_no_subdiv=force_no_subdiv)
            rantom.store(f"geometry_generation_ms", (datetime.now() - geom_start_time).total_seconds() * 1000)
            utils.store_geometry_counts(style)

            m.pre_render(style, passes=passes) # albedo etc...

            def start_timer(scene):
                global render_start_time
                render_start_time = datetime.now()

            def end_timer(scene):
                global render_start_time
                ms = (datetime.now() - render_start_time).total_seconds() * 1000
                print(f"{style} render time {ms}ms")
                rantom.store(f"{style}_render_time_ms", ms)

            handlers.render_pre.append(start_timer)
            handlers.render_post.append(end_timer)

            bpy.context.scene.render.filepath = f'{config.render_path}/{style}/{render_name}.png'
            bpy.ops.render.render(write_still=True)

            handlers.render_pre.remove(start_timer)
            handlers.render_post.remove(end_timer)

            m.post_render(style, render_name, passes) # undo albedo etc...


        bpy.context.view_layer.update()
        print(bpy.context.scene.statistics(bpy.context.view_layer))

        rantom.write_file(f'{config.render_path}/attribs/{render_name}.txt')  # "seed=%020d\n\n" % seed

        if todo_list:
            utils.todo_done(seed, render_name)

        if os.path.exists(f'{config.render_path}stop.txt'):
            sys.exit("quit!!")

