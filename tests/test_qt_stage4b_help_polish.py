"""Stage 4B help and forecast presentation regression tests."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'desktop/qt_app'
KEEP = {
    # Stage 4C adds one meaningful help button beside the preview mode selector.
    'preview_modes', 'source_palette_assignments',
    'live_forecast','expected_palette',
    'color_optimization','native_project_template','advanced_settings',
    'filament_source','filament_colors','protect_solid_colors',
}


class HelpPolishContractTests(unittest.TestCase):
    def test_python_sources_compile(self):
        for name in ('section_help.py','main_window.py','results_tab.py',
                     'filaments_tab.py','forecast_visuals.py'):
            ast.parse((UI/name).read_text(encoding='utf-8'))

    def test_only_meaningful_sections_have_help(self):
        source=(UI/'section_help.py').read_text(encoding='utf-8')
        tree=ast.parse(source)
        table=next(n for n in tree.body if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='TOPICS' for t in n.targets))
        keys={ast.literal_eval(k) for k in table.value.keys}
        self.assertEqual(keys, KEEP)
        main=(UI/'main_window.py').read_text(encoding='utf-8')
        self.assertIn("SectionHelpButton('preview_modes')", main)
        self.assertNotIn("SectionHelpButton('model_preview')", main)
        results=(UI/'results_tab.py').read_text(encoding='utf-8')
        self.assertNotIn("SectionHelpButton('optimization_details')",main)
        self.assertNotIn('help_heading(',results)
        self.assertNotIn('SectionHelpButton(',results)
        self.assertIn("_text('CURRENT SESSION', 'sectionTitle')",results)
        self.assertIn("_text('CURRENT ACTIVITY', 'sectionTitle')",results)
        self.assertIn("_text('EXISTING / GENERATED REPORT', 'sectionTitle')",results)

    def test_custom_library_links_are_actual_repo_examples(self):
        source=(UI/'section_help.py').read_text(encoding='utf-8')
        self.assertIn('README.md#custom-brands',source)
        self.assertIn('examples/custom-palette.example.json',source)
        self.assertIn('Custom filament library',source)
        self.assertIn('Save Filaments',source)
        self.assertIn('browser.setOpenExternalLinks(True)',source)

    def test_small_circle_uses_painter_and_does_not_clip_question_mark(self):
        source=(UI/'section_help.py').read_text(encoding='utf-8')
        self.assertIn('self.setFixedSize(20, 20)',source)
        self.assertIn('def paintEvent(self, event):',source)
        self.assertIn('painter.drawEllipse(QPointF(center_x, center_y), radius, radius)',source)
        self.assertIn("Qt.AlignmentFlag.AlignCenter, '?')",source)
        self.assertIn('circle_bounds(self.width(), self.height())',source)
        self.assertIn("self.setText('?')",source)

    def test_worst_match_is_under_expected_palette_and_gauges_have_caption_spacing(self):
        main=(UI/'main_window.py').read_text(encoding='utf-8')
        self.assertIn('inner.addWidget(self.worst_match_panel)',main)
        self.assertNotIn('col.addWidget(self.worst_match_panel)',main)
        visual=(UI/'forecast_visuals.py').read_text(encoding='utf-8')
        self.assertIn('painter.drawText(QRectF(0,y+diameter+7,width,17)',visual)
        self.assertIn('self.setMinimumSize(86, 101)',visual)
        self.assertIn("block.setFixedSize(24, 24)",visual)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,'PySide6 not installed')
class QtHelpPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_help_button_is_circular_with_visible_question_mark(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from desktop.qt_app.section_help import SectionHelpButton
        b=SectionHelpButton('filament_source')
        try:
            b.show();self.app.processEvents()
            self.assertEqual(b.text(),'?')
            self.assertEqual((b.width(),b.height()),(20,20))
            out=QImage(b.size(),QImage.Format.Format_ARGB32)
            out.fill(Qt.GlobalColor.transparent)
            b.render(out)
            # Corners should remain unpainted; '?' is bright in the middle.
            center=[out.pixelColor(x,y) for x in range(5,13) for y in range(5,13)]
            self.assertGreater(sum(c.green()>125 and c.blue()>130 for c in center),4)
            self.assertLess(out.pixelColor(0,0).alpha(),100)
        finally:b.close()

    def test_filament_source_dialog_has_working_links(self):
        from desktop.qt_app.section_help import SectionHelpButton
        from PySide6.QtWidgets import QTextBrowser
        b=SectionHelpButton('filament_source')
        try:
            d=b.create_dialog()
            try:
                browser=d.findChild(QTextBrowser)
                self.assertTrue(browser.openExternalLinks())
                html=browser.toHtml()
                self.assertIn('README.md#custom-brands',html)
                self.assertIn('custom-palette.example.json',html)
            finally:d.close()
        finally:b.close()

    def test_results_tab_has_no_help_controls(self):
        from desktop.qt_app.results_tab import ResultsTab
        from desktop.qt_app.section_help import SectionHelpButton
        w=ResultsTab()
        try:self.assertFalse(w.findChildren(SectionHelpButton))
        finally:w.close()

    def test_mac_style_worst_match_row(self):
        from desktop.qt_app.forecast_visuals import WorstMatchPanel
        p=WorstMatchPanel()
        try:
            p.set_forecast({'gapMessage':'Worst target #2088A0 becomes #4581A9 (dE 9.0).',
                            'maximumDeltaE':9.0})
            self.assertEqual(p.source[1].toolTip(),'Target: #2088A0')
            self.assertEqual(p.predicted[1].toolTip(),'Predicted: #4581A9')
            self.assertIn('ΔE 9.0',p.delta.text())
            p.set_forecast({})
            self.assertIn('unavailable',p.details.text().lower())
        finally:p.close()


if __name__=='__main__':unittest.main()
