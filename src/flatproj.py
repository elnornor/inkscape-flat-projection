#! /usr/bin/python3
#
# flatproj.py -- apply a transformation matrix to an svg object
#
# (C) 2019 Juergen Weigert <juergen@fabmail.org>
# Distribute under GPLv2 or ask.
#
# recursivelyTraverseSvg() is originally from eggbot. Thank!
# inkscape-paths2openscad and inkscape-silhouette contain copies of recursivelyTraverseSvg()
# with almost identical features, but different inmplementation details. The version used here is derived from
# inkscape-paths2openscad.
#
# ---------------------------------------------------------------
# 2019-01-12, jw, v0.1  initial draught. Idea and an inx. No code, but a beer.
# 2019-01-12, jw, v0.2  option parser drafted. inx refined.
# 2019-01-14, jw, v0.3  creating dummy objects. scale and placing is correct.
# 2019-01-15, jw, v0.4  correct stacking of middle layer objects.
# 2019-01-16, jw, v0.5  standard and free projections done. enforce stroke-width option added.
# 2019-01-19, jw, v0.6  slightly improved zcmp(). Not yet robust.
# 2019-01-26, jw, v0.7  option autoscale done, proj_* attributes added to g.
# 2019-03-10, jw, v0.8  using ZSort from  src/zsort42.py -- code complete, needs debugging.
#                       * fixed style massaging. No regexp, but disassembly into a dict
# 2019-05-12, jw, v0.9  using zsort2d, no debugging needed, but code incomplete.
#                       * obsoleted: fix zcmp() to implement correct depth sorting of quads
#                       * obsoleted: fix zcmp() to sort edges always above their adjacent faces
#
# TODO:
#   * test: adjustment of line-width according to transformation.
#   * objects jump wildly when rotated. arrange them around their source.
# ---------------------------------------------------------------
#
# Dimetric 7,42: Rotate(Y, 69.7 deg), Rotate(X, 19.4 deg)
# Isometric:     Rotate(Y, 45 deg),   Rotate(X, degrees(atan(1/sqrt2)))    # 35.26439 deg
#

# Isometric transformation example:
# Ry = genRy(np.radians(45))
# Rx = genRx(np.radians(35.26439))
# np.matmul( np.matmul( [[0,0,-1], [1,0,0], [0,-1,0]], Ry ), Rx)
#   array([[-0.70710678,  0.40824829, -0.57735027],
#          [ 0.70710678,  0.40824829, -0.57735027],
#          [ 0.        , -0.81649658, -0.57735027]])
# R = np.matmul(Ry, Rx)
# np.matmul( [[0,0,-1], [1,0,0], [0,-1,0]], R )
#  -> same as above :-)
#
# Extend an array of xy vectors array into xyz vectors
# a = np.random.rand(5,2) * 100
#  array([[ 86.85675737,  85.44421643],
#       [ 31.11925583,  11.41818619],
#       [ 71.83803221,  63.15662683],
#       [ 45.21094383,  75.48939099],
#       [ 63.8159168 ,  49.47674044]])
#
# b = np.zeros( (a.shape[0], 3) )
# b[:,:-1] = a
# b += [0,0,33]
#  array([[ 86.85675737,  85.44421643,  33.        ],
#        [ 31.11925583,  11.41818619,  33.        ],
#        [ 71.83803221,  63.15662683,  33.        ],
#        [ 45.21094383,  75.48939099,  33.        ],
#        [ 63.8159168 ,  49.47674044,  33.        ]])
# np.matmul(b, R)


# python2 compatibility:
from __future__ import print_function

import sys, time, functools
import numpy as np            # Tav's perspective extension also uses numpy.

sys_platform = sys.platform.lower()
if sys_platform.startswith('win'):
  sys.path.append('C:\Program Files\Inkscape\share\extensions')
elif sys_platform.startswith('darwin'):
  sys.path.append('~/.config/inkscape/extensions')
else:   # Linux
  sys.path.append('/usr/share/inkscape/extensions/')


## INLINE_BLOCK_START
# for easier distribution, our Makefile can inline these imports when generating flat-projection.py from src/flatproj.py
from inksvg import InkSvg, LinearPathGen
## INLINE_BLOCK_END

