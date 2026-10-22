"""Stage 5 v8: one painted, gap-free slicer selection with unified hover."""
from __future__ import annotations
import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT/'desktop/qt_app/main_window.py'
PILL = ROOT/'desktop/qt_app/export_slicer_segment.py'


class SlicerPillContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding='utf-8-sig')
        cls.pill = PILL.read_text(encoding='utf-8-sig')

    def test_sources_compile(self):
        ast.parse(self.main)
        ast.parse(self.pill)

    def test_painter_draws_both_halves_inside_one_canvas(self):
        self.assertIn('painter.drawRoundedRect(bounds, radius, radius)', self.pill)
        self.assertIn('painter.drawRoundedRect(selected, radius, radius)', self.pill)
        self.assertIn('QPainter.RenderHint.Antialiasing', self.pill)
        self.assertIn("self.selected_color = QColor('#2183f5')", self.pill)

    def test_hover_changes_parent_background_not_buttons(self):
        self.assertIn("'#343b46' if self._hovered else '#282a30'",self.pill)
        self.assertNotIn('QPushButton:hover:!checked',self.main)
        self.assertIn("'QPushButton:hover { background: transparent; }'",self.main)
        self.assertIn('self.slicer_segment.watch_button(button)',self.main)

    def test_no_padding_gap_and_existing_preference_binding(self):
        for phrase in ('slicer_row.setContentsMargins(0, 0, 0, 0)',
                       'slicer_row.setSpacing(0)',
                       'self.slicer_segment.setMaximumWidth(268)',
                       'self.output_application.currentIndexChanged.connect(self._sync_slicer_choice_buttons)',
                       'self.slicer_segment.set_selected(1 if value == \'Bambu Studio\' else 0)'):
            self.assertIn(phrase,self.main)
        self.assertEqual(self.main.count('    def _sync_slicer_choice_buttons('),1)

    def test_removed_legacy_assertions(self):
        help_text=(ROOT/'tests/test_qt_stage4b_help_polish.py').read_text(encoding='utf-8-sig')
        export_text=(ROOT/'tests/test_qt_stage4dc_export_workspace.py').read_text(encoding='utf-8-sig')
        v4=(ROOT/'tests/test_qt_stage5_compact_export_v4.py').read_text(encoding='utf-8-sig')
        self.assertNotIn('self.assertIn("_text(\'OUTPUT SETUP\', \'sectionTitle\')",results)',help_text)
        self.assertNotIn("'OUTPUT SETUP', 'NATIVE 3MF EXPORT'",export_text)
        self.assertNotIn('self.assertIn("grid.addWidget(slicer_box, 3, 0)", s)',v4)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,'PySide6 not installed')
class SlicerPillQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def create_window(self):
        from desktop.qt_app.main_window import MainWindow
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        window=MainWindow(settings_path=Path(tmp.name)/'settings.json')
        self.addCleanup(window.close)
        window.show()
        window.tabs.setCurrentWidget(window.results_panel)
        self.app.processEvents()
        return window

    def test_clicks_restore_slicer_preference_and_pill_fill(self):
        window=self.create_window()
        segment=window.slicer_segment
        w,h=segment.width(),segment.height()
        self.assertGreater(w,120)
        self.assertLessEqual(w,268)
        self.assertGreaterEqual(h,36)
        # Sample near the lower edge of each half, away from button text.
        def colors():
            img=segment.grab().toImage()
            return img.pixelColor(w//4,h-5).name(),img.pixelColor(3*w//4,h-5).name()
        window.slicer_choice_buttons['OrcaSlicer'].click()
        self.app.processEvents()
        left,right=colors()
        self.assertEqual(left,'#2183f5')
        self.assertNotEqual(right,'#2183f5')
        window.slicer_choice_buttons['Bambu Studio'].click()
        self.app.processEvents()
        left,right=colors()
        self.assertNotEqual(left,'#2183f5')
        self.assertEqual(right,'#2183f5')
        self.assertEqual(window.output_application.currentData(),'Bambu Studio')

    def test_container_hover_is_single_uniform_paint(self):
        window=self.create_window()
        segment=window.slicer_segment
        window.slicer_choice_buttons['OrcaSlicer'].click()
        self.app.processEvents()
        w,h=segment.width(),segment.height()
        segment._set_hovered(False)
        before=segment.grab().toImage().pixelColor(3*w//4,h-5).name()
        segment._set_hovered(True)
        after=segment.grab().toImage().pixelColor(3*w//4,h-5).name()
        self.assertNotEqual(before,after)
        self.assertEqual(after,'#343b46')


if __name__=='__main__':
    unittest.main()
