"""Optional lightweight Qt layout check; doesn't construct an OpenGL viewport."""
from __future__ import annotations

import os
import unittest

try:
    from PySide6.QtWidgets import QApplication, QLabel, QWidget
    from desktop.qt_app.preview_toolbar import AdaptivePreviewToolbar
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, 'PySide6 is not installed')
class AdaptiveToolbarRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_wide_one_row_narrow_two_rows_without_clipping(self):
        heading = QLabel('MODEL PREVIEW')
        view, plate, camera = [QWidget() for _ in range(3)]
        for widget, width in ((view, 205), (plate, 173), (camera, 88)):
            widget.setFixedWidth(width)
            widget.setFixedHeight(36)
        bar = AdaptivePreviewToolbar(heading, view, plate, camera)
        bar.resize(850, 80)
        bar.show()
        self.app.processEvents()
        bar.refresh()
        self.assertFalse(bar._compact_box.isVisible())
        bar.resize(410, 100)
        self.app.processEvents()
        bar.refresh()
        self.assertTrue(bar._compact_box.isVisible())
        self.assertLessEqual(view.geometry().right(), bar.width()+1)
        self.assertLessEqual(camera.mapTo(bar, camera.rect().topRight()).x(), bar.width()+1)
        bar.close()
        bar.deleteLater()
        self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
