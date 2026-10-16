"""Phase 4 v3: confirmed per-filament fields must follow re-ordered output slots."""
from __future__ import annotations
import json
import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from native_project_template import _fill_template_settings, MATERIAL_SLOT_FIELDS

CYAN='#08ABFB';GREY='#9199A4';MAGENTA='#D93B90';YELLOW='#F9ED3D';BLACK='#000000'


def fixture_template():
    data={
        'filament_colour':[CYAN,MAGENTA,YELLOW,GREY,BLACK],
        'filament_is_mixed':['0']*5,
        'filament_multi_colour':[CYAN,MAGENTA,YELLOW,GREY,BLACK],
        'filament_settings_id':['Panchroma']*4+['Bambu Basic'],
        'filament_ids':['PMPL13']*4+['GFA00'],
        'default_filament_colour':['']*5,
        'filament_mixed_components':['']*5,
        'filament_mixed_sublayer_ratios':['']*5,
        'filament_self_index':['1','1','2','2','3','3','4','4','5','5','5'],
        'filament_flow_ratio':['0.96','nil']*4+['0.99']*3,
        'filament_max_volumetric_speed':['15','nil']*4+['25','40','25'],
        'nozzle_temperature':['220']*8+['225']*3,
        'flush_volumes_matrix':['120']*25,
        'printable_area':['0x0','200x0','200x200','0x200'],
        'printer_variant':['0.4'],
        'bridge_speed':['50']*5,
        'nozzle_flush_dataset':['1','2','3','4','5'],
    }
    for field in MATERIAL_SLOT_FIELDS:
        if field not in data:
            data[field]=['60','60','60','60','40']
    data['fan_max_speed']=['100']*4+['80']
    data['cool_plate_temp']=['60']*4+['35']
    data['nozzle_temperature_range_high']=['230']*4+['240']
    return data


def plan():
    colors=[CYAN,GREY,MAGENTA,YELLOW,BLACK]+[CYAN]*27
    return {'filament_colour':colors,'filament_is_mixed':['0']*5+['1']*27,
            'filament_multi_colour':colors[:],
            'default_filament_colour':['']*32,
            'filament_mixed_components':['']*5+['1,5']*27,
            'filament_mixed_sublayer_ratios':['']*5+['0.5,0.5']*27}


class MaterialArrayMappingTests(unittest.TestCase):
    def test_all_slicer_confirmed_material_fields_have_one_entry_per_output_slot(self):
        template=fixture_template()
        result=_fill_template_settings(template,plan(),5)
        for field in MATERIAL_SLOT_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(len(result[field]),32)

    def test_black_specific_fan_and_bed_settings_remain_attached_to_black(self):
        result=_fill_template_settings(fixture_template(),plan(),5)
        self.assertEqual(result['fan_max_speed'][:5],['100','100','100','100','80'])
        self.assertEqual(result['cool_plate_temp'][:5],['60','60','60','60','35'])
        self.assertEqual(result['nozzle_temperature_range_high'][:5],['230','230','230','230','240'])
        self.assertEqual(result['fan_max_speed'][5],'100')

    def test_global_and_process_arrays_are_not_expanded_by_coincidental_length(self):
        original=fixture_template()
        result=_fill_template_settings(original,plan(),5)
        self.assertEqual(result['bridge_speed'],original['bridge_speed'])
        self.assertEqual(result['nozzle_flush_dataset'],original['nozzle_flush_dataset'])
        self.assertEqual(result['printable_area'],original['printable_area'])
        self.assertEqual(result['printer_variant'],original['printer_variant'])

    def test_standard_and_high_flow_variant_records_untouched(self):
        result=_fill_template_settings(fixture_template(),plan(),5)
        self.assertEqual(result['filament_flow_ratio'][:11],['0.96','nil']*4+['0.99']*3)
        self.assertEqual(result['filament_max_volumetric_speed'][:11],['15','nil']*4+['25','40','25'])
        self.assertEqual(set(map(int,result['filament_self_index'])),set(range(1,33)))
        self.assertEqual(len(result['filament_flow_ratio']),len(result['filament_self_index']))

    def test_mixed_paint_slot_count_and_references_unchanged(self):
        result=_fill_template_settings(fixture_template(),plan(),5)
        self.assertEqual(result['filament_is_mixed'],['0']*5+['1']*27)
        self.assertEqual(result['filament_mixed_components'][5:8],['1,5']*3)
        self.assertEqual(result['filament_mixed_sublayer_ratios'][5:8],['0.5,0.5']*3)

    def test_reference_project_if_available(self):
        path=os.environ.get('FULLSPECTRUM_PHASE4_REFERENCE_3MF')
        if not path or not Path(path).is_file():
            self.skipTest('Private material 3MF reference not distributed with repository')
        with ZipFile(path) as z:
            source=json.loads(z.read('Metadata/project_settings.config'))
        result=_fill_template_settings(source,plan(),5)
        for key in MATERIAL_SLOT_FIELDS:
            if key in source and isinstance(source[key],list) and len(source[key])==5:
                with self.subTest(key=key):
                    self.assertEqual(len(result[key]),32)
        self.assertEqual(result['cool_plate_temp'][:5],['60','60','60','60','35'])
        self.assertEqual(result['filament_flow_ratio'][:11],['0.96','nil']*4+['0.99']*3)


if __name__=='__main__':
    unittest.main()
