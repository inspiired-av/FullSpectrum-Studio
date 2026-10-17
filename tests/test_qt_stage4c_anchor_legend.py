"""Stage 4C: honest anchored viewport legend and nonintrusive stale lifecycle."""
from __future__ import annotations
import ast, importlib.util, os
from pathlib import Path
import unittest
from desktop.qt_app.anchor_legend_state import anchor_legend_rows, ANCHOR_OVERLAY_COLORS
ROOT=Path(__file__).resolve().parents[1]

def sample(count=6):
    return {'planningDetails':{'realSlots':count,'pinnedAnchorKeys':['k1'],
            'anchors':[dict(slot=i,key=f'k{i}',color=f'#{i:02X}BB55',
                            name=f'Example PLA {i}') for i in range(1,count+1)]}}

class AnchorStateTests(unittest.TestCase):
    def test_anchors_are_engine_paired_not_estimated(self):
        rows=anchor_legend_rows(sample())
        self.assertEqual(len(rows),6)
        self.assertEqual(rows[0]['overlay'], '#28B8D5')
        self.assertEqual(rows[0]['filament'],'#01BB55')
        self.assertEqual(rows[0]['name'],'Example PLA 1')
        self.assertTrue(rows[0]['pinned'])
        self.assertFalse(rows[1]['pinned'])

    def test_matches_palette_in_engine_source(self):
        tree=ast.parse((ROOT/'fullspectrum_engine.py').read_text(encoding='utf-8'))
        for fn in ('plan_analysis_preview_colors','analysis_preview_colors'):
            block=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==fn)
            assignment=next(n for n in ast.walk(block) if isinstance(n,ast.Assign) and
                any(isinstance(x,ast.Name) and x.id=='influence_palette' for x in n.targets))
            self.assertEqual(tuple(ast.literal_eval(assignment.value)),ANCHOR_OVERLAY_COLORS)

    def test_repeated_overlay_categories_are_truthful(self):
        rows=anchor_legend_rows(sample(8))
        self.assertEqual(rows[6]['overlay'],rows[0]['overlay'])
        self.assertEqual(rows[7]['overlay'],rows[1]['overlay'])

    def test_missing_or_corrupt_anchors_fail_closed(self):
        for invalid in (None,{}, {'planningDetails':{'anchors':[],'realSlots':6}}):
            self.assertEqual(anchor_legend_rows(invalid),())
        for edit in ({'slot':2},{'slot':0},{'color':'invalid'},{'name':''}):
            item=sample(2);item['planningDetails']['anchors'][0].update(edit)
            self.assertEqual(anchor_legend_rows(item),(),edit)

    def test_main_window_lifecycle_and_ui_placement(self):
        src=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertIn('AnchorInfluenceLegend(self.preview_surface)',src)
        self.assertIn("anchor_legend_rows(result) if meshes.get('influence')",src)
        self.assertIn('self.anchor_legend.set_rows(())',src)
        self.assertIn('self.anchor_legend.setVisible(False)',src)
        self.assertIn('not self._live_preview_stale and self.anchor_legend.has_rows',src)
        self.assertIn('self.preview_surface.set_mesh(target, preserve_camera=True)',src)
        legend=(ROOT/'desktop/qt_app/preview_legend.py').read_text(encoding='utf-8')
        self.assertIn('WA_TransparentForMouseEvents',legend)
        self.assertIn('parent.height()-self.height()-12',legend)
        self.assertIn('first recipe component',legend)

@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,'PySide6 unavailable')
class QtAnchorLegendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_widget_uses_lower_left_and_wont_block_orbit(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget
        from desktop.qt_app.preview_legend import AnchorInfluenceLegend
        parent=QWidget();parent.resize(550,450)
        legend=AnchorInfluenceLegend(parent)
        try:
            legend.set_rows(anchor_legend_rows(sample()))
            parent.show();legend.show();self.app.processEvents()
            self.assertTrue(legend.has_rows)
            self.assertTrue(legend.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            self.assertEqual(legend.x(),12)
            self.assertLessEqual(legend.y()+legend.height(),parent.height())
            parent.resize(430,230);self.app.processEvents()
            legend.position_over_viewport()
            self.assertLessEqual(legend.y()+legend.height(),parent.height())
            legend.set_rows(())
            self.assertFalse(legend.has_rows)
        finally:parent.close()

    def test_no_malformed_qt_stylesheets(self):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QWidget
        from desktop.qt_app.preview_legend import AnchorInfluenceLegend
        warnings=[]
        old=qInstallMessageHandler(lambda typ,context,msg:warnings.append(str(msg)))
        parent=QWidget();parent.resize(530,340)
        try:
            legend=AnchorInfluenceLegend(parent)
            legend.set_rows(anchor_legend_rows(sample()))
            parent.show();legend.show();self.app.processEvents()
        finally:
            parent.close();qInstallMessageHandler(old)
        self.assertFalse([w for w in warnings if 'Could not parse stylesheet' in w],warnings)

if __name__=='__main__': unittest.main()
