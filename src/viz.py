import builtins
import math
import os
import sys

import PIL
import numpy as np
import pyglet
from pyglet.gl import *
from ctypes import pointer, sizeof
from pyglet import image

import pyglet.window.key as key
from pyglet import shapes
import numpy as np

# Zooming constants
# import utils
from pyglet.graphics import Batch
from pyglet.shapes import _ShapeGroup, _ShapeBase

ZOOM_IN_FACTOR = 1.2
ZOOM_OUT_FACTOR = 1/ZOOM_IN_FACTOR


class OutlineLine(_ShapeBase):
    def __init__(self, x, y, x2, y2, width=1, color=(255, 255, 255), batch=None, group=None):

        self._x = x
        self._y = y
        self._x2 = x2
        self._y2 = y2

        self._rotation = 0

        self._rgb = color

        self._batch = batch or Batch()
        self._group = _ShapeGroup(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, group)
        self._vertex_list = self._batch.add(2, GL_LINE_STRIP, self._group, 'v2f', 'c4B')
        self._update_position()
        self._update_color()

    def _update_position(self):

        # Adjust all coordinates by the anchor.
        anchor_x = self._anchor_x
        anchor_y = self._anchor_y
        # coords = [[x - anchor_x, y - anchor_y] for x, y in self._coordinates]

        self._vertex_list.vertices = tuple([self._x,self._y,self._x2, self._y2])

    def _update_color(self):
        self._vertex_list.colors[:] = [*self._rgb, int(self._opacity)] * 2

