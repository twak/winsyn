import copy
import math, mathutils
import numpy as np
from src import rantom
from src import profile as prof
from functools import partial

"""
A splittable splits a curve, e.g., create window pane shapes from an outer window. There are different 
classes for different shaped windows. Each Shape will usually have a Splittable method assigned.
"""

class Splittable:

    def __init__(self):
        self.subterminal = True
        self.terminal = True
        self.parent = None
        self.hingable_edges=[True, True, True, True] # xmin, xmax, ymin, ymax
        self.curve_res = 1
        self.children=[]

    def split(self, profile_width, prof_idx, r2, key=None, initial_shape=None):
        pass

    def to_bezier(self):
        pass

    def offset_copy(s, dist_in, depth):

        out = copy.copy(s)
        out.parent = s
        out.shape = prof.dumb_offset(s.shape, dist_in)
        #bpy.context.scene.collection.objects.link(out.shape)
        out.shape.location[2] += depth
        out.rect = prof.curve_xywh(out.shape)

        s.children.append(out)

        return out

class UnSplittable (Splittable):

    def __init__(self, shape, curve_res = 1, key="?!"):
        super().__init__()
        self.shape = shape
        self.curve_res = curve_res
        self.rect = prof.curve_xywh(self.shape)
        self.subterminal = True
        self.terminal = rantom.randrange(5, f"unsplittable_is_terminal_{key}") == 1 
        self.hingable_edges=[False, False, False, False]

    def to_bezier(self):

        return self.shape

    def split(self, profile_width, prof_idx, r2, key=None, initial_shape=None):

        if key is None:
            key = str(prof_idx)

        if prof_idx == 0 or r2.randrange(2, f"circle_split_{key}", "Chance of circle splitting") == 0: # don't split
            out = copy.copy(self)
            out.terminal = r2.randrange(5, f"circ_terminate_{key}") == 1
            out.subterminal = True
            return [out]
        else:
            return None


