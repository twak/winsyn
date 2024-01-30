from dis import dis
import bpy
from . import rantom
import random

from src import subframe
from src import utils
from src import profile as prof
from src import splittable as split
import copy

class Shape: # generates a window shape (a bezier curve) and associated metadata (window-sill, lintels, how we can split it for frames...)
    
    def __init__(self, geom):
        self.geom = geom

    def go(self, wall_rect, geom, r2=None, circular=True):
                
        self.r2 = rantom.RantomCache(0.1) if r2 is None else r2
        self.geom = geom

        # sample data

        if "mode" in self.geom and (self.geom["mode"] == "only_rectangles" or self.geom["mode"] == "only_squares"):
            border_gen = [
                Shape.rect_border
            ]
            idx = self.r2.weighted_int([1], "shape_border_gen")

        if "mode" in self.geom and self.geom["mode"] == "no_rectangles":
            border_gen = [
                Shape.pointy_rect_border_tmp,
                Shape.arched_border,
                Shape.circular_border            ]
            idx = self.r2.weighted_int([1, 2, 1 if circular else 0], "shape_border_gen")
        else:
            border_gen = [
                Shape.rect_border,
                Shape.pointy_rect_border, # fixme: just does the same as rect_border?!
                Shape.arched_border,
                Shape.circular_border
            ]
            idx = self.r2.weighted_int([20, 1, 2, 1 if circular else 0], "shape_border_gen")

        shapeOB = self.geom['shapeOB'] = border_gen[idx](self, wall_rect)

        bpy.context.scene.collection.objects.link(shapeOB)

        shapeOB.name = "xxx-window-shape"
        shapeOB.hide_set(True)
        shapeOB.hide_render = True

        return shapeOB

    def pointy_rect_border_tmp(self, border): # remove me, roll into the one below

        r = self.geom["rect"]

        # if r.height > 0.4:
        exh1 = self.r2.uniform ( r.height/5, r.height/2, "shape_rect_extra_h",
            "Additional height added to one top corner to slope top edge of frame")
        # else:
        #     exh1 =0
        exh2 = 0

        if self.r2.random("shape_rect_swap", "Swap which corner is raised") < 0.5:
            exh2 = exh1
            exh1 = 0

        return self.rect_border(border, exh1 = exh1, exh2=exh2)

    def pointy_rect_border(self, border):

        r = self.geom["rect"]

        # if r.height > 0.4:
        exh1 = self.r2.uniform_mostly (0.99, 0, 0.2, r.height/2, "shape_rect_extra_h",
            "Additional height added to one top corner to slope top edge of frame")
        # else:
        #     exh1 =0
        exh2 = 0

        if self.r2.random("shape_rect_swap", "Swap which corner is raised") < 0.5:
            exh2 = exh1
            exh1 = 0

        return self.rect_border(border, exh1 = exh1, exh2=exh2)

    def rect_border(self, border, exh1=0, exh2=0):

        r = self.geom["rect"]

        width = r.width
        height = r.height
        xd = 0
        yd = 0

        if "mode" in self.geom and self.geom["mode"] == "only_squares":
            width = min (r.width, r.height)
            height = width
            xd = (r.width - width) / 2
            yd = (r.height - height) / 2

        verts = [ 
                (r.x + xd      , r.y + yd + height - exh2, 0 ),
                (r.x + xd+width, r.y + yd + height - exh1, 0 ),
                (r.x + xd+width, r.y + yd                , 0 ),
                (r.x + xd      , r.y + yd                , 0 )
            ]

        shapeOB, info = prof.build_curve_info(1, verts, geom=self.geom)

        info['max_profile_frac'] = 1

        lintel_dist = self.r2.uniform_mostly(0.8, 0, 0.05, 0.1, "rect_sill_down_sides" )

        info['lintel_sill'] = [[-lintel_dist,1+lintel_dist],[2,3]]
        info['splittable'] = split.Rect(shape=shapeOB, key="top", r2 = self.r2) if exh1 == exh2 else PointedRectSplittable(shapeOB, self.r2, key="top")
        self.geom['rectfill'] = prof.build_curve(1, [verts, border.get_verts()])
        self.geom['rectfill'].name = "xxx-window-wall-fill"

        return shapeOB


    def arched_border(self, border):

        r = self.geom["rect"]
        
        ww2 = r.width /2
        wh2 = r.height/2

        # mode 4 is very silly, let's not go there.
        mode = self.r2.weighted_int([1,1,1,1,0,1,1,1], "shape_pointed_mode", "How we treat the central top points of the shape")

        numPts = self.r2.randrange(2, "arched_high_pts", "How many Spline points are added to a rectangle to create an arch.") +1

        if numPts ==3:
            # tendency for nice ratios for addition point height
            mh  = self.r2.uniform(0.2, wh2*1.5,"shape_pointed_mh", "Pointed frame middle height") if self.r2.randrange(3, "pointed_nice_mh") == 0 else (ww2 * 2 / 3) 
        else:
            # tendency for nice ratios for addition point height
            mh  = self.r2.uniform(0.2, wh2*1.5,"shape_pointed_mh", "Pointed frame middle height") if self.r2.randrange(2, "pointed_nice_mh") == 0 else ww2

        mh = min(r.height - 0.1, mh)

        verts = [
                (r.x          , r.y + r.height - mh, 0 ),
                (r.x          , r.y, 0 ),
                (r.x + r.width, r.y, 0 ),
                (r.x + r.width, r.y + r.height - mh, 0 )
            ]

        for i in range (numPts):
            verts.insert(4, ( (ww2 * 2 * (i+1))/(numPts+1) + r.x, r.y + r.height,0) )
            
        handleR = prof.create_straight_handles(1, verts)
        handleL = prof.create_straight_handles(-1, verts)
        
        # circular ratios are great
        cfrac = self.r2.uniform(0.33, 0.8, "shape_pointed_mh", "Length of Bezier handles as fraction of dimension") if self.r2.randrange(4, "pointed_use_circular_ratio") == 0 else 0.552125

        if mode == 3 or mode == 5: 
            handleL[0] = (r.x          , r.y + r.height - mh * (1-cfrac) ,0) # edge arches up
            handleR[3] = (r.x + r.width, r.y + r.height - mh * (1-cfrac), 0)
        if mode == 2 or mode == 4: 
            handleL[0] = (r.x + ww2 * cfrac, r.y + r.height - mh, 0) # edge arches in
            handleR[3] = (r.x + r.width - ww2 * cfrac, r.y + r.height - mh, 0)
        if mode == 2 or mode == 3: 
            handleL[4] = (r.x +ww2 + ww2 * cfrac, r.y + r.height ,0 ) # middle arches out
            handleR[len(verts)-1] = (r.x +ww2 - ww2 * cfrac, r.y + r.height,0 )            
        if mode == 4 or mode == 5: 
            handleL[4] = (verts[4][0]                      , r.y + r.height - mh * cfrac * 0.5, 0 )  # middle arches down / slope at  45 degrees
            handleR[len(verts)-1] = (verts[len(verts)-1][0], r.y + r.height - mh * cfrac * 0.5, 0 )            
            
        subs = 16 if 5 >= mode >= 2 else 1
        profile_frac = 0.2 if 5 >= mode >= 2 else 1
            
        verts.reverse() # oops
        handleL.reverse()
        handleR.reverse()

        shapeOB, info = prof.build_curve_info(subs, verts, handleR, handleL, geom=self.geom)

        info['max_profile_frac'] = profile_frac
        info['lintel_sill'] = [[-1, 1],[2,3]] if numPts == 1 else [[-1,2], [3,4]]

        info['splittable'] = ArchedSplittable(shapeOB, self.r2, key="top")
        self.geom['rectfill'] = prof.build_curve(subs, [verts, border.get_verts()], [handleR, None], [handleL, None] )

        return shapeOB

    def circular_border(self, border):
        
        r = self.geom["rect"]

        # rad = self.r2.uniform( 0.3, 1.5, "shape_circle_radius", "Circular frame radius")

        i = self.r2.randrange(4, "shape_circle_remove_point")

        verts, handleL, handleR, rad = self.create_circle_points(r, i)

        # lintel_frac = self.r2.uniform(0.2,1, "shape_circular_lintel", "fraction of circle shape used for lintel")
        # sill_frac   = self.r2.uniform(0.2, 1, "shape_circular_sill" , "fraction of circle shape used for sill")
        lintel_sill = [[0, 2],[2, 4]]  #[[1-lintel_frac, lintel_frac+1],[3-sill_frac, sill_frac+3]]

        hinge = [False, False, False, False] # circles don't hinge!

        if i is not None: 
            if i == 1:
                lintel_sill = [[0, 1], []]
                hinge[3] = True
            elif i == 2:
                lintel_sill = [[],[]]
                hinge[1] = True
            elif i == 3:
                lintel_sill = [[], [2,3]]
                hinge[2] = True
            else:
                lintel_sill = [[],[]]
                hinge[0] = True

        shapeOB, info = prof.build_curve_info(16, verts, handleL, handleR, self.geom)

        info['max_profile_frac'] = 0.2
        info['lintel_sill'] = lintel_sill
        sp = CircSplittable( rad, i, shapeOB, r, self.r2, key="top")
        sp.hingable_edges = hinge
        info['splittable'] = sp

        self.geom['rectfill'] = prof.build_curve(16, [verts, border.get_verts()], [handleL, None], [handleR, None] )
        
        return shapeOB


    def create_circle_points(s, r, i=None ): # i is the point to delete

        diam = min(r.width/2, r.height/2)

        ww2 = wh2 = diam

        h = 0.552125 # * rad

        verts = [
            (-ww2,  0  , 0),
            ( 0  ,  wh2, 0 ),
            ( ww2,  0  , 0),
            ( 0  , -wh2, 0),
        ]

        handleL = [
            (  -ww2,  -h * wh2, 0),
            (-h*ww2,       wh2, 0),
            (   ww2,   h * wh2, 0),
            ( h*ww2,      -wh2, 0),
        ]    

        handleR = [
            (  -ww2,  h * wh2, 0),
            ( h*ww2,      wh2, 0),
            (   ww2, -h * wh2, 0),
            (-h*ww2,     -wh2, 0),
        ]

        if i is not None:
            del(verts[i])
            del(handleL[i])
            del(handleR[i])
            handleR[(i+2)%3] = (0,0,0)
            handleL[i%3] = (0,0,0)

        for v in [verts, handleL, handleR]:
            for j in range(len(verts)):
                v[j] = (v[j][0] + r.x + r.width/2, v[j][1] + r.y + r.height/2, 0 )

        return verts,handleL,handleR, ww2


