import math

import bpy
import bisect
import math
from collections import defaultdict
from mathutils import Matrix, Vector
from src import cgb_building
from src import cgb
from src import rantom
from src import profile as prof
import random
from src.cgb import shp, rect, tri, cuboid, parallel, repeat_x, repeat_y, split_x, split_y, split_z
from bisect import bisect_left, bisect_right
import math

import numpy as np
from src.profile import sub, length, norm, add, scale, dot


def horiz_at_height(graph, max_z):
    top_horiz = defaultdict(set)
    for a in graph:
        if a[2] == max_z:
            for b in graph[a]:
                if b[2] == max_z:
                    top_horiz[a].add(b)

    return top_horiz


# djikstra's algorithm for finding the shortest path between two points in a graph with edge lengths
def djikstra(graph, start, ends, length):


    dist = defaultdict(lambda: math.inf)
    dist[start] = 0
    prev = {}
    unvisited = set(graph.keys())
    # end = None

    while len(unvisited) > 0:
        u = None
        for n in unvisited:
            if u is None or dist[n] < dist[u]:
                u = n

        unvisited.remove(u)

        for v in graph[u]:
            alt = dist[u] + length(v, u)
            if v not in dist or alt < dist[v]:
                dist[v] = alt
                prev[v] = u

        if u in ends:
            break

    path = []

    best_e = math.inf
    for e in ends:
        if e in dist and dist[e] < best_e:
            best_e = dist[e]
            u = e

    if best_e == math.inf:
        return []

    # u = random.choice ( list ( filter( lambda e: prev[e] != None, ends) ) )

    while u in prev:
        path.insert(0, u)
        u = prev[u]

    path.insert(0, start)

    return path

# add the gutters into the graphe and connect them to the edges over the walls...
def add_gutter_edges ( graph, gutter_lines, gutter_height ):

    def distance(s,e, x):
        # distance between 3d line s,e and point x
        t = ( (x[0]-s[0])*(e[0]-s[0]) + (x[1]-s[1])*(e[1]-s[1]) + (x[2]-s[2])*(e[2]-s[2]) ) / ( (e[0]-s[0])**2 + (e[1]-s[1])**2 + (e[2]-s[2])**2 )
        return math.sqrt( (s[0] + t*(e[0]-s[0]) - x[0])**2 + (s[1] + t*(e[1]-s[1]) - x[1])**2 + (s[2] + t*(e[2]-s[2]) - x[2])**2 )


    def project (s,e, x):
        # project x onto line s,e in 3d
        t = ( (x[0]-s[0])*(e[0]-s[0]) + (x[1]-s[1])*(e[1]-s[1]) + (x[2]-s[2])*(e[2]-s[2]) ) / ( (e[0]-s[0])**2 + (e[1]-s[1])**2 + (e[2]-s[2])**2 )
        return (s[0] + t*(e[0]-s[0]), s[1] + t*(e[1]-s[1]), s[2] + t*(e[2]-s[2]))

    divide = rantom.uniform_mostly(0.1, 0, 0.2, 0.8, "gutter_dropdown_shape")

    start_pts = []
    total_length = 0

    for gl in gutter_lines:

        glc = gl.world_verts()
        s,e = glc[0], glc[1]
        s[2] -= gutter_height
        e[2] -= gutter_height

        best, best_d = [], 1
        for a in graph:

            d = distance(s,e, a)
            if s[2] - a[2] > 0.2:
                if  d < best_d - 0.001:
                    best_d = d
                    best = [a]
                elif d < best_d + 0.001:
                    best.append(a)

        if len (best) > 0:
            total_length += length(sub(s,e))

        for a in best:

            b = project(s,e, a)
            start_pts.append(b)
            if divide == 0:
                graph[b].add(a)
            else: # zig-zag
                d = s[2] - a[2]
                v1 = (b[0], b[1], b[2] - d * divide)
                # v2 = (a[0], a[1], a[2] + d * divide)
                graph[b].add(v1)
                graph[v1].add(a)
                # graph[v2].add(a)

            # curve = prof.build_curve(1, ((a[0], a[1], a[2]), (b[0], b[1], b[2])), d='3D', cyclic=False)
            # curve.name = "xxx-gutter_target"
            # bpy.context.scene.collection.objects.link(curve)
    return start_pts, total_length


