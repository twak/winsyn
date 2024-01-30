import collections

import bpy
import math
import mathutils
from math import pi
import copy
from . import profile as prof
from . import utils
#import profile as prof
import functools
from collections import defaultdict
from mathutils import Matrix, Euler, Vector
import numpy as np
from . import rantom

CGB_COUNT = 0
RND_COUNT = 0

def reset_rnd():
    global  RND_COUNT, CGB_COUNT
    RND_COUNT = collections.defaultdict(lambda : 0)
    CGB_COUNT = 0

reset_rnd()

"""
minimal CGA Shape implementation. Strongly typed on shapes. Axis aligned. But we have triangles.
"""

def get_output():
    return defaultdict(lambda: [])

def split_x(*args):
    return functools.partial( lambda *brgs, shape : shape.split_d_(0, get_output(), *brgs), *args )

def split_y(*args):
    return functools.partial( lambda *brgs, shape : shape.split_d_(1, get_output(), *brgs), *args )

def split_z(*args):
    return functools.partial( lambda *brgs, shape : shape.split_d_(2, get_output(), *brgs), *args )

def rot(*args):
    return functools.partial( lambda *brgs, shape : shape.rotate_(get_output(), *brgs), *args )

def spin(*args): # switch the axes of a rect (axis-aligned)
    return functools.partial( lambda *brgs, shape : shape.spin_(get_output(), *brgs), *args )

def trans(*args): # translate in the shape-coordinate system
    return functools.partial( lambda *brgs, shape : shape.translate_(get_output(), *brgs), *args )

def split_trif(*args):
    return functools.partial( lambda *brgs, shape : shape.split_tri_d_(0, get_output(), *brgs), *args )

def split_trib(*args):
    return functools.partial( lambda *brgs, shape : shape.split_tri_d_(1, get_output(), *brgs), *args )

def split_tril(*args):
    return functools.partial( lambda *brgs, shape : shape.split_tri_d_(2, get_output(), *brgs), *args )

def split_trir(*args):
    return functools.partial( lambda *brgs, shape : shape.split_tri_d_(3, get_output(), *brgs), *args )

def split_tri_c(d, *args):
    return functools.partial( lambda *brgs, shape : shape.split_tri_d_(d, get_output(), *brgs), *args )

def split_lines(*args):
    return functools.partial( lambda *brgs, shape : shape.split_lines_(get_output(), *brgs), *args )

def repeat_x(*args):
    return functools.partial( lambda *brgs, shape : shape.repeat_d_(0, get_output(), *brgs), *args )

def repeat_y(*args):
    return functools.partial( lambda *brgs, shape : shape.repeat_d_(1, get_output(), *brgs), *args )

def parallel(*args):
    return functools.partial( lambda *brgs, shape : shape.parallel(get_output(), *brgs), *args )

def set_value(*args):
    return functools.partial( lambda *brgs, shape : shape.set_value_(get_output(), *brgs), *args )

def split_faces(*args):
    return functools.partial( lambda *brgs, shape : shape.split_faces_(get_output(), *brgs), *args )

def extrude(*args):
    return functools.partial( lambda *brgs, shape : shape.extrude_(get_output(), *brgs), *args )

# def sx(*args):
#     return functools.partial( lambda shape : shape.size_(0), *args )
#
# def sy(*args):
#     return functools.partial( lambda shape : shape.size_(1), *args )
#
# def sz(*args):
#     return functools.partial( lambda shape : shape.size_(2), *args )

def chance(*args):
    return functools.partial( lambda *brgs, shape : shape.chance_( get_output(), *brgs), *args )

def gt(*args):
    return functools.partial( lambda *brgs, shape : shape.compare_(lambda a, b: a > b, get_output(), *brgs), *args )

def lt(*args):
    return functools.partial( lambda *brgs, shape : shape.compare_(lambda a, b: a < b, get_output(), *brgs), *args )

# --------------------------------------------------------------------------------------------------------------------------------


pi2 = math.pi/2

