"""Windows Tkinter colored mesh preview with an actual per-pixel depth buffer.

Source display only; does not alter the 3MF's geometry or print recipes.
For standard 3MF imports, optional face tags keep exact original source colors.
"""
from __future__ import annotations

from array import array
import math
import random
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw, ImageTk
from desktop.source_color_preview import normalized_vertices

MAX_VERTICES = 650_000
MAX_FACES = 6000


def _material_colors(path):
    colors = {}
    current = None
    if not path.is_file():
        return colors
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "newmtl" and len(parts) > 1:
                current = parts[1]
            elif parts[0] == "Kd" and len(parts) >= 4 and current:
                try:
                    r, g, b = (min(255, max(0, round(float(x) * 255))) for x in parts[1:4])
                    colors[current] = (r, g, b)
                except ValueError:
                    continue
    return colors


def read_colored_obj(filename, max_faces=MAX_FACES):
    """Parse OBJ/MTL, retaining a deterministic bounded sample for the display."""
    path = Path(filename)
    vertices, faces = [], []
    count = 0
    material = (136, 152, 165)
    rng = random.Random(2105)
    materials = _material_colors(path.with_suffix(".mtl"))
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v "):
                fields = line.split()
                if len(fields) < 4:
                    continue
                if len(vertices) >= MAX_VERTICES:
                    raise ValueError("Viewport model exceeds the safe vertex limit")
                coords = tuple(float(x) for x in fields[1:4])
                if not all(math.isfinite(x) for x in coords):
                    raise ValueError("Viewport model contains non-finite coordinates")
                vertices.append(coords)
            elif line.startswith("usemtl "):
                material = materials.get(line.split()[1], (136, 152, 165))
            elif line.startswith("f "):
                fields = line.split()[1:]
                if len(fields) < 3:
                    continue
                try:
                    idx = [int(part.split("/")[0]) for part in fields]
                    idx = [i-1 if i > 0 else len(vertices)+i for i in idx]
                except ValueError:
                    continue
                if not all(0 <= i < len(vertices) for i in idx):
                    continue
                for k in range(1, len(idx)-1):
                    face = (idx[0], idx[k], idx[k+1], material, None)
                    count += 1
                    if len(faces) < max_faces:
                        faces.append(face)
                    else:
                        replacement = rng.randrange(count)
                        if replacement < max_faces:
                            faces[replacement] = face
    if not vertices or not faces:
        raise ValueError("The preview OBJ has no renderable triangles")
    return normalized_vertices(vertices, faces), faces, count


def _project(vertices, width, height, yaw, pitch, zoom):
    co, si, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    scale = max(1, min(width, height)) * 0.79 * zoom
    cx, cy = width / 2, height / 2
    result = []
    for x,y,z in vertices:
        h = x*co - y*si
        d = x*si + y*co
        result.append((cx-h*scale, cy-(z*cp-d*sp)*scale, z*sp+d*cp))
    return result


def projected_faces(vertices, faces, width, height, yaw=-1.47, pitch=0.20,
                    zoom=1.0, wireframe=False, max_draw=MAX_FACES):
    """Compatibility helper: returns depth-ordered polygons for old test callers."""
    positions = _project(vertices, width, height, yaw, pitch, zoom)
    stride = max(1, math.ceil(len(faces)/max_draw))
    polygons = []
    for face in faces[::stride]:
        a,b,c,color=face[:4]
        p,q,r = [positions[i] for i in (a,b,c)]
        depth = (p[2]+q[2]+r[2])/3
        polygons.append((depth, (p[0],p[1],q[0],q[1],r[0],r[1]),
                         "#%02x%02x%02x" % color))
    polygons.sort(key=lambda x:x[0])
    return polygons


def _shaded(color, mode, selected, protected):
    if mode == 'selected':
        return (255, 190, 40)
    if mode == 'protected':
        return (45, 230, 215)
    return tuple(max(0,min(255,int(v*0.87))) for v in color)


