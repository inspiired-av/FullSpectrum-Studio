"""Native-template preview images should not retain blank template thumbnails."""
import io
import unittest
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from native_preview_thumbnail import add_native_thumbnails, render_plate_preview, _single_paint_slot
from PIL import Image

SAMPLE=(
  '<?xml version="1.0" encoding="utf-8"?>'
  '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
  '<resources><object id="1"><mesh><vertices>'
  '<vertex x="0" y="0" z="0"/><vertex x="0" y="20" z="0"/>'
  '<vertex x="0" y="20" z="30"/><vertex x="0" y="0" z="30"/>'
  '</vertices><triangles>'
  '<triangle v1="0" v2="1" v3="2" paint_color="0C"/>'
  '<triangle v1="0" v2="2" v3="3" paint_color="1C"/>'
  '</triangles></mesh></object></resources><build/></model>'
).encode('utf-8')

class NativeThumbnailTests(unittest.TestCase):
    def test_leaf_codes(self):
        for raw,expected in [('8',2),('0C',3),('1C',4),('DC',16),('4FC',22)]:
            self.assertEqual(_single_paint_slot(raw),expected)

    def test_thumbnails_derive_from_model_and_are_not_blank(self):
        colors=['#000000','#FFFFFF','#FF0000','#0000FF']
        payload={name:b'blank' for name in (
            'Metadata/plate_1.png','Metadata/plate_1_small.png',
            'Metadata/plate_no_light_1.png','Metadata/top_1.png','Metadata/pick_1.png')}
        add_native_thumbnails(payload,SAMPLE,{'filament_colour':colors})
        self.assertNotEqual(payload['Metadata/plate_1.png'],b'blank')
        big=Image.open(io.BytesIO(payload['Metadata/plate_1.png'])).convert('RGB')
        small=Image.open(io.BytesIO(payload['Metadata/plate_1_small.png']))
        self.assertEqual(big.size,(512,512))
        self.assertEqual(small.size,(128,128))
        self.assertGreaterEqual(len(set(big.get_flattened_data())),4)

if __name__=='__main__':
    unittest.main()
