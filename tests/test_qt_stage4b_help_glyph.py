"""Regression for blank contextual-help glyphs with global Qt padding."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'desktop' / 'qt_app' / 'section_help.py'


class HelpGlyphSourceTests(unittest.TestCase):
    def test_text_only_and_padding_override(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertIn('self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)', source)
        self.assertIn("self.setText('?')", source)
        self.assertIn('painter.drawEllipse(QPointF(center_x, center_y), radius, radius)', source)
        self.assertIn("Qt.AlignmentFlag.AlignCenter, '?')", source)
        self.assertIn('self.setFixedSize(20, 20)', source)
        self.assertIn('self.setToolTip(topic.summary)', source)
        self.assertIn('self.clicked.connect(self.show_help)', source)


    def test_centered_circle_even_if_qt_stretches_widget(self):
        import ast
        source = SOURCE.read_text(encoding='utf-8')
        parsed = ast.parse(source)
        function = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == 'circle_bounds')
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                     str(SOURCE), 'exec'), namespace)
        centered_circle = namespace['circle_bounds']
        for width,height in ((20,20),(12,26),(26,12),(18,40)):
            x,y,r = centered_circle(width,height)
            self.assertAlmostEqual(x,width/2)
            self.assertAlmostEqual(y,height/2)
            self.assertGreater(r,0)
            self.assertLessEqual(2*r,min(width,height))
        self.assertEqual(centered_circle(12,26)[2], centered_circle(26,12)[2])


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None, 'PySide6 not installed')
class HelpGlyphRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        from desktop.qt_app.theme import apply_theme
        apply_theme(cls.app)

    def test_foreground_question_mark_is_visible_with_production_stylesheet(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from desktop.qt_app.section_help import SectionHelpButton, TOPICS
        button = SectionHelpButton('live_forecast')
        self.addCleanup(button.close)
        button.show()
        self.app.processEvents()
        self.assertEqual(button.text(), '?')
        self.assertEqual(button.toolTip(), TOPICS['live_forecast'].summary)
        # Capture the actual widget under the application-wide stylesheet;
        # count bright cyan glyph pixels in the interior, excluding the ring.
        image = QImage(button.size(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        button.render(image)
        bright = 0
        for y in range(5, button.height()-5):
            for x in range(5, button.width()-5):
                color = image.pixelColor(x,y)
                if color.red() > 105 and color.green() > 145 and color.blue() > 145:
                    bright += 1
        self.assertGreater(bright, 3, 'Help question mark is clipped or invisible')


if __name__ == '__main__':
    unittest.main()