def render_depth_image(vertices, faces, width, height, *, yaw=-1.47,
                       pitch=0.20, zoom=1.0, wireframe=False,
                       selected_color=None, protected_colors=(),
                       max_draw=MAX_FACES):
    """Rasterize with per-pixel depth testing to prevent false triangle overlaps.

    A painter's algorithm ordered by triangle-center depth draws the back half
    of large faces over nearer geometry. This z-buffer keeps the closer face at
    each individual pixel and works even for overlapping projected triangles.
    """
    w,h = max(2,int(width)),max(2,int(height))
    canvas = Image.new("RGB",(w,h),(15,17,18))
    transformed = _project(vertices,w,h,yaw,pitch,zoom)
    if not transformed:
        return canvas
    protected = {str(c).upper() for c in protected_colors}
    selected = str(selected_color).upper() if selected_color else None
    stride = max(1,math.ceil(len(faces)/max(1,max_draw)))
    if wireframe:
        draw = ImageDraw.Draw(canvas)
        for face in faces[::stride]:
            p,q,r = [transformed[i] for i in face[:3]]
            tag = face[4] if len(face)>4 else None
            mode = "selected" if tag and tag == selected else ("protected" if tag in protected else "normal")
            color = _shaded(face[3],mode,selected,protected)
            draw.line([(p[0],p[1]),(q[0],q[1]),(r[0],r[1]),(p[0],p[1])],
                      fill=color,width=1)
        return canvas
    depths = array('f',[-float('inf')])*(w*h)
    pixels = canvas.load()
    for face in faces[::stride]:
        a,b,c,base = face[:4]
        p,q,r=transformed[a],transformed[b],transformed[c]
        x0,y0,z0=p; x1,y1,z1=q; x2,y2,z2=r
        det=(x1-x0)*(y2-y0)-(y1-y0)*(x2-x0)
        if abs(det)<1e-5:
            continue
        left=max(0,math.floor(min(x0,x1,x2))); right=min(w-1,math.ceil(max(x0,x1,x2)))
        top=max(0,math.floor(min(y0,y1,y2))); bottom=min(h-1,math.ceil(max(y0,y1,y2)))
        if left>right or top>bottom:
            continue
        tag=face[4] if len(face)>4 else None
        mode = "selected" if tag and tag == selected else ("protected" if tag in protected else "normal")
        color=_shaded(base,mode,selected,protected)
        inv=1.0/det
        for iy in range(top,bottom+1):
            yy=iy+0.5-y0
            base_idx=iy*w
            for ix in range(left,right+1):
                xx=ix+0.5-x0
                v=(xx*(y2-y0)-yy*(x2-x0))*inv
                u=((x1-x0)*yy-(y1-y0)*xx)*inv
                if u < -0.000001 or v < -0.000001 or u+v > 1.000001:
                    continue
                z=z0*(1-v-u)+z1*v+z2*u
                address=base_idx+ix
                if z>depths[address]:
                    depths[address]=z
                    pixels[ix,iy]=color
    return canvas


class MeshPreviewCanvas(tk.Canvas):
    """Orbit and zoom depth-tested colored viewport with HEX identification."""
    def __init__(self, master=None, **kwargs):
        super().__init__(master,**kwargs)
        self._vertices=[]; self._faces=[]
        self._filename=None; self._file_stamp=None
        self._drag_point=None
        self._redraw_after=None
        self._image=None
        self.yaw=-1.47; self.pitch=0.20; self.zoom=1.0
        self.wireframe=False
        self.selected_color=None
        self.protected_colors=set()
        self.bind('<ButtonPress-1>',self._press)
        self.bind('<B1-Motion>',self._move)
        self.bind('<ButtonRelease-1>',self._release)
        self.bind('<MouseWheel>',self._wheel)
        self.bind('<Button-4>',lambda e:self._zoom(1.1))
        self.bind('<Button-5>',lambda e:self._zoom(1/1.1))
        self.bind('<Configure>',lambda e:self._request_draw())

    def set_highlights(self, selected=None, protected=()):
        self.selected_color=selected
        self.protected_colors=set(protected)
        self.redraw()

    def load_source_mesh(self, vertices, faces):
        self._vertices,self._faces=vertices,faces
        self._filename=None;self._file_stamp=None
        self.wireframe=False
        self.redraw()

    def load_mesh(self, path, wireframe=False):
        filename=str(Path(path).resolve())
        source=Path(filename)
        stamp=(source.stat().st_mtime_ns,source.stat().st_size)
        if filename!=self._filename or stamp!=self._file_stamp:
            self._vertices,self._faces,_=read_colored_obj(filename)
            self._filename=filename;self._file_stamp=stamp
        self.wireframe=wireframe
        self.redraw()

    def clear_mesh(self):
        self._vertices=[];self._faces=[]
        self._filename=None;self._file_stamp=None
        self.delete('all')
        self._image=None

    def reset_camera(self):
        self.yaw,self.pitch,self.zoom=-1.47,0.20,1.0
        self.redraw()

    def _press(self,event):
        self._drag_point=(event.x,event.y)

    def _move(self,event):
        if not self._drag_point or not self._faces:return
        dx,dy=event.x-self._drag_point[0],event.y-self._drag_point[1]
        self._drag_point=(event.x,event.y)
        self.yaw+=dx*0.008
        self.pitch=max(-1.45,min(1.45,self.pitch+dy*0.008))
        self.redraw(interactive=True)

    def _release(self,event):
        self._drag_point=None
        self.redraw()

    def _zoom(self,factor):
        self.zoom=max(0.25,min(5,self.zoom*factor))
        self.redraw()

    def _wheel(self,event):
        self._zoom(1.1 if event.delta>0 else 1/1.1)

    def _request_draw(self):
        if self._redraw_after is not None:self.after_cancel(self._redraw_after)
        self._redraw_after=self.after(90,self.redraw)

    def redraw(self,interactive=False):
        self._redraw_after=None
        if not self._faces:return
        image=render_depth_image(
            self._vertices,self._faces,max(2,self.winfo_width()),max(2,self.winfo_height()),
            yaw=self.yaw,pitch=self.pitch,zoom=self.zoom,wireframe=self.wireframe,
            selected_color=self.selected_color,protected_colors=self.protected_colors,
            max_draw=1300 if interactive else MAX_FACES,
        )
        self._image=ImageTk.PhotoImage(image)
        self.delete('all')
        self.create_image(0,0,anchor='nw',image=self._image)