class Line():
    def __init__(self,x1,y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def build(self, batch):
        return OutlineLine(self.x1, self.y1, self.x2, self.y2, width=0.1, color=(50,50,50), batch = batch)

class OutlinePolygon(pyglet.shapes._ShapeBase):
    def __init__(self, *coordinates, color=(255, 255, 255), batch=None, group=None):

        # len(self._coordinates) = the number of vertices and sides in the shape.
        self._coordinates = list(coordinates)

        self._rotation = 0

        self._rgb = color

        self._batch = batch or Batch()
        self._group = _ShapeGroup(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, group)
        self._vertex_list = self._batch.add(len(self._coordinates), GL_LINE_STRIP, self._group, 'v2f', 'c4B')
        self._update_position()
        self._update_color()

    def _update_position(self):
        if not self._visible:
            self._vertex_list.vertices = tuple([0] * ((len(self._coordinates) - 2) * 6))
        else:
            # Adjust all coordinates by the anchor.
            anchor_x = self._anchor_x
            anchor_y = self._anchor_y
            coords = [[x - anchor_x, y - anchor_y] for x, y in self._coordinates]

            self._vertex_list.vertices = tuple ( value for coord in coords for value in coord )

    def _update_color(self):
        self._vertex_list.colors[:] = [*self._rgb, int(self._opacity)] * len(self._coordinates)


class Spline():

    def __init__(self, spline, res = 32):
        self.spline = np.array(spline)
        self.res = res

    def from_curve(self, curve, i):

        a = curve.bezier_points[i]
        b = curve.bezier_points[(i + 1) % curve.point_count_u]

        return np.array([[a.co[0], a.co[1], a.co[2]],
                         [a.handle_right[0], a.handle_right[1], a.handle_right[2]],
                         [b.handle_left[0], b.handle_left[1], b.handle_left[2]],
                         [b.co[0], b.co[1], b.co[2]]])

    def coord_at_t(self, ca, t0):  # https://stackoverflow.com/a/11704152

        u0 = 1 - t0
        return u0 ** 3 * ca[0] + 3 * (t0 * u0 * u0) * ca[1] + 3 * (t0 * t0 * u0) * ca[2] + t0 ** 3 * ca[3]

    def build(self, batch):

        coords = []
        for s in range (int ( len ( self.spline) / 4 ) ):
            vals = self.spline[s*4:(s+1)*4]
            for d in range (self.res + 1):
                c3 = self.coord_at_t(vals, float(d)/self.res)
                coords.append(c3[:2].tolist())

        return OutlinePolygon( *coords, color=(50,50,50), batch = batch)



class Viz(pyglet.window.Window): #https://stackoverflow.com/a/19453006/708802

    def __init__(self, width, height, scale = 100, *args, **kwargs):

        self.left = -20
        self.right = 20
        self.bottom = -20
        self.top = 20

        self.zoom_level = 1
        self.zoomed_width = 40
        self.zoomed_height = 40


        self.scale = scale

        self.batch_dirty = False
        # self.shapes = [Line(0, 0, -100, -100)]
        self.shapes = [Spline([[0,0,0],[0,10,0],[10,0,0],[10,10,0]] ), Line(1,1,1,-10) ,  Line(-10,1,-10,-10)]
        self.shape_batch = pyglet.graphics.Batch()
        self.batch_dirty = True

        conf = Config(sample_buffers=1,
                      samples=4,
                      depth_size=16,
                      double_buffer=True)

        super().__init__(width, height, config=conf,*args, **kwargs)

        pyglet.clock.schedule_interval(self.update, 1 / 30.0)
        self.on_mouse_scroll(0,0,0,0)


        # self.pic = image.load('magma.png')

    def update(self, dt):
        pass

    def init_gl(self, width, height):

        # Set clear color
        glClearColor(1.,1., 1., 1.)

        # Set antialiasing
        glEnable( GL_LINE_SMOOTH )
        glEnable( GL_POLYGON_SMOOTH )
        glHint( GL_LINE_SMOOTH_HINT, GL_NICEST )

        # Set alpha blending
        glEnable( GL_BLEND )
        glBlendFunc( GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA )

        # Set viewport
        glViewport( 0, 0, width, height )


    def on_resize(self, width, height):
        # Set window values
        self.width  = width
        self.height = height
        # Initialize OpenGL context
        self.init_gl(width, height)

    def on_key_release(self, symbol, modifiers):

        match symbol:
            case key.UP:
                print("up")

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        # Move camera

        h = dx * (self.right - self.left) / self.width
        v = dy * (self.top - self.bottom) / self.height

        self.left   -= h
        self.right  -= h
        self.bottom -= v
        self.top    -= v

    def on_mouse_scroll(self, x, y, dx, dy):
        # Get scale factor
        f = ZOOM_IN_FACTOR if dy < 0 else ZOOM_OUT_FACTOR if dy > 0 else 1
        # If zoom_level is in the proper range
        if .002 < self.zoom_level*f < 50:

            self.zoom_level *= f
            print (self.zoom_level)

            mouse_x = x/self.width
            mouse_y = y/self.height

            mouse_x_in_world = self.left   + mouse_x*self.zoomed_width
            mouse_y_in_world = self.bottom + mouse_y*self.zoomed_height

            self.zoomed_width  *= f
            self.zoomed_height *= f

            self.left   = mouse_x_in_world - mouse_x*self.zoomed_width
            self.right  = mouse_x_in_world + (1 - mouse_x)*self.zoomed_width
            self.bottom = mouse_y_in_world - mouse_y*self.zoomed_height
            self.top    = mouse_y_in_world + (1 - mouse_y)*self.zoomed_height


    def add (self, shape):
        self.batch_dirty = True
        self.shapes.append(shape)

    def lazy_update(self):


        if self.batch_dirty:
            self.pyglet_shapes = []
            self.shape_batch = pyglet.graphics.Batch()
            for s in self.shapes:
                self.pyglet_shapes.append ( s.build(self.shape_batch) )

            self.batch_dirty = False


    def on_draw(self):

        self.lazy_update()

        # Clear window with ClearColor
        glClear( GL_COLOR_BUFFER_BIT )

        # Initialize Projection matrix
        glMatrixMode( GL_PROJECTION )
        glLoadIdentity()

        # Initialize Modelview matrix
        glMatrixMode( GL_MODELVIEW )
        glLoadIdentity()
        # Save the default modelview matrix
        glPushMatrix()

        # Set orthographic projection matrix
        glOrtho( self.left, self.right, self.bottom, self.top, 1, -1 )

        # b = pyglet.graphics.Batch()
        # line = pyglet.shapes.Line(0,0,1000,1000, batch = b)
        # b.draw()

        self.shape_batch.draw()

        glPopMatrix()

    def run(self):
        pyglet.app.run()


def main():

    Viz(1500, 1500 ).run()


if __name__ == '__main__':
    # Input Directory holding npz files
    # sys.argv.append(r'npz')

    # Output Directory to save the images
    # sys.argv.append(r'npz\img')

    main()