class PointedRectSplittable (split.Splittable):

    def __init__(self, shape, r2, curve_res = 1, key="?!"):
        super().__init__()
        self.shape = shape
        self.curve_res = curve_res
        self.rect = prof.curve_xywh(self.shape)
        self.subterminal = True
        self.r2 = r2
        self.terminal = self.r2.randrange(5, f"pointed_rect_is_terminal_{key}") == 1 
        self.hingable_edges=[False, False, False, False]

    def to_bezier(self):

        return self.shape

    def split(self, profile_width, prof_idx, r2, key=None, initial_shape=None):
        
        if key is None:
            key = str(prof_idx)

        if prof_idx == 0 or self.r2.randrange(3, f"pointed_rect_{key}", "Chance of pointed rect intially splitting") == 0: # don't split
            out = copy.copy(self)
            out.terminal = self.r2.randrange(5, f"pointed_rect_splittable_terminate_{key}") == 1 
            out.subterminal = True
            return [out]
        else:
            
            out = []

            # triangle at the top
            verts, hl, hr = prof.deconstruct_curve(self.shape, as_copy=True)
            
            if verts[0][1] < verts [1][1]:
                lp = verts[0][1]
                higher_x= verts[1][0]
            else:
                lp = verts[1][1]
                higher_x= verts[0][0]

            verts[2][1] = lp
            verts[2][0] = higher_x

            verts = verts[:-1]
            hl = prof.create_straight_handles(-1, verts)
            hr = prof.create_straight_handles( 1, verts)

            us = split.UnSplittable ( prof.build_curve(1, verts, hl, hr), key=key+"+" ) 
            us.hingable_edges = [False, False, True, False]
            out.append (us)

            # rectangle at the bottom
            verts, hl, hr = prof.deconstruct_curve(self.shape, as_copy=True)
            verts[1][1] = verts[0][1] = lp
            hl = prof.create_straight_handles(-1, verts)
            hr = prof.create_straight_handles( 1, verts)
            
            out.append (split.Rect ( shape = prof.build_curve(1, verts, hl, hr), key=key+"+", r2 = r2 ) )

            return out

