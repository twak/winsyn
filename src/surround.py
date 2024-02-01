

import bpy
from . import rantom, profile, utils

from src import profile as prof
from src import shape
# from .profile import Profile

"""
Things that surround windows: sills, frames, lintels...
"""

class Surround:

    def __init__(self, geom, glass_pos):

        self.geom = geom
        self.shapeOB = geom['shapeOB']
        self.shape_info = utils.get_curve_info(geom, self.shapeOB)

        self.lintel_sill = self.shape_info['lintel_sill']

        self.glass_pos = glass_pos

        # to transfer (synchronize) parameters from lintel to sill
        self.last_profile = None
        self.last_ex = None
        self.last_ex_dist = None

    def go(self, r2):

        out = []
        self.geom["surround_profiles"] = []
        self.r2 = r2

        if len ( self.lintel_sill[0] ) == 0 and len (self.lintel_sill[1]) == 0:
            out.append(self.full_surround())
        else:
            if isinstance ( self.shape_info['splittable'], shape.CircSplittable):
                opts = [0, 1, 2] # don't do both if
            else:
                opts = [0, 0]
                if len ( self.lintel_sill[0]) > 0:
                    opts.append(1)
                if len ( self.lintel_sill[1]) > 0:
                    opts.append(2)
                if len(opts) ==3:
                    opts.extend([3] * 3)

            st = self.r2.choice(opts, "surround_type", "Choice of surround type")

            # st = self.r2.weighted_int([2, 1, 1, 1], "surround_type", "Choice of surround type")

            match (st):
                case 0:
                    out.append(self.full_surround())
                case 1:
                    if len ( self.lintel_sill[0] ) > 0 and self.r2.randrange(2, "surround_lintel", "Generate lintel if 0") == 0: # lintel half the time
                        out.append ( self.partial_surround (self.lintel_sill[0], "lintel"))
                case 2:
                    if len ( self.lintel_sill[1] ) > 0 and self.r2.randrange(6, "surround_sill"  , "Generate sill if 0"  ) > 0: # often do sill
                        out.append( self.partial_surround(self.lintel_sill[1], "sill"))
                case 3:
                    if len ( self.lintel_sill[1] ) > 0 and self.r2.randrange(6, "surround_sill"  , "Generate sill if 0"  ) > 0: # often do sill
                        out.append( self.partial_surround(self.lintel_sill[1], "sill"))
                    if len ( self.lintel_sill[0] ) > 0 and self.r2.randrange(2, "surround_lintel", "Generate lintel if 0") == 0: # lintel half the time
                        out.append ( self.partial_surround (self.lintel_sill[0], "lintel"))

        return out

    def move_first_last_pts(self, curve, glass_pos):
        # move first and last spline points in y by glass_pos (ignores tangents for now)

        curve = curve.data.splines[0]

        for ia in [0, curve.point_count_u-1]:  # set locations based on offset

            pt = curve.bezier_points[ia].co
            curve.bezier_points[ia].co = (pt[0], pt[1] + glass_pos, pt[2])


    def full_surround(self):
        # create copy of a surround profile
        profiles = bpy.data.collections["surround_profiles"].objects
        profile_template = profiles[self.r2.randrange(len(profiles), "surround_profile_curve", "Surrounding wall-frame profile")]

        if "mode" in self.geom and self.geom["mode"] == "mono_profile":
            profile_template = profiles[0]

        frame_depth = self.r2.uniform(0,0.03, "surround_depth", "Additional depth to surround frame") + 0.005

        return self.from_profile( self.shapeOB, profile_template, frame_depth)

    def from_profile(self, shape, profile_template, frame_depth, copy_shape = True):

        prof = profile_template.copy()
        prof.data = prof.data.copy()
        prof.name= "xxx-surround-prof-tmp"
        bpy.context.scene.collection.objects.link(prof)

        # extend profile for glass-depth
        self.move_first_last_pts (prof, self.glass_pos -  frame_depth )

        if copy_shape:
            shape = shape.copy()
            shape.data = shape.data.copy()
            shape.name = "xxx-tmp-shape"
            bpy.context.scene.collection.objects.link(shape)

        # apply profile
        shape.data.bevel_mode = 'OBJECT'
        shape.data.bevel_object = prof
        shape.data.offset = -0.005 # surround wins over window frame
        shape.data.fill_mode = 'NONE'
        shape.data.use_fill_caps = True

        #shape = utils.to_mesh(shape, delete=False)
        shape = utils.to_mesh(shape, delete=True)

        shape.data.use_auto_smooth = True
        shape.data.auto_smooth_angle = 0.349066
        shape.name = "xxx-surround"

        shape.location[2] = shape.location[2] -frame_depth

        return shape

    def partial_surround(self, fraction, name="unkown"):

        frame_depth = self.r2.uniform(0,0.03, "surround_depth_"+name, "Additional depth to surround frame") + 0.005

        if self.last_profile == None or self.r2.randrange(2, "surround_copy_from_prev", "Should the sill copy profile and depth from lintel") == 0:
            profiles = bpy.data.collections["surround_profiles"].objects
            profile_template = profiles[self.r2.randrange(len(profiles), "surround_profile_curve", "Surrounding wall-frame profile")]

            if "mode" in self.geom and self.geom["mode"] == "mono_profile":
                profile_template = profiles[0]

            self.geom["surround_profiles"].append (profile_template)
        else:
            profile_template = self.last_profile
            frame_depth      = self.last_depth

        self.last_profile = profile_template
        self.last_depth = frame_depth


        # cut section of shape
        partial_shape = profile.slice_cuve( self.shapeOB, fraction[0], fraction[1])
        partial_shape.name = "xxx-surround-partial"

        #bpy.context.scene.collection.objects.link(partial_shape)
        # extend horizontally on random

        dist = self.r2.uniform(0.01, 0.15, "surround_extends_dist_" + name, "Distance to extend the lintel or sill")

        p_w = prof.curve_wh(profile_template)[0]
        dist = max(dist, p_w * 1.5)

        self.last_ex_dist = dist

        match self.r2.randrange(4 if self.last_ex is None else 6, "surround_extends_profile_profile_"+name, "Do we extend "+name+"? - 0: no, 1: horizontally, 2: tangent"):
            case 0:
                pass
            case 1 | 2:
                self.last_ex = 'tangent'
                partial_shape = self.extend_curve(partial_shape, self.last_ex, dist)
            case 3:
                self.last_ex = 'horz_for' if name == 'lintel' else 'horz-rev'
                partial_shape = self.extend_curve(partial_shape, self.last_ex, dist)
            case 4 | 5: # sill is same as lintel
                if self.last_ex != 'tangent':
                    self.last_ex = 'horz_for' if name == 'lintel' else 'horz-rev' # still reverse for sill
                partial_shape = self.extend_curve(partial_shape, self.last_ex, self.last_ex_dist)

        partial_shape.name = 'xxx-extended-'+name
        bpy.context.scene.collection.objects.link(partial_shape)
        #return partial_shape

        # if !is_lintel or option_1: create profile at depth and apply. chance to use same profile as previous call.



        #bpy.data.objects.remove(partial_shape, do_unlink=True)

        out = self.from_profile( partial_shape, profile_template, frame_depth, copy_shape=False)
        out.name = f"xxx-{name}"
        return out


    def extend_curve(self, partial_shape, tangent, dist): # extend curve following current tangent, or horizontally by given dist-ance

        curve = partial_shape.data.splines[0]

        extended_data = bpy.data.curves.new('xxx-surround-ext-partial-%f.2' % dist, type='CURVE')
        extended_polyline = extended_data.splines.new('BEZIER')
        extended_data.dimensions = '2D'
        extended_polyline.bezier_points.add(curve.point_count_u - 1 + 2)  # already one there
        extended_polyline.use_cyclic_u = curve.use_cyclic_u
        extended_polyline.resolution_u = curve.resolution_u

        for curve_pts in range(curve.point_count_u):  # set locations based on offset

            epbp = extended_polyline.bezier_points[curve_pts+1]
            cbpl = curve.bezier_points[curve_pts]

            epbp.co = cbpl.co
            epbp.handle_left = cbpl.handle_left
            epbp.handle_right = cbpl.handle_right

        cbp0 = curve.bezier_points[0]
        curve_pts = curve.point_count_u
        cbpl = curve.bezier_points[curve_pts-1]


        if tangent == 'tangent': # extension follows line of lintel
            first_opp = cbp0.handle_right
            last_opp = cbpl.handle_left
        else:
            delta = 1 if tangent == 'horz_for' else -1 # top or bottom = forwards ofr backwards

            first_opp = (curve.bezier_points[0          ].co[0]+delta, curve.bezier_points [0         ].co[1], 0)
            last_opp  = (curve.bezier_points[curve_pts-1].co[0]-delta, curve.bezier_points[curve_pts-1].co[1], 0)

        # extra at start
        cbp0 = curve.bezier_points[0]
        factor = dist / prof.dist(cbp0.co, first_opp)
        extended_polyline.bezier_points[0].co           = prof.opp(cbp0.co, first_opp, factor)
        extended_polyline.bezier_points[0].handle_right = prof.opp(cbp0.co, first_opp, factor * 0.66)
        extended_polyline.bezier_points[1].handle_left  = prof.opp(cbp0.co, first_opp, factor * 0.33)
        extended_polyline.bezier_points[0].handle_left  = extended_polyline.bezier_points[0].co # tidy first handle

        # extra at end
        extended_polyline.bezier_points[curve_pts+1].co             = prof.opp(cbpl.co, last_opp, factor)
        extended_polyline.bezier_points[curve_pts + 1].handle_left  = prof.opp(cbpl.co, last_opp, factor * 0.66)
        extended_polyline.bezier_points[curve_pts].handle_right     = prof.opp(cbpl.co, last_opp, factor * 0.33)
        extended_polyline.bezier_points[curve_pts + 1].handle_right = extended_polyline.bezier_points[curve_pts+1].co # tidy final handle

        return bpy.data.objects.new(extended_data.name, extended_data)
