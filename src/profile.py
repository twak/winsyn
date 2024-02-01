import math
import random

import bpy, bmesh
from mathutils import Vector
import numpy as np

from math import sqrt, cos, floor, ceil
from random import randrange, uniform
from src import utils
from src import shape

import numbers

"""
A bunch of curve functionality
"""


# quadric bezier inds
CO = 0
HANDLE_LEFT = 1
HANDLE_RIGHT = 2
CO2 = 3


def add (a,b):
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

def sub (a,b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def scale (a, factor):
    return (a[0]*factor, a[1]*factor, a[2] * factor)

def dot(a,b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def length (a):
    return sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])

def dist (a,b):
    return length(sub(a,b))

def angle(a, b): # angle twixt vectors in rads
    d = (length(a)*length(b))
    if d == 0:
        return 0
    return math.acos(dot(a,b)/d)

def opp (a, d, frac = 1):
    return (a[0]+(a[0]-d[0]) * frac, a[1]+(a[1]-d[1]) * frac, a[2]+(a[2]-d[2]) * frac )


def lerp (a, b, frac):
    return (a[0] + (b[0]-a[0]) * frac, a[1] + (b[1]-a[1]) * frac, a[2] + (b[2]-a[2]) * frac)

def norm (a):
    d = sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])
    if d == 0:
        return a
    ilen = 1/d
    return (a[0]*ilen, a[1]*ilen, a[2]* ilen)

def len2 (a):
    return a[0]*a[0] + a[1]*a[1] + a[2]*a[2]



def angle_twixt(a,b,c):  # numpy /in abc, radians https://stackoverflow.com/a/35178910

    if not type(a) == list:
        a = np.array(a)
    if not type(b) == list:
        b = np.array(b)
    if not type(c) == list:
        c = np.array(c)

    ba = a - b
    bc = c - b

    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
    return np.arccos(cosine_angle)

