"""Stage 5 v6: aligned compact slicer switch, visible-panel centered diagnostics, zoom depth."""
from __future__ import annotations
import ast
import importlib.util
import math
import os
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'desktop/qt_app/main_window.py'
RESULTS=ROOT/'desktop/qt_app/results_tab.py'
VIEWPORT=ROOT/'desktop/qt_app/gl_viewport.py'

class V6Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main=MAIN.read_text(encoding='utf-8-sig')
        cls.results=RESULTS.read_text(encoding='utf-8-sig')
        cls.viewport=VIEWPORT.read_text(encoding='utf-8-sig')

    def test_source_compiles(self):
        for text in (self.main,self.results,self.viewport):ast.parse(text)

    def test_mac_style_switch_is_shorter_and_has_no_inset(self):
        self.assertIn('self.slicer_segment.setMaximumWidth(268)',self.main)
        self.assertIn('slicer_row.setContentsMargins(0, 0, 0, 0)',self.main)
        self.assertIn('slicer_row.setSpacing(0)',self.main)
        self.assertIn("self.slicer_segment = ExportSlicerSegment()",self.main)
        self.assertIn('slicer_col.addWidget(self.slicer_segment, 0, Qt.AlignmentFlag.AlignLeft)',self.main)

    def test_export_action_is_separated_from_settings(self):
        self.assertIn("self.export_section_divider.setObjectName('exportActionDivider')",self.main)
        self.assertIn('col.addWidget(self.export_section_divider)',self.main)
        self.assertIn('col.addSpacing(8)',self.main)

    def test_diagnostics_centered_against_visible_viewport(self):
        self.assertIn('self.diagnostics_mode_group = QWidget(self)',self.results)
        self.assertIn('(self.width() - group.width()) // 2',self.results)
        self.assertIn('header.mapTo(self, QPoint(0, 0))',self.results)
        self.assertIn('self.diagnostics_header.installEventFilter(self)',self.results)
        self.assertIn('self._center_diagnostics_switch()',self.results)

    def test_zoom_clip_planes_are_bounded(self):
        t=ast.parse(self.viewport)
        node=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='_camera_clip_planes')
        module=ast.Module(body=[node],type_ignores=[])
        namespace={}
        exec(compile(ast.fix_missing_locations(module),'<clip helper>','exec'),namespace)
        clip=namespace['_camera_clip_planes']
        for distance in (0.16,0.25,1.0,3.2,16.0):
            near,far=clip(1.,distance)
            self.assertGreater(near,0.)
            self.assertGreater(far,distance+1.)
            self.assertLess(far/near,350.)
        self.assertIn('gl.glEnable(gl.GL_MULTISAMPLE)',self.viewport)
        self.assertIn('near,far=_camera_clip_planes(radius,eye_distance)',self.viewport)

@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,'PySide6 not installed')
class V6QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def open_window(self):
        from desktop.qt_app.main_window import MainWindow
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        w=MainWindow(settings_path=Path(temp.name)/'settings.json')
        self.addCleanup(w.close)
        w.show();w.tabs.setCurrentWidget(w.results_panel)
        self.app.processEvents()
        return w

    def test_segment_width_and_divider(self):
        w=self.open_window()
        self.assertLessEqual(w.slicer_segment.width(),268)
        self.assertEqual(w.slicer_segment.layout().spacing(),0)
        self.assertEqual(w.slicer_segment.layout().contentsMargins().left(),0)
        self.assertTrue(w.export_section_divider.isVisibleTo(w))

    def test_centered_diagnostics_across_widths_and_modes(self):
        w=self.open_window()
        tab=w.results_panel
        for width,height in ((1220,760),(1640,1040)):
            w.resize(width,height)
            self.app.processEvents()
            for name in ('activity','report'):
                tab._select_diagnostics(name)
                self.app.processEvents()
                center=tab.diagnostics_mode_group.mapTo(tab,tab.diagnostics_mode_group.rect().center()).x()
                self.assertLess(abs(center-tab.width()/2),30,(width,name,center,tab.width()))
                self.assertTrue(tab.diagnostics_mode_group.isVisibleTo(w))

if __name__=='__main__': unittest.main()