class ArchedSplittable (split.Splittable):

    def __init__(self, shape, r2, curve_res = 1, key="?!"):
        super().__init__()
        self.shape = shape
        self.r2 = r2
        self.curve_res = curve_res
        self.rect = prof.curve_xywh(self.shape)
        self.subterminal = True
        self.terminal = self.r2.randrange(5, f"arch_splittable_is_terminal_{key}") == 1 
        self.hingable_edges=[False, False, False, False]

    def to_bezier(self):

        return self.shape

    def split(self, profile_width, prof_idx, r2, key=None, initial_shape=None):

        if key is None:
            key = str(prof_idx)

        if prof_idx == 0 or self.r2.randrange(3, f"arched_rect_{key}", "Chance of arched shape intially splitting") == 0: # don't split
            out = copy.copy(self)
            out.terminal = self.r2.randrange(5, f"arch_terminate_{key}") == 1 
            out.subterminal = True
            return [out]

        elif self.shape.data.splines[0].point_count_u == 5:
            
            out = []

            vs, hl, hr = prof.deconstruct_curve(self.shape, as_copy=True)
                
            verts = [vs[4],vs[0],vs[1]]
            handleL = prof.create_straight_handles(-1, verts)
            handleL[2] = hl[1]
            handleL[1] = hl[0]
            handleR = prof.create_straight_handles( 1, verts)
            handleR[1] = hr[0]
            handleR[0] = hr[4]

            us = split.UnSplittable ( prof.build_curve (self.shape.data.splines[0].resolution_u, verts, handleL, handleR ), key=key+"+" ) 
            us.hingable_edges = [False, False, True, False]
            out.append (us)

            # rectangle at the bottom
            out.append (split.Rect ( rect = [ vs[3][0], vs[3][1], vs[1][0]-vs[3][0], vs[1][1]-vs[3][1] ], key=key+"+", r2 = r2 ))

            return out

        elif self.shape.data.splines[0].point_count_u == 6:

            out = []

            if self.r2.randrange (2, f"arched_rect_{key}", "Does arched split into top/bottom or side/side?") == 0: #rows

                # parallelogram at the top
                vs, hl, hr = prof.deconstruct_curve(self.shape, as_copy=True)
                
                verts = [vs[0],vs[1],vs[2],vs[5]]
                handleL = prof.create_straight_handles(-1, verts)
                handleL[0] = hl[0]
                handleL[2] = hl[2]

                handleR = prof.create_straight_handles( 1, verts)
                handleR[3] = hr[5]
                handleR[1] = hr[1]

                us = split.UnSplittable ( prof.build_curve (self.shape.data.splines[0].resolution_u, verts, handleL, handleR ),key=key+"+" ) 
                us.hingable_edges = [False, False, True, True]
                out.append (us)

                # rectangle at the bottom
                verts, hl, hr = prof.deconstruct_curve(self.shape, as_copy=True)
                out.append (split.Rect ( rect = [ vs[5][0], vs[5][1], vs[3][0]-vs[5][0], vs[3][1]-vs[5][1] ], key=key+"+", r2 = r2  ))

            else: # columns

                v, hl, hr = prof.deconstruct_curve(self.shape, as_copy=True)
                v_36 = [v[1][0], v[3][1], 0]
                v_33 = [v[0][0], v[3][1], 0]
                
                # left column
                verts = [v[0], v_33, v[4], v[5]]

                handleL = prof.create_straight_handles(-1, verts)
                handleL[0] = hl[0]
                handleR = prof.create_straight_handles( 1, verts)
                handleR[3] = hr[5]
                
                us = split.UnSplittable ( prof.build_curve (self.shape.data.splines[0].resolution_u, verts, handleL, handleR ), key=key+"+" ) 
                us.hingable_edges = [True, False, True, False]
                out.append (us)

                # central rectangle
                out.append (split.Rect ( rect = [ v[0][0], v[3][1], v[1][0]-v[0][0],  v[0][1] - v[3][1] ], key=key+"+", r2 = r2 ) )

                # right column
                verts = [v[1], v[2], v[3], v_36]
                handleL = prof.create_straight_handles(-1, verts)
                handleL[1] = hl[2]

                handleR = prof.create_straight_handles( 1, verts)
                handleR[0] = hr[1]

                us = split.UnSplittable ( prof.build_curve (self.shape.data.splines[0].resolution_u, verts, handleL, handleR ), key=key+"+" ) 
                us.hingable_edges = [False, True, True, False]
                out.append (us)

            return out