class shp():

    def __init__(self, name=None, curve=None, to_world=None):
        global CGB_COUNT
        self.parent = None
        if name is None:
            self.name = f"_{CGB_COUNT}"
        else:
            self.name = name
        
        if curve:
            self.curve = curve
        if to_world:
            self.to_world = to_world

        self.to_world = Matrix()

        self.parent = None
        self.lookup = {}

        CGB_COUNT += 1

    def get_value(self, key):

        if key in self.lookup:
            return self.lookup[key]

        if self.parent is not None:
            return self.parent.get_value(key)

        return None

    def set_value_(self, out, *args):

        for k, v in zip (args[0::2], args[1::2]):

            if callable( v ):
                v = v(shape=self)

            self.lookup[k] = v

        self.eval(out, args[-1], self)

        return out

    def normal(self):
        return Vector((self.to_world[0][0], self.to_world[1][0], self.to_world[2][0])) #

    def to_curve(self):
        return self.curve

    def parallel(self, out, *args):

        for p in args:
            if p is not None:
                self.eval(out, p, self)

        return out

    def eval(self, out, thing, neu_shape):

        if self is not neu_shape:
            neu_shape.parent = self

        if isinstance(thing, str):
            neu_shape.name = thing
            out[thing].append(neu_shape)
        else:
            # try:
            for k, v in thing(shape=neu_shape).items():
                out[k].extend(v)
            # except AttributeError:
            #     print(f"(str{thing} did not return a map of lists...")


    def evalf(self, f): # evaluate a float 
        if type(f) == int or type(f) == float:
            return f
        
        return f(shape = self)

    def count_abs_rel(self, args):

        total_abs = 0
        total_rel = 0
        total = 0

        for size, thing in zip(args[0::2], args[1::2]):
            size = self.evalf(size)
            if size > 0:  # absolute size
                total_abs += size
                total += size
            if size < 0:  # relative size
                total_rel -= size
                total -= size

        return total, total_abs, total_rel

    def chance_(self, out, *args):
        # RantomCache?, key, [probability, fn]+

        global RND_COUNT

        r2 = self.get_value("r2")
        if r2 is None:
            r2 = rantom.ROOT

        key = args[0]
        RND_COUNT[key] += 1

        args = self.eval_args(list (args[1:]))
        total, total_abs, total_rel = self.count_abs_rel(args)

        r = r2.random (f"{key}_{RND_COUNT[key]}")
        tot = 0

        for chance, thing in zip(args[0::2], args[1::2]):
            tot += (chance/total)
            if tot > r:
                self.eval (out, thing, self)
                return out

        print("nothing hit in chance?!")
        return out

    def compare_(self, fn, out, *args):  # if args[0] < args[1] then args[2] else args[3]

        values = self.eval_args(list (args[:2]))

        if fn ( values[0], values[1]):
            self.eval(out, args[2], self)
        else:
            self.eval(out, args[3], self)

        return out


    def eval_args (self, args):
        
        for i in range (0, len(args), 2):
            args[i] = self.evalf(args[i]) # bake in random here
        return args


