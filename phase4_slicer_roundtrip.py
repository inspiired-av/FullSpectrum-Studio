#!/usr/bin/env python3
"""Phase 4: read-only native 3MF / Bambu Studio / OrcaSlicer integrity checks.

No printer operation, slicing, or source mutation. Python standard library only.
Usage:
  python phase4_slicer_roundtrip.py templates 'C:/path/to/templates'
  python phase4_slicer_roundtrip.py audit 'C:/path/to/output.3mf'
  python phase4_slicer_roundtrip.py compare 'C:/path/to/before.3mf' 'C:/path/to/saved-by-slicer.3mf'

Exit: 0 = pass (possibly with warnings), 1 = integrity errors, 2 = input/tool error.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET

MAX_JSON = 12_000_000
MAX_XML = 90_000_000
MAX_MEMBERS = 350
MAX_TRIANGLES = 3_000_000
HEX = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
SLOT_FIELDS = ("filament_colour", "filament_is_mixed", "filament_mixed_components",
               "filament_mixed_sublayer_ratios", "filament_settings_id", "filament_ids",
               "filament_multi_colour", "filament_colour_type", "default_filament_colour")
MATERIAL_PROFILE_FIELDS = ("filament_flow_ratio", "filament_max_volumetric_speed",
                           "filament_nozzle_temperature", "filament_nozzle_temperature_range_low",
                           "filament_nozzle_temperature_range_high", "filament_vendor",
                           "filament_type", "filament_density", "filament_pressure_advance")

class InputError(ValueError):
    pass


def local(tag):
    return tag.rsplit('}', 1)[-1]


def _zip_file(path):
    path = Path(path)
    if not path.is_file():
        raise InputError('File not found: ' + str(path))
    try:
        z = ZipFile(path, 'r')
    except BadZipFile as exc:
        raise InputError('Not a readable 3MF ZIP: ' + str(path)) from exc
    if len(z.infolist()) > MAX_MEMBERS:
        z.close()
        raise InputError('3MF has too many archive entries')
    seen = set()
    for item in z.infolist():
        key = item.filename.replace('\\', '/').lower()
        if key in seen or key.startswith('/') or '..' in key.split('/'):
            z.close()
            raise InputError('Unsafe or duplicated archive entry: ' + item.filename)
        seen.add(key)
    return z


def _read(z, name, limit):
    try:
        info = z.getinfo(name)
    except KeyError as exc:
        raise InputError('Missing native 3MF member: ' + name) from exc
    if info.file_size > limit:
        raise InputError('Excessively large 3MF member: ' + name)
    return z.read(info)


def _xml(z, path):
    try:
        return ET.fromstring(_read(z, path, MAX_XML))
    except ET.ParseError as exc:
        raise InputError('Invalid 3MF XML in ' + path) from exc


def _config(z):
    try:
        cfg = json.loads(_read(z, 'Metadata/project_settings.config', MAX_JSON))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError('Invalid native project_settings.config') from exc
    if not isinstance(cfg, dict):
        raise InputError('Native settings are not a JSON object')
    return cfg


def _metadata(root):
    return {x.get('name'): (x.text or '') for x in root if local(x.tag) == 'metadata'}


def version_of(z):
    root = _xml(z, '3D/3dmodel.model')
    meta = _metadata(root)
    app = meta.get('Application', '')
    if meta.get('OrcaSlicer'):
        return 'OrcaSlicer', meta['OrcaSlicer']
    if app.startswith('BambuStudio-'):
        return 'Bambu Studio', app.removeprefix('BambuStudio-')
    return 'Unidentified', app or '?'


def _mesh_data(z):
    names = [x for x in z.namelist() if x.startswith('3D/Objects/') and x.endswith('.model')]
    if not names:  # Some slicers store the mesh in the main model instead.
        names = ['3D/3dmodel.model']
    totals = Counter()
    vertex_total = 0
    tri_total = 0
    color_counts = Counter()
    examples = []
    for name in names:
        root = _xml(z, name)
        for mesh in (x for x in root.iter() if local(x.tag) == 'mesh'):
            verts = [tuple(float(x.get(k)) for k in ('x','y','z'))
                     for x in mesh.iter() if local(x.tag) == 'vertex']
            tris = [x for x in mesh.iter() if local(x.tag) == 'triangle']
            vertex_total += len(verts)
            tri_total += len(tris)
            if tri_total > MAX_TRIANGLES:
                raise InputError('Mesh exceeds the comparison triangle limit')
            for triangle in tris:
                try:
                    a,b,c = (verts[int(triangle.get(k))] for k in ('v1','v2','v3'))
                except (ValueError, TypeError, IndexError) as exc:
                    raise InputError('Invalid mesh vertex index in ' + name) from exc
                if any(not math.isfinite(x) for v in (a,b,c) for x in v):
                    raise InputError('Non-finite vertex coordinates')
                # Translation/rotation invariant triangle signature, tolerant of
                # ~0.01 mm edge rounding when a slicer recenters the mesh.
                edges = tuple(sorted(round(sum((u[i]-v[i])**2 for i in range(3)), 2)
                                     for u,v in ((a,b),(b,c),(c,a))))
                paint = triangle.get('paint_color', '').upper().lstrip('0') or '0'
                totals[(edges,paint)] += 1
                color_counts[paint] += 1
    return {'vertices':vertex_total,'triangles':tri_total, 'triangles_by_shape_and_paint':totals,
            'paint_counts':color_counts}


def _validate_config(cfg):
    problems=[]
    colors=cfg.get('filament_colour')
    if not isinstance(colors,list) or not 1<=len(colors)<=32:
        raise InputError('Missing or invalid 1–32 filament_colour array')
    n=len(colors)
    for i,c in enumerate(colors,1):
        if not isinstance(c,str) or not HEX.fullmatch(c):
            problems.append(f'Slot {i}: invalid color {c!r}')
    for key in SLOT_FIELDS:
        x=cfg.get(key)
        if x is not None and (not isinstance(x,list) or len(x)!=n):
            problems.append(f'{key}: expected {n} values, found {len(x) if isinstance(x,list) else "non-list"}')
    mixed=cfg.get('filament_is_mixed')
    if not isinstance(mixed,list) or len(mixed)!=n:
        problems.append('filament_is_mixed missing/inconsistent')
        return n,0,problems
    physical=sum(str(x)!='1' for x in mixed)
    if not 1<=physical<=n:
        problems.append('No physical filament slots')
    if any(str(x)=='1' for x in mixed[:physical]) or any(str(x)!='1' for x in mixed[physical:]):
        problems.append('Physical and mixed slots are not contiguous')
    components=cfg.get('filament_mixed_components',[])
    ratios=cfg.get('filament_mixed_sublayer_ratios',[])
    if len(components)==n and len(ratios)==n:
        for i in range(physical,n):
            try:
                cc=[int(x.strip()) for x in components[i].split(',')]
                rr=[float(x.strip()) for x in ratios[i].split(',')]
            except (ValueError,TypeError,AttributeError) as exc:
                problems.append(f'Mixed slot {i+1}: invalid recipe tokens')
                continue
            if not cc or len(cc)!=len(rr) or any(c<1 or c>physical for c in cc):
                problems.append(f'Mixed slot {i+1}: invalid physical-component references')
            if any(not math.isfinite(r) or r<0 or r>1 for r in rr) or abs(sum(rr)-1)>0.02:
                problems.append(f'Mixed slot {i+1}: ratios do not sum to 1')
    return n,physical,problems


def snapshot(path):
    with _zip_file(path) as z:
        cfg=_config(z)
        n,p,problems=_validate_config(cfg)
        slicer, version=version_of(z)
        mesh=_mesh_data(z)
        if mesh['triangles'] == 0:
            problems.append('No printable triangles found (blank project or unsupported mesh location)')
    return {'file':str(path), 'config':cfg,'slots':n,'physical':p,'slicer':slicer,
            'version':version,'mesh':mesh,'errors':problems}


def template_details(path):
    with _zip_file(path) as z:
        cfg = _config(z)
        slicer,version=version_of(z)
        model=_xml(z,'3D/3dmodel.model')
        resources=next((x for x in model if local(x.tag)=='resources'),None)
        build=next((x for x in model if local(x.tag)=='build'),None)
        blank=resources is not None and build is not None and not list(resources) and not list(build)
        required=['Metadata/model_settings.config','Metadata/slice_info.config']
        missing=[k for k in required if k not in z.namelist()]
        return {'name':Path(path).name,'slicer':slicer,'version':version,
                'printer':cfg.get('printer_model') or cfg.get('printer_settings_id','?'),
                'nozzle':str(cfg.get('printer_variant','?')),
                'process':cfg.get('print_settings_id','?'), 'slots':len(cfg.get('filament_colour',[])),
                'blank':bool(blank), 'issues':missing}


def check_roundtrip(before, after):
    a,b=snapshot(before),snapshot(after)
    errors=list(a['errors'])+[f'Saved: {x}' for x in b['errors']]
    warnings=[]
    if a['physical']!=b['physical'] or a['slots']!=b['slots']:
        errors.append(f'Filament slot count changed: {a["physical"]}+{a["slots"]-a["physical"]} -> {b["physical"]}+{b["slots"]-b["physical"]}')
    for key in ('printer_model','printer_variant'):
        if str(a['config'].get(key,''))!=str(b['config'].get(key,'')):
            errors.append(f'{key} changed: {a["config"].get(key)!r} -> {b["config"].get(key)!r}')
    for key in ('printer_settings_id','print_settings_id'):
        if a['config'].get(key)!=b['config'].get(key):
            warnings.append(f'{key} changed during slicer save')
    for key in ('filament_colour','filament_is_mixed', 'filament_mixed_components',
                'filament_mixed_sublayer_ratios'):
        v1=a['config'].get(key);v2=b['config'].get(key)
        if v1!=v2:
            if key=='filament_colour' and isinstance(v1,list) and isinstance(v2,list):
                same = len(v1)==len(v2) and all(str(c).upper()==str(d).upper() for c,d in zip(v1,v2))
            elif key=='filament_mixed_sublayer_ratios' and isinstance(v1,list) and isinstance(v2,list) and len(v1)==len(v2):
                def parse(v):
                    try:return tuple(round(float(x),4) for x in v.split(','))
                    except (AttributeError,ValueError):return v
                same=all(parse(x)==parse(y) for x,y in zip(v1,v2))
            else:
                same=False
            if not same:
                errors.append(f'Filament palette changed: {key}')
    if a['mesh']['triangles']!=b['mesh']['triangles']:
        errors.append(f'Mesh triangle count changed: {a["mesh"]["triangles"]} -> {b["mesh"]["triangles"]}')
    if a['mesh']['triangles_by_shape_and_paint']!=b['mesh']['triangles_by_shape_and_paint']:
        ca=a['mesh']['triangles_by_shape_and_paint'];cb=b['mesh']['triangles_by_shape_and_paint']
        errors.append(f'Mesh shape or paint assignments changed: {sum((ca-cb).values())} missing and {sum((cb-ca).values())} added triangle signatures')
    for key in ('filament_settings_id','filament_ids'):
        a_val=a['config'].get(key,[])[:a['physical']]
        b_val=b['config'].get(key,[])[:b['physical']]
        if a_val!=b_val:
            warnings.append(f'Physical preset identity changed: {key} (check intentional slicer normalization)')
    changed_material=[key for key in MATERIAL_PROFILE_FIELDS
                      if a['config'].get(key)!=b['config'].get(key)]
    if changed_material:
        warnings.append(f'{len(changed_material)} material parameter field(s) changed: '+', '.join(changed_material))
    if a['slicer']!=b['slicer']:
        warnings.append(f'Cross-slicer save: {a["slicer"]} -> {b["slicer"]}; slicer-specific metadata may be normalized')
    return {'before':a,'after':b,'errors':errors,'warnings':warnings}


def format_catalog(paths):
    lines=['Phase 4 — Native Slicer Template Matrix','',
           '| Template | Slicer | Version | Printer | Nozzle (mm) | Empty |',
           '| --- | --- | --- | --- | --- | --- |']
    rows=[]
    for p in paths:
        try:
            x=template_details(p)
            rows.append(x)
            safe=lambda v:str(v).replace('|','/')
            lines.append('| '+ ' | '.join(safe(x[k]) for k in ('name','slicer','version','printer','nozzle','blank'))+' |')
        except (InputError,BadZipFile,OSError,UnicodeError) as exc:
            lines.append(f'| {Path(p).name} | ERROR | {exc} | | | |')
    lines.append('')
    for x in rows:
        if not x['blank']:
            lines.append(f'- Warning: {x["name"]} is not an empty project template.')
        if x['issues']:
            lines.append(f'- Warning: {x["name"]} is missing metadata: {", ".join(x["issues"])}')
        if x['slicer']=='OrcaSlicer' and x['printer'].lower().find('h2c')>=0 and not x['version'].startswith('2.5'):
            lines.append(f'- Warning: {x["name"]} uses an OrcaSlicer version not identified as H2C-capable.')
    bambu={x['printer'].lower():x for x in rows if x['slicer']=='Bambu Studio'}
    for x in rows:
        if x['slicer']=='OrcaSlicer' and x['printer'].lower() in bambu:
            ref=bambu[x['printer'].lower()]
            if x['nozzle']!=ref['nozzle']:
                lines.append(f'- **Nozzle mismatch:** {x["printer"]} has Bambu Studio {ref["nozzle"]} mm and OrcaSlicer {x["nozzle"]} mm templates; compare with matching-nozzle exports.')
    return '\n'.join(lines)+'\n'


def format_audit(s):
    return '\n'.join([
        'Phase 4 — Native Project Audit','',f'File: {Path(s["file"]).name}',
        f'Slicer: {s["slicer"]} {s["version"]}',
        f'Printer: {s["config"].get("printer_model","?")} / {s["config"].get("printer_variant","?")} mm',
        f'Slots: {s["physical"]} physical + {s["slots"]-s["physical"]} mixed = {s["slots"]}',
        f'Geometry: {s["mesh"]["vertices"]} vertices, {s["mesh"]["triangles"]} triangles',
        f'Paint states: {len(s["mesh"]["paint_counts"])} unique serialized paint codes',
        'Integrity: ' + ('FAIL' if s['errors'] else 'PASS'),
        *('  ERROR: '+p for p in s['errors']),
    ])+'\n'


def format_comparison(r):
    a,b=r['before'],r['after']
    lines=['Phase 4 — Slicer Save/Reopen Integrity','',
           f'Before: {Path(a["file"]).name} ({a["slicer"]} {a["version"]})',
           f'After:  {Path(b["file"]).name} ({b["slicer"]} {b["version"]})',
           f'Filament slots: {a["physical"]}+{a["slots"]-a["physical"]} -> {b["physical"]}+{b["slots"]-b["physical"]}',
           f'Mesh triangles: {a["mesh"]["triangles"]} -> {b["mesh"]["triangles"]}',
           'Integrity: '+('FAIL' if r['errors'] else 'PASS'),
           *('  ERROR: '+e for e in r['errors']),
           *('  NOTICE: '+w for w in r['warnings'])]
    return '\n'.join(lines)+'\n'


def cli(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    cmd=parser.add_subparsers(dest='command',required=True)
    tp=cmd.add_parser('templates', help='Summarize empty native project templates')
    tp.add_argument('paths',nargs='+',help='Native 3MF files or directories')
    ap=cmd.add_parser('audit',help='Validate native output before slicer save')
    ap.add_argument('file')
    cp=cmd.add_parser('compare',help='Compare a generated file with slicer-resaved file')
    cp.add_argument('before');cp.add_argument('after')
    for p in (tp,ap,cp):
        p.add_argument('--report',help='Write optional Markdown/text report to this path')
    args=parser.parse_args(argv)
    try:
        if args.command=='templates':
            paths=[]
            for item in args.paths:
                p=Path(item)
                if p.is_dir(): paths.extend(sorted(p.glob('*.3mf')))
                else: paths.append(p)
            if not paths: raise InputError('No .3mf files found')
            report=format_catalog(paths);result=0
        elif args.command=='audit':
            snap=snapshot(args.file);report=format_audit(snap);result=1 if snap['errors'] else 0
        else:
            r=check_roundtrip(args.before,args.after)
            report=format_comparison(r);result=1 if r['errors'] else 0
    except (InputError,OSError,UnicodeError,BadZipFile) as exc:
        print('Cannot audit 3MF: '+str(exc),file=sys.stderr)
        return 2
    if args.report:
        Path(args.report).write_text(report,encoding='utf-8')
    print(report,end='')
    return result

if __name__=='__main__':
    raise SystemExit(cli())
