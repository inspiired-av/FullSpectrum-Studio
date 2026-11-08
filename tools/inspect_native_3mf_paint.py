"""Read-only Bambu/Orca face-paint summary; no Qt or project modifications.

Usage: python tools/inspect_native_3mf_paint.py model.3mf
The reported percentages cover split-painted source triangles only. They are
surface-area percentages, NOT the proportions of filament throughout a print.
"""
from __future__ import annotations

from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

# Allow direct "python tools/script.py" execution from a repository checkout.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop.qt_app.preview_3mf_split_paint import decode_paint_regions,PaintDecodeError


def local(name):return name.rsplit('}',1)[-1]


def twice_area(triangle):
    a,b,c=triangle
    u=tuple(b[i]-a[i] for i in range(3))
    v=tuple(c[i]-a[i] for i in range(3))
    x=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    return sum(k*k for k in x)**0.5


def inspect(path):
    counts=Counter()
    split_faces=0
    display_regions=0
    paint_area=defaultdict(float)
    error_faces=0
    source_triangles=0
    with ZipFile(path) as z:
        if len(z.namelist())>700:
            raise ValueError('3MF exceeds archive member limit')
        try:
            project=z.getinfo('Metadata/project_settings.config')
        except KeyError as exc:
            raise ValueError('Not a slicer-native 3MF project') from exc
        if project.file_size>12_000_000:
            raise ValueError('Project settings exceed size limit')
        swatches=json.loads(z.read(project)).get('filament_colour',[])
        if not isinstance(swatches,list) or not 1<=len(swatches)<=256:
            raise ValueError('Invalid native filament palette')
        models=[info for info in z.infolist() if info.filename.endswith('.model')]
        for item in models:
            if item.file_size>90_000_000:
                raise ValueError('3MF model member too large')
            root=ET.fromstring(z.read(item))
            for obj in root.iter():
                if local(obj.tag)!='mesh':continue
                verts=[tuple(float(e.get(key)) for key in ('x','y','z'))
                       for elem in obj for e in elem if local(elem.tag)=='vertices'
                       and local(e.tag)=='vertex']
                for elem in obj:
                    if local(elem.tag)!='triangles':continue
                    for face in elem:
                        if local(face.tag)!='triangle':continue
                        source_triangles+=1
                        code=face.get('paint_color')
                        if not code:
                            counts['unpainted']+=1
                            continue
                        counts['painted']+=1
                        try:
                            tri=tuple(verts[int(face.get(key))] for key in ('v1','v2','v3'))
                            regions=decode_paint_regions(tri,code,len(swatches))
                            if len(regions)>1:
                                split_faces+=1
                                display_regions+=len(regions)
                                for region in regions:
                                    paint_area[region.slot]+=twice_area(region.points)
                        except (IndexError,TypeError,ValueError,PaintDecodeError):
                            error_faces+=1
    print('File:',path)
    print('Source triangles:',f'{source_triangles:,}')
    print('Native filament swatches:',len(swatches))
    print('Explicit painted source faces:',f"{counts['painted']:,}")
    print('Unpainted source faces:',f"{counts['unpainted']:,}")
    print('Split-painted source faces:',f'{split_faces:,}')
    print('Split-painted display regions:',f'{display_regions:,}')
    print('Undecodable painted source faces:',f'{error_faces:,}')
    area=sum(paint_area.values())
    if area:
        print('Split-painted surface area by filament (split faces only):')
        for slot,value in sorted(paint_area.items()):
            color=swatches[slot-1] if slot else 'inherited part color'
            print(f'  slot {slot:2}: {value/area*100:7.3f}%  {color}')
    return error_faces


if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: python tools/inspect_native_3mf_paint.py model.3mf')
    raise SystemExit(int(bool(inspect(Path(sys.argv[1])))))