class CircSplittable(split.Splittable):

    def __init__(self, rad, deleted_point, shape, r, r2, key):
        super().__init__()
        self.rad = rad
        self.total_offset = 0
        self.shape = shape
        self.curve_res = 16
        self.rect = prof.curve_xywh(self.shape)
        self.r = r
        self.subterminal = True
        self.r2 = r2
        self.terminal = self.r2.randrange(5, f"circ_terminate_{key}") == 1 
        self.deleted_point = deleted_point

    def split(self, profile_w, prof_idx, r2, key=None, initial_shape=None):
        
        if key is None:
            key = str(prof_idx)

        if prof_idx == 0 or self.r2.randrange(2, f"circle_split_{key}", "Chance of circle not splitting") == 0: # don't split
            out = CircSplittable(self.rad, self.deleted_point, self.shape, self.r, self.r2, key=key+"+")
            out.hingable_edges = self.hingable_edges
            out.terminal = self.r2.randrange(5, f"circ_terminate_{key}") == 1 
            out.subterminal = True
            return [out]

        verts, handleL, handleR = prof.deconstruct_curve(self.shape)

        out = []

        spoke_centre = (self.r.x + self.r.width/2, self.r.y + self.r.height/2, 0) # moves around because of offset
        skip_ida = -1

        # find centre if a semi-circle
        for ida, ca in enumerate(verts):
            idb = ( ida + 1 ) % len (verts)
            cb = verts[ idb ]
            
            if abs(self.r.width - self.r.height) < 0.2 and prof.dist (ca, cb) - 2  * self.rad > - 0.001: # skip long edges when semi-circular
                spoke_centre = prof.opp(ca, cb, -0.5)
                skip_ida = ida

        for ida, ca in enumerate(verts):

            idb = ( ida + 1 ) % len (verts)
            cb = verts[ idb ]

            if ida == skip_ida:
                continue

            vs = [ca, cb, spoke_centre]
            hl = [ prof.opp(ca, spoke_centre, -0.3), handleL[idb], prof.opp(spoke_centre, cb, -0.3) ]
            hr = [ handleR[ida], prof.opp(cb, spoke_centre, -0.6), prof.opp(ca, spoke_centre, -0.6) ]

            us = split.UnSplittable ( prof.build_curve(16, vs, hl, hr), key=key+"+" )

            us.hingable_edges = [False, False, False, False]

            if ca[1] > cb[1]:
                us.hingable_edges[0] = True
            else:
                us.hingable_edges[1] = True

            if ca[0] > cb[0]:
                us.hingable_edges[3] = True
            else:
                us.hingable_edges[2] = True

            us.curve_res = 16

            out.append ( us )

        return out

    def offset_copy(s, dist_in, depth):

        out = copy.copy(s)
        out.parent = s
        out.shape = prof.dumb_offset(s.shape, dist_in)
        out.shape.location[2] += depth
        out.rect = prof.curve_xywh(out.shape)
        out.rad = s.rad - dist_in
        out.total_offset = s.total_offset + dist_in
        s.children.append(out)

        return out

    def to_bezier(self):
        return self.shape