from bisect import bisect_left, bisect_right
import collections
from src.cgb import rect

def adjacent (a, b):

    outs = []

    if a.y == b.y and a.height == b.height:
        if a.x + a.width == b.x:
            outs.append( ( a.height, rect(a.x, a.y, a.width + b.width, a.height )))
        if b.x + b.width == a.x:
            outs.append( ( b.height, rect(b.x, b.y, b.width + a.width, b.height )))

    if a.x == b.x and a.width == b.width:
        if a.y + a.height == b.y:
            outs.append ( ( a.width, rect( a.x, a.y, a.width, a.height + b.height )))
        if b.y + b.height == a.y:
            outs.append ( ( b.width, rect( b.x, b.y, b.width, b.height + a.height )))

    for l, r in outs:
        r.to_world = a.to_world
        r.parent   = a.parent
        r.lookup   = a.lookup
        r.name     = a.name

    return outs

def merge_rects (shapes):

    lookup = Adjacent (shapes)

    done = False
    remaining = set ( shapes )

    while not done and len (remaining) > 1:

        done = True

        for a in remaining.copy():

            if not a in remaining:
                continue

            best_l = 0
            best, best_u  = None, None
            for b in lookup.get_adjacent(a):
                if b != a:
                    for l, u in adjacent(a,b):
                        if l > best_l:
                            best, best_u, best_l = b, u, l

            if best is not None:
                done = False
                remaining.remove(a)
                remaining.remove(best)
                lookup.remove(a)
                lookup.remove(best)
                remaining.add(best_u)
                lookup.add(best_u)

    return remaining


def same_to_world (shapes):

    d = collections.defaultdict(lambda : set())

    for s in shapes:
        d[s.to_world.copy().freeze()].add(s)

    return d

class Adjacent():

    def __init__(self, shapes):
        self.xes = []
        self.x_val = []
        self.yes = []
        self.y_val = []


        for s in shapes: #  create list + sort?
            self.add (s)


    def add(self, shape):

        def ins(lit, values, position, rect):

            i = bisect_left(lit, position)
            if i < len(lit) and lit[i] == position:
                values[i].add(rect)
            else:
                lit.insert(i, position)
                values.insert(i, set([rect]))

        if str(shape.__class__) == str(rect ):
            ins(self.xes, self.x_val, shape.x, shape)
            ins(self.xes, self.x_val, shape.x + shape.width, shape)
            ins(self.yes, self.y_val, shape.y, shape)
            ins(self.yes, self.y_val, shape.y + shape.height, shape)


    def remove (self, shape, eps=0.001):

        def rem (lit, values, position, rect):

            i = bisect_left(lit, position)
            if i < len (lit) and lit[i] == position:
                values[i].remove(rect)

        if str(shape.__class__) == str(rect ):
            rem(self.xes, self.x_val, shape.x, shape)
            rem(self.xes, self.x_val, shape.x + shape.width, shape)
            rem(self.yes, self.y_val, shape.y, shape)
            rem(self.yes, self.y_val, shape.y + shape.height, shape)

        # for ss in self.x_val:
        #     for s in ss:
        #         if s == shape:
        #             print ("oh no!")
        #
        # for ss in self.y_val:
        #     for s in ss:
        #         if s == shape:
        #             print ("oh no!")

    def get (self, lit, values, position, eps=0.001):

        ix, iy = bisect_left(lit, position-eps), bisect_right(lit, position+eps)

        if ix >= 0 and ix < len (lit) and iy >= 0 and iy <= len(lit):
            out = set()
            for i in range (ix, iy):
                out = out.union ( values[ix] )
            return out
        else:
            return set()

    def get_adjacent(self, shape):

        x_found = self.get(self.xes, self.x_val, shape.x ).union ( self.get(self.xes, self.x_val, shape.x + shape.width ) )
        y_found = self.get(self.yes, self.y_val, shape.y ).union ( self.get(self.yes, self.y_val, shape.y + shape.height ) )

        return x_found.intersection (y_found)


# class rect():
#
#     def __init__(self, x, y, width, height, name="foo", to_world=None) -> None:
#         self.name = "rect"
#
#         self.dim = [x,y,width,height]
#
#         self.x = x
#         self.y = y
#         self.width = width
#         self.height = height
#         self.to_world = "to_world"
#         self.parent = ""
#         self.lookup = ""
#
#     def __str__(self):
#         return f"[{self.x}, {self.y}, {self.width}, {self.height}]"
#
# rs = [rect(0,0,10,20), rect(10, 10, 10, 10) , rect(10, 0, 10, 10), rect(-20, 0, 20, 20)]
#
# for s in merge_rects(rs):
#     print (s)