class cuboid(shp):

    def __init__(self, coords, name=None, to_world=None) -> None:

        shp.__init__(self, name)
        self.name = self.__class__.__name__ + self.name

        self.coords = coords # [x,y,z, width (x, left/right), depth (y, in), height (z, up)]
        
        self.to_world = to_world if to_world is not None else Matrix()

    def split_tri_d_(self, d, out, *args):
        
        points = np.array ( [
            [ self.coords[0]               , self.coords[1]                 , self.coords[2]                  ],
            [ self.coords[0]+self.coords[3], self.coords[1]                 , self.coords[2]                  ],
            [ self.coords[0]+self.coords[3], self.coords[1] + self.coords[4], self.coords[2]                  ],
            [ self.coords[0]               , self.coords[1] + self.coords[4], self.coords[2]                  ],
            
            [ self.coords[0]               , self.coords[1]                 , self.coords[2] + self.coords[5] ],
            [ self.coords[0]+self.coords[3], self.coords[1]                 , self.coords[2] + self.coords[5] ],
            [ self.coords[0]+self.coords[3], self.coords[1] + self.coords[4], self.coords[2] + self.coords[5] ],
            [ self.coords[0]               , self.coords[1] + self.coords[4], self.coords[2] + self.coords[5] ]  ] )

        midface = np.array ([
            (points[0] + points[2] ) * 0.5,
            (points[0] + points[5] ) * 0.5,
            (points[0] + points[7] ) * 0.5,
            (points[2] + points[5] ) * 0.5,
            (points[2] + points[7] ) * 0.5,
            (points[4] + points[6] ) * 0.5  ])

        points = np.concatenate( (points, midface ))

        for i in range(points.shape[0]):
            w = self.to_world @ Vector (points[i])
            points[i] = w

        # if d == 10:
        #     xxx = bpy.data.objects.new( f"xxx-foo-four", None )
        #     xxx.location = points[4]
        #     bpy.context.scene.collection.objects.link(xxx)

        def build (thing, pts, up, right, project=None):
            
            r = points[right[1]] - points[right[0]]
            r = r / np.linalg.norm(r)
            
            if not isinstance( up, list ): # project point up onto right
                pt = Vector ( utils.intersect_point_line( points[up], points[right[0]], points[right[1]] ).tolist() ) 
                
                u = points[up] - pt
            else:
                u = points[up[1]] - points[up[0]]


            u = u / np.linalg.norm(u)

            o = np.cross(u,r) * -1
            
            mat3 = np.concatenate( ( r.reshape((-1, 1)), u.reshape((-1, 1)), o.reshape((-1, 1)) ), axis=1).tolist()
            to_world = utils.mat3_to_Matrix(mat3, points[pts[0]])


            from_world = to_world.inverted()

            flat = [ from_world @ Vector ( points[x] ) for x in pts ]

            if len (pts) == 4:
                xyz = utils.bounds_Vector(flat)
                shape = rect ( xyz[0][0], xyz[1][0], xyz[0][1]-xyz[0][0], xyz[1][1]-xyz[1][0], to_world=to_world )
            else:
                shape = tri( flat, to_world=to_world ) 

            self.eval ( out, thing, shape )

        sides = "none"
        floor = "none"

        if len (args) >= 1:
            roof = args[0]
        if len (args) >= 2:
            sides = args[1]
        if len (args) >= 3:
            floor = args[2]

        match d:

            # rectangular slopes from bottom edge to top. coord system on sides probably wrong.
            case 0:
                build ( roof , [0,1,6,7], [0,7], [0,1] )
                build ( sides, [0,7,3]  , [3,7], [3,0] )
                build ( sides, [1,6,2]  , [2,6], [1,2] )
                build ( floor, [2,3,6,7], [2,6], [2,3] )
            case 1:
                build ( roof , [2,3,4,5], [2,5], [2,3] )
                build ( sides, [2,5,1]  , 2, [5,1] )
                build ( sides, [3,4,0]  , 3, [0,4] )
                build ( floor, [0,1,4,5], [0,4], [0,1] )
            case 2:
                build ( roof , [0,3,6,5], [0,5], [3,0] )
                build ( sides, [0,5,1]  , [1,5], [0,1] )
                build ( sides, [3,6,2]  , [2,6], [2,3] )
                build ( floor, [1,2,6,5], [1,5], [1,2] )
            case 3:
                build ( roof , [1,2,7,4], [1,4], [1,2] )
                build ( sides, [1,4,0]  , [0,4], [0,1] )
                build ( sides, [2,7,3]  , [3,7], [2,3] )
                build ( floor, [3,0,4,7], [3,7], [3,0] )
            
            # triangular corners for roofs with two planes
            case 4:
                build ( roof, [0,1,6], [1,6], [0,1] )
                build ( roof, [0,3,6], [3,6], [3,0] )
            case 5:
                build ( roof, [1,2,7], [2,7], [1,2] )
                build ( roof, [1,0,7], [0,7], [0,1] )
            case 6:
                build ( roof, [2,3,4], [3,4], [2,3] )
                build ( roof, [2,1,4], [1,4], [1,2] )
            case 7:
                build ( roof, [3,0,5], [0,5], [3,0] )
                build ( roof, [3,2,5], [2,5], [2,3] )

            # single triangles over diagonal
            case 8:
                build ( roof, [0,2,5], 2, [0, 5] )
            case 9:
                build ( roof, [0,2,7], [0, 2], [8, 7] )
            case 10:
                build ( roof, [1,3,4], 3, [4, 1] )
            case 11:
                build ( roof, [1,3,6], [1, 3], [8, 6] )
            # ...tbc...

            case _:
                raise Exception(f"unkown split dir {d}")

        return out


    def split_d_(self, d, out, *args):

        args = self.eval_args(list (args))

        total, total_abs, total_rel = self.count_abs_rel(args)

        self_width = self.coords[3+d]

        if total_abs > self_width:
            per_rel = 0
            per_abs = max(0, (self_width            ) / max(0.01, total_abs ) )
        else:
            per_rel = max(0, (self_width - total_abs) / max(0.01, total_rel ) )
            per_abs = 1

        self.build(self, args, d, per_rel, out, per_abs = per_abs)

        return out

    def repeat_d_(self, d, out, *args):

        args = self.eval_args(list(args))

        total, total_abs, total_rel = self.count_abs_rel(args)
        self_width = self.coords[3 + d]

        if self_width <= 0:
            return out

        count = max(1, math.floor( self_width/float(total))) # count of repeating subunits
        width_per = self_width/count

        if total_abs > self_width: # count should be 1 here
            per_abs = max(0, (self_width ) / max(0.01, total_abs ) )
        else:
            per_abs = 1

        per_rel = max(0, (width_per - total_abs) / max(0.1,total_rel ) )

        for i in range (count): # for each subunit
            # this guy surrounds the repeating subunit:
            ipw = i * width_per
            repeat_rect = cuboid( [
                self.coords[0] + (ipw if d == 0 else 0),
                self.coords[1] + (ipw if d == 1 else 0),
                self.coords[2] + (ipw if d == 2 else 0),

                self.coords[3] if d != 0 else width_per,
                self.coords[4] if d != 1 else width_per,
                self.coords[5] if d != 2 else width_per ] )

            self.build(repeat_rect, args, d, per_rel, out, per_abs=per_abs)

        return out

    def build(self, r, args, d, per_rel, out, per_abs=1):

        d_loc = 0

        mask = [1 if d == 0 else 0, 1 if d == 1 else 0, 1 if d == 2 else 0 ]

        for size, thing in zip(args[0::2], args[1::2]):

            if size >= 0:  # absolute size
                nr_d = size * per_abs
            if size < 0:  # relative size
                nr_d = -per_rel * size

            if nr_d < 0.001: # threshold to hide geometry?
                continue

            neu_cuboid = cuboid (

                [r.coords[0] + d_loc * mask[0],
                 r.coords[1] + d_loc * mask[1],
                 r.coords[2] + d_loc * mask[2],
                 r.coords[3] * (1-mask[0]) + nr_d * mask[0],
                 r.coords[4] * (1-mask[1]) + nr_d * mask[1],
                 r.coords[5] * (1-mask[2]) + nr_d * mask[2] ],

                to_world=self.to_world )

            self.eval(out, thing, neu_cuboid)

            d_loc += nr_d

        return d_loc

    def split_faces_(self, out, *args):
        '''
            args length 1: [all]
                 length 2: [sides, top]
                 length 3: [front, sides, top]
                 length 4: [front, left_and_right, back, top]
                 length 5: [front, left, right, back, top]
                 length 6: [front, left, right, back, top, bottom]
        '''
        x,y,z,width,depth,height = self.coords

        # different face directions
        t = rect( 0, 0, width, depth,  to_world = self.to_world @ Matrix.Translation(Vector((x,y,z+height))) )
        b = rect( 0, 0, width, depth,  to_world = self.to_world @ Matrix.Translation(Vector((x,y+depth,z))) @ Matrix.Rotation(pi, 4, 'X') )
        l = rect( 0, 0, depth, height, to_world = self.to_world @ Matrix.Translation(Vector((x,y+depth,z))) @ Matrix.Rotation(-pi2, 4, 'Z') @ Matrix.Rotation(pi2, 4, 'X'))
        r = rect( 0, 0, depth, height, to_world = self.to_world @ Matrix.Translation(Vector((x + width,y,z))) @ Matrix.Rotation(pi2, 4, 'Z') @ Matrix.Rotation(pi2, 4, 'X'))
        f = rect( 0, 0, width, height, to_world = self.to_world @ Matrix.Translation(Vector((x,y,z))) @ Matrix.Rotation(pi2, 4, 'X') ) 
        x = rect( 0, 0, width, height, to_world = self.to_world @ Matrix.Translation(Vector((x+width,y+depth,z))) @ Matrix.Rotation(pi2, 4, 'X') @ Matrix.Rotation(pi, 4, 'Y') )  # back
        

        match len(args):
            case 1:
                for rct in [b, l, r, t, f, x]:
                    self.eval(out, args[0], rct )
            case 2:
                for i, rct in enumerate( [l, r, f, x] ):
                    self.eval(out, args[0], rct )
                self.eval(out, args[1], t )
            case 3:
                self.eval(out, args[0], f )
                for i, rct in enumerate( [l, r, x] ):
                    self.eval(out, args[1], rct )
                self.eval(out, args[2], t )
            case 4:
                self.eval(out, args[0], f )
                for i, rct in enumerate( [l, r] ):
                    self.eval(out, args[1], rct )
                self.eval(out, args[2], x )
                self.eval(out, args[3], t )
            case 5:
                self.eval(out, args[0], f )
                self.eval(out, args[1], l )
                self.eval(out, args[2], r )
                self.eval(out, args[3], x )
                self.eval(out, args[4], t )
            case 6:
                self.eval(out, args[0], f )
                self.eval(out, args[1], l )
                self.eval(out, args[2], r )
                self.eval(out, args[3], x )
                self.eval(out, args[4], t )
                self.eval(out, args[5], b )
            case _:
                raise Exception("split_faces expects 1-6 args")

        return out

    # def repeat_d_(self, d, out, *args):
    #     return out

    def random_point(self, r2, name="camera_pos"):

        v = Vector((
            r2.uniform(self.coords[0], self.coords[0]+self.coords[3], f"{name}_x"),
            r2.uniform(self.coords[1], self.coords[1]+self.coords[4], f"{name}_y"),
            r2.uniform(self.coords[2], self.coords[2]+self.coords[5], f"{name}_z")
        ))

        v = v @ self.to_world

        return v

    def spin_(self, out, *args):

        # re-orients scope (keeping same shape/location in space) args = axes  (x, y, z)
        # (x,y,z) = args[0]

        t = self.centre()

        transform = self.to_world @ Matrix.Translation(t) @\
                    Euler((pi2 * args[0][0], pi2 * args[0][1], pi2 * args[0][2])).to_matrix().to_4x4() @ \
                    Matrix.Translation(-t)

        # this is horribly hacky code for a single case.
        if args[0][0] % 2 == 1: #x
            assert args[0][1] == 0 and args[0][2] == 0
            # n = cuboid ( self.coords, to_world=transform )
            delta = self.coords[5] - self.coords[4]
            n = cuboid((self.coords[0],
                        self.coords[1] - delta / 2,
                        self.coords[2] + delta / 2,
                        self.coords[3], self.coords[5], self.coords[4]), to_world=transform)
        elif args[0][1] % 2 == 1: #y
            assert args[0][0] == 0 and args[0][2] == 0
            # n = cuboid ( self.coords, to_world=transform )
            delta = self.coords[5] - self.coords[3]
            n = cuboid((self.coords[0] - delta / 2,
                        self.coords[1],
                        self.coords[2] + delta / 2,
                        self.coords[5], self.coords[4], self.coords[3]), to_world=transform)
        elif args[0][2] % 2 == 1: # z
            assert args[0][0] == 0 and args[0][1] == 0
            delta = self.coords[4] - self.coords[3]
            n = cuboid((self.coords[0] - delta / 2,
                        self.coords[1] + delta / 2,
                        self.coords[2],
                        self.coords[4], self.coords[3], self.coords[5]), to_world=transform)
        else:
            n = cuboid ( self.coords, to_world=transform )

        self.eval(out, args[1], n)

        return out

    def centre(self):
        return Vector((self.coords[0] + self.coords[3] / 2, self.coords[1] + self.coords[4] / 2, self.coords[2] + self.coords[5] / 2))


    def translate_(self, out, *args):

        c2 = self.coords.copy()
        for i in range (3):
            c2[i] += args[0][i]
        next = cuboid (c2, name=self.name, to_world=self.to_world)

        self.eval(out, args[1], next)
        return out

