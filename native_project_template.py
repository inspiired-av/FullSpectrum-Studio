"""Build a slicer-native 3MF from a FullSpectrum-painted 3MF and a blank slicer project.

No arbitrary template files are executed, and the template is never overwritten.
This module deliberately supports the single-mesh output of the standard-colored-3MF
importer; existing complete native projects need no template.
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile
import xml.etree.ElementTree as ET

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
MAX_UNCOMPRESSED = 1_000_000_000
MAX_ENTRIES = 1500
MAX_FILAMENTS = 32
HEX = re.compile(r"#[0-9a-fA-F]{6}$")


class TemplateError(ValueError):
    """A template cannot safely supply a native slicer project."""


def _xml(data, member):
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise TemplateError(f"Malformed XML in {member}: {exc}") from exc


def _safe_archive(archive):
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
        raise TemplateError("3MF exceeds the safe archive limits")
    seen = set()
    for info in infos:
        name = info.filename.replace('\\', '/')
        if name.startswith('/') or name.startswith('../') or '/..' in name or re.match(r'^[A-Za-z]:', name):
            raise TemplateError("Unsafe archive member: " + info.filename)
        if name.lower() in seen:
            raise TemplateError("Duplicate archive member: " + info.filename)
        seen.add(name.lower())


def inspect_template(path):
    """Return identifying data for a slicer-saved, EMPTY project."""
    path = Path(path).expanduser().resolve()
    try:
        with ZipFile(path) as z:
            _safe_archive(z)
            needed = {
                '3D/3dmodel.model', 'Metadata/project_settings.config',
                'Metadata/model_settings.config', 'Metadata/slice_info.config',
                '[Content_Types].xml', '_rels/.rels',
            }
            if missing := needed.difference(z.namelist()):
                raise TemplateError('Not a native slicer project; missing ' + ', '.join(sorted(missing)))
            main = _xml(z.read('3D/3dmodel.model'), '3D/3dmodel.model')
            if main.tag != f'{{{CORE}}}model':
                raise TemplateError('Unexpected main 3MF model namespace')
            resources = main.find(f'{{{CORE}}}resources')
            build = main.find(f'{{{CORE}}}build')
            if resources is None or build is None:
                raise TemplateError('Template has no 3MF resources/build sections')
            if list(resources) or list(build):
                raise TemplateError('Template is not empty. Remove models and save a blank slicer project.')
            settings = json.loads(z.read('Metadata/project_settings.config'))
            if not isinstance(settings, dict) or not settings.get('printer_settings_id'):
                raise TemplateError('Template is missing a saved printer profile')
            colors = settings.get('filament_colour')
            if not isinstance(colors, list) or not (1 <= len(colors) <= MAX_FILAMENTS):
                raise TemplateError('Template filament definitions are missing or invalid')
            if any(not isinstance(x, str) or not HEX.fullmatch(x) for x in colors):
                raise TemplateError('Template has an invalid filament color')
            _xml(z.read('Metadata/model_settings.config'), 'Metadata/model_settings.config')
            _xml(z.read('Metadata/slice_info.config'), 'Metadata/slice_info.config')
            _xml(z.read('[Content_Types].xml'), '[Content_Types].xml')
            rels = _xml(z.read('_rels/.rels'), '_rels/.rels')
            if not any(x.get('Target') == '/3D/3dmodel.model' for x in rels):
                raise TemplateError('Template is missing its native model relationship')
            metadata = {el.get('name'): el.text for el in main.findall(f'{{{CORE}}}metadata')}
            app = metadata.get('Application', '') or ''
            orca = metadata.get('OrcaSlicer')
            if not app.startswith('BambuStudio-'):
                raise TemplateError('Template does not have a Bambu/Orca slicer project marker')
            return {
                'path': str(path), 'printer': settings.get('printer_model') or settings['printer_settings_id'],
                'printerPreset': settings['printer_settings_id'],
                'processPreset': settings.get('print_settings_id', ''),
                'nozzle': settings.get('printer_variant', ''),
                'slicer': 'OrcaSlicer' if orca else 'Bambu Studio',
                'slicerVersion': orca or app.removeprefix('BambuStudio-'),
                'filamentCount': len(colors),
            }
    except (BadZipFile, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TemplateError(f'Could not read native project template: {exc}') from exc


def _bbox_model(xml_bytes):
    bounds_min = [float('inf')]*3
    bounds_max = [float('-inf')]*3
    nvertices = 0
    ntriangles = 0
    for _, node in ET.iterparse(io.BytesIO(xml_bytes), events=('end',)):
        name = node.tag.rsplit('}', 1)[-1]
        if name == 'vertex':
            xyz = [float(node.get(k)) for k in ('x','y','z')]
            if any(not math.isfinite(x) for x in xyz):
                raise TemplateError('Mesh contains nonfinite vertices')
            for i,x in enumerate(xyz):
                bounds_min[i] = min(bounds_min[i],x)
                bounds_max[i] = max(bounds_max[i],x)
            nvertices += 1
        elif name == 'triangle':
            ntriangles += 1
        node.clear()
    if nvertices < 3 or ntriangles < 1:
        raise TemplateError('Painted 3MF has no printable mesh')
    return bounds_min, bounds_max, nvertices, ntriangles


def _bed_bounds(settings):
    area = settings.get('printable_area')
    if not isinstance(area, list) or len(area) < 3:
        raise TemplateError('Template is missing printer printable_area')
    try:
        coords = [tuple(float(v) for v in p.lower().split('x')) for p in area]
        if any(len(p) != 2 for p in coords):
            raise ValueError('wrong polygon shape')
        x0,x1 = min(p[0] for p in coords),max(p[0] for p in coords)
        y0,y1 = min(p[1] for p in coords),max(p[1] for p in coords)
        h = float(settings.get('printable_height', 0))
    except (ValueError, TypeError) as exc:
        raise TemplateError('Invalid printer build-volume information') from exc
    if x1 <= x0 or y1 <= y0 or h <= 0:
        raise TemplateError('Invalid printer build volume')
    return x0,x1,y0,y1,h


def _nearest_indices(template_colors, out_colors, template_mixed, real_count):
    def distance(c1,c2):
        a = tuple(int(c1[i:i+2],16) for i in (1,3,5))
        b = tuple(int(c2[i:i+2],16) for i in (1,3,5))
        return sum((x-y)**2 for x,y in zip(a,b))
    physical = [i for i,v in enumerate(template_mixed) if str(v) != '1']
    mixed = [i for i,v in enumerate(template_mixed) if str(v) == '1']
    physical = physical or list(range(len(template_colors)))
    return [min((mixed or physical) if i>=real_count else physical,
                key=lambda j: distance(color,template_colors[j])) for i,color in enumerate(out_colors)]


# Phase 4 v3: slicer-confirmed per-material fields. Do not indiscriminately
# resize same-length printer/process arrays (they may be coincidental).
MATERIAL_SLOT_FIELDS = frozenset("""activate_air_filtration additional_cooling_fan_speed additional_fan_full_speed_layer
chamber_temperatures circle_compensation_speed close_additional_fan_first_x_layers
close_fan_the_first_x_layers complete_print_exhaust_fan_speed cool_plate_temp
cool_plate_temp_initial_layer cooling_perimeter_transition_distance
cooling_slowdown_logic counter_coef_1 counter_coef_2 counter_coef_3
counter_limit_max counter_limit_min diameter_limit during_print_exhaust_fan_speed
enable_overhang_bridge_fan enable_pressure_advance eng_plate_temp
eng_plate_temp_initial_layer fan_cooling_layer_time fan_max_speed fan_min_speed
first_x_layer_fan_speed first_x_layer_part_fan_speed full_fan_speed_layer
hole_coef_1 hole_coef_2 hole_coef_3 hole_limit_max hole_limit_min
hot_plate_temp hot_plate_temp_initial_layer impact_strength_z ironing_fan_speed
no_slow_down_for_cooling_on_outwalls nozzle_temperature_range_high
nozzle_temperature_range_low overhang_fan_speed overhang_fan_threshold
overhang_threshold_participating_cooling pre_start_fan_time pressure_advance
reduce_fan_stop_start_freq required_nozzle_HRC slow_down_for_layer_cooling
slow_down_layer_time supertack_plate_temp supertack_plate_temp_initial_layer
temperature_vitrification textured_plate_temp textured_plate_temp_initial_layer""".split())

def _fill_template_settings(template, planned, real_count):
    """Resize *all* recognized filament arrays from a valid slicer profile."""
    old = template['filament_colour']
    new = planned['filament_colour']
    m,n = len(old),len(new)
    if not 2 <= real_count <= n <= MAX_FILAMENTS:
        raise TemplateError('Invalid resulting physical/mixed slot count')
    mixed = template.get('filament_is_mixed', ['0']*m)
    indices = _nearest_indices(old,new,mixed,real_count)
    variant_self = template.get('filament_self_index')
    variant_groups = None
    if isinstance(variant_self, list) and len(variant_self) > m:
        # H2C stores Standard / High Flow (and sometimes E3D) as variable
        # counts per *physical* material. Infer boundaries only from the
        # slicer-saved slot index list, never from fixed 2- or 3-wide guesses.
        if len(variant_self) > MAX_FILAMENTS * 6:
            raise TemplateError('Template contains too many filament variants')
        variant_groups = []
        cursor = 0
        for slot in range(1, m + 1):
            start = cursor
            while cursor < len(variant_self) and str(variant_self[cursor]) == str(slot):
                cursor += 1
            if cursor == start:
                raise TemplateError('Invalid native filament variant sequence')
            variant_groups.append((start, cursor))
        if cursor != len(variant_self):
            raise TemplateError('Invalid native filament variant sequence')
    variant_fields = {
        'nozzle_temperature', 'nozzle_temperature_initial_layer',
        'long_retractions_when_ec', 'retraction_distances_when_ec',
        'slow_down_min_speed', 'override_process_overhang_speed',
        'volumetric_speed_coefficients',
    }
    result = dict(template)
    for key,values in template.items():
        if not isinstance(values,list):
            continue
        if key in ('flush_volumes_matrix','purging_volumes_matrix') and len(values) % (m*m) == 0:
            blocks = len(values)//(m*m)
            if blocks not in (1,2,4):
                continue
            extended = []
            for block in range(blocks):
                raw = values[block*m*m:(block+1)*m*m]
                for row,ii in enumerate(indices):
                    for col,jj in enumerate(indices):
                        val = raw[ii*m+jj]
                        if row != col and str(val) in ('0','0.0'):
                            val = '120'
                        extended.append(val)
            result[key] = extended
        elif (variant_groups is not None and len(values) == len(variant_self)
              and (key.startswith('filament_') or key in variant_fields)):
            # Rebuild Standard/High Flow/E3D records for the actual output
            # slot order. This keeps the physical profile tied to its HEX
            # anchor, even if source and planner slot orders differ.
            if key == 'filament_self_index':
                result[key] = [str(slot + 1)
                               for slot, original_idx in enumerate(indices)
                               for _ in range(variant_groups[original_idx][1] -
                                              variant_groups[original_idx][0])]
            else:
                result[key] = [value
                               for original_idx in indices
                               for value in values[variant_groups[original_idx][0]:
                                                   variant_groups[original_idx][1]]]
        elif key in MATERIAL_SLOT_FIELDS and len(values) == m:
            # Match each physical or mixed output to its native material source.
            # This must happen before the generic filament_* logic. Values
            # remain the exact slicer-saved strings (no inferred calibration).
            result[key] = [values[idx] for idx in indices]
        elif (key.startswith('filament_') or key == 'default_filament_colour') and m and len(values) % m == 0:
            width = len(values)//m
            if 1 <= width <= 4:
                if key == 'filament_self_index':
                    result[key] = [str(i+1) for i in range(n) for _ in range(width)]
                else:
                    result[key] = [v for idx in indices for v in values[idx*width:(idx+1)*width]]
        elif key.startswith('flush_volumes_vector') and m and len(values) % m == 0:
            width = len(values)//m
            if width in (1,2,4):
                result[key] = [v for idx in indices for v in values[idx*width:(idx+1)*width]]
    # The planner's colors and recipes take precedence; process/machine settings
    # come from the native project (never from a generic 3MF conversion).
    for key in (
        'filament_colour','filament_multi_colour','filament_is_mixed',
        'filament_mixed_components','filament_mixed_sublayer_ratios',
        'filament_colour_type','filament_mixed_gradient',
        'filament_mixed_gradient_per_part','filament_mixed_gradient_range',
    ):
        if key in planned:
            result[key] = list(planned[key])
    if len(result.get('filament_multi_colour',[])) != n:
        result['filament_multi_colour'] = list(new)
    # Some native slicer projects omit this optional template field. The
    # engine's output validator still requires one value per final slot.
    defaults = result.get('default_filament_colour')
    if not isinstance(defaults, list) or len(defaults) != n:
        planned_defaults = planned.get('default_filament_colour')
        if not isinstance(planned_defaults, list) or len(planned_defaults) != n:
            raise TemplateError('Neither template nor plan has valid default_filament_colour values')
        result['default_filament_colour'] = list(planned_defaults)
    for field in ('filament_colour','filament_is_mixed','filament_mixed_components',
                  'filament_mixed_sublayer_ratios','filament_multi_colour','filament_settings_id',
                  'default_filament_colour'):
        if len(result.get(field,[])) != n:
            raise TemplateError(f'Native profile could not resize {field} to {n} slots')
    for field in MATERIAL_SLOT_FIELDS:
        original = template.get(field)
        if isinstance(original, list) and len(original) == m:
            if not isinstance(result.get(field), list) or len(result[field]) != n:
                raise TemplateError(
                    f'Native material field {field} has wrong output slot count; expected {n}'
                )
    return result


def _serialized(root):
    # 'requiredextensions="p"' requires the production namespace to use prefix p.
    ET.register_namespace('p', PROD)
    ET.register_namespace('', REL if root.tag.startswith(f'{{{REL}}}') else CORE)
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def graft_native_project(source, template, destination, *, real_count):
    """Combine painted source geometry/recipes with slicer-native metadata.

    Returns a dict of verification info. Source and template are never modified.
    """
    source, template, destination = (Path(x).expanduser().resolve() for x in (source,template,destination))
    if destination in (source,template):
        raise TemplateError('Native export destination must not overwrite its inputs')
    details = inspect_template(template)
    with ZipFile(source) as original, ZipFile(template) as native:
        _safe_archive(original)
        members = [n for n in original.namelist() if n.startswith('3D/Objects/') and n.endswith('.model')]
        if len(members) != 1:
            raise TemplateError('Native project export currently requires exactly one painted mesh')
        child_path = members[0]
        child_bytes = original.read(child_path)
        src_root = _xml(child_bytes, child_path)
        source_objects = src_root.findall(f'{{{CORE}}}resources/{{{CORE}}}object')
        if len(source_objects) != 1 or source_objects[0].get('id') != '1':
            raise TemplateError('Single imported source mesh must have object id 1')
        if source_objects[0].find(f'{{{CORE}}}mesh') is None:
            raise TemplateError('Imported source object has no mesh')
        mins,maxs,verts,faces = _bbox_model(child_bytes)
        planned = json.loads(original.read('Metadata/project_settings.config'))
        template_json = json.loads(native.read('Metadata/project_settings.config'))
        merged = _fill_template_settings(template_json, planned, real_count)
        x0,x1,y0,y1,height = _bed_bounds(merged)
        if (maxs[0]-mins[0]) > (x1-x0) or (maxs[1]-mins[1]) > (y1-y0) or (maxs[2]-mins[2]) > height:
            raise TemplateError('Model exceeds the selected template printer build volume; check model units/orientation')
        dx = (x0+x1 - (mins[0]+maxs[0]))/2
        dy = (y0+y1 - (mins[1]+maxs[1]))/2
        dz = -mins[2]
        dx,dy,dz = (0.0 if abs(v) < 0.00001 else v for v in (dx,dy,dz))
        parent_id = 2
        stable_id = uuid.uuid5(uuid.NAMESPACE_URL, str(source) + '|' + str(template))
        native_main = _xml(native.read('3D/3dmodel.model'), '3D/3dmodel.model')
        resources = native_main.find(f'{{{CORE}}}resources')
        build = native_main.find(f'{{{CORE}}}build')
        parent = ET.SubElement(resources, f'{{{CORE}}}object', {
            'id': str(parent_id), 'type': 'model', f'{{{PROD}}}UUID': str(stable_id),
        })
        components = ET.SubElement(parent, f'{{{CORE}}}components')
        ET.SubElement(components, f'{{{CORE}}}component', {
            'objectid': '1',f'{{{PROD}}}path': '/'+child_path,
            f'{{{PROD}}}UUID': str(uuid.uuid5(stable_id,'component')),
            'transform': '1 0 0 0 1 0 0 0 1 0 0 0',
        })
        transform = f'1 0 0 0 1 0 0 0 1 {dx:.9g} {dy:.9g} {dz:.9g}'
        ET.SubElement(build, f'{{{CORE}}}item', {
            'objectid': str(parent_id), f'{{{PROD}}}UUID': str(uuid.uuid5(stable_id,'build')),
            'transform': transform, 'printable':'1',
        })
        child_obj = source_objects[0]
        child_obj.set(f'{{{PROD}}}UUID', str(uuid.uuid5(stable_id,'mesh')))
        if src_root.find(f'{{{CORE}}}metadata[@name="BambuStudio:3mfVersion"]') is None:
            meta = ET.Element(f'{{{CORE}}}metadata',{'name':'BambuStudio:3mfVersion'})
            meta.text = '1'
            src_root.insert(0,meta)
        src_root.set('requiredextensions','p')
        # Submodel geometry is referenced via a component in the native main model.
        # Keeping a second build item here can import a duplicate ghost object.
        child_build=src_root.find(f'{{{CORE}}}build')
        if child_build is not None:
            child_build.clear()
        model_config = _xml(native.read('Metadata/model_settings.config'),'Metadata/model_settings.config')
        object_el = ET.Element('object',{'id':str(parent_id), 'auto_drop':'1'})
        ET.SubElement(object_el,'metadata',{'key':'name','value':source.stem})
        ET.SubElement(object_el,'metadata',{'key':'extruder','value':'1'})
        part = ET.SubElement(object_el,'part',{'id':'1','subtype':'normal_part'})
        for key,value in (
            ('name',source.stem),('matrix','1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1'),
            ('source_file',source.name),('source_object_id','1'),('source_volume_id','0'),
            ('source_offset_x','0'),('source_offset_y','0'),('source_offset_z','0'),('extruder','1'),
        ):
            ET.SubElement(part,'metadata',{'key':key,'value':value})
        ET.SubElement(part,'mesh_stat',{
            'edges_fixed':'0','degenerate_facets':'0','facets_removed':'0',
            'facets_reversed':'0','backwards_edges':'0',
        })
        plate = model_config.find('plate')
        if plate is None:
            raise TemplateError('Template has no plate configuration')
        model_config.insert(list(model_config).index(plate),object_el)
        instance = ET.SubElement(plate,'model_instance')
        for key,value in (('object_id',str(parent_id)),('instance_id','0'),('identify_id','1')):
            ET.SubElement(instance,'metadata',{'key':key,'value':value})
        assemble = model_config.find('assemble')
        if assemble is None:
            assemble = ET.SubElement(model_config,'assemble')
        ET.SubElement(assemble,'assemble_item',{
            'object_id':str(parent_id),'instance_id':'0',
            'transform':'1 0 0 0 1 0 0 0 1 0 0 0', 'offset':'0 0 0',
        })
        relationships = ET.Element(f'{{{REL}}}Relationships')
        ET.SubElement(relationships,f'{{{REL}}}Relationship',{
            'Target':'/'+child_path,'Id':'rel-1',
            'Type':'http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel',
        })
        payload = {n:native.read(n) for n in native.namelist() if not n.endswith('/')}
        # Replace black placeholders; thumbnail failure must not discard
        # an otherwise valid, fully-painted native slicer project.
        try:
            from native_preview_thumbnail import add_native_thumbnails
            add_native_thumbnails(payload, child_bytes, planned)
        except Exception as thumbnail_error:
            import warnings
            warnings.warn(f'Native thumbnail unavailable: {thumbnail_error}', RuntimeWarning)
        # Imported OBJ and GLB models can refer to embedded image assets.
        # The native template is the configuration source, but model resources
        # must come from the converted source. Never silently overwrite a
        # conflicting native member.
        for name in original.namelist():
            if name.startswith('3D/Textures/') and not name.endswith('/'):
                resource = original.read(name)
                if name in payload and payload[name] != resource:
                    raise TemplateError('Native template texture conflicts with source: ' + name)
                payload[name] = resource
        payload.update({
            '3D/3dmodel.model':_serialized(native_main),
            child_path:_serialized(src_root),
            '3D/_rels/3dmodel.model.rels':_serialized(relationships),
            'Metadata/project_settings.config':json.dumps(merged,indent=2,ensure_ascii=False).encode('utf-8'),
            'Metadata/model_settings.config':_serialized(model_config),
        })
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,tempname = tempfile.mkstemp(prefix='.native-',suffix='.3mf',dir=destination.parent)
    os.close(fd)
    try:
        with ZipFile(tempname,'w',ZIP_DEFLATED) as result:
            for name,data in payload.items():
                result.writestr(name,data)
        with ZipFile(tempname) as verify:
            _safe_archive(verify)
            main = _xml(verify.read('3D/3dmodel.model'),'3D/3dmodel.model')
            if len(main.findall(f'{{{CORE}}}build/{{{CORE}}}item'))!=1:
                raise TemplateError('Native build item missing after export')
            m = _xml(verify.read(child_path),child_path)
            if len(m.findall(f'.//{{{CORE}}}triangle'))!=faces:
                raise TemplateError('Mesh triangle count changed')
            settings=json.loads(verify.read('Metadata/project_settings.config'))
            for k in ('filament_colour','filament_is_mixed','filament_mixed_components','filament_mixed_sublayer_ratios'):
                if settings[k] != planned[k]:
                    raise TemplateError('Native project recipe values changed during merge: '+k)
        os.replace(tempname,destination)
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)
    return {
        **details,'output':str(destination),'triangleCount':faces,'vertexCount':verts,
        'physicalSlots':real_count,'totalSlots':len(planned['filament_colour']),
        'position':[round(dx,3),round(dy,3),round(dz,3)],
    }

# Native output-colors/thumbnail patch v1