class Profile:

    def __init__(self, geom=None, frame=None, profile=None, resolution = 10, bevel = 0, offset = 0, is_rect = False):

        if geom is not None:
            self.bezierOB = geom['shapeOB']
            self.profile = geom['profile']
        else:
            self.bezierOB = frame
            self.profile = profile
        self.resolution = resolution
        self.bevel = bevel
        self.offset = offset
        self.is_rect = is_rect


    def mid_plane(s, pt, ha, hb, start, prof_width):
        # create a clip-plane through pt, containing the point (ha+hb)
        
        pa = norm(sub(ha, pt))
        pb = norm(sub(pt, hb))
        pbh = norm(sub(hb, pt))
        
        normal = add(pa, pb)
                

        a = max(0.001, angle ( pa, pbh ) )
        diagonal = (prof_width+0.04) / math.sin (a * 0.5)
        scalee = diagonal
        z_size = 10
        # scale = max (diagonal, 0.333)
        
        if len2(normal) < 0.01:
            normal = sub(pt, hb) if start else sub(hb, pt)
            along =  norm(normal)
        else:
            along  = norm((-normal[1], normal[0], normal[2]))
        
        f = add(pt, scale ( along, scalee + (10 if start else 0)  )) # back goes back a long way - improves boolean sability
        b = sub(pt, scale ( along, scalee + (0  if start else 10)  ))

        verts = [
                  (f[0], f[1], -z_size),
                  (f[0], f[1],  z_size),
                  (b[0], b[1],  z_size),
                  (b[0], b[1], -z_size),
                ]
                 
        edges = []
        faces = [[0, 1,2, 3]]

        mesh = bpy.data.meshes.new("xxx-clip-plane")  # add the new mesh
        mesh.from_pydata(verts, edges, faces)
        obj = bpy.data.objects.new(mesh.name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        
        return obj
    #    bpy.context.view_layer.objects.active = obj

        
    def split_curve(s, curve):
        
        # pull a bezier apart into individual segments. create clip-planes.
        out = []
            
        prof_width = curve_wh(s.profile)
        prof_width = max (prof_width[0], prof_width[1])

        for i in range (curve.point_count_u):
            
            # out.extend(curve.bezier_points[i].co)
            
            curveData = bpy.data.curves.new('xxx-profile-fragment', type='CURVE')
            curveData.dimensions = '2D'

            polyline = curveData.splines.new('BEZIER')
            polyline.bezier_points.add(3) # for a total of 4

            a_co = curve.bezier_points[i].co
            a_hl = curve.bezier_points[i].handle_left
            a_hr = curve.bezier_points[i].handle_right
            
            ip1 = (i + 1) % curve.point_count_u
            b_co = curve.bezier_points[ip1].co
            b_hl = curve.bezier_points[ip1].handle_left
            b_hr = curve.bezier_points[ip1].handle_right

            polyline.bezier_points[0].co = opp (a_co, a_hr, 2)
            polyline.bezier_points[0].handle_left  = opp(a_co, a_hr, 3)
            polyline.bezier_points[0].handle_right = opp (a_co, a_hr, 1)

            polyline.bezier_points[1].co = a_co
            polyline.bezier_points[1].handle_left  = opp(a_co, a_hr, 1)
            polyline.bezier_points[1].handle_right = a_hr

            polyline.bezier_points[2].co = b_co
            polyline.bezier_points[2].handle_left  = b_hl
            polyline.bezier_points[2].handle_right = opp(b_co, b_hl, 1)

            polyline.bezier_points[3].co = opp (b_co, b_hl, 2)
            polyline.bezier_points[3].handle_left  = opp(b_co, b_hl, 1)
            polyline.bezier_points[3].handle_right = opp(b_co, b_hl, 3)

            curveOB = bpy.data.objects.new('xxx-segment', curveData)

            yield [curveOB, s.mid_plane(a_co, a_hr, a_hl, True, prof_width), s.mid_plane(b_co, b_hl, b_hr, False,prof_width)]

    def go(self):
        
        if self.offset != 0:
            self.bezierOB.data.offset = self.offset

        if self.is_rect:
            return self.trivial()

        bezier = self.bezierOB.data.splines[0]
        
        scn = bpy.context.scene
        objs = bpy.data.objects
        
        bm = bmesh.new()
                    
        for (i, l, r) in self.split_curve( bezier ):
            
            scn.collection.objects.link(i)
            i.data.bevel_mode = 'OBJECT'
            i.data.resolution_u = self.resolution
            i.data.resolution_v = self.resolution
            i.data.bevel_object = self.profile
            i.data.use_fill_caps = True

            meshOB = utils.to_mesh(i)

            # boolean ops work better without nearly parallel faces...
            # mod_bool =  meshOB.modifiers.new('merge_tris', 'DECIMATE')
            # mod_bool.decimate_type = 'DISSOLVE'
            # mod_bool.angle_limit = 0.01

            # clip against left plane
            mod_bool =  meshOB.modifiers.new('left', 'BOOLEAN')
            mod_bool.operation = 'DIFFERENCE'
            mod_bool.object = l

            # clip again stright plane
            mod_bool =  meshOB.modifiers.new('right', 'BOOLEAN')
            mod_bool.operation = 'DIFFERENCE'
            mod_bool.object = r

            m = utils.to_mesh(meshOB, False).data

            clean_up_and_trivial = self.bad_boolean(l, m, r, bezier.point_count_u) # boolean failure

            bm.from_mesh(m)

            if True or clean_up_and_trivial:
                objs.remove(i,      do_unlink=True)
                objs.remove(l,      do_unlink=True)
                objs.remove(r,      do_unlink=True)
                objs.remove(meshOB, do_unlink=True)

            if clean_up_and_trivial:
                print("boolean operation failed :(") #rest of split curve loop needs removing
                return self.trivial()


        m3 = bpy.data.meshes.new( "xxx-tt" )
        bm.to_mesh( m3 ) # all combined meshes
        meshOB3 = objs.new("xxx-frame", m3.copy())
        
        bpy.context.scene.collection.objects.link(meshOB3)

        
        if self.bevel != 0:
            mod_bool =  meshOB3.modifiers.new('bevel', 'BEVEL')
            mod_bool.offset_type = 'WIDTH'
            mod_bool.use_clamp_overlap = True
            mod_bool.width = self.bevel
            
            meshOB4 = utils.to_mesh(meshOB3) # with bevel
            objs.remove(meshOB3, do_unlink=True) 
        else:
            meshOB4 = meshOB3
        
        meshOB4.data.use_auto_smooth = True
        meshOB4.data.auto_smooth_angle = 0.349066

        global XXX_FRAME_COUNT
        XXX_FRAME_COUNT = XXX_FRAME_COUNT +1
        meshOB4.name = "xxx-frame-%d"%XXX_FRAME_COUNT
        meshOB4.location = self.bezierOB.location #copy depth offset

        return meshOB4

    def trivial(self):

        self.bezierOB.data.use_fill_caps = True
        self.bezierOB.data.bevel_mode = 'OBJECT'
        self.bezierOB.data.bevel_object = self.profile

        ob = self.bezierOB.evaluated_get(bpy.context.evaluated_depsgraph_get())

        meshOB = bpy.data.objects.new("xxx-frame-trivial", ob.to_mesh().copy())
        bpy.context.scene.collection.objects.link(meshOB)

        utils.set_auto_smooth(meshOB)

        self.bezierOB.data.bevel_mode = 'ROUND' # now we have a mesh...don't need bezier
        meshOB.location = self.bezierOB.location

        return meshOB

    def bad_boolean(self, l, m, r, pt_count): # did the boolean op fail and include the planes?

        expected_points = pt_count * 2 # twice the number of pts in profile curve

        if len(m.vertices)  < expected_points  or len (m.edges) < expected_points: return True

        for side in [l, r]:

            norm = side.data.polygons[0].normal
            origin = side.data.vertices[0]

            for v in side.data.vertices.values():
                for x in m.vertices:
                    if v.co == x.co:
                        return True

                    if dot (norm, sub(x.co, origin.co) ) < -0.001: # pts behind clip-plane
                        return True

                # break # usually only one or all verts are bad

        return False


XXX_FRAME_COUNT = 0

def dumb_offset(curve_ob, distance=0.2): # move each bezier point towards interior & handles to match. edges. may. collide.

    curve = curve_ob.data.splines[0]

    offset_data = bpy.data.curves.new('xxx-segment-offset-%f.2'%distance, type='CURVE')
    offset_polyline = offset_data.splines.new('BEZIER')
    offset_data.dimensions = '2D'
    offset_data.fill_mode = curve_ob.data.fill_mode
    offset_data.resolution_u = curve_ob.data.resolution_u

    offset_polyline.bezier_points.add(curve.point_count_u-1) # already one there
    offset_polyline.use_cyclic_u = curve.use_cyclic_u

    for ia in range(curve.point_count_u): # set locations based on offset

        a = curve.bezier_points[ia].co
        hl = curve.bezier_points[ia].handle_left
        hr = curve.bezier_points[ia].handle_right

        pa = norm(sub(hl, a))
        pb = norm(sub(a, hr))

        normal = add(pa, pb)

        if len2(normal) < 0.01: # parallel-ish edges
            along = norm(sub(hl, a))
            d = distance
        else:
            along = norm((-normal[1], normal[0], normal[2]))
            d = distance / cos ( angle(pa, pb) / 2.0 )

        offset_polyline.bezier_points[ia].co = add(a, scale(along, d))

    def tween(a1, a2, b1, b2, pt):

        if abs ( a2[0] - a1[0] ) < 0.01:
            t0 = b2[0]
        else:
            t0 = ((pt[0] - a1[0]) / (a2[0] - a1[0])) * (b2[0] - b1[0]) * 1 + b1[0]

        if abs ( a2[1] - a1[1]) < 0.01:
            t1 = b2[1]
        else:
            t1 = ((pt[1] - a1[1]) / (a2[1] - a1[1])) * (b2[1] - b1[1]) * 1 + b1[1]

        return t0, t1, 0  # jesus tom, just import numpy

    for ia in range(curve.point_count_u): # set handles based on local scales

        ib = (ia+ curve.point_count_u - 1) % curve.point_count_u

        a = curve.bezier_points[ia].co
        b = curve.bezier_points[ib].co

        ahl = curve.bezier_points[ia].handle_left
        bhr = curve.bezier_points[ib].handle_right

        aa = offset_polyline.bezier_points[ia].co
        bb = offset_polyline.bezier_points[ib].co

        offset_polyline.bezier_points[ia].handle_left  = tween ( a, b, aa, bb, ahl )
        offset_polyline.bezier_points[ib].handle_right = tween ( b, a, bb, aa, bhr )
        # offset_polyline.bezier_points[ib].handle_right = tween ( a, b, aa, bb, bhr )

    ob = bpy.data.objects.new(offset_data.name, offset_data)

    #utils.get_curve_info(geom, curve_ob).updateutils.get_curve_info(geom, ob) # verts and handles incorrect...

    return ob

def to_array(curve, i):

    a = curve.bezier_points[i]
    b = curve.bezier_points[(i+1) % curve.point_count_u]

    return np.array ([ [a.co          [0], a.co          [1], a.co          [2]],
                       [a.handle_right[0], a.handle_right[1], a.handle_right[2]],
                       [b.handle_left [0], b.handle_left [1], b.handle_left [2]],
                       [b.co          [0], b.co          [1], b.co          [2] ] ] )

def slice_array (ca, t0, t1): # https://stackoverflow.com/a/11704152

    #print (f'slice_array {t0}, {t1}')

    u0 = 1-t0
    u1 = 1-t1

    return np.array ([
        u0**3 * ca[0] + 3 * (t0 * u0 * u0) * ca[1] + 3 * (t0 * t0 * u0) * ca[2] + t0**3 * ca[3],
        u0 * u0 * u1 * ca[0] + (t0 * u0 * u1 + u0 * t0 * u1 + u0 * u0 * t1) * ca[1] + (t0 * t0 * u1 + u0 * t0 * t1 + t0 * u0 * t1) * ca[2] + t0 * t0 * t1 * ca[3],
        u0 * u1 * u1 * ca[0] + (t0 * u1 * u1 + u0 * t1 * u1 + u0 * u1 * t1) * ca[1] + (t0 * t1 * u1 + u0 * t1 * t1 + t0 * u1 * t1) * ca[2] + t0 * t1 * t1 * ca[3],
        u1**3 * ca[0] + 3 * (t1 * u1 * u1) * ca[1] + 3 * (t1 * t1 * u1) * ca[2] + t1**3 * ca[3]
    ])

def totuple(a): #https://stackoverflow.com/a/10016613/708802
    try:
        return tuple(totuple(i) for i in a)
    except TypeError:
        return a

def slice_cuve(curve_ob, t0 = 0, t1 = 1 ):

    curve = curve_ob.data.splines[0]

    cas = [] # output bezier points

    def add (cas, x0, x1):

        pts = to_array (curve, math.floor(x0))

        if math.ceil(x0) > x0 or math.floor(x1) < x1:
            pts = slice_array(pts, x0 - floor(x0), 1 - (ceil(x1)-x1) )

        cas.append (pts)

    if math.ceil(t0) > t0:
        add (cas, t0, t1 if ceil(t1) == ceil(t0) else ceil(t0))

    for i in range (math.ceil(t0), math.floor(t1)):
        add ( cas, i, i+1)

    if math.floor(t1) < t1 and ceil(t1) != ceil(t0):
        add (cas, math.floor (t1), t1)

    slice_data = bpy.data.curves.new('xxx-segment-slice-%f.2-%f.2' % (t0, t1), type='CURVE')
    slice_polyline = slice_data.splines.new('BEZIER')
    slice_data.dimensions = '2D'
    slice_polyline.use_cyclic_u = False
    slice_polyline.resolution_u = curve.resolution_u

    slice_polyline.bezier_points.add( len(cas) -1 +1 ) # already size 1, but extra pt at end


    # export to bpy spline
    for i in range (0, len(cas)):
        slice_polyline.bezier_points[i  ].co           = totuple( cas[i  ][CO          ] )
        slice_polyline.bezier_points[i  ].handle_right = totuple( cas[i  ][HANDLE_LEFT ] )
        slice_polyline.bezier_points[i+1].handle_left  = totuple( cas[i  ][HANDLE_RIGHT] )

    i = len(cas)-1
    slice_polyline.bezier_points[i+1].co = totuple (cas[i][CO2] ) # final location

    #tidy unused handles
    slice_polyline.bezier_points[i+1].handle_right = totuple(cas[i][CO2])
    slice_polyline.bezier_points[0].handle_left = totuple( cas[0][CO          ] )

    ob = bpy.data.objects.new(slice_data.name, slice_data)

    return ob

def deconstruct_curve(curve_ob, as_copy= False):

    coords  = []
    handleL = []
    handleR = []

    curve = curve_ob.data.splines[0]

    for ia in range(curve.point_count_u): # set handles based on local scales

        coords .append ( curve.bezier_points[ia].co )
        handleL.append ( curve.bezier_points[ia].handle_left )
        handleR.append ( curve.bezier_points[ia].handle_right )

    if as_copy:
        return list ( map ( lambda x: [x[0],x[1],x[2]], coords ) ), list ( map ( lambda x: [x[0],x[1],x[2]], handleL ) ), list ( map ( lambda x: [x[0],x[1],x[2]], handleR ) )
    else:
        return coords, handleL, handleR

def build_curve(subs, coordses, handleLs = None, handleRs = None, d='2D', cyclic = True):  # subs, coords, handleL, handleR):

    curveOB, _ = build_curve_info(subs, coordses, handleLs=handleLs, handleRs=handleRs, d =d, cyclic=cyclic)

    return curveOB




def build_curve_info (subs, coordses, handleLs = None, handleRs = None, geom=None, d='2D', cyclic = True): 

    if isinstance(coordses[0][0], numbers.Number):
        coordses = [coordses]
        handleLs = [handleLs]
        handleRs = [handleRs]
    elif handleLs is None:
        handleLs = [None] * len (coordses)
        handleRs = [None] * len (coordses)


    # create the Curve Datablock
    curveData = bpy.data.curves.new('xxx-curve', type='CURVE')
    curveData.dimensions =  d # '2D'

    for coords, handleL, handleR in zip (coordses, handleLs, handleRs):

        if handleL == None:
            handleL = create_straight_handles(-1, coords)

        if handleR == None:
            handleR = create_straight_handles( 1, coords)

        # map coords to spline
        polyline = curveData.splines.new('BEZIER')
        polyline.bezier_points.add(len(coords) - 1)
        polyline.use_cyclic_u = cyclic

        for num in range(len(coords)):
            polyline.bezier_points[num].co = coords[num]
            polyline.bezier_points[num].handle_left = handleL[num]
            polyline.bezier_points[num].handle_right = handleR[num]

    curveOB = bpy.data.objects.new('xxx-curve', curveData)

    curveOB.data.resolution_u = subs
    curveOB.data.fill_mode = 'FRONT'

    info = None
    if geom is not None:
        info = utils.get_curve_info(geom, curveOB)
        info['subs'] = 1
        info['coords'] = coordses
        info['handleL'] = handleLs
        info['handleR'] = handleRs

    return curveOB, info


def curve_bounds(curve):
    curve = curve.data.splines[0]

    big = 1e308
    r = [[big, -big], [big, -big], [big, -big]]

    for i in range(curve.point_count_u):
        bounds = curve.bezier_points[i].co
        for x in range(3):
            b_pt = curve.bezier_points[i].co[x]
            r[x] = [min(b_pt, r[x][0]), max(b_pt, r[x][1])]
    return r

def curve_wh(curve): # 3D bounds

    r = curve_bounds(curve)

    return (r[0][1] - r[0][0], r[1][1] - r[1][0], r[2][1] - r[2][0])

def curve_xyzwhd(curve): # 3d

    r = curve_bounds(curve)

    return ( r[0][0], r[1][0], r[2][0],
         r[0][1] - r[0][0], r[1][1] - r[1][0], r[2][1] - r[2][0])

def curve_world_bb(obj): # 3D world-space bounds in xyz,whd

    curve = obj.data.splines[0]

    big = 1e308
    r = [[big, -big], [big, -big], [big, -big]]

    for i in range(curve.point_count_u):
        bounds = curve.bezier_points[i].co
        wsp = curve.bezier_points[i] 
        wsp = Vector( [wsp.co[0], wsp.co[1], wsp.co[2]] ) @ obj.matrix_world 
        for x in range(3):
            b_pt = wsp[x]
            r[x] = [min(b_pt, r[x][0]), max(b_pt, r[x][1])]

    return ( r[0][0], r[1][0], r[2][0],
         r[0][1] - r[0][0], r[1][1] - r[1][0], r[2][1] - r[2][0])


def curve_collection_wh(cc): # 3D

    big = 1e308
    r = [[big, -big], [big, -big], [big, -big]]

    for ob in cc:
        curve = ob.data.splines[0]
        for i in range(curve.point_count_u):
            for x in range(3):
                b_pt = curve.bezier_points[i].co[x]
                r[x] = [min(b_pt, r[x][0]), max(b_pt, r[x][1])]

    return (r[0][1] - r[0][0], r[1][1] - r[1][0], r[2][1] - r[2][0])

def curve_xywh(curve): # 2D
    curve = curve.data.splines[0]

    big = 1e308
    r = [[big, -big], [big, -big], [big, -big]]

    for i in range(curve.point_count_u):
        bounds = curve.bezier_points[i].co
        for x in range(3):
            b_pt = curve.bezier_points[i].co[x]
            r[x] = [min(b_pt, r[x][0]), max(b_pt, r[x][1])]

    return [r[0][0], r[1][0], r[0][1] - r[0][0], r[1][1] - r[1][0]]

def rect_to_curve(r): # rect as xywh

    #print (" >>> " + str(r))

    verts =[
        [r[0]       , r[1]       , 0],
        [r[0]       , r[1] + r[3], 0],
        [r[0] + r[2], r[1] + r[3], 0],
        [r[0] + r[2], r[1]       , 0] ]

    handleR = create_straight_handles( 1, verts)
    handleL = create_straight_handles(-1, verts)

    return build_curve(1, verts, handleL, handleR)


def create_straight_handles(dir, verts):

    def ot(a, b):
        return (
            (b[0]-a[0])*0.333 + a[0],
            (b[1]-a[1])*0.333 + a[1],
            (b[2]-a[2])*0.333 + a[2] )

    out = []
    l = len( verts )
    
    for i in range ( l ):
        out.append( ot( verts[i], verts[ (i+dir+l) % l ] ) )
    
    return out



if __name__ == "__main__":  

    objs = bpy.data.objects
    for o in objs:
        if o.name.startswith("xxx-"):
            objs.remove(o, do_unlink=True)
            
    profiles = bpy.data.collections["profiles"]
    profile = profiles.objects[randrange(len(profiles.objects))]

    bevel = 0 # 0.005
    if randrange(2) == 1:
        bevel=uniform (0.001, 0.003)

    t_profile = Profile (objs["arch"], profile, 10, bevel, 20)
    t_profile.go()
