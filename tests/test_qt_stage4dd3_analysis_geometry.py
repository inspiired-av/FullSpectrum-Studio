"""Stage 4D-D3: native analysis OBJ preserves 3MF world placement/slots."""
from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from preview_world_geometry import model_instances, preview_geometry


ROOT = Path(__file__).resolve().parents[1]
CORE = ('http://schemas.microsoft.com/3dmanufacturing/core/2015/02')
PROD = ('http://schemas.microsoft.com/3dmanufacturing/production/2015/06')


def fixture(folder):
    """Same mesh referenced twice in different locations/physical slots."""
    path = Path(folder) / 'native-multi-object.3mf'
    root = f'''<?xml version="1.0"?>
<model xmlns="{CORE}" xmlns:p="{PROD}" unit="millimeter">
 <resources>
  <object id="2" type="model"><components><component p:path="/3D/Objects/one.model" objectid="1" /></components></object>
  <object id="4" type="model"><components><component p:path="/3D/Objects/one.model" objectid="1" /></components></object>
 </resources>
 <build>
  <item objectid="2" transform="1 0 0 0 1 0 0 0 1 10 0 3" />
  <item objectid="4" transform="0 1 0 -1 0 0 0 0 1 40 0 5" />
 </build>
</model>'''
    mesh = f'''<?xml version="1.0"?>
<model xmlns="{CORE}" unit="millimeter"><resources><object id="1" type="model"><mesh>
<vertices><vertex x="0" y="0" z="0" /><vertex x="3" y="0" z="0" />
<vertex x="0" y="3" z="0" /><vertex x="0" y="0" z="3" /></vertices>
<triangles><triangle v1="0" v2="1" v3="2" />
<triangle v1="0" v2="2" v3="3" /><triangle v1="0" v2="3" v3="1" />
<triangle v1="1" v2="3" v3="2" /></triangles></mesh></object></resources></model>'''
    settings = '''<config><object id="2"><metadata key="extruder" value="1" /></object>
<object id="4"><metadata key="extruder" value="2" /></object></config>'''
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        z.writestr('3D/3dmodel.model', root)
        z.writestr('3D/Objects/one.model', mesh)
        z.writestr('Metadata/model_settings.config', settings)
    return path


class AnalysisPlacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = fixture(self.temp.name)

    def test_root_build_instances_not_just_object_files(self):
        with ZipFile(self.path) as z:
            instances, scale = model_instances(z, 2)
        self.assertEqual(len(instances), 2)
        self.assertEqual([x[-1] for x in instances], [1, 2])
        self.assertEqual(scale, 1.)
        self.assertEqual(instances[0][0], instances[1][0])

    def test_full_preview_keeps_both_placed_objects_and_default_slots(self):
        with ZipFile(self.path) as z:
            points, faces = preview_geometry(z, 2, slot_lookup=lambda code,n: 1)
        self.assertEqual(len(points), 8)
        self.assertEqual(len(faces), 8)
        self.assertEqual(Counter(slot for _,slot in faces.values()), {1: 4, 2: 4})
        self.assertEqual(min(x for x,_,_ in points), 10.)
        self.assertEqual(max(x for x,_,_ in points), 40.)
        self.assertEqual(min(z for _,_,z in points), 3.)
        self.assertEqual(max(z for _,_,z in points), 8.)
        self.assertEqual(max(y for _,y,_ in points), 3.)

    def test_grid_preview_keeps_instances_separate(self):
        with ZipFile(self.path) as z:
            points, faces = preview_geometry(z, 2, grid_resolution=120,
                                              slot_lookup=lambda code,n: 1)
        self.assertEqual(len(faces), 8)
        self.assertEqual(Counter(slot for _,slot in faces.values()), {1: 4, 2: 4})
        self.assertEqual(min(x for x,_,_ in points), 10.)
        self.assertEqual(max(x for x,_,_ in points), 40.)

    def test_no_root_graph_uses_legacy_fixture_fallback(self):
        with ZipFile(Path(self.temp.name)/'basic.zip','w') as z:
            z.writestr('3D/Objects/one.model', '<mesh/>')
        with ZipFile(Path(self.temp.name)/'basic.zip') as z:
            self.assertIsNone(preview_geometry(z, 2, slot_lookup=lambda code,n: 1))

    def test_engine_uses_placed_preview_and_rebuilds_cache(self):
        text = (ROOT/'fullspectrum_engine.py').read_text(encoding='utf-8')
        self.assertIn('PREVIEW_CACHE_VERSION = 2', text)
        block = text.split('def reduced_preview_geometry(', 1)[1].split('\ndef export_preview_mesh(', 1)[0]
        self.assertIn('from preview_world_geometry import preview_geometry', block)
        self.assertIn('preview_geometry(', block)


if __name__ == '__main__':
    unittest.main()
