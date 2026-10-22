"""Tests for Phase 4 non-destructive filament preset audit."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phase4_material_profiles import (
    audit_material_profiles, audit_project, warning_lines, MaterialAuditError, _base_preset,
)


class MaterialProfileTests(unittest.TestCase):
    def setUp(self):
        self.settings={
            'filament_colour':['#08ABFB','#9199A4','#000000','#123456'],
            'filament_settings_id':['Bambu PLA Basic @BBL H2C',
                                    'Bambu PLA Basic @BBL H2C',
                                    'Generic PLA @BBL H2C 0.4 nozzle',
                                    'Bambu PLA Basic @BBL H2C'],
            'filament_is_mixed':['0','0','0','1'],
            'filament_vendor':['Bambu Lab','Bambu Lab','Generic','Bambu Lab'],
            'filament_ids':['GFA00','GFA00','GFL99','GFA00']
        }
        self.anchors=[
            {'name':'Polymaker Panchroma Cyan','color':'#08ABFB',
             'preset':'Bambu Panchroma Translucent PLA @base'},
            {'name':'Polymaker Panchroma Grey','color':'#9199A4',
             'preset':'Bambu Panchroma Translucent PLA @base'},
            {'name':'Bambu PLA Basic Black','color':'#000000',
             'preset':'Bambu PLA Basic @base'},
        ]

    def test_actual_mismatches_are_reported(self):
        rows=audit_material_profiles(self.settings,self.anchors)
        self.assertEqual([x['status'] for x in rows],['review']*3)
        self.assertIn('3/3 physical slots',warning_lines(rows)[0])
        self.assertIn('Generic PLA',warnings if (warnings:=warning_lines(rows)[-1]) else '')

    def test_machine_suffix_is_not_false_mismatch(self):
        self.settings['filament_settings_id'][0]='Bambu Panchroma Translucent PLA @BBL H2C 0.4 nozzle'
        rows=audit_material_profiles(self.settings,self.anchors)
        self.assertEqual(rows[0]['status'],'matched')

    def test_wrong_color_detected_with_same_profile(self):
        self.settings['filament_settings_id'][0]='Bambu Panchroma Translucent PLA @BBL H2C'
        self.settings['filament_colour'][0]='#112233'
        rows=audit_material_profiles(self.settings,self.anchors)
        self.assertEqual(rows[0]['status'],'review')
        self.assertIn('differs',rows[0]['problems'][0])

    def test_missing_preset_not_verified(self):
        self.settings['filament_settings_id'][0]=''
        rows=audit_material_profiles(self.settings,self.anchors)
        self.assertIn('no saved',rows[0]['problems'][0])

    def test_mixed_outputs_not_considered_physical(self):
        rows=audit_material_profiles(self.settings,self.anchors,real_count=3)
        self.assertEqual(len(rows),3)

    def test_missing_expected_profile_is_unverified(self):
        self.settings['filament_settings_id'][0]='Bambu PLA Basic @BBL H2C'
        rows=audit_material_profiles(self.settings,[{'name':'Unknown','color':'#08ABFB'},*self.anchors[1:]])
        self.assertEqual(rows[0]['status'],'unverified')
        self.assertIn('no verified',warning_lines(rows)[-1])

    def test_array_length_mismatch_is_rejected(self):
        with self.assertRaises(MaterialAuditError):
            audit_material_profiles(self.settings,self.anchors,real_count=4)

    def test_read_only_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.3mf'
            with ZipFile(path,'w') as z:
                z.writestr('Metadata/project_settings.config',json.dumps(self.settings))
            before=path.read_bytes()
            self.assertEqual(len(audit_project(path,self.anchors)),3)
            self.assertEqual(path.read_bytes(),before)

    def test_name_matches_do_not_claim_calibration(self):
        for i,anchor in enumerate(self.anchors):
            self.settings['filament_settings_id'][i]=anchor['preset'].replace('@base','@BBL H2C')
        rows=audit_material_profiles(self.settings,self.anchors)
        self.assertEqual(warning_lines(rows),[])
        self.assertTrue(all(x['status']=='matched' for x in rows))


if __name__=='__main__':unittest.main()