def smooth_handles(coords, frac, rr, m):

    handleLs, handleRs = [], []
    dist_twixt_pts = rr.uniform(0.1, 2)

    # add extra points to the wire
    if len (coords) >= 3:

        c2 = [coords[0]]

        for i in range(1, len(coords) - 2):

            c2.append(coords[ i ])

            a = coords[i]
            b = coords[i + 1]
            extra = math.ceil( length (sub ( a,b )) / dist_twixt_pts ) -1
            for j in range ( extra ):
                t = (j + 1) / (extra + 1)
                c2.append ( prof.lerp(a, b, t ) )

        c2.append(coords[-2])
        c2.append(coords[-1])

        coords = c2

    ofx = (m[0][0], m[1][0], m[2][0]) # x and z directions on wall...
    ofy = (m[0][1], m[1][1], m[2][1])

    # set smooth tangents along curve with a bit of noise
    R = rr.uniform(0.01, 0.7) # random things up a bit
    for i in range(len(coords)):

        if i < len(coords) - 1 and i > 0:

            c = coords[i]
            n = coords[(i + 1)]
            p = coords[(i - 1)]

            average = norm ( add (sub(p, c), sub(c, n)) )

            r = add ( scale ( ofx, rr.uniform(-R, R) ), scale(ofy, rr.uniform(-R, R)) )
            average = norm ( add (average, r ) )

            handleLs.append(add(c, scale(average, length(sub(c, p)) * frac)))
            handleRs.append(add(c, scale(average, -length(sub(c,n)) * frac)))
        else:
            handleLs.append(coords[i])
            handleRs.append(coords[i])

    if len (coords) >= 4:

        # first and last segments are straight
        handleRs[ 0] = prof.lerp(coords[ 0], coords[ 1], 0.33)
        handleLs[ 1] = prof.lerp(coords[ 1], coords[ 0], 0.33)
        handleLs[-1] = prof.lerp(coords[-1], coords[-2], 0.33)
        handleRs[-2] = prof.lerp(coords[-2], coords[-1], 0.33)

    return coords, handleLs, handleRs

def curve_corners(coords, rad):

    c2=[coords[0]]

    handleLs, handleRs = [coords[0]], [coords[0]]

    def lerd(a, b, dist):

        frac = dist / length(sub ( a, b) )
        return (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac, a[2] + (b[2] - a[2]) * frac)

    for i in range(1,len ( coords )-1):
        p = coords[i-1]
        c = coords[i]
        n = coords[i+1]

        if prof.angle_twixt(p, c, n) > 3.1:
            c2.append(c)
            handleLs.append(c)
            handleRs.append(c)
            continue

        got_c = False
        if length(sub(p,c)) > 3 * rad:

            pt = lerd(c,p,rad)
            c2.append(pt)
            handleLs.append(prof.lerp(pt, p, 0.33))
            handleRs.append(prof.lerp(pt, c, 0.66))
        else:
            c2.append(c)
            handleLs.append(c)
            handleRs.append(c)
            got_c = True

        if length(sub(c,n)) > 3 * rad:

            pt = lerd(c,n,rad)
            c2.append(pt)
            handleRs.append(prof.lerp(pt, n, 0.33))
            handleLs.append(prof.lerp(pt, c, 0.66))

        elif not got_c:
            c2.append(c)
            handleLs.append(c)
            handleRs.append(c)

    c2.append(coords[-1])
    handleLs.append(coords[-1])
    handleRs.append(coords[-1])

    return c2, handleLs, handleRs