import json
import inkex
import gettext

CMP_EPS = 0.000001

# python2 compatibility. Inkscape runs us with python2!
if sys.version_info.major < 3:
        def bytes(tupl):
                return "".join(map(chr, tupl))


class FlatProjection(inkex.Effect):

    # CAUTION: Keep in sync with flat-projection.inx and flat-projection_de.inx
    __version__ = '0.8'         # >= max(src/flatproj.py:__version__, src/inksvg.py:__version__)

    def __init__(self):
        """
Option parser example:

'flat-projection.py', '--id=g20151', '--tab=settings', '--rotation-type=standard_rotation', '--standard-rotation=x-90', '--manual_rotation_x=90', '--manual_rotation_y=0', '--manual_rotation_z=0', '--projection-type="standard_projection"', '--standard-projection=7,42', '--standard-projection-autoscale=true', '--trimetric-projection-x=7', '--trimetric-projection-y=42', '--depth=3.2', '--apply-depth=red_black', '--stroke_width=0.1', '--dest-layer=3d-proj', '--smoothness=0.2', '/tmp/ink_ext_XXXXXX.svgDTI8AZ']

        """
        # above example generated with inkex.errormsg(repr(sys.argv))
        #
        inkex.localize()    # does not help for localizing my *.inx file
        inkex.Effect.__init__(self)
        try:
            self.tty = open("/dev/tty", 'w')
        except:
            from os import devnull
            self.tty = open(devnull, 'w')  # '/dev/null' for POSIX, 'nul' for Windows.
        # print("FlatProjection " + self.__version__ + " inksvg "+InkSvg.__version__, file=self.tty)

        self.OptionParser.add_option(
            "--tab",  # NOTE: value is not used.
            action="store", type="string", dest="tab", default="settings",
            help="The active tab when Apply was pressed. One of settings, advanced, about")

        self.OptionParser.add_option(
            "--rotation_type", action="store", type="string", dest="rotation_type", default="standard_rotation",
            help="The active rotation type tab when Apply was pressed. Oneof standard_rotation, manual_rotation")

        self.OptionParser.add_option(
            "--projection_type", action="store", type="string", dest="projection_type", default="standard_projection",
            help="The active projection type tab when Apply was pressed. One of standard_projection, trimetric_projection")

        self.OptionParser.add_option(
            "--standard_rotation", action="store", type="string", dest="standard_rotation", default="None",
            help="one of None, x-90, x+90, y-90, y+90, y+180, z-90, z+90. Used when rotation_type=standard_rotation")


        self.OptionParser.add_option(
            "--manual_rotation_x", action="store", type="float", dest="manual_rotation_x", default=float(90.0),
            help="Rotation angle about X-Axis. Used when rotation_type=manual_rotation")

        self.OptionParser.add_option(
            "--manual_rotation_y", action="store", type="float", dest="manual_rotation_y", default=float(0.0),
            help="Rotation angle about Y-Axis. Used when rotation_type=manual_rotation")

        self.OptionParser.add_option(
            "--manual_rotation_z", action="store", type="float", dest="manual_rotation_z", default=float(0.0),
            help="Rotation angle about Z-Axis. Used when rotation_type=manual_rotation")

        self.OptionParser.add_option(
            "--standard_projection", action="store", type="string", dest="standard_projection", default="7,42",
            help="One of the DIN ISO 128-30 axonometric projections: '7,42' (dimetric left), '42,7' (dimetric right), '30,30' (isometric right) and '30,30l' (isometric left). Used when projection_type=standard_projection.")

        self.OptionParser.add_option(
            "--standard_projection_autoscale", action="store", type="inkbool", dest="standard_projection_autoscale", default=True,
            help="scale isometric and dimetric projection so that apparent lengths are original lengths. Used when projection_type=standard_projection")

        self.OptionParser.add_option(
            "--with_sides", action="store", type="inkbool", dest="with_sides", default=True,
            help="Render perimeter faces. Default: True")

        self.OptionParser.add_option(
            "--with_back", action="store", type="inkbool", dest="with_back", default=True,
            help="Render back wall. Default: True")


        self.OptionParser.add_option(
            '--trimetric_projection_y', dest='trimetric_projection_y', type='float', default=float(19.4), action='store',
            help='Manally define a projection, by first(!) rotating about the y-axis. Used when projection_type=trimetric_projection')

        self.OptionParser.add_option(
            '--trimetric_projection_x', dest='trimetric_projection_x', type='float', default=float(69.7), action='store',
            help='Manally define a projection, by second(!) rotating about the x-axis. Used when projection_type=trimetric_projection')


        self.OptionParser.add_option(
            "--depth", action="store", type="float", dest="depth", default=float(10.0),
            help="Extrusion length along the Z-axis. Applied to some, all, or none paths of the svg object, to convert it to a 3D object.")

        self.OptionParser.add_option(
            "--apply_depth", action="store", type="string", dest="apply_depth", default="red",
            help="Stroke color where depth is applied. One of red, red_black, green, green_blue, not_red, not_red_black, not_green, not_green_blue, any, none")

        self.OptionParser.add_option(
            "--stroke_width", action="store", type="string", dest="stroke_width", default='0.1',
            help="Enforce a uniform stroke-width on generated objects. Enter '=' to use the stroke-widths as computed by inksvg.py -- (sometimes wrong!)")

        self.OptionParser.add_option(
            '--dest_layer', dest='dest_layer', type='string', default='3d-proj', action='store',
            help='Place transformed objects into a specific svg document layer. Empty preserves layer.')

        self.OptionParser.add_option(
            '--smoothness', dest='smoothness', type='float', default=float(0.2), action='store',
            help='Curve smoothing (less for more [0.0001 .. 5]). Default: 0.2')


        self.OptionParser.add_option('-V', '--version',
          action = 'store_const', const=True, dest = 'version', default = False,
          help='Just print version number ("'+self.__version__+'") and exit.')


    def colorname2rgb(self, name):
        if name is None:      return None
        if name == 'none':    return False
        if name == 'any':     return True
        if name == 'red':     return [ 255, 0, 0]
        if name == 'green':   return [ 0, 255, 0]
        if name == 'blue':    return [ 0, 0, 255]
        if name == 'black':   return [ 0, 0, 0]
        if name == 'white':   return [ 255, 255, 255]
        if name == 'cyan':    return [ 0, 255, 255]
        if name == 'magenta': return [ 255, 0, 255]
        if name == 'yellow':  return [ 255, 255, 0]
        raise ValueError("unknown colorname: "+name)


    def is_extrude_color(self, svg, node, apply_color):
        """
        apply_color is one of the option values defined for the --apply_depth option
        """
        apply_color = re.split('[ _-]', apply_color.lower())
        nomatch = False
        if apply_color[0] == 'not':
          nomatch = True
          apply_color = apply_color[1:]
        for c in apply_color:
          if svg.matchStrokeColor(node, self.colorname2rgb(c)):
            return(not nomatch)
        return nomatch

    def find_selected_id(self, node):
        while node is not None:
          id = node.attrib.get('id', '')
          if id in self.selected: return id
          node = node.getparent()
        return None


    def effect(self):
        smooth = float(self.options.smoothness) # svg.smoothness to be deprecated!
        pg = LinearPathGen(smoothness=smooth)
        svg = InkSvg(document=self.document, pathgen=pg, smoothness=smooth)

        # Viewbox handling
        svg.handleViewBox()

        if self.options.version:
            # FIXME: does not work. Error: Unable to open object member file: --version
            print("Version "+self.__version__+" (inksvg "+svg.__version__+")")
            sys.exit(0)

        ## First find or create find the destination layer
        ns = { 'svg': 'http://www.w3.org/2000/svg',
               'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
               'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd' }
        dest_layer = None
        for i in self.current_layer.findall("../*[@inkscape:groupmode='layer']", ns):        # all potential layers
            print('Existing layer', i, i.attrib, file=self.tty)
            if self.options.dest_layer in (i.attrib.get('id', ''), i.attrib.get(inkex.addNS('label', 'inkscape'), ''), i.attrib.get('label', ''), i.attrib.get('name', '')):
                dest_layer = i
        if dest_layer is None:
            print('Creating dest_layer', self.options.dest_layer, file=self.tty)
            dest_layer = inkex.etree.SubElement(self.current_layer.find('..'), 'g', {
              inkex.addNS('label','inkscape'): self.options.dest_layer,
              inkex.addNS('groupmode','inkscape'): 'layer',
              'id': self.options.dest_layer })
        # print('dest_layer', dest_layer, dest_layer.attrib, file=self.tty)

        # Second traverse the document (or selected items), reducing
        # everything to line segments.  If working on a selection,
        # then determine the selection's bounding box in the process.
        # (Actually, we just need to know it's extrema on the x-axis.)

        if self.options.ids:
            # Traverse the selected objects
            for id in self.options.ids:
                transform = svg.recursivelyGetEnclosingTransform(self.selected[id])
                svg.recursivelyTraverseSvg([self.selected[id]], transform)
        else:
            # Traverse the entire document building new, transformed paths
            svg.recursivelyTraverseSvg(self.document.getroot(), svg.docTransform)


        ## First simplification: paths_tupls[]
        ## Remove the bounding boxes from paths
        ## from (<Element {http://www.w3.org/2000/svg}path at 0x7fc446a583b0>,
        ##                  [[[[207, 744], [264, 801]], [207, 264, 744, 801]], [[[207, 801], [264, 744]], [207, 264, 744, 801]], ...])
        ## to   (<Element {http://www.w3.org/2000/svg}path at 0x7fc446a583b0>,
        ##                  [[[207, 744], [264, 801]],                         [[207, 801], [264, 744]]], ... ]
        ##
        paths_tupls = []
        for tup in svg.paths:
            ll = []
            for e in tup[1]:
                ll.append(e[0])
            paths_tupls.append( (tup[0], ll, tup[2]) )          # tup[2] is a transform matrix.
        self.paths = None       # free some memory

        print("paths_tupls:\n", repr(paths_tupls), self.selected, svg.dpi, self.current_layer, file=self.tty)

        depth = self.options.depth / 25.4 * svg.dpi             # convert from mm to svg units

        proj_scale = 1.0 # autoscale value: 1.063 for dimetric, 1.22 for isometric
        proj_yx = ''     # describe the projection as a string of two floating point angles as used with trimetric projection.
        proj_rot = ''    # describe the user rotation as a string of three floating point angles.
        dest_ids = {}    # map from src_id to dest_id, so that we know if we already have one, or if we need to create one.
        dest_g = {}      # map from dest_id to (group element, suffix)
        def find_dest_g(node, dest_layer):
            """ We prepare a set of 4 groups to hold the projection of an object.
                g1 to hold the front face, g3 to hold the back face, and g2 to hold all the side walls.
                g groups g1, g2, g3
                For each selected objects a separate set of these 4 groups is created.
                xml-nodes belonging to the same selected object receive the same set.
            """
            src_id = self.find_selected_id(node)
            if src_id in dest_ids:
              return dest_g[dest_ids[src_id]]
            existing_ids = map(lambda x: x.attrib.get('id', ''), list(dest_layer))
            n = 0;
            if src_id is None:
                print("Please select one or more objects.", file=dev.stderr)
                return
            print("find_selected_id:\n", src_id, node, file=self.tty)
            id = src_id+'_'+str(n)
            while id in existing_ids:
              n = n+1
              id = src_id+'_'+str(n)
            dest_ids[src_id] = id
            src_path = self.current_layer.attrib.get('id','')+'/'+src_id
            g = inkex.etree.SubElement(dest_layer, 'g', { 'id': id, 'proj_src': src_path, 'proj_depth': str(self.options.depth),
              'proj_apply_depth': self.options.apply_depth, 'proj_smoothness': str(self.options.smoothness),
              'proj_yx': proj_yx, 'proj_rot': proj_rot, 'proj_scale': str(proj_scale) })
            # created in reverse order, so that g1 sits on top of the visibility stack
            g3 = inkex.etree.SubElement(g, 'g', { 'id': id+'_3', 'src': src_path })
            g2 = inkex.etree.SubElement(g, 'g', { 'id': id+'_2', 'src': src_path })
            g1 = inkex.etree.SubElement(g, 'g', { 'id': id+'_1', 'src': src_path })
            dest_g[id] = ( g1, g2, g3, '_'+str(n)+'_' )
            return dest_g[id]

        def cmp_f(a, b):
          " comparing floating point is hideous. "
          d = a - b
          if d > CMP_EPS: return 1
          if d < -CMP_EPS: return -1
          return 0

        def points_to_svgd(p, scale=1.0):
          " convert list of points into a closed SVG path list"
          f = p[0]
          p = p[1:]
          closed = False
          if cmp_f(p[-1][0], f[0]) == 0 and cmp_f(p[-1][1], f[1]) == 0:
            p = p[:-1]
            closed = True
          svgd = 'M%.6f,%.6f' % (f[0]*scale, f[1]*scale)
          for x in p:
            svgd += 'L%.6f,%.6f' % (x[0]*scale, x[1]*scale)
          if closed:
            svgd += 'z'
          return svgd

        def paths_to_svgd(paths, scale=1.0):
          " multiple disconnected lists of points can exist in one svg path"
          d = ''
          for p in paths:
            d += points_to_svgd(p, scale) + ' '
          return d[:-1]

        # from fablabnbg/inkscape-paths2openscad
        def getPathStyle(node):
          style = node.get('style', '')
          ret = {}
          # fill:none;fill-rule:evenodd;stroke:#000000;stroke-width:10;stroke-linecap:butt;stroke-linejoin:miter;stroke-miterlimit:4;stroke-dasharray:none;stroke-opacity:1
          for elem in style.split(';'):
            if len(elem):
                try:
                    (key, val) = elem.strip().split(':')
                except:
                    print >> sys.stderr, "unparsable element '{1}' in style '{0}'".format(elem, style)
                ret[key] = val
          return ret

        def fmtPathStyle(sty):
          "Takes a dict generated by getPathStyle() and formats a string that can be fed to getPathStyle()."
          s = ''
          for key in sty: s += str(key)+':'+str(sty[key])+';'
          return s.rstrip(';')

        # shapes from http://mathworld.wolfram.com/RotationMatrix.html
        # (this disagrees with https://en.wikipedia.org/wiki/Rotation_matrix#Basic_rotations, though)
        def genRx(theta):
          "A rotation matrix about the X axis. Example: Rx = genRx(np.radians(30))"
          c, s = np.cos(theta), np.sin(theta)
          return np.array( ((1, 0, 0), (0, c, s), (0, -s, c)) )

        def genRy(theta):
          "A rotation matrix about the Y axis. Example: Ry = genRy(np.radians(30))"
          c, s = np.cos(theta), np.sin(theta)
          return np.array( ((c, 0, -s), (0, 1, 0), (s, 0, c)) )

        def genRz(theta):
          "A rotation matrix about the Z axis. Example: Rz = genRz(np.radians(30))"
          c, s = np.cos(theta), np.sin(theta)
          return np.array( ((c, s, 0), (-s, c, 0), (0, 0, 1)) )

        def genRz2D(theta):
          "A 2D rotation matrix about the Z axis. Example: Rz2D = genRz2D(np.radians(30))"
          c, s = np.cos(theta), np.sin(theta)
          return np.array( ((c, s), (-s, c)) )

        def genSc(s):
          "A uniform scale matrix in xyz"
          return np.array( ((s, 0, 0), (0, s, 0), (0, 0, s)) )

        def scaleFromM(transform):
          "Extract scale from a 2D transformation matrix"
          if type(transform[0]) == type([]):
            a = transform[0][0]
            b = transform[1][0]
            c = transform[0][1]
            d = transform[1][1]
          else:
            a = transform[0]
            b = transform[1]
            c = transform[2]
            d = transform[3]
          delta = a * d - b * c
          r = np.sqrt(a*a + b*b)
          if r > CMP_EPS:
            return (r, delta/r)
          else:
            s = np.sqrt(c*c + d*d)
            if s > CMP_EPS:
              return (delta/s, s)
          return (1, 1)


        def avgScaleFromM(transform):
          sx, sy = scaleFromM(transform)
          return 0.5 * (abs(sx)+abs(sy))


        def phi2D(R):
          """
          Given a 3D rotation matrix R, we compute the angle phi projected in the
          x-y plane of point 0,0,1 relative to the negative Y axis.
          """
          (x2d_vec, y2d_vec, dummy) = np.matmul( [0,0,-1], R )
          if abs(x2d_vec) < CMP_EPS:
            if abs(y2d_vec) < CMP_EPS: return 0.0
            phi = 0.5*np.pi
            if y2d_vec < 0:
              phi = -0.5*np.pi
            else:
              phi = 0.5*np.pi
          else:
            phi = np.arctan(y2d_vec/x2d_vec)
          if x2d_vec < 0:       # adjustment for quadrant II and III
            phi += np.pi
          elif y2d_vec < 0:     # adjustment for quadrant IV
            phi += 2*np.pi
          phi += 0.5*np.pi      # adjustment for starting with 0 deg at neg Y-axis.
          if phi >= 2*np.pi:
            phi -= 2*np.pi      # adjustment to remain within 0..359.9999 deg
          return phi


        # user rotation
        uR = genRx(np.radians(0.0))
        if self.options.rotation_type.strip(" '\"") == 'standard_rotation':
          if   self.options.standard_rotation == 'x+90':
            uR = genRx(np.radians(90.))
            proj_rot = '90,0,0'
          elif self.options.standard_rotation == 'x-90':
            uR = genRx(np.radians(-90.))
            proj_rot = '-90,0,0'
          elif self.options.standard_rotation == 'y+90':
            uR = genRy(np.radians(90.))
            proj_rot = '0,90,0'
          elif self.options.standard_rotation == 'y+180':
            uR = genRy(np.radians(180.))
            proj_rot = '0,180,0'
          elif self.options.standard_rotation == 'y-90':
            uR = genRy(np.radians(-90.))
            proj_rot = '0,-90,0'
          elif self.options.standard_rotation == 'z+90':
            uR = genRz(np.radians(90.))
            proj_rot = '0,0,90'
          elif self.options.standard_rotation == 'z-90':
            uR = genRz(np.radians(-90.))
            proj_rot = '0,0,-90'
          elif self.options.standard_rotation == 'none':
            pass
          else:
            inkex.errormsg("unknown standard_rotation="+self.options.standard_rotation+" -- use one of x+90, x-90, y+90, y-90, y+180, z+90, or z-90")
            sys.exit(1)
        else:
          Rx = genRx(np.radians(float(self.options.manual_rotation_x)))
          Ry = genRx(np.radians(float(self.options.manual_rotation_y)))
          Rz = genRx(np.radians(float(self.options.manual_rotation_z)))
          uR = np.matmul(Rx, np.matmul(Ry, Rz))
          proj_rot = self.options.manual_rotation_x+','+self.options.manual_rotation_y+','+self.options.manual_rotation_z

        # default: dimetric 7,42
        Ry = genRy(np.radians(90-69.7))
        Rx = genRx(np.radians(19.4))
        if self.options.standard_projection_autoscale: proj_scale = 1.0604
        proj_yx = '20.3,19.4'
        # Argh. Quotes are included here!
        if self.options.projection_type.strip(" '\"") == 'standard_projection':
            if   self.options.standard_projection in ('7,42', '7,41'):
                pass    # default above.
            elif self.options.standard_projection in ('42,7', '41,7'):
                Ry = genRy(np.radians(69.7-90))
                Rx = genRx(np.radians(19.4))
                proj_yx = '-20.3,19.4'
            elif self.options.standard_projection == '30,30':
                Ry = genRy(np.radians(45.0))
                Rx = genRx(np.radians(35.26439))
                if self.options.standard_projection_autoscale: proj_scale = 1.22
                proj_yx = '45,35.26439'
            elif self.options.standard_projection == '30,30l':
                Ry = genRy(np.radians(-45.0))
                Rx = genRx(np.radians(35.26439))
                if self.options.standard_projection_autoscale: proj_scale = 1.22
                proj_yx = '45,35.26439'
            else:
                inkex.errormsg("unknown standard_projection="+self.options.standard_projection+" -- use one of '7,42'; '42,7'; '30,30', or '30,30l'")
                sys.exit(1)
        else:
            # inkex.errormsg("free proj")
            Ry = genRy(np.radians(float(self.options.trimetric_projection_y)))
            Rx = genRx(np.radians(float(self.options.trimetric_projection_x)))
            proj_yx = self.options.trimetric_projection_y+','+self.options.trimetric_projection_x
            proj_scale = 1.0

        R = np.matmul(genSc(proj_scale), np.matmul(uR, np.matmul(Ry, Rx)))
        Rz2D = genRz2D(phi2D(R))

        missing_id = int(10000*time.time())     # use a timestamp, in case there are objects without id.
        v = np.matmul([[0,0,depth]], R)         # test in which way depth points
        if v[0][2] < 0.0:
            backview = True
        else:
            backview = False

        paths3d_2 = []                         # side: visible edges and faces
        for tupl in paths_tupls:
            (elem, paths, transform) = tupl
            (g1, g2, g3, suf) = find_dest_g(elem, dest_layer)
            if backview:
                g1,g3 = g3,g1
            path_id = elem.attrib.get('id', '')+suf
            style_d = getPathStyle(elem)
            # print("stroke-width", style_d['stroke-width'], transform, file=self.tty)
            strokew = self.options.stroke_width.strip(' =')
            if strokew != '':
                strokew = strokew.replace(',', '.')
                sc = avgScaleFromM(transform)   # FIXME: is this scaling correct here?
                style_d["stroke-width"] = str(float(strokew) * sc)
            style_d_nostroke = style_d.copy()
            style_d_nostroke['stroke'] = 'none'
            style = fmtPathStyle(style_d)
            style_nostroke = fmtPathStyle(style_d_nostroke)

            if path_id == suf:
              path_id = 'pathx'+str(missing_id)+suf
              missing_id += 1
            paths3d_1 = []
            paths3d_3 = []
            extrude = self.is_extrude_color(svg, elem, self.options.apply_depth)
            for path in paths:
              # Extend an array of xy vectors (path) into into xyz vectors with all z==0 (path3d_1)
              p3d_1 = np.zeros( (len(path), 3) )
              p3d_1[:,:-1] = path       # magic numpy slicing ..
              # paths3d_1 is the front face: rotate p3d_1 into 3D space according to R
              paths3d_1.append(np.matmul(p3d_1, R))
              if extrude:
                # paths3d_3 is the back face: translate p3d_1 along z-axis then rotate into 3D space according to R
                p3d_1 += [0, 0, depth]
                paths3d_3.append(np.matmul(p3d_1, R))

                # paths3d_2 holds all permimeter faces: beware of z-sort dragons.
                ##########################
                if self.options.with_sides:
                  for i in range(0, len(paths3d_1[-1])-1):
                    a, b = paths3d_1[-1][i],   paths3d_3[-1][i]
                    c, d = paths3d_1[-1][i+1], paths3d_3[-1][i+1]
                    paths3d_2.append({
                      'edge_style': style, 
                      'edge_data': [[a, b], [c, d]],
                      'edge_visible': [1, 1],
                      'style': style_nostroke, 
                      'data': [a,b,d,c,a]})

            if extrude and self.options.with_back:
                # populate back face with selected colors only
                inkex.etree.SubElement(g3, 'path', { 'id': path_id+'3', 'style': style, 'd': paths_to_svgd(paths3d_3, 25.4/svg.dpi) })
            # populate front face with all colors
            inkex.etree.SubElement(g1, 'path', { 'id': path_id+'1', 'style': style, 'd': paths_to_svgd(paths3d_1, 25.4/svg.dpi) })

        if self.options.with_sides:
          for path in paths3d_2:
            if path['edge_visible'][0]:
              inkex.etree.SubElement(g2, 'path', { 'id': 'path_e1_id'+str(missing_id), 'style': path['edge_style'], 'd': paths_to_svgd([path['edge_data'][0]], 25.4/svg.dpi) })
            if path['edge_visible'][1]:
              inkex.etree.SubElement(g2, 'path', { 'id': 'path_e2_id'+str(missing_id), 'style': path['edge_style'], 'd': paths_to_svgd([path['edge_data'][1]], 25.4/svg.dpi) })
            inkex.etree.SubElement(g2,   'path', { 'id': 'path_e_id'+str(missing_id),  'style': path['style'],      'd': paths_to_svgd([path['data']], 25.4/svg.dpi) })
            missing_id += 1


if __name__ == '__main__':
    e = FlatProjection()
    e.affect()