class tri(shp):

    def __init__(self, coords, name=None, to_world=None) -> None:

        shp.__init__(self, name)
        self.name = self.__class__.__name__ + self.name

        self.coords = coords
        self.to_world = to_world

    def to_curve(self, z=0):

        if len (self.coords[0]) == 2:
            verts = list (map(lambda x: [*x, z], self.coords))
        else:
            verts = self.coords

        handle_r = prof.create_straight_handles( 1, verts)
        handle_l = prof.create_straight_handles(-1, verts)

        return prof.build_curve(1, verts, handle_l, handle_r ) # , d='3D'

    def split_tri_d_(self, d, out, *args):

        # d = 0: offset from all edges
        # args = offset distance, rule for exterior, rule for interior

        mx = my = 0 # centre of triangle
        for c in self.coords:
            mx += c[0]
            my += c[1]
        mx /= len (self.coords)
        my /= len (self.coords)

        for idx, ca in enumerate(self.coords):
            sb = self.coords[ ( idx+1 )%len ( self.coords) ]

    def split_lines_(self, out, *args):

        c = self.coords

        # order: horizontal, vertical, diagonal
        for i in range(3):
            a = i
            b = (i+1) % 3
            if c[a][0] == c[b][0]:
                pos = 0
            elif c[a][1] == c[b][1]:
                pos = 1
            else:
                pos = 2

            out[args[pos]].append ( line( [ [c[a][0], c[a][1]], [c[b][0], c[b][1]] ], to_world=self.to_world ) )

        return out

