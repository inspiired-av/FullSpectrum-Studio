"""Phase 4: saved H2C material profiles follow physical slot and variant order."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_project_template import _fill_template_settings, TemplateError
from phase4_material_profiles import audit_material_profiles


C, M, Y, G, K = '#08ABFB', '#D93B90', '#F9ED3D', '#9199A4', '#000000'
PANCHROMA = 'Panchroma PLA Translucent @Bambu Lab H2C 0.4 nozzle'
BLACK = 'Bambu PLA Basic @BBL H2C'


def saved_h2c_settings():
    colors=[C,M,Y,G,K]
    group_sizes=[2,2,2,2,3]
    self_index=[str(i+1) for i,n in enumerate(group_sizes) for _ in range(n)]
    return {
        'filament_colour': colors,
        'filament_multi_colour': colors[:],
        'default_filament_colour': ['']*5,
        'filament_is_mixed': ['0']*5,
        'filament_settings_id': [PANCHROMA]*4+[BLACK],
        'filament_ids': ['PMPL13']*4+['GFA00'],
        'filament_type': ['PLA']*5,
        'filament_vendor': ['Polymaker']*4+['Bambu Lab'],
        'filament_density': ['1.17']*4+['1.26'],
        'filament_self_index': self_index,
        'filament_extruder_variant': ['Standard','High Flow']*4+['Standard','High Flow','E3D'],
        'filament_flow_ratio': ['0.96','nil']*4+['0.99','0.99','0.99'],
        'filament_max_volumetric_speed': ['15','nil']*4+['25','40','25'],
        'nozzle_temperature': [str(210+i*10) for i,n in enumerate(group_sizes) for _ in range(n)],
        'nozzle_temperature_initial_layer': [str(215+i*10) for i,n in enumerate(group_sizes) for _ in range(n)],
        'textured_plate_temp': ['60']*4+['55'],
        'flush_volumes_matrix': ['120']*25,
        'filament_mixed_components': ['']*5,
        'filament_mixed_sublayer_ratios': ['']*5,
    }


def planned_output(count=32):
    colors=[C,G,M,Y,K]+[C] * (count-5)
    return {
        'filament_colour':colors,
        'default_filament_colour':['']*count,
        'filament_is_mixed':['0']*5+['1']*(count-5),
        'filament_mixed_components':['']*5+['1,5']*(count-5),
        'filament_mixed_sublayer_ratios':['']*5+['0.5000,0.5000']*(count-5),
        'filament_multi_colour': colors[:],
    }


class NativeVariantMappingTests(unittest.TestCase):
    def test_physical_presets_follow_colors_not_initial_slot_position(self):
        out = _fill_template_settings(saved_h2c_settings(), planned_output(), 5)
        self.assertEqual(out['filament_colour'][:5],[C,G,M,Y,K])
        self.assertEqual(out['filament_settings_id'][:5],[PANCHROMA]*4+[BLACK])
        self.assertEqual(out['filament_ids'][:5],['PMPL13']*4+['GFA00'])
        self.assertEqual(out['filament_vendor'][:5],['Polymaker']*4+['Bambu Lab'])
        self.assertEqual(out['filament_density'][:5],['1.17']*4+['1.26'])
        self.assertEqual(out['textured_plate_temp'][:5],['60','60','60','60','55'])

    def test_variant_groups_follow_reordered_physical_filaments(self):
        out = _fill_template_settings(saved_h2c_settings(), planned_output(), 5)
        self.assertEqual(out['filament_self_index'][:11], ['1','1','2','2','3','3','4','4','5','5','5'])
        self.assertEqual(out['nozzle_temperature'][:11], ['210','210','240','240','220','220','230','230','250','250','250'])
        self.assertEqual(out['filament_flow_ratio'][:11], ['0.96','nil']*4+['0.99']*3)
        self.assertEqual(out['filament_max_volumetric_speed'][:11], ['15','nil']*4+['25','40','25'])
        self.assertEqual(out['filament_extruder_variant'][:11], ['Standard','High Flow']*4+['Standard','High Flow','E3D'])
        # The output grows the nozzle-variant index for every final filament slot.
        self.assertEqual(len(out['filament_self_index']),len(out['nozzle_temperature']))
        self.assertEqual(len(out['filament_self_index']),len(out['filament_flow_ratio']))
        self.assertEqual(set(map(int,out['filament_self_index'])),set(range(1,33)))

    def test_invalid_variant_index_rejected_without_guessing(self):
        template=saved_h2c_settings()
        template['filament_self_index'][1]='3'
        with self.assertRaisesRegex(TemplateError,'variant sequence'):
            _fill_template_settings(template,planned_output(),5)

    def test_non_variant_arrays_still_resize(self):
        template=saved_h2c_settings()
        template.pop('filament_self_index')
        # A project with no variant map still uses per-slot arrays; no variant-inference.
        out=_fill_template_settings(template,planned_output(),5)
        self.assertEqual(len(out['filament_settings_id']),32)
        self.assertEqual(out['filament_density'][1],'1.17')

    def test_panchroma_alias_is_semantically_matched(self):
        out=_fill_template_settings(saved_h2c_settings(),planned_output(),5)
        names=['Polymaker Panchroma Translucent PLA - Cyan','Polymaker Panchroma Translucent PLA - Grey',
               'Polymaker Panchroma Translucent PLA - Magenta','Polymaker Panchroma Translucent PLA - Yellow',
               'Bambu PLA Basic - Black']
        anchors=[{'name':name,'color':color,
                  'preset':('Bambu Panchroma Translucent PLA @base' if i<4 else 'Bambu PLA Basic @base')}
                 for i,(name,color) in enumerate(zip(names,[C,G,M,Y,K]))]
        audit=audit_material_profiles(out,anchors,5)
        self.assertEqual([i['status'] for i in audit],['matched']*5)

    def test_same_family_different_variant_is_not_treated_as_match(self):
        template=saved_h2c_settings()
        template['filament_settings_id'][0] = 'Panchroma PLA Silk @Bambu Lab H2C 0.4 nozzle'
        out=_fill_template_settings(template,planned_output(),5)
        anchors=[{'name':'Cyan','color':C,'preset':'Bambu Panchroma Translucent PLA @base'}]
        anchors += [{'name':str(i),'color':col,'preset':PANCHROMA if i<4 else BLACK}
                    for i,col in enumerate([G,M,Y,K],start=1)]
        audit=audit_material_profiles(out,anchors,5)
        self.assertEqual(audit[0]['status'],'review')

    def test_real_saved_h2c_fixture_if_available(self):
        # Private reference is intentionally not packaged with public tests.
        path=Path(__file__).resolve().parents[2]/'H2C_Correct_Material_Profiles.3mf'
        if not path.is_file():
            self.skipTest('Optional real H2C reference not included in repository')
        with ZipFile(path) as z:
            s=json.loads(z.read('Metadata/project_settings.config'))
        out=_fill_template_settings(s,planned_output(),5)
        self.assertEqual(out['filament_settings_id'][:5],[PANCHROMA]*4+[BLACK])
        self.assertEqual(out['filament_flow_ratio'][:8],['0.96','nil']*4)
        self.assertEqual(out['filament_max_volumetric_speed'][:8],['15','nil']*4)
        self.assertEqual(out['filament_flow_ratio'][8:11],['0.99']*3)

if __name__=='__main__':unittest.main()