def create_gutter(faces, parent, cgb_building, gutter_height):

    g, gi = {}, {}

    for shape in faces["roof_gutter"]:
        a,b = shape.world_verts()
        a, b = tuple(a), tuple(b)
        g[a] = b
        gi[b] = a

    def find_start():

        # edge with single start
        for a in g:
            if b in gi:
                continue; # not a single-start
            return a

        for a in g:
            return a # just take one

        return None # all done

    curves = []
    coords = []

    a = find_start()
    while a:
        # pick an edge in the graph with a single connection
        c = a
        while c:
            coords.append(c)

            if c not in g: # found an end
                curves.append(coords)
                coords = []
                break

            old = c
            c = g[c]

            del g[old]
            del gi[c]

            if c == a: # back at start
                curves.append(coords)
                coords = []
                break

        a = find_start()

    for i, coords in enumerate ( curves ):
        curve = prof.build_curve(1, coords, d='3D', cyclic=False)
        curve.name = f"xxx-gutter-curve-{i}"
        curve.data.bevel_mode = 'OBJECT'
        curve.data.bevel_object = rantom.choice(bpy.data.collections["gutter_profiles"].all_objects, "gutter_profile_choice")

        if "mode" in cgb_building.geom and cgb_building.geom["mode"] == "mono_profile":
            curve.data.bevel_object = bpy.data.collections["gutter_profiles"].all_objects[0]

        curve.data.use_fill_caps = True
        curve.parent = parent
        curve.location = curve.location + Vector((0, 0, -gutter_height))
        bpy.context.scene.collection.objects.link(curve)
        cgb_building.geom['gutter'].append(curve)

def graphs_to_pipes(graph, gutter_starts, gutter_length, pull, wall_starts, wire_graph, m, wall_count, parent, rr):


    max_z = -100000
    for a in graph:
        max_z = max(max_z, a[2])
    # filter graph for edges with start and end at max_z
    tops = list(filter(lambda x: x[2] == max_z, graph.keys()))
    bottoms = set()
    for a in graph:
        for b in graph[a]:
            if b[2] < 0.01:
                bottoms.add(b)
    bottoms = list(bottoms)
    big_pipe_edges = set()

    def length_more_verticals(a, b):
        l = math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
        if a[0] == b[0] and a[1] == b[1]:
            l *= 0.8  # prefer vertical edges
        return l

    def length(a, b):
        l = math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
        return l

    # first do small wires non-destructively
    global pipe_number
    pipe_number = 0

    def create(g, start, end, count, radius, destructive, length, offset=0, is_wire=False, add_removed_edges_to=None):

        global pipe_number

        all = []
        r = radius()

        for c in range(count()):
            path = djikstra(g, start() if callable(start) else start, end() if callable(end) else end, length)
            if len(path) > 0:

                if is_wire:
                    coords, hl, hr = smooth_handles(path, 0.33, rr, m)
                else: # if rr.uniform(0, 1) < 1 : #0.5:
                    coords, hl, hr = curve_corners(path, r)  # path, None, None
                # else:
                #     coords, hl, hr = path, None, None # no curve


                curve = prof.build_curve(1, coords, handleLs=hl, handleRs=hr, d='3D', cyclic=False)
                curve.name = f"xxx-pipe-curve-{wall_count}-{pipe_number}"
                curve.data.bevel_depth = r
                curve.data.fill_mode = 'FULL'
                curve.parent = parent
                curve.data.render_resolution_u = curve.data.resolution_u = 10 if is_wire else 30

                all.append(curve)
                bpy.context.scene.collection.objects.link(curve)
                pipe_number += 1

                # translate curve to wall
                if offset != 0:
                    o = Vector((0, 0, offset - r)) @ m
                    curve.location = o  # (curve.location[0], curve.location[1], curve.location[2] + offset)

                if destructive:
                    for i in range(0, len(path) - 1):
                        if add_removed_edges_to is not None:
                            add_removed_edges_to.add(path[i])
                            add_removed_edges_to.add(path[i + 1])
                        if path[i] in g and path[i - 1] in g[path[i]]:
                            g[path[i]].remove(path[i - 1])

        return all

    # different thicknesses and styles of pipes (starting with wires, then drainpipes, then plumbing)
    picks = lambda x: lambda: rantom.choice(x, f"pipe_start_{wall_count}_{pipe_number}")
    picke = lambda x: lambda: [rantom.choice(x, f"pipe_end_{wall_count}_{pipe_number}")]
    ui = lambda l, u: lambda: rantom.randrange(u - l, f"pipe_type_repeats_{wall_count}_{pipe_number}") + l
    ud = lambda l, u: lambda: rantom.uniform(u, l, f"pipe_radius_{wall_count}_{pipe_number}")

    wires       = create(wire_graph, picks(wall_starts),
                         picke(wall_starts), ui(1, 10), ud(0.002, 0.001), False, length, is_wire=True, offset=pull)

    drain_pipes = create(graph, picks(gutter_starts) if len(gutter_starts) > 0 else picks(tops),
                         lambda: bottoms + list(big_pipe_edges), ui(1, int ( max(1, gutter_length/2) ) ), lambda : pull, True,
                         length_more_verticals, add_removed_edges_to=big_pipe_edges)

    lil_pipes   = create(graph, picks(wall_starts),
                         bottoms if len(big_pipe_edges) == 0 else lambda: bottoms + list(big_pipe_edges),
                         ui(0, max (2, int(gutter_length) ) ), ud(0.01, 0.025), True, length)

    return wires, drain_pipes, lil_pipes


def max_subdivide(faces, cgb_building, include_others=True):

    cgb_building.geom['wires'], cgb_building.geom['drain_pipes'], cgb_building.geom['small_pipes'],  cgb_building.geom['gutter'] = [],[],[], []

    gutter_height = 0.05
    parent = bpy.data.objects.new( f"xxx-pipes", None )
    bpy.context.scene.collection.objects.link(parent)
    create_gutter(faces, parent, cgb_building, gutter_height)

    if rantom.weighted_int([1,1], "do_pipes") == 0:
        return

    # split all wall faces on the same plane to share xes and yes (for drainpipes and merging the meshes).
    mat2shapes = defaultdict(list)
    shape2name = {}
    shout = cgb.get_output()

    for name in faces:
        if name in cgb_building.wall_names and not name in ["wm", "wn"]:
            for s in faces[name]:  # process each wall
                if s.normal().x > 0.5: # front facing only
                    mat2shapes[Matrix(s.to_world).freeze()].append(s)
                    shape2name[s] = name
        elif include_others:
            shout[name].extend(faces[name])
            # for s in faces[name]:  # just output
            #     shout[name].append(s)

    mat2shapes2 = defaultdict(list)
    sxr, syr = rantom.uniform(1, 2, "pipes_y_repeat"), rantom.uniform(0.5, 2, "pipes_x_repeat")
    gutter_dropdown = rantom.uniform(0.2, 0.5, "gutter_dropdown")


    tol = 0.01

    def insert(value, lst):
        i = bisect_left(lst, value)
        if i < len(lst) and abs(lst[i] - value) < tol:
            return

        if i+1 < len(lst) and abs(lst[i+1] - value) < tol:
            return

        lst.insert(i, value)

    gutter_heights = []
    for f in faces["roof_gutter"]:
        for v in f.world_verts():
            gutter_heights.append(v.z - gutter_height - gutter_dropdown)

    for m in mat2shapes:
        xes, yes = [], []

        for g in gutter_heights:
            insert(g, yes)

        for s in mat2shapes[m]:
            if isinstance(s, cgb.rect):

                splitz = repeat_x(-sxr, repeat_y ( -syr, "w" ) ) (shape=s)

                for s2 in splitz["w"]:
                    insert(s2.x, xes)
                    insert(s2.x + s2.width, xes)
                    insert(s2.y, yes)
                    insert(s2.y + s2.height, yes)

            elif isinstance(s, cgb.tri): # don't split tris, but use their verts
                for v in s.coords:
                    insert(v.x, xes)
                    insert(v.y, yes)

                if include_others:
                    shout[shape2name[s]].append(s)

        def find(lst, value):
            i = bisect_left(lst, value)

            for ii in [i-1, i, i+1]:
                if ii >= 0 and ii < len(lst) and abs(lst[ii] - value) < tol:
                    return ii


        for s in mat2shapes[m]:
            if isinstance(s, cgb.rect):
                for i in range(find(xes, s.x), find(xes, s.x + s.width)):
                    for j in range(find(yes, s.y), find(yes, s.y + s.height)):
                        shp = cgb.rect(
                            xes[i], yes[j], xes[i + 1] - xes[i], yes[j + 1] - yes[j],
                            to_world=s.to_world, name=s.name)
                        shout[shape2name[s]].append( shp )
                        mat2shapes2[m].append(shp)

    # build a graph of all the potential pipe locations

    wall_count = 0
    rr = np.random.RandomState(seed=rantom.randrange( 1e7, f"pipes_seed") )
    connectivity = 1 # rantom.uniform(0.5, 1, "pipes_connectivity_prob")
    wall_starts = []

    for m in mat2shapes2:

        graph = defaultdict(set) # water flows down/forwards along the pipe graph
        wire_graph = defaultdict(set) # bidirectional graph for wires including horizontal
        pull = rantom.uniform(0.025, 0.05, f"big_drainpipe_width_{wall_count}" )

        def add (verts, wall_verts, i, j, is_horiz=False):
            # global rr
            if rr.uniform(0, 1) < connectivity:

                if not is_horiz:
                    graph[verts[i]].add(verts[j])

                wire_graph[verts[i]].add(verts[j])
                wire_graph[verts[j]].add(verts[i])


                for k in [i,j]:
                    if wall_verts[k][2] > 0.2:
                        graph[wall_verts[k]].add(verts[k])
                        graph[verts[k]].add(wall_verts[k])
                        wall_starts.append(wall_verts[k])

                        if is_horiz:
                            wire_graph[verts[k]].add(wall_verts[k])
                            wire_graph[wall_verts[k]].add(verts[k])

        for s in mat2shapes2[m]:
            if isinstance(s, cgb.rect):

                verts, wall_verts = \
                    [(y.x, y.y, y.z) for y in (s.to_world @ x for x in s.get_verts(z=pull, vector=True))],\
                    [(y.x, y.y, y.z) for y in (s.to_world @ x for x in s.get_verts(z=0, vector=True))]

                # pipes only go down
                add(verts, wall_verts, 3, 0)
                add(verts, wall_verts, 2, 1)
                add(verts, wall_verts, 2, 0)
                add(verts, wall_verts, 3, 1)

                # wires can go in more directions
                add(verts, wall_verts, 0, 1, is_horiz=True)
                add(verts, wall_verts, 2, 3, is_horiz=True)

        gutter_starts, gutter_length = add_gutter_edges(graph, faces["roof_gutter"], gutter_height)

        if False: # debug

            parent = bpy.data.objects.new(f"xxx-all-pipes", None)
            bpy.context.scene.collection.objects.link(parent)

            for a in graph:
                for b in graph[a]:
                    if a != b:
                        curve = prof.build_curve(1, ((a[0], a[1], a[2]), (b[0], b[1], b[2])), d='3D', cyclic=False)
                        curve.name = "xxx-complete"

                        bpy.context.scene.collection.objects.link(curve)
                        curve.parent = parent
                        print(f"edge {a} -> {b}")

        wires, big, small = graphs_to_pipes(graph, gutter_starts, gutter_length, pull, wall_starts, wire_graph, m.copy(), wall_count, parent, rr)

        cgb_building.geom['wires'].extend(wires)
        cgb_building.geom['drain_pipes'].extend(big)
        cgb_building.geom['small_pipes'].extend(small)

        wall_count += 1


    return shout
