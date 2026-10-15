"""Phase 3 core tests; no proprietary models or slicer installation required."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from direct_source_palette import (
    load_exact_color_targets, mapped_source_paint_colors, rewrite_staged_faces,
    fallback_representatives, write_predicted_obj,
)


class DirectSourcePaletteTests(unittest.TestCase):
    def fixture(self, folder):
        source = Path(folder) / "standard-colors.3mf"
        model = '''<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
       xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
       unit="millimeter">
<resources>
  <m:colorgroup id="7">
    <m:color color="#9199A4"/><m:color color="#1188BB"/><m:color color="#55CC22"/>
  </m:colorgroup>
  <object id="1" type="model"><mesh><vertices>
    <vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>
    <vertex x="0" y="1" z="0"/><vertex x="0" y="0" z="1"/>
  </vertices><triangles>
    <triangle v1="0" v2="1" v3="2" pid="7" p1="0"/>
    <triangle v1="0" v2="1" v3="3" pid="7" p1="1"/>
    <triangle v1="0" v2="2" v3="3" pid="7" p1="2"/>
    <triangle v1="1" v2="2" v3="3" pid="7" p1="1"/>
  </triangles></mesh></object>
</resources><build><item objectid="1"/></build></model>
'''
        with zipfile.ZipFile(source,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("3D/3dmodel.model",model)
        return source

    def test_exact_source_palette_and_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = load_exact_color_targets(self.fixture(tmp))
            self.assertEqual(source["triangle_count"], 4)
            self.assertEqual(source["colors"], ["#9199A4", "#1188BB", "#55CC22"])
            self.assertEqual(dict(source["usage"]), {1:1,2:2,3:1})
            self.assertEqual(source["source_slots"]["#9199A4"],1)
            self.assertEqual(source["approximate_vertex_blends"],0)
            mapped = mapped_source_paint_colors(source,{1:2,2:5,3:6},lambda slot:f"{slot:X}C",6)
            self.assertEqual(mapped,["2C","5C","6C","5C"])

    def test_write_exact_repaint_preserves_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            part=directory/"3D"/"Objects"/"object_1.model"
            part.parent.mkdir(parents=True)
            original=(b'<model><mesh><vertices><vertex x="0"/></vertices><triangles>\n'
                      + b'\n'.join(f'<triangle v1="0" v2="1" v3="2" paint_color="{c}"/>'.encode()
                                   for c in ['4','4','4','4'])
                      + b'\n</triangles></mesh></model>')
            part.write_bytes(original)
            path, counts=rewrite_staged_faces(directory,["8","1C","2C","1C"])
            result=part.read_bytes()
            self.assertEqual(path,["3D/Objects/object_1.model"])
            self.assertEqual(counts,{"8":1,"1C":2,"2C":1})
            self.assertEqual(result.count(b'<triangle '),4)
            self.assertIn(b'<vertex x="0"/>',result)
            self.assertEqual(result.replace(b'"8"',b'"4"').replace(b'"1C"',b'"4"').replace(b'"2C"',b'"4"'),original)

    def test_rejects_mismatched_triangle_count_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            path=directory/"3D"/"Objects"/"object_1.model"
            path.parent.mkdir(parents=True)
            original=b'<triangle v1="0" v2="1" v3="2" paint_color="4"/>'
            path.write_bytes(original)
            with self.assertRaisesRegex(RuntimeError,"Triangle mismatch"):
                rewrite_staged_faces(directory,["8","C"])
            self.assertEqual(path.read_bytes(),original)

    def test_rejects_missing_output_slot_and_bad_encode(self):
        source={"source_slots":{"#112233":1},"face_colors":["#112233"]}
        with self.assertRaisesRegex(RuntimeError,"lacks a printable output slot"):
            mapped_source_paint_colors(source,{1:33},str,32)
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            part=directory/"3D"/"Objects"/"object_1.model"
            part.parent.mkdir(parents=True)
            part.write_bytes(b'<triangle paint_color="4"/>')
            with self.assertRaisesRegex(RuntimeError,"invalid 3MF paint state"):
                rewrite_staged_faces(directory,["nothex"])

    def test_preview_obj_matches_direct_color_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=load_exact_color_targets(self.fixture(tmp))
            out=write_predicted_obj(source,{1:2,2:5,3:6},
                                    ['#000000','#9199A4','#FFFFFF','#112233','#08ABFB','#55CC22'],
                                    Path(tmp)/"predicted.obj")
            mesh=out.read_text()
            material=out.with_suffix(".mtl").read_text()
            self.assertEqual(mesh.count('\nf '),4)
            self.assertEqual(mesh.count('usemtl predicted_5'),2)
            self.assertIn('usemtl predicted_2',mesh)
            self.assertIn('newmtl predicted_6',material)

    def test_representatives_use_property_colors_only(self):
        def distance(a,b):
            return abs(int(a[1:],16)-int(b[1:],16))
        reps=fallback_representatives(['#000000','#FFFFFF'],['#111111','#EEEEEE'],distance)
        self.assertEqual(reps,[1,2])

    def test_optional_real_world_vsla_color_count(self):
        path=Path(__file__).resolve().parents[1]/'VSLA v4_SOLID_NoFilter.3mf'
        if not path.is_file():
            self.skipTest('Private VSLA test file not included in public repository')
        source=load_exact_color_targets(path)
        self.assertEqual(source['triangle_count'],1304)
        self.assertEqual(len(source['colors']),59)


if __name__ == '__main__':
    unittest.main()
