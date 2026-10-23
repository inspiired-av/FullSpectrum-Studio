"""First Advanced 3D Preview increment: safe file drops and viewport controls."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from desktop.qt_app.preview_stage6a import classify_model_drop, SUPPORTED_MODEL_SUFFIXES

ROOT = Path(__file__).resolve().parents[1]


class ModelDropTests(unittest.TestCase):
    def test_exact_model_types(self):
        self.assertEqual(SUPPORTED_MODEL_SUFFIXES, {'.3mf', '.obj', '.glb'})

    def test_case_insensitive_local_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'Shape.3MF'
            p.write_bytes(b'example')
            self.assertEqual(classify_model_drop([p]), (str(p), ''))

    def test_unsupported_extension_does_not_open(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'unsafe.exe'
            p.write_bytes(b'example')
            self.assertIsNone(classify_model_drop([p])[0])

    def test_missing_file_does_not_open(self):
        self.assertIsNone(classify_model_drop(['missing.obj'])[0])

    def test_multiple_or_empty_files_rejected(self):
        self.assertIsNone(classify_model_drop([])[0])
        self.assertIsNone(classify_model_drop(['a.obj', 'b.obj'])[0])

    def test_non_path_input_rejected(self):
        self.assertIsNone(classify_model_drop([None])[0])
        self.assertIsNone(classify_model_drop(['bad\x00file.3mf'])[0])

    def test_python_source_parses(self):
        for path in ('desktop/qt_app/gl_viewport.py',
                     'desktop/qt_app/preview_chrome.py',
                     'desktop/qt_app/main_window.py',
                     'desktop/qt_app/export_ui_icons.py'):
            with self.subTest(path=path):
                ast.parse((ROOT / path).read_text(encoding='utf-8'))


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 unavailable')
class QtPreviewControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        from desktop.qt_app.main_window import MainWindow
        from qt_test_cleanup import dispose_test_widget
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        w = MainWindow(settings_path=Path(self.tmp.name) / 'settings.json')
        self.addCleanup(dispose_test_widget, w)
        w.show()
        self.app.processEvents()
        return w

    def test_sidebar_toggle_and_expand_restore(self):
        w = self.make_window()
        self.assertTrue(w.workspace_sidebar.isVisible())
        w.sidebar_toggle.click()
        self.app.processEvents()
        self.assertFalse(w.workspace_sidebar.isVisible())
        w.sidebar_toggle.click()
        self.app.processEvents()
        self.assertTrue(w.workspace_sidebar.isVisible())
        w.expand_preview_toggle.click()
        self.app.processEvents()
        self.assertTrue(w.isMaximized())
        self.assertFalse(w.isFullScreen())
        self.assertTrue(w.preview_mode.isVisible())
        self.assertFalse(w.workspace_header.isVisible())
        self.assertFalse(w.workspace_sidebar.isVisible())
        self.assertFalse(w._source_palette_area.isVisible())
        w.expand_preview_toggle.click()
        self.app.processEvents()
        self.assertFalse(w.isFullScreen())
        self.assertTrue(w.workspace_sidebar.isVisible())
        self.assertTrue(w._source_palette_area.isVisible())

    def test_metadata_forecast_stale_and_export_drop_gate(self):
        w = self.make_window()
        overlay = w.preview_chrome
        overlay.set_model('test.3mf', 750, 1000, sampled=True)
        # Model title/count already appear in header/status; no duplicate.
        self.assertTrue(overlay.model_label.isHidden())
        self.assertEqual(overlay.model_label.toolTip(), '')
        overlay.set_estimate(92.25)
        self.assertEqual(overlay.estimate_label.x(), 12)
        self.assertEqual(overlay.estimate_label.y(), 12)
        self.assertIn('92.2%', overlay.estimate_label.text())
        overlay.mark_outdated()
        self.assertEqual(overlay.estimate_label.text(), 'Forecast outdated')
        overlay.set_estimate(None)
        self.assertTrue(overlay.estimate_label.isHidden())
        w.preview_surface.set_drop_enabled(False)
        self.assertFalse(w.preview_surface._drop_enabled)
        w.preview_surface.set_drop_enabled(True)
        self.assertTrue(w.preview_surface._drop_enabled)


    def test_camera_reset_and_expand_are_independent(self):
        w = self.make_window()
        w.preview_surface.yaw = 0.7
        w.preview_surface.zoom = 3.5
        w.reset_camera_button.setEnabled(True)  # no source mesh needed for camera state
        w.reset_camera_button.click()
        self.assertAlmostEqual(w.preview_surface.yaw, -1.47)
        self.assertAlmostEqual(w.preview_surface.zoom, 1.0)
        self.assertFalse(w.isFullScreen())
        self.assertFalse(w.expand_preview_toggle.isChecked())
        self.assertIn('Reset camera', w.reset_camera_button.toolTip())
        w.expand_preview_toggle.click()
        self.app.processEvents()
        self.assertTrue(w.isMaximized())
        self.assertFalse(w.isFullScreen())
        self.assertTrue(w.preview_mode.isVisible())
        w._handle_view_escape()
        self.app.processEvents()
        self.assertFalse(w.isFullScreen())
        self.assertFalse(w.expand_preview_toggle.isChecked())

    def test_expand_preserves_hidden_sidebar_and_window_maximization(self):
        w = self.make_window()
        w.sidebar_toggle.setChecked(False)
        self.app.processEvents()
        w.showMaximized()
        self.app.processEvents()
        w.expand_preview_toggle.setChecked(True)
        self.app.processEvents()
        self.assertTrue(w.isMaximized())
        self.assertFalse(w.isFullScreen())
        w.expand_preview_toggle.setChecked(False)
        self.app.processEvents()
        self.assertTrue(w.isMaximized())
        self.assertTrue(w.workspace_sidebar.isHidden())
        self.assertFalse(w.sidebar_toggle.isChecked())

    def test_preview_mode_dropdown_is_visible_in_expanded_view(self):
        w = self.make_window()
        w.preview_mode.setEnabled(True)
        names = [w.preview_mode.itemText(i) for i in range(w.preview_mode.count())]
        self.assertEqual(names, ['Original', 'Predicted', 'Color Loss',
                                 'Anchor Influence', 'Wireframe'])
        self.assertEqual(w.preview_mode.maxVisibleItems(), len(names))
        w.expand_preview_toggle.setChecked(True)
        self.app.processEvents()
        self.assertFalse(w.isFullScreen())
        # On Windows the default popup must be able to appear above the model.
        w.preview_mode.showPopup()
        self.app.processEvents()
        self.assertTrue(w.preview_mode.view().isVisible())
        w.preview_mode.hidePopup()
        self.app.processEvents()

    def test_expansion_never_uses_native_fullscreen(self):
        source = (ROOT / 'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        method = source.split('    def _set_expanded_preview(self, expanded):', 1)[1]
        method = method.split('    def _handle_view_escape(self):', 1)[0]
        self.assertNotIn('self.showFullScreen()', method)
        self.assertIn('self.showMaximized()', method)
        self.assertIn('self.workspace_sidebar.hide()', method)


if __name__ == '__main__':
    unittest.main()
