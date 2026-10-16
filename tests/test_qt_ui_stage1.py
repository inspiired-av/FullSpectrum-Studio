"""Qt Stage 1 regression tests: safe to run without PySide6 installed."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from desktop.qt_app.shell_state import (
    ShellState, display_filename, MODEL_FILE_FILTER, REFERENCE_FILE_FILTER,
)
from desktop.qt_app import theme

ROOT = Path(__file__).resolve().parents[1]


class ShellStateTests(unittest.TestCase):
    def test_cancelled_dialog_does_not_clear_previous_model(self):
        s = ShellState()
        self.assertTrue(s.select_model('C:\\Models\\test.3mf'))
        self.assertFalse(s.select_model(''))
        self.assertEqual(s.model_path, 'C:\\Models\\test.3mf')

    def test_reference_stays_independent_of_model(self):
        s = ShellState()
        s.select_model('/tmp/test.3mf')
        s.select_reference('/tmp/example.png')
        self.assertEqual(s.model_path, '/tmp/test.3mf')
        self.assertEqual(s.reference_path, '/tmp/example.png')
        self.assertFalse(s.select_reference('bad\x00path'))

    def test_filename_displays_windows_and_unix_paths(self):
        self.assertEqual(display_filename('C:\\a\\b\\obj.3mf'), 'obj.3mf')
        self.assertEqual(display_filename('/tmp/painted.3mf'), 'painted.3mf')
        self.assertEqual(display_filename(''), 'No model selected')

    def test_file_dialogs_support_existing_workflow_inputs(self):
        for extension in ('.3mf', '.obj', '.glb'):
            self.assertIn('*' + extension, MODEL_FILE_FILTER)
        for extension in ('.png', '.jpg', '.glb'):
            self.assertIn('*' + extension, REFERENCE_FILE_FILTER)

    def test_theme_is_dark_and_has_accessible_focus_style(self):
        self.assertEqual(theme.COLORS['background'], '#0f1216')
        self.assertIn('QPushButton:focus', theme.STYLE)
        self.assertIn('QTabBar::tab:selected', theme.STYLE)

    def test_existing_frontend_does_not_need_qt(self):
        # Importing the new package must never import the Qt libraries or engine.
        code = 'import desktop.qt_app, desktop.qt_app.shell_state, desktop.qt_app.theme; '
        code += 'import sys; assert "PySide6" not in sys.modules; '
        code += 'assert "fullspectrum_engine" not in sys.modules; '
        code += 'assert "tkinter" not in sys.modules'
        p = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_shell_never_imports_engine_or_tkinter(self):
        contents = (ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertNotIn('from fullspectrum_engine import', contents)
        self.assertNotIn('import tkinter', contents)
        self.assertIn('QSplitter', contents)
        self.assertIn('QTabWidget', contents)

    def test_qt_dependency_stays_separate(self):
        requirements = (ROOT/'requirements-qt.txt').read_text(encoding='utf-8')
        self.assertIn('PySide6', requirements)
        self.assertTrue((ROOT/'desktop/qt_app/__main__.py').is_file())


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is optional for Stage 1')
class OptionalQtSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        from desktop.qt_app.theme import apply_theme
        apply_theme(cls.app)

    def test_window_renders_and_tabs_work_without_engine(self):
        from desktop.qt_app.main_window import MainWindow
        window = MainWindow()
        self.addCleanup(window.close)
        self.assertEqual(window.tabs.count(), 3)
        self.assertEqual([window.tabs.tabText(i) for i in range(3)],
                         ['Plan', 'Filaments', 'Results'])
        self.assertFalse(window.compose_button.isEnabled())
        self.assertFalse(window.preview_mode.isEnabled())
        self.assertTrue(window.open_button.isEnabled())
        window.tabs.setCurrentIndex(2)
        self.assertEqual(window.tabs.currentIndex(), 2)

    def test_model_path_selected_without_touching_disk(self):
        from desktop.qt_app.main_window import MainWindow
        window = MainWindow()
        self.addCleanup(window.close)
        with patch('desktop.qt_app.main_window.QFileDialog.getOpenFileName',
                   return_value=('C:/test/model.3mf', '')):
            window.open_button.click()
        self.assertEqual(window.state.model_path, 'C:/test/model.3mf')
        self.assertEqual(window.project_subtitle.text(), 'model.3mf')


if __name__ == '__main__':
    unittest.main()