class Rect(Splittable):

    # most windows are rectangular and we can do complicated splits
    def __init__(s, rect=None, shape=None, profile_width=0, depth=0, key="?!",  r2=None):

        if rect is not None:
            s.rect = rect
            s.shape = prof.rect_to_curve(s.rect)
        elif shape is not None:
            s.shape = shape
            s.rect = prof.curve_xywh(s.shape)
        else:
            raise ValueError("rect or shape expected")

        s.shape.location[2] = depth
        s.min_to_split = 0.2
        s.parent = None
        s.hingable_edges=[True, True, True, True] # xmin, xmax, ymin, ymax
        s.curve_res = 1
        s.children=[]

        s.set_terms(profile_width, key, r2)

    def to_bezier(s):
        return s.shape

    def set_terms(s, profile_width, key, r2):

        # if not isattr(s, "rect"):
        #     s.rect = prof.curve_xywh(out.shape)

        # don't split small, stop splitting sometimes for no reason
        s.subterminal = ((s.rect[2] < (s.min_to_split + 2 * profile_width)) or
                         s.rect[3] < (s.min_to_split + 2 * profile_width)) \
                        or r2.randrange(2, f"rect_is_subterminal_{key}") == 0

        if s.rect[2] * s.rect[3] > 4 and r2.randrange(5, f"rect_big_is_not_subterminal_{key}") > 0:  # often split big shapes
            s.subterminal = False

        s.terminal = r2.randrange(5, f"rect_set_terminal_{key}") == 1  # but mostly limited by number of profiles...

    def split(s, profile_width, prof_idx, r2, key=None, initial_shape=None):

        out = []
        if key is None:
            key=str(prof_idx)

        # compute centre of s.rect

        split_top_more = False
        if initial_shape and isinstance(initial_shape, Rect):
            if s.rect[1] + s.rect[3] / 2. > initial_shape.rect[1] + initial_shape.rect[3] / 2.:
                split_top_more = True


        opts = [4] # don't split

        if prof_idx != 0 or not split_top_more:  # rarely split
            opts.extend([4] * 4)
        else:
            opts.append(4)

        # horz splits
        if s.rect[3] > 4 * profile_width + 2 * s.min_to_split: # split horizontal if tall
            opts.append(0)
            opts.append(2)
            if s.rect[3] > s.rect[2] - 0.4:  # if taller, horizontal more
                opts.extend([0]*2)
                opts.extend([2]*2)

        # vertical splits
        if s.rect[2] > 4 * profile_width + 2 * s.min_to_split: # split vert if wide
            opts.append(1)
            opts.append(3)
            if s.rect[2] > s.rect[3] - 0.4:  # if wider, split vertically more
                opts.extend([1]*2) # just always...
                opts.extend([3]*2)

        s.do_split( r2.choice(opts, f"split_type_{key}", "Type of split at current level: H, V, H*, V*, None") , profile_width, out, r2, key+"+")

        return out

    def do_split(s, i, profile_width, out, r2, key):

        match i:
            case 0: # horizontal split

                min = 2*profile_width + s.min_to_split
                maxx = s.rect[3] - 2*profile_width - s.min_to_split
                if min < maxx:
                    height = r2.uniform(min, maxx, f"rect_split_height_{key}")
                else:
                    height = s.rect[3] / 2.

                out.append( Rect(rect=[s.rect[0], s.rect[1]       , s.rect[2], height           ], profile_width=profile_width, depth=s.shape.location[2], key=key+"-1", r2 = r2) )
                out.append( Rect(rect=[s.rect[0], s.rect[1]+height, s.rect[2], s.rect[3]-height ], profile_width=profile_width, depth=s.shape.location[2], key=key+"-2", r2 = r2) )

            case 1: # vertical split

                min = 2* profile_width + s.min_to_split
                maxx = s.rect[2] - 2* profile_width - s.min_to_split

                if min < maxx and r2.weighted_int([2, 1], f"do_less_splits_{key}" ) == 0:
                    width = r2.uniform(min, maxx, f"rect_split_width_{key}")
                else : # do more single vertical splits
                    width = s.rect[2]/2.

                out.append( Rect(rect=[s.rect[0]      , s.rect[1], width          , s.rect[3]], profile_width=profile_width, depth=s.shape.location[2], key=key+"-1", r2 = r2) )
                out.append( Rect(rect=[s.rect[0]+width, s.rect[1], s.rect[2]-width, s.rect[3]], profile_width=profile_width, depth=s.shape.location[2], key=key+"-2", r2 = r2) )

            case 2: # repeating horizontal split

                max_count = max (1, math.ceil( s.rect[3] / (s.min_to_split + 2*profile_width ) )-1)
                count = r2.randrange(max_count, f"rect_split_count_{key}") + 1
                height = s.rect[3]/float(count)

                for j in range (count):
                    r = Rect(rect=[s.rect[0], s.rect[1] + j * height, s.rect[2], height ], profile_width=profile_width, depth=s.shape.location[2], key=f"{key}-{j}", r2 = r2)
                    out.append(r)

            case 3: # repeating vertical split

                max_count = max (1, math.ceil( s.rect[2] / (s.min_to_split + 2*profile_width ) ))
                count = r2.randrange(max_count, f"rect_split_count_{key}") + 1
                width = s.rect[2] / float(count)

                for j in range(count):
                    r = Rect(rect=[s.rect[0] + j * width, s.rect[1], width, s.rect[3]], profile_width=profile_width, depth=s.shape.location[2], key=f"{key}-{j}", r2 = r2)
                    out.append(r)

            case 4: # just output
                out.append (Rect(rect=s.rect, profile_width=profile_width, depth=s.shape.location[2], key="key", r2 = r2) )

        is_single = len(out) == 1
        for o in out:
            o.parent = s

            o.hingable_edges[0] = o.rect[0]           == s.rect[0]
            o.hingable_edges[1] = o.rect[0]+o.rect[2] == s.rect[0]+s.rect[2]
            o.hingable_edges[2] = o.rect[1]           == s.rect[1]
            o.hingable_edges[3] = o.rect[1]+o.rect[3] == s.rect[1]+s.rect[3]

            if is_single:
                o.subterminal = True


