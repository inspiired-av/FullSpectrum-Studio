"""Stage 4D-C: export settings cannot invalidate a forecast, native metadata
has one provenance value, and native thumbnails do not skip arbitrary faces.
"""
from __future__ import annotations
import ast
from pathlib import Path
import io
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
CORE='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'


class RefinementContracts(unittest.TestCase):
    def test_ui_export_fields_do_not_invalidate(self):
        s=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertIn("if field in ('native_project_template', 'auto_open', 'output_application',", s)
        self.assertIn("if not changed:\n            return", s)
        self.assertIn("self.review_export_button = QPushButton('Review && Export →')", s)
        self.assertIn('if before != after:', s)
        self.assertIn('if source_changed:', s)
        self.assertIn('self._refresh_filament_setup_ui()', s)

    def test_forecast_plan_does_not_consume_export_template(self):
        s=(ROOT/'desktop/qt_app/forecast_service.py').read_text(encoding='utf-8')
        self.assertIn('custom_catalog_path=custom, native_template_path=None,', s)
        # Export still passes the configured template to its existing converter.
        export=(ROOT/'desktop/qt_app/export_service.py').read_text(encoding='utf-8')
        self.assertIn("native_template_path=s.get('native_project_template') or None", export)

    def test_template_version_metadata_is_deduplicated_and_provenance_is_separate(self):
        from native_project_template import _normalize_native_slicer_metadata
        data = (f'<model xmlns="{CORE}">'
                '<metadata name="Application">BambuStudio-2.8</metadata>'
                '<metadata name="OrcaSlicer">2.5.0-alpha</metadata>'
                '<metadata name="OrcaSlicer">2.5.0-dev</metadata>'
                '<metadata name="Other">unchanged</metadata>'
                '<resources/><build/></model>')
        root=ET.fromstring(data)
        _normalize_native_slicer_metadata(root)
        by_name={}
        for item in root.findall(f'{{{CORE}}}metadata'):
            by_name.setdefault(item.get('name'), []).append(item.text)
        self.assertEqual(by_name['OrcaSlicer'], ['2.5.0-dev'])
        self.assertEqual(by_name['Application'], ['BambuStudio-2.8'])
        self.assertEqual(by_name['Other'], ['unchanged'])
        self.assertEqual(len(by_name['FullSpectrumStudio:Version']), 1)
        self.assertTrue(by_name['FullSpectrumStudio:Version'][0].startswith('v'))
        self.assertEqual(len(root.findall(f'{{{CORE}}}resources')), 1)
        _normalize_native_slicer_metadata(root)
        self.assertEqual(len([item for item in root.findall(f'{{{CORE}}}metadata')
                              if item.get('name')=='FullSpectrumStudio:Version']), 1)

    def test_bambu_duplicate_versions_follow_same_rule(self):
        from native_project_template import _normalize_native_slicer_metadata
        root=ET.fromstring(f'<model xmlns="{CORE}">'
            '<metadata name="Application">BambuStudio-2.7</metadata>'
            '<metadata name="Application">BambuStudio-2.8</metadata>'
            '<metadata name="BambuStudio:3mfVersion">1</metadata>'
            '<metadata name="BambuStudio:3mfVersion">1</metadata>'
            '<resources/><build/></model>')
        _normalize_native_slicer_metadata(root)
        nodes=root.findall(f'{{{CORE}}}metadata')
        self.assertEqual([node.text for node in nodes if node.get('name')=='Application'],
                         ['BambuStudio-2.8'])
        self.assertEqual([node.text for node in nodes if node.get('name')=='BambuStudio:3mfVersion'],['1'])

    def test_native_project_validates_deduplicated_archive_metadata(self):
        source=(ROOT/'native_project_template.py').read_text(encoding='utf-8')
        self.assertIn('_normalize_native_slicer_metadata(native_main)',source)
        self.assertIn('Ambiguous generated slicer provenance:',source)

    def test_thumbnail_renders_every_face_instead_of_sampling_strides(self):
        from native_preview_thumbnail import render_plate_preview
        from PIL import Image
        # 25,001 triangles: the last paints the face red. The old stride=2
        # drops it entirely, leaving only the black background triangles.
        vertices=('\n<vertex x="0" y="0" z="0"/>'
                  '<vertex x="0" y="24" z="0"/>'
                  '<vertex x="0" y="12" z="40"/>')
        triangles = ('<triangle v1="0" v2="1" v3="2" paint_color="4"/>' * 25000
                     + '<triangle v1="0" v2="1" v3="2" paint_color="0C"/>')
        xml=(f'<model xmlns="{CORE}"><resources><object id="1"><mesh>'
             f'<vertices>{vertices}</vertices><triangles>{triangles}</triangles>'
             '</mesh></object></resources><build/></model>').encode('utf-8')
        image,_ = render_plate_preview(xml,['#111111','#FFFFFF','#FF0000'])
        pic=Image.open(io.BytesIO(image)).convert('RGB')
        self.assertGreater(sum(1 for px in pic.getdata() if px[0]>140 and px[1]<85 and px[2]<85),300)
        with self.assertRaisesRegex(ValueError, 'safety limit'):
            render_plate_preview(xml,['#111111','#FFFFFF','#FF0000'],max_faces=100)

    def test_sources_compile(self):
        for path in ('desktop/qt_app/main_window.py','desktop/qt_app/forecast_service.py',
                     'native_project_template.py','native_preview_thumbnail.py'):
            ast.parse((ROOT/path).read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
