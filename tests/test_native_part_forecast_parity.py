"""Native Bambu/Orca component-part slot inheritance and forecast parity.

Uses self-contained synthetic ZIPs; no private/customer 3MF is distributed.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from native_part_slot_defaults import read_part_slot_defaults
from preview_world_geometry import model_instances, preview_geometry

CORE = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PROD = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'


def fake_archive(path, *, overrides=None, parent='3', bad_metadata=False, duplicate_part=False):
    overrides = {2: 2, 3: 2, 4: 4, 5: 4} if overrides is None else overrides
    refs = '\n'.join(
        f'<component objectid="{i}" p:path="/3D/Objects/object_1.model" '
        f'transform="1 0 0 0 1 0 0 0 1 {i*18} 0 0" />'
        for i in range(1, 7)
    )
    root = (f'<model xmlns="{CORE}" xmlns:p="{PROD}" unit="millimeter">'
            f'<resources><object id="13"><components>{refs}</components></object></resources>'
            '<build><item objectid="13" /></build></model>')
    meshes = '\n'.join(
        f'<object id="{i}"><mesh><vertices>'
        '<vertex x="0" y="0" z="0" /><vertex x="9" y="0" z="0" />'
        '<vertex x="0" y="9" z="0" /></vertices><triangles>'
        f'<triangle v1="0" v2="1" v3="2"' + (' paint_color="4"' if i == 1 else '')
        + '/></triangles></mesh></object>' for i in range(1, 7))
    objects = f'<model xmlns="{CORE}"><resources>{meshes}</resources></model>'
    parts = '\n'.join(f'<part id="{key}"><metadata key="extruder" value="{value}" /></part>'
                      for key, value in overrides.items())
    if duplicate_part:
        parts += '<part id="2"><metadata key="extruder" value="2" /></part>'
    config = f'<config><object id="13"><metadata key="extruder" value="{parent}"/>{parts}</object></config>'
    if bad_metadata:
        config = '<config><object id="13">'
    with ZipFile(path, 'w') as archive:
        archive.writestr('3D/3dmodel.model', root)
        archive.writestr('3D/Objects/object_1.model', objects)
        archive.writestr('Metadata/model_settings.config', config)
    return path


def leaf_slot(code, count):
    # The test's only face-paint code 4 means source slot 1.
    return 1 if code == '4' else 3


class ComponentPartParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'fixture.3mf'

    def test_inherited_and_overridden_slots_with_face_paint(self):
        fake_archive(self.path)
        with ZipFile(self.path) as archive:
            self.assertEqual(read_part_slot_defaults(archive, 4),
                             {('13', '2'): 2, ('13', '3'): 2,
                              ('13', '4'): 4, ('13', '5'): 4})
            instances, scale = model_instances(archive, 4)
            self.assertEqual([entry[-1] for entry in instances], [3, 2, 2, 4, 4, 3])
            self.assertEqual(scale, 1.0)
            vertices, faces = preview_geometry(archive, 4, slot_lookup=leaf_slot)
            self.assertEqual(len(vertices), 18)
            self.assertEqual(Counter(slot for _, slot in faces.values()),
                             Counter({1: 1, 2: 2, 4: 2, 3: 1}))
            self.assertEqual(len(faces), 6)

    def test_reduced_preview_retains_disconnected_part_slots(self):
        fake_archive(self.path)
        with ZipFile(self.path) as archive:
            _, faces = preview_geometry(archive, 4, grid_resolution=512, slot_lookup=leaf_slot)
            self.assertEqual(Counter(slot for _, slot in faces.values()),
                             Counter({1: 1, 2: 2, 4: 2, 3: 1}))

    def test_missing_override_inherits_parent(self):
        fake_archive(self.path, overrides={2: 2})
        with ZipFile(self.path) as archive:
            instances, _ = model_instances(archive, 4)
            self.assertEqual([entry[-1] for entry in instances], [3, 2, 3, 3, 3, 3])

    def test_valid_duplicate_color_slot_ids_remain_separate(self):
        fake_archive(self.path)
        with ZipFile(self.path) as archive:
            # No color lookup occurs: two palette slots may share the same HEX.
            entries = read_part_slot_defaults(archive, 4)
            self.assertNotEqual(entries[('13', '2')], entries[('13', '4')])

    def test_invalid_explicit_part_never_silently_uses_parent(self):
        for invalid in ('n/a', 0, 5, -1):
            with self.subTest(invalid=invalid):
                fake_archive(self.path, overrides={2: invalid})
                with ZipFile(self.path) as archive:
                    with self.assertRaisesRegex(ValueError, 'part extruder'):
                        model_instances(archive, 4)

    def test_duplicate_part_assignment_rejected(self):
        fake_archive(self.path, duplicate_part=True)
        with ZipFile(self.path) as archive:
            with self.assertRaisesRegex(ValueError, 'Duplicate native'):
                read_part_slot_defaults(archive, 4)

    def test_engine_analysis_obj_recolors_correct_source_slots(self):
        import importlib.util
        if importlib.util.find_spec('fullspectrum_engine') is None:
            self.skipTest('FullSpectrum engine not installed in isolated source test environment')
        from fullspectrum_engine import export_preview_mesh
        fake_archive(self.path)
        palette = ['#123456', '#FFFFFF', '#61C680', '#000000']
        out = Path(self.tmp.name) / 'predicted.obj'
        with ZipFile(self.path) as archive:
            result, usage = export_preview_mesh(archive, palette, out,
                                                return_usage=True)
        self.assertEqual(usage, Counter({1: 1, 2: 2, 3: 1, 4: 2}))
        self.assertEqual(result, out)
        lines = out.read_text().splitlines()
        groups = Counter()
        current = None
        for line in lines:
            if line.startswith('usemtl '):
                current = int(line.rsplit('_', 1)[1])
            elif line.startswith('f '):
                groups[current] += 1
        self.assertEqual(groups, usage)
        self.assertTrue(out.with_suffix('.mtl').is_file())

    def test_bad_xml_rejected(self):
        fake_archive(self.path, bad_metadata=True)
        with ZipFile(self.path) as archive:
            with self.assertRaisesRegex(ValueError, 'malformed XML'):
                read_part_slot_defaults(archive, 4)

    def test_no_model_settings_preserves_legacy_parent_behavior(self):
        fake_archive(self.path)
        with ZipFile(self.path, 'r') as source:
            archive_path = Path(self.tmp.name) / 'no_settings.3mf'
            with ZipFile(archive_path, 'w') as dest:
                for name in source.namelist():
                    if name != 'Metadata/model_settings.config':
                        dest.writestr(name, source.read(name))
        with ZipFile(archive_path) as archive:
            self.assertEqual(read_part_slot_defaults(archive, 4), {})
            entries, _ = model_instances(archive, 4)
            self.assertTrue(all(e[-1] == 1 for e in entries))


if __name__ == '__main__':
    unittest.main()