class rect(shp):

    def __init__(self, x, y, width, height, name=None, to_world=None) -> None:

        shp.__init__(self,name)
        self.name = "rect" + self.name

        self.dim = [x,y,width,height]

        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.to_world = to_world

    def to_curve(self, z=0):

        return prof.build_curve(1, self.get_verts(z=z) )

    def get_verts(self, z=0, vector=False): # format for curve
        
        vs = [
            ( self.x             , self.y              , z ),
            ( self.x + self.width, self.y              , z ),
            ( self.x + self.width, self.y + self.height, z ),
            ( self.x             , self.y + self.height, z )
        ]

        if vector:
            return [Vector((x[0], x[1], x[2])) for x in vs]
        else:
            return vs

    def world_center(self):
        v = Vector((self.x+self.width/2, self.y + self.height/2, 0))
        return self.to_world @ v

    def world_verts(self, z=0):
        # list ( map (lambda x-> self.to_world @ x, self.get_verts(z=z) ) )
        return [self.to_world @ x for x in self.get_verts(z=z, vector=True)]


    def offset(self, dist):
        self.x += dist
        self.y += dist
        self.width -= 2 * dist
        self.height -= 2* dist
        self.dim = [self.x,self.y,self.width,self.height]


    def split_d_(self, d, out, *args):

        args = self.eval_args(list(args))

        total, total_abs, total_rel = self.count_abs_rel(args)

        self_width = self.dim[2+d]

        if total_abs > self_width:
            per_rel = 0
            per_abs = max(0, (self_width            ) / max(0.01, total_abs ) )
        else:
            per_rel = max(0, (self_width - total_abs) / max(0.01, total_rel ) )
            per_abs = 1

        self.build(self, args, d, per_rel, out, per_abs = per_abs)

        return out

    def repeat_d_(self, d, out, *args):

        args = self.eval_args(list(args))

        total, total_abs, total_rel = self.count_abs_rel(args)
        self_width = self.dim[2 + d]

        if self_width <= 0:
            return out

        count = max(1, math.floor( self_width/float(total))) # count of repeating subunits
        width_per = self_width/count

        if total_abs > self_width: # count should be 1 here
            per_abs = max(0, (self_width ) / max(0.01, total_abs ) )
        else:
            per_abs = 1

        per_rel = max(0, (width_per - total_abs) / max(0.1,total_rel ) )

        for i in range (count): # for each subunit
            # this guy surrounds the repeating subunit:
            repeat_rect = rect(
                self.x + (0 if d else (i * width_per)),
                self.y + ((i * width_per) if d else 0),
                self.width if d else width_per,
                width_per if d else self.height )

            self.build(repeat_rect, args, d, per_rel, out, per_abs=per_abs)

        return out

    def split_lines_(self, out, *args):

        lines = []

        lines.append(line([[self.x             , self.y              ], [self.x + self.width, self.y              ]], to_world=self.to_world ) )
        lines.append(line([[self.x + self.width, self.y              ], [self.x + self.width, self.y + self.height]], to_world=self.to_world ) )
        lines.append(line([[self.x + self.width, self.y + self.height], [self.x             , self.y + self.height]], to_world=self.to_world ) )
        lines.append(line([[self.x             , self.y + self.height], [self.x             , self.y              ]], to_world=self.to_world ) )

        for i, l in enumerate ( lines ):
            l.to_world = self.to_world
            self.eval(out, args[i], l )

        return out

    def split_tri_d_(self, forwards, out, *args):

        a = [self.x, self.y]
        b = [self.x+self.width, self.y]
        c = [self.x + self.width, self.y+ self.height]
        d = [self.x, self.y + self.height]

        if forwards: # forwards /
           
            tris = [
                    tri([ a, b, d ]),
                    tri([ c, d, b ])
                     ]
        else: # backwards \
            tris= [ 
                     tri([ d, a, c ]),
                      tri([ b, c, a ])
            ]

        for i, t in enumerate ( tris ):
            t.to_world = self.to_world
            self.eval(out, args[i], t  )

        return out

    def build(self, r, args, d, per_rel, out, per_abs=1):

        d_loc = 0

        for size, thing in zip(args[0::2], args[1::2]):

            if size >= 0:  # absolute size
                nr_d = size * per_abs
            if size < 0:  # relative size
                nr_d = -per_rel * size

            if nr_d < 0.001: # threshold to hide geometry?
                continue

            neu_rect = rect(
                r.x + d_loc * (1 - d),
                r.y + d_loc * d,
                d * r.width + (1 - d) * nr_d,
                (1 - d) * r.height + d * nr_d, to_world=self.to_world)

            self.eval(out, thing, neu_rect)

            d_loc += nr_d

        return d_loc

    def extrude_(self, out, *args):

        distance = args[0]
        thing = args[1]

        extruded = cuboid([self.x, self.y, 0, self.width, self.height, distance], to_world=self.to_world)

        self.eval(out, thing, extruded )

        return out

    def rotate_(self, out, *args):

        scaled = copy.deepcopy( self )
        
        # scaled.to_world = Matrix(self.to_world)

        t = Vector((self.x + self.width/2, self.y + self.height/2, 0))
        f = Vector((-self.x - self.width/2, -self.y - self.height/2, 0))

        scaled.to_world = scaled.to_world @ Matrix.Translation(t) @ Euler((args[1], args[2], args[3])).to_matrix().to_4x4() @ Matrix.Translation(f)

        self.eval(out, args[0], scaled )

        return out

    def spin_(self, out, *args):

        nw = self.height
        nh = self.width

        t = Vector(( self.x + self.width/2,  self.y + self.height/2, 0))
        f = Vector((-self.x - self.width/2, -self.y - self.height/2, 0))

        #math.pi/2
        transform = self.to_world @ Matrix.Translation(t) @ Euler((0,0,pi2*args[1])).to_matrix().to_4x4() @ Matrix.Translation(f)
        
        if args[1] % 2 ==1:
            n = rect(self.x - (nw-self.width)/2, self.y + (self.height-nh)/2, nw, nh, to_world=transform )
        else:
            n = rect(self.x, self.y, self.width, self.height, to_world=transform )

        self.eval(out, args[0], n )

        return out

    def size_(self, d):

        match d:
            case 0:
                return self.width
            case 1:
                return self.height
        
        return -1

class line(shp):
    def __init__(self, coords, name=None, to_world=None) -> None:

        shp.__init__(self, name)
        self.name = self.__class__.__name__ + self.name

        self.coords = coords
        self.to_world = to_world

    def spin_(self, out, *args):

        # tmp = self.coords[0]
        # self.coords[0] = self.coords[1]
        # self.coords[1] = tmp

        #self.eval(out, args[0], n )

        n = line([self.coords[1], self.coords[0]], to_world=self.to_world)

        self.eval(out, args[0], n )

        return out

    def world_verts(self):
        return [self.to_world @ Vector((x[0], x[1], 0)) for x in self.coords]

    def to_curve(self, z=0):

        if len (self.coords[0]) == 2:
            verts = list (map(lambda x: [*x, z], self.coords))
        else:
            verts = self.coords

        # handle_r = prof.create_straight_handles( 1, verts)
        # handle_l = prof.create_straight_handles(-1, verts)

        return prof.build_curve(1, verts, None, None, cyclic = False ) # handle_l, handle_r ) # , d='3D'