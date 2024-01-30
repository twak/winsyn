
import bpy
import json, os
from src import rantom
from src import config
from collections import OrderedDict
from collections.abc import Iterable 
import random
from mathutils import Vector, Matrix
import bmesh
from mathutils import Vector
from bmesh.types import BMVert
import numpy as np
import time

JUNK_SUMMARY = None

def read_todo_list():

    todo_list = None
    if os.path.exists(os.path.join(config.render_path, "todo.txt")):
        with open(os.path.join(config.render_path, "todo.txt")) as f:
            todo_list = []

            for l in f.readlines():
                l = l.strip()
                if len(l) > 2:
                    todo_list.append(l)

            random.shuffle(todo_list) # hopefully different on each node...
            print(f"todo list found with {len(todo_list)} entries")
            return todo_list

    return None

def next_todo(todo_list):

    os.makedirs(os.path.join ( config.render_path, "done" ), exist_ok=True)

    rendername = None
    # done_tmp = os.listdir(os.path.join ( config.render_path, "done" ))
    # dones, no_subdivs = [], []

    no_subdivs = False

    for t in [*todo_list]:
        file = os.path.join(config.render_path, "done", t)

        if not os.path.exists(file):
            rendername = t
            print(f"rendering {rendername}")
            break

        if os.path.getmtime(file) < time.time() - 40 * 60:  # if file older that 40 minteus
            with open(file, "r") as f:
                if "started" in f.read():  # started a while back, assume crashed
                    rendername = t
                    no_subdivs = True
                    print (f"re-rendering {rendername}")
                else:  # finished succesfully, don't re-do!
                    todo_list.remove(t)

    if rendername == None:
        return None, False

    with open(os.path.join(config.render_path, "done", rendername), "w") as f:
        f.write(f"started by {config.jobid}\n")

    # remove leading 0s from rendername
    style = rendername.lstrip("0")
    seed = int(style)

    return seed, no_subdivs

def todo_done(seed, rendername):

    with open(os.path.join(config.render_path, "done", rendername), "w") as f:
        f.write(f"done by {config.jobid}\n")


def junk_loader():

    root = os.path.join (config.resource_path, "interior_junk")

    # if JUNK_SUMMARY is None:
    vals = list ( json.load( open ( os.path.join (root, "summary.json") ) ) )

    # global JUNK_SUMMARY
    JUNK_SUMMARY = []
    for x in vals:
        dict = OrderedDict()
        JUNK_SUMMARY.append(dict)
        for k in reversed(sorted(x)):
            dict[float(k)] = x[k][0]

    # print (JUNK_SUMMARY[0])

    x = y = 0

    for k, folder in JUNK_SUMMARY[0].items():
        bpy.ops.import_scene.obj(filepath=os.path.join(root, folder, "meshes", "model.obj" ), axis_up='Z' )
        obj_object = bpy.context.selected_objects[0]

        mat = obj_object.material_slots[0].material
        internal_image = bpy.data.images.load(os.path.join(root, folder, "materials", "textures", "texture.png" ) )
        internal_image.name = "xxx_" +folder+"_" + internal_image.name
        mat.node_tree.nodes["Image Texture"].image = internal_image

        obj_object.name = f"xxx_{folder}"
        obj_object.location = [x* 0.6, y * 0.6, 0]

        x += 1
        if x > 5:
            x = 0
            y += 1

            if y == 15:
                return

        print(obj_object)
        # break

    

def to_mesh(obj, add = True, delete = False):
    
    dg = bpy.context.evaluated_depsgraph_get() 
    ob = obj.evaluated_get(dg) 
    me2 = ob.to_mesh() 
    meshOB = bpy.data.objects.new("xxx-"+obj.name, me2.copy())

    set_auto_smooth(meshOB)

    if add:
        bpy.context.scene.collection.objects.link(meshOB)

    if delete:
        bpy.data.objects.remove(obj, do_unlink=True)


    return meshOB

def set_auto_smooth(meshOB):
    meshOB.data.use_auto_smooth = True
    meshOB.data.auto_smooth_angle = 0.349066


def extrude_edges(curve, dir, add = True, use_normal_flip=True, name = None): # curve -> mesh -> extrude in dir

    old_curve_fill_mode = curve.data.fill_mode
    curve.data.fill_mode = 'NONE'

    mesh_window = to_mesh ( curve )

    curve.data.fill_mode = old_curve_fill_mode

    bm = bmesh.new()
    dg = bpy.context.evaluated_depsgraph_get()
    bm.from_object( mesh_window, dg )
    all_edges = bm.edges[:]
    ret = bmesh.ops.extrude_edge_only(bm, edges=all_edges, use_normal_flip=use_normal_flip)
    geom_extrude_mid = ret["geom"]
    verts_extrude_b = [ele for ele in geom_extrude_mid if isinstance(ele, bmesh.types.BMVert)]
    bmesh.ops.translate(
        bm,
        verts=verts_extrude_b,
        vec=(dir[0], dir[1], dir[2]))
    del ret
    mesh = bpy.data.meshes.new("Mesh")
    bm.to_mesh(mesh)
    bm.free()

    bpy.data.objects.remove( mesh_window, do_unlink=True)

    me = bpy.data.objects.new(f"xxx-{curve.name}" if name is None else name, mesh )

    if add:
        bpy.context.scene.collection.objects.link(me)

    return me

def bounce_clamp(num, min_value, max_value):
    
    if num > max_value:
        return max (2*max_value-num, min_value)
    
    if num < min_value:
        return min (2*min_value-num, max_value)
    
    return num

def clamp (num, min_value = 0, max_value = 1):
    return min (max_value, max (min_value, num))

def hsv_to_rgb(h, s, v): # from colorsys

    h = h % 1

    if s == 0.0:
        return (v, v, v, 1)
    i = int(h*6.0) # XXX assume int() truncates!
    f = (h*6.0) - i
    p = v*(1.0 - s)
    q = v*(1.0 - s*f)
    t = v*(1.0 - s*(1.0-f))
    i = i%6
    if i == 0:
        return (v, t, p, 1)
    if i == 1:
        return (q, v, p, 1)
    if i == 2:
        return (p, v, t, 1)
    if i == 3:
        return (p, q, v, 1)
    if i == 4:
        return (t, p, v, 1)
    if i == 5:
        return (v, p, q, 1)
    # Cannot get here

def rgb_to_hsv(r, g, b): # https://github.com/python/cpython/blob/3.11/Lib/colorsys.py
    maxc = max(r, g, b)
    minc = min(r, g, b)
    rangec = (maxc-minc)
    v = maxc
    if minc == maxc:
        return 0.0, 0.0, v
    s = rangec / maxc
    rc = (maxc-r) / rangec
    gc = (maxc-g) / rangec
    bc = (maxc-b) / rangec
    if r == maxc:
        h = bc-gc
    elif g == maxc:
        h = 2.0+rc-bc
    else:
        h = 4.0+gc-rc
    h = (h/6.0) % 1.0
    return h, s, v

def get_curve_info(geom, shapeOB):

    if 'curve_info' not in geom:
        geom['curve_info'] = {}

    if shapeOB not in geom['curve_info']:
        geom['curve_info'][shapeOB] = {}

    return geom['curve_info'][shapeOB]


def urban_canyon_go(geom):

    c = bpy.data.node_groups["canyon_shader_generator"]
    c.nodes["Value.001"].outputs[0].default_value = rantom.randrange(1e6, "canyon_seed", "random_seed_canyon_generation")

    match rantom.randrange( 3, "use_canyon", "Do we add canyon occluders?"):
        case 0: # vertical pipes
            c.nodes["Distribute Points on Faces"].inputs[4].default_value = rantom.gauss( 0.2,0.1, "canyon_density", "canyon occluder density")
            c.nodes["Value"].outputs[0].default_value = rantom.gauss_clamped( 0.4,0.3, 0, 3, "canyon_width", "width range of canyon occluders")
        case 1: # buildings
            c.nodes["Distribute Points on Faces"].inputs[4].default_value = max (0.01, rantom.gauss( 0.02,0.02, "canyon_density", "canyon occluder density") )
            c.nodes["Value"].outputs[0].default_value = rantom.gauss( 8, 3, "canyon_width", "width range of canyon occluders")   
        case _: # nothing!
            c.nodes["Distribute Points on Faces"].inputs[4].default_value 

    # geom['canyon'].hide_set(True)
    

def is_parent(object, query, is_child):

    if query in is_child:
        return is_child[query]
    else:
        if query == object:
            is_child[query] = True
            return True
        elif query.parent == None:
            is_child[query] = False
            return False
        else:
            out = is_parent(object, query.parent, is_child)
            is_child[query] = out
            return out


def all_children(object):

    is_child = {}

    for o in bpy.data.objects:
        if (is_parent(object, o, is_child)):
            yield o

def world_bounds_children(roots):

    bpy.context.view_layer.update()

    big = 1e308
    r = [[big, -big], [big, -big], [big, -big]]

    if not isinstance(roots, Iterable):
        roots = [roots]

    for root in roots:
        for o in all_children (root):
            bbox_corners = [o.matrix_world @ Vector(corner) for corner in o.bound_box]
            for pt in bbox_corners:
                for x in range(3):
                    r[x] = [min(pt[x], r[x][0]), max(pt[x], r[x][1])]

    return r


def apply_transfrom(ob, use_location=False, use_rotation=False, use_scale=False): #https://blender.stackexchange.com/a/159540
    
    mb = ob.matrix_basis
    I = Matrix()
    loc, rot, scale = mb.decompose()

    # rotation
    T = Matrix.Translation(loc)
    #R = rot.to_matrix().to_4x4()
    R = mb.to_3x3().normalized().to_4x4()
    S = Matrix.Diagonal(scale).to_4x4()

    transform = [I, I, I]
    basis = [T, R, S]

    def swap(i):
        transform[i], basis[i] = basis[i], transform[i]

    if use_location:
        swap(0)
    if use_rotation:
        swap(1)
    if use_scale:
        swap(2)
        
    M = transform[0] @ transform[1] @ transform[2]
    if hasattr(ob.data, "transform"):
        ob.data.transform(M)
    for c in ob.children:
        c.matrix_local = M @ c.matrix_local
        
    ob.matrix_basis = basis[0] @ basis[1] @ basis[2]


# def apply_transform_to_obj (matrix, object):
#     t, r, s = shape.to_world().decompose()
#     mesh.location = t
#     mesh.rotation_quaternion = r
#     mesh.scale = s

def mat3_to_Matrix (m, point):

    mat = Matrix ( (
        (m[0][0], m[0][1], m[0][2], 0), 
        (m[1][0], m[1][1], m[1][2], 0), 
        (m[2][0], m[2][1], m[2][2], 0), 
        (0,0,0,1)
    ))

    return  Matrix.Translation(Vector(point)) @ mat


def bounds_Vector ( vs ):

    big = 1e308
    r = [[big, -big], [big, -big], [big, -big]]

    for i in vs:
        for x in range(3):
            b_pt = i[x]
            r[x] = [min(b_pt, r[x][0]), max(b_pt, r[x][1])]
    return r

def intersect_point_line(point, ls, le): # np vectors

    ld = le - ls
    pd = point - ls

    length = np.linalg.norm(ld)

    if length == 0:
        return ls

    param = np.dot(pd, ld) / length

    out = ld * param / length
    out += ls

    return out


def cleanup_last_scene(geom=None):
    objs = bpy.data.objects

    for o in objs:
        if o.name.startswith("xxx"):
            objs.remove(o, do_unlink=True)

    for img in bpy.data.images:
        if img.name.startswith("xxx"):
            bpy.data.images.remove(img, do_unlink=True)

    for m in bpy.data.materials:
        if m.name.startswith("xxx"):
            bpy.data.materials.remove(m, do_unlink=True)

    for n in bpy.data.node_groups:
        if n.name.startswith("xxx"):
            bpy.data.node_groups.remove(n, do_unlink=True)

    bpy.ops.object.select_all(action='DESELECT')
    print("starting purge...")
    bpy.ops.outliner.orphans_purge(do_recursive=True)  # "server stability"
    print("purge complete")

    if not geom:
        geom = {}
    else:
        geom.clear()

    geom['curve_info'] = {}

    return geom

def overlap (al, ah, bl, bh):
    return ah > bl and al < bh

def project_3d_point(camera: bpy.types.Object,
                     ps: [Vector],
                     render: bpy.types.RenderSettings = bpy.context.scene.render) -> [Vector]:
    """
    https://blender.stackexchange.com/a/86570

    Given a camera and its projection matrix M;
    given p, a 3d point to project:

    Compute P’ = M * P
    P’= (x’, y’, z’, w')

    Ignore z'
    Normalize in:
    x’’ = x’ / w’
    y’’ = y’ / w’

    x’’ is the screen coordinate in normalised range -1 (left) +1 (right)
    y’’ is the screen coordinate in  normalised range -1 (bottom) +1 (top)

    :param camera: The camera for which we want the projection
    :param p: The 3D point to project
    :param render: The render settings associated to the scene.
    :return: The 2D projected point in normalized range [-1, 1] (left to right, bottom to top)
    """

    if camera.type != 'CAMERA':
        raise Exception("Object {} is not a camera.".format(camera.name))

    # Get the two components to calculate M
    modelview_matrix = camera.matrix_world.inverted()
    projection_matrix = camera.calc_matrix_camera(
        bpy.context.evaluated_depsgraph_get() ,
        x = render.resolution_x,
        y = render.resolution_y,
        scale_x = render.pixel_aspect_x,
        scale_y = render.pixel_aspect_y,
    )

    # print(projection_matrix * modelview_matrix)

    out = []

    # Compute P’ = M * P
    for p in ps:

        if len(p) != 3:
            raise Exception( "Vector {} is not three-dimensional".format(p) )

        p1 = projection_matrix @ modelview_matrix @ Vector((p.x, p.y, p.z, 1))
        out.append ( Vector(((p1.x/p1.w, p1.y/p1.w))) )


    return out

def store_geometry_counts(style):

    global obj
    depsgraph = bpy.context.evaluated_depsgraph_get()

    all_verts = 0
    all_polygons = 0
    all_edges = 0
    all_objects = 0

    for obj in bpy.context.scene.objects:

        if obj.hide_render:
            continue

        all_objects += 1

        if obj.type == 'CURVE':
            me = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)
        elif obj.type == 'MESH':
            me = obj.evaluated_get(depsgraph).data

        if 'me' in locals():
            all_verts += len(me.vertices)
            all_edges += len(me.edges)
            all_polygons += len(me.polygons)

    rantom.store(f"polygon_count_{style}", all_polygons ) # these don't match blender's stats!
    rantom.store(f"edge_count_{style}"   , all_edges )
    rantom.store(f"vertex_count_{style}" , all_verts )
    rantom.store(f"object_count_{style}" , all_objects )



