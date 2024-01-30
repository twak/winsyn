import copy
import math, mathutils
from mathutils import Matrix
import bpy, bmesh
import numpy as np
from src import utils as utils, rantom
from src import profile as prof
from random import randrange, uniform
from functools import partial
from src import splittable as split
from copy import copy

def create_glass(bez, glass_w, out_glass_objs):

    mesh = bez.to_mesh()
    meshOB = bpy.data.objects.new("xxx-glass", mesh.copy())

    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(meshOB, depsgraph)
    bm.faces.ensure_lookup_table()

    r = bmesh.ops.extrude_face_region(bm, geom=bm.faces)
    verts = [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, glass_w), verts=verts)

    bm.to_mesh(mesh)
    glass_ob = bpy.data.objects.new("xxx-glass", mesh.copy())
    bpy.context.scene.collection.objects.link(glass_ob)

    bm.free()

    out_glass_objs.append ( glass_ob )

    return glass_ob


class Subframe:

    def __init__(self, geom, force_windows_closed=False):
        self.geom = geom
        self.force_windows_closed = force_windows_closed

    def unpack_a_stack(self):

        profile_stacks = bpy.data.collections[self.profile_stacks].children
        collection = profile_stacks[self.r2.randrange(len(profile_stacks), f"profile_stack_{self.name}", "Choice of profile stack for frame/subframes")]

        if "mode" in self.geom and self.geom["mode"] == "mono_profile":

            collection = None
            for c in bpy.data.collections[self.profile_stacks].children:
                if c.name == "medium_pvc": # hard code a simple stack
                    collection = c
                    break

            collection = collection if collection else profile_stacks[0]

        print("using profile stack %s " % collection.name)

        all = []
        for o in collection.objects:
            index = int (o.name.split('.')[0] )
            while len(all) <= index:
                all.append([])
            all[index].append(o)

        all.pop(0) # start at 1 in names


        profiles = []
        for idx, listt in enumerate ( all ):
            a = self.r2.choice ( listt, f"subframe_{idx}", f"{idx}th subframe profile selection" )
            profiles.append ( a )

        return profiles

    def go(self, name, r2=None, glass_w=None, shape=None, profile_stacks="profile_stacks", glass_fn=create_glass, open_windows=True, root_hinges_left=None ):

        if shape is None:
            shapeOB = self.geom['shapeOB']
        else:
            shapeOB = shape

        self.r2 = r2 = rantom.RantomCache(0.1) if r2 is None else r2

        self.name = name
        self.glass_fn = glass_fn

        
        self.profile_stacks = profile_stacks

        # shrunkOB = prof.dumb_offset(shapeOB, 0.03)
        # bpy.context.scene.collection.objects.link(shrunkOB)
        # shape_wh = utils.curve_wh(geom['shapeOB'])

        out_frame_objs = []
        out_glass_objs = []

        shapeOB_info = utils.get_curve_info(self.geom, shapeOB)
        initial_shape = shapeOB_info['splittable']
        remaining = [ initial_shape ]

        frames = {}
        initial_shape.parent = None
        initial_shape.prof_idx = 0
        # frames[0] = [initial_shape]
        profiles = {}

        if glass_w == None:
            glass_w = self.r2.uniform(0.003, 0.02, "glass_depth", "Depth/thickness of the glass sheet")

        bevel = self.r2.other(lambda: 0 if randrange(2) == 1 else uniform(0.001, 0.003), "bevel_dist", "Distance to bevel (0 or uniform)")

        self.profile_stack = profile_stack = self.unpack_a_stack ()
        prof_idx = 0
        bevel = self.r2.other(lambda: 0 if randrange(2) == 1 else uniform(0.001, 0.003), "bevel_dist", "Distance to bevel (0 or uniform)")

        while len(remaining) > 0 and prof_idx < len(profile_stack): # loop over different profiles/layers of nesting

            # pick global profile to fit all shapes. override if opening.
            profile = profile_stack[prof_idx]

            frames[prof_idx] = []

            # compute offset for our frame (profile_w) and the next subframe's depth
            if prof_idx == len(profile_stack)-1:
                profile_w = prof.curve_wh(profile)[0]
                next_profile_depth = 0 # no next at end of profile stack
            else:
                profile_w = profile_stack[prof_idx+1].location[0] - profile.location[0]
                next_profile_depth = profile_stack[prof_idx + 1].location[1] - profile_stack[0].location[1] # depth offset of pane

            profiles[prof_idx] = profile

            if len (remaining) > 16:
                for s in remaining:
                    s.terminal = True
                    frames[prof_idx].append(s)
                print("stopping here, too complex!")
                break
            if self.is_too_small(remaining, profile_w):
                for s in remaining:
                    s.terminal = True
                    frames[prof_idx].append(s)
                print("stopping here, too small for frame!")
                profile_stack[prof_idx] = bpy.data.objects['2.iom.012'] # really small frame
                break

            next_remaining = []
            subremaining = remaining.copy()

            for s in subremaining:
                if type(s) is split.Rect:
                    s.hingable_edges = [True, True, True, True] # after instancing a frame, opening in any direction is an option

            sub_idx = 0
            while len(subremaining) > 0 and len ( subremaining ) < 128: # keep splitting shapes which will have the same profile

                next_subremaining = []

                for splitt in subremaining:

                    if "mode" in self.geom and self.geom["mode"] == "nosplitz":
                        subframe = [copy(splitt)]
                        subframe[0].subterminal = True
                    else:
                        subframe = splitt.split(profile_w, prof_idx, self.r2, key=f"{prof_idx}_{sub_idx}")

                    if subframe != None and prof_idx > 0: # don't split small panels relative to pane
                        if any( list (map ( lambda s : min(s.rect[2], s.rect[3]) * 0.33 < profile_w, subframe ) ) ): 
                            subframe = None
                            splitt.terminal = True
                            frames[prof_idx-1].append(splitt)
                            
                    sub_idx += 1

                    # else:
                    #     subframe = splitt.split(profile_w, prof_idx)

                    if subframe is not None:
      

                        for s in subframe:
                            s.prof_idx = prof_idx
                            
                            if prof_idx == len(profile_stack)-1:
                                s.terminal=True

                            if s.terminal:
                                frames[prof_idx].append(s)
                            else:
                                if s.subterminal:
                                    frames[prof_idx].append(s)
                                    next_remaining.append(s)
                                else:
                                    next_subremaining.append(s)

                    else:
                        splitt.terminal = True # this guy is never output as geometry, but please  stop here.
                        if splitt.parent is not None:
                            splitt.parent.terminal = True # ask non-offset parent to output glass!

                subremaining = next_subremaining

            if len (subremaining) != 0: # emergence! everyone just add a frame
                for s in subremaining:
                    frames[prof_idx].append(s)

            remaining = list(map(lambda s : s.offset_copy(profile_w, next_profile_depth), next_remaining))
             
            for s in frames[prof_idx]: # also create an offset shape for the glass for all others
                if len(s.children) == 0:
                    s.offset_copy(profile_w, next_profile_depth)

            prof_idx = prof_idx + 1


        # root (blender) parent of all frames
        frame_parent = bpy.data.objects.new( f"xxx-{name}", None )     

        bpy.context.scene.collection.objects.link(frame_parent)
        self.geom[f'{name}OB'] = frame_parent
        
        # create geometry
        for prof_idx in sorted ( frames ):

            # glass_overlap = 0 #self.r2.uniform(0, 0.01, f"glass_overlap_{prof_idx}", "how far the glass and frame overlap" )

            for splitt in frames[prof_idx]:

                frame_ob, glass_ob = self.build_geometry (profile_stack, splitt, bevel, glass_w, out_frame_objs, out_glass_objs  )

                splitt.frame_ob = frame_ob

                s2 = splitt
                while s2.parent is not None and not hasattr (s2.parent, "frame_ob"): # a shape that has no geometry (a rectangle that was split)
                    s2 = s2.parent


                if s2.parent is None:
                    frame_ob.parent = frame_parent  
                    if root_hinges_left is not None:
                        frame_ob.location[0] -= s2.rect[0] if root_hinges_left else s2.rect[0] + s2.rect[2]
                else:
                    frame_ob.parent = s2.parent.frame_ob


                # compensate for parenting location change
                frame_ob.location[2] -= frame_ob.parent.location[2] 

                if glass_ob is not None:
                    glass_ob.parent = frame_ob
                    if prof_idx > 0:
                        p_height = prof.curve_bounds(profile_stack[prof_idx])[1][0] # difference between shape origin and bottom of curve
                        glass_ob.location[2] = -glass_w + p_height 
                    else:
                        glass_ob.location[2] = -glass_w

        if open_windows:
            self.open_windows(frames, profile_stack)

        frame_geom_key = f'{name}OBs'     
        glass_geom_key = f'{name}GlassOBs'

        if frame_geom_key in self.geom:
            self.geom[frame_geom_key].extend (out_frame_objs)
        else:
            self.geom[frame_geom_key] = out_frame_objs

        if glass_geom_key in self.geom:
            self.geom[glass_geom_key].extend(out_glass_objs) 
        else:
            self.geom[glass_geom_key] = out_glass_objs



        return frame_parent

    def is_adjacent(self, ra, rb, dir):

        # dir is 0 (horizontal) or 1 (vertical).
        # returns 0 (not adjacent), -1, or 1 (ra can move in this direction behind rb)

        if ra[1-dir] == rb[1-dir] and ra[1-dir+2] == rb[1-dir+2]: # do we align horizontally?

            if ra[dir] + ra[dir+2] == rb[dir]:
                return 1 # can move up
            elif ra[dir] == rb[dir] + rb[dir+2]:
                return -1 # can move down
            return 0

        else:
            return 0


    def open_windows(self, frames, profile_stack): # frische alles die luft!

        total_angle = np.array ( [0.,0.])
        max_angle = 1.5 # could be bigger to allow windows to flap wide!

        moved = set()

        for prof_idx in sorted ( frames ):

            outwards = 'o' in profile_stack[prof_idx].name
            middle   = 'm' in profile_stack[prof_idx].name
            inwards  = 'i' in profile_stack[prof_idx].name

            rects = list(filter(lambda x: issubclass(x.__class__, split.Rect), frames[prof_idx]))

            type_choices = [-1, -1] # don't open

            if len (rects) >= 2:
                type_choices.append(0)  # sash/translate openeing
                type_choices.append(0)

            if not ( prof_idx == 0 or (not outwards and not inwards and not middle) ):
                type_choices.append(1) # rotational windows

            type = self.r2.choice(type_choices, "window_open_type", "sash or sliding window") == 0
            if type == 0:

                for ai, ra in enumerate ( rects ):
                    for bi, rb in enumerate ( rects ):


                        already_moved = False

                        x = ra
                        while x != None:
                            already_moved |= x in moved
                            x = x.parent

                        x = rb
                        while x != None:
                            already_moved |= x in moved
                            x = x.parent

                        if already_moved or ai in moved or bi in moved:
                            continue

                        # can we translate/open horizontally or vertically?
                        hv = [ self.is_adjacent(ra.rect, rb.rect, 0), self.is_adjacent(ra.rect, rb.rect, 1) ]

                        choices = [2] # otherwise we just do nothing

                        for i in range (2):
                            if hv[i] != 0:
                                choices.append(i)

                        choice = self.r2.choice(choices, f"sash_chance_v_{prof_idx}_{ai}_{bi}")

                        if choice != 2:

                            # profile_stack[prof_idx:]

                            setback = -prof.curve_collection_wh(profile_stack[prof_idx:])[1] - 0.002
                            dist = self.r2.uniform_mostly( 0.2, 0,  0.1, 0.95, f"sash_open_fract_{prof_idx}_{ai}_{bi}")\
                                   * min(ra.rect[ 2 + choice ], rb.rect[ 2 + choice ]) \
                                   * hv[choice]

                            if not self.force_windows_closed:
                                trans = Matrix.Translation(  ( (dist * (1-choice), dist * choice, setback ) ) )
                                mw = ra.frame_ob.matrix_local
                                mw @= trans

                            moved.add(ra) # don't move things twice
                            moved.add(rb)

            elif type == 1: # rotational window opening.

                rot   = self.r2.uniform(0.1 , 1.2, f"frame_open_edge_angle_{prof_idx}")
                rot_m = self.r2.uniform(-0.3, 0.3, f"frame_open_middle_angle_{prof_idx}")

                if inwards:
                    rot = -rot* 0.3 # open inwards, and not so much

                do_edge_rot = True # outwards or inwards

                max_rot = np.array ( [0.,0.])

                for split_idx, splitt in enumerate ( frames[prof_idx] ):

                    if self.r2.randrange(4, f"do_hinge_{prof_idx}_{split_idx}", "What is the probability of us hinging this pane") != 0:
                        continue

                    hingeable = splitt.hingable_edges

                    x_rot = 0
                    x_t = 0
                    y_t = 0
                    y_rot = 0

                    r = splitt.rect

                    choices=[]
                    if hingeable[0] and do_edge_rot: choices.append(0) # compare to cases below
                    if hingeable[1] and do_edge_rot: choices.append(1)
                    if middle                      : choices.append(2)
                    if hingeable[2] and do_edge_rot: choices.append(3)
                    if hingeable[3] and do_edge_rot: choices.append(4)
                    if middle                      : choices.append(5)

                    if len(choices) == 0:
                        continue

                    match self.r2.choice (choices, f"hinge_type_{prof_idx}_{split_idx}", "do we open a window by rotating on an edge or the middle?"):
                        case 0:
                            rot2 = rot * 0.3  if splitt.rect[2] > splitt.rect[3] else rot # wide windows open less
                            x_t = r[0]
                            x_rot = -min(max_angle - total_angle[0], rot2 * 0.5)
                        case 1:
                            rot2 = rot * 0.3  if splitt.rect[2] > splitt.rect[3] else rot
                            x_t = r[0] + r[2]
                            x_rot = min(max_angle - total_angle[0], rot2*0.5)
                        case 2:
                            x_t = r[0] + r[2] * 0.5
                            x_rot = rot_m
                        case 3:
                            rot2 = rot * 0.3  if splitt.rect[3] > splitt.rect[2] else rot
                            y_t = r[1]
                            y_rot = min(max_angle - total_angle[1], rot2)
                        case 4:
                            rot2 = rot * 0.3  if splitt.rect[3] > splitt.rect[2] else rot
                            y_t = r[1] + r[3]
                            y_rot = -min(max_angle - total_angle[1], rot2)
                        case 5:
                            y_t = r[1] + r[3] * 0.5
                            y_rot = rot_m


                    mat_loc   = mathutils.Matrix.Translation(( x_t,  y_t, 0))
                    mat_loc_1 = mathutils.Matrix.Translation((-x_t, -y_t, 0))

                    max_rot = np.maximum ( max_rot, [abs(x_rot), abs(y_rot)])

                    if not self.force_windows_closed:
                        eul = mathutils.Euler((y_rot, x_rot, 0.0), 'XYZ')
                        R = eul.to_matrix().to_4x4()
                        mw = splitt.frame_ob.matrix_local
                        mw @= mat_loc @ R @ mat_loc_1

                total_angle += max_rot


    def build_geometry(self, profile_stack, splittable, bevel, glass_w, out_frame_objs, out_glass_objs):

        bez = splittable.to_bezier()
        if not bez.name in bpy.context.scene.collection.objects: # root shape is already in the scene
            bpy.context.scene.collection.objects.link(bez)
        bez.hide_set(True)
        bez.hide_render = True
        bez.name= f"xxx-{self.name}-{splittable.prof_idx}"

        profile = profile_stack[splittable.prof_idx]

        if splittable.terminal:
            child = bez
            if len ( splittable.children ) == 1: # the children here should only be the offset copies
                child = splittable.children[0].to_bezier()
            glass_ob = self.glass_fn (child , glass_w, out_glass_objs )
        else:
            glass_ob = None

        frame_ob = prof.Profile(frame=splittable.to_bezier(), profile = profile, resolution = splittable.shape.data.resolution_u, bevel = bevel).go()
        out_frame_objs.append ( frame_ob )
        bez.parent = frame_ob

        return frame_ob, glass_ob

    def is_too_small(self, remaining, profile_w):

        vals = map(lambda  x : prof.curve_wh ( x.to_bezier() ), remaining)
        vals = map(lambda x: min(x[0], x[1]), vals)

        return min (vals) < 3*profile_w # all lengths <

