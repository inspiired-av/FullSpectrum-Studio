"""Stage 3C UX: reversible selection and explicit protection legend/tint."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class CodeCompatibilityTests(unittest.TestCase):
    def test_protected_tint_is_opt_in(self):
        shader=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8')
        self.assertIn('uniform int showProtectedOverlay;',shader)
        self.assertIn('} else if (showProtectedOverlay != 0) {',shader)
        self.assertIn('self.show_protected_overlay=False',shader)
        self.assertIn("'showProtectedOverlay'",shader)
        self.assertIn('def set_protected_overlay(self, enabled):',shader)
        self.assertIn('def set_highlights(self, selected=None, protected=()):',shader)

    def test_shader_data_not_rebuilt_on_selection(self):
        viewer=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8')
        start=viewer.index('    def set_protected_overlay(')
        end=viewer.index('    def reset_camera(',start)
        self.assertNotIn('_flatten_faces',viewer[start:end])
        self.assertNotIn('glBufferData',viewer[start:end])

    def test_palette_uses_non_destructive_protection_dot(self):
        swatch=(ROOT/'desktop/qt_app/source_palette.py').read_text(encoding='utf-8')
        self.assertIn('def paintEvent(self, event):',swatch)
        self.assertIn('if self._protected:',swatch)
        self.assertIn('painter.drawEllipse(',swatch)
        self.assertIn('Protected source color',swatch)

    def test_selection_has_clear_and_shortcut(self):
        ui=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertIn('def _toggle_palette_color(self, color):',ui)
        self.assertIn('def _clear_palette_selection(self):',ui)
        self.assertIn('def _show_protection_controls(self):',ui)
        self.assertIn("QKeySequence('Escape')",ui)
        self.assertIn('self.preview_surface.background_clicked.connect(',ui)
        self.assertIn('chip.chosen.connect(self._toggle_palette_color)',ui)
        self.assertIn('self.filaments_panel.select_source_color(color)',ui)

    def test_clear_synchronizes_filaments_selection(self):
        tab=(ROOT/'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        self.assertIn('self.solid_table.clearSelection()',tab)
        self.assertIn('self.solid_table.setCurrentCell(-1,-1)',tab)
        self.assertIn('self.select_source_color(color)',tab)


try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.main_window import MainWindow
    from desktop.qt_app.mesh_loader import _build_mesh
except ImportError:
    QApplication=None


@unittest.skipUnless(QApplication is not None,'PySide6 not available')
class QtBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_toggle_and_clear_sync_from_palette_to_table(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            window=MainWindow(settings_path=Path(tmp)/'settings.json')
            try:
                model=_build_mesh([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)],'m',['#ABCDEF'])
                window._preview_loaded(0,window.state.model_path,model,None)
                tab=window.filaments_panel
                tab.source_colors={'#ABCDEF':1}
                tab._populate_solid_colors()
                window._toggle_palette_color('#ABCDEF')
                self.assertEqual(window._source_palette_selected,'#ABCDEF')
                self.assertEqual(tab._current_color(),'#ABCDEF')
                self.assertTrue(window.clear_palette_button.isEnabled())
                window._toggle_palette_color('#ABCDEF')
                self.assertIsNone(window._source_palette_selected)
                self.assertIsNone(tab._current_color())
                self.assertFalse(window.clear_palette_button.isEnabled())
                window._toggle_palette_color('#ABCDEF')
                window._clear_palette_selection()
                self.assertIsNone(tab._current_color())
            finally:
                window.close()

    def test_protected_overlay_is_off_until_explicitly_enabled(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            w=MainWindow(settings_path=Path(tmp)/'s.json')
            try:
                mesh=_build_mesh([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)],'m',['#FF0000'])
                w._preview_loaded(0,w.state.model_path,mesh,None)
                baseline=w.preview_surface._data
                w._protections_updated({'#FF0000':'key'})
                self.assertTrue(w.tint_protected.isEnabled())
                self.assertFalse(w.tint_protected.isChecked())
                self.assertFalse(w.preview_surface.show_protected_overlay)
                w.tint_protected.setChecked(True)
                self.assertTrue(w.preview_surface.show_protected_overlay)
                w._select_palette_color('#FF0000')
                self.assertTrue(next(iter(w._source_palette_cells))._selected)
                self.assertTrue(next(iter(w._source_palette_cells))._protected)
                self.assertIs(baseline,w.preview_surface._data)
                w._protections_updated({})
                self.assertFalse(w.tint_protected.isChecked())
                self.assertFalse(w.tint_protected.isEnabled())
                self.assertFalse(w.preview_surface.show_protected_overlay)
            finally:
                w.close()

    def test_manage_shortcut_does_not_duplicate_controls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            w=MainWindow(settings_path=Path(tmp)/'s.json')
            try:
                w._show_protection_controls()
                self.assertIs(w.tabs.currentWidget(),w.filaments_panel)
            finally:w.close()


if __name__=='__main__':unittest.main()
