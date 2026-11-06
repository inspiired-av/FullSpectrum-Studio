"""Preview toolbar controls, source policy, and plate-save intent.

Structural checks do not import OpenGL. Optional Qt checks require PySide6 and
are confined to lightweight toolbar widgets (no QOpenGLWidget creation).
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
PICKER = ROOT / 'desktop/qt_app/plate_ui.py'
STATE = ROOT / 'desktop/qt_app/preview_toolbar_state.py'


def method_source(source, method):
    parsed = ast.parse(source)
    main = next(x for x in parsed.body if isinstance(x, ast.ClassDef) and x.name=='MainWindow')
    node = next(x for x in main.body if isinstance(x,ast.FunctionDef) and x.name==method)
    return ast.get_source_segment(source,node)


class PreviewSourcePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('preview_toolbar_state', STATE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.state = staticmethod(module.preview_options_state)

    def test_without_model_menu_is_hidden_and_import_disabled(self):
        state=self.state(False,True,True,True)
        self.assertFalse(state['menu_visible'])
        self.assertFalse(state['import_enabled'])
        self.assertFalse(state['sources_visible'])

    def test_with_model_import_is_available_before_any_forecast(self):
        state=self.state(True,False,False,False)
        self.assertTrue(state['menu_visible'])
        self.assertTrue(state['import_enabled'])
        self.assertFalse(state['sources_visible'])

    def test_both_sources_are_explicit_without_running_forecast(self):
        state=self.state(True,True,True,True)
        self.assertTrue(state['sources_visible'])
        self.assertTrue(state['imported_checked'])
        self.assertFalse(state['live_checked'])
        state=self.state(True,True,True,False)
        self.assertTrue(state['live_checked'])
        self.assertFalse(state['imported_checked'])

    def test_missing_source_cannot_be_selected(self):
        state=self.state(True,True,False,False)
        self.assertTrue(state['live_enabled'])
        self.assertFalse(state['imported_enabled'])
        self.assertFalse(state['sources_visible'])


class PreviewToolbarStructuralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main=MAIN.read_text(encoding='utf-8-sig')
        cls.picker=PICKER.read_text(encoding='utf-8-sig')
        ast.parse(cls.main)
        ast.parse(cls.picker)

    def test_old_import_button_replaced_by_optional_menu_action(self):
        self.assertNotIn('self.load_predicted_button',self.main)
        self.assertIn("self.preview_import_action = self.preview_options_menu.addAction('Import Predicted OBJ…')",self.main)
        self.assertIn('self.preview_options_button.hide()',self.main)
        self.assertIn('self._update_preview_options()',method_source(self.main,'_preview_loaded'))
        self.assertIn('self.preview_options_button.setVisible',method_source(self.main,'_update_preview_options'))

    def test_import_preserves_obj_mtl_color_check_and_stale_guard(self):
        opened=method_source(self.main,'_open_predicted')
        loaded=method_source(self.main,'_predicted_loaded')
        self.assertIn('ModelLoadWorker(path,self)',opened)
        self.assertIn('self._predicted_serial+=1',opened)
        self.assertIn("'Wavefront OBJ (*.obj)'",opened)
        self.assertIn('serial!=self._predicted_serial',loaded)
        self.assertIn("getattr(mesh,'palette_counts',())",loaded)
        self.assertIn('self._use_external_predicted = True',loaded)

    def test_visualization_sources_can_be_switched_without_forecast(self):
        live=method_source(self.main,'_use_live_predicted_preview')
        imported=method_source(self.main,'_use_imported_predicted_preview')
        self.assertIn('self._use_external_predicted = False',live)
        self.assertIn('self._use_external_predicted = True',imported)
        for method in (live,imported):
            self.assertNotIn('self._request_forecast(',method)
            self.assertNotIn('self._load_preview(',method)

    def test_plate_and_camera_are_clear_and_independent(self):
        pane=method_source(self.main,'_preview_pane')
        self.assertIn('AdaptivePreviewToolbar(',pane)
        self.assertIn('self.plate_button.clicked.connect(self._choose_plate)',pane)
        self.assertIn('self.plate_visibility_button.clicked.connect(self._toggle_plate_visibility)',pane)
        self.assertIn("preview_toolbar_icon('reset')",pane)
        self.assertIn("preview_toolbar_icon('expand')",pane)
        self.assertIn("self.reset_camera_button.setObjectName('resetCameraButton')",pane)
        self.assertIn("self.expand_preview_toggle.setObjectName('toggleExpandedPreview')",pane)
        self.assertNotIn("self.reset_camera_button.setText('Reset View')",pane)
        self.assertNotIn("self.plate_visibility_button.setText('Hide Plate'",pane)

    def test_expanded_preview_does_not_switch_windows_hdr_presentation_mode(self):
        method=method_source(self.main,'_set_expanded_preview')
        self.assertIn('self.showMaximized()',method)
        self.assertNotIn('self.showFullScreen()',method.replace('showFullScreen() promotes',''))
        self.assertIn("'restore' if expanded else 'expand'",method)

    def test_default_plate_intent_does_not_require_selection(self):
        self.assertIn('self.remember_default.setEnabled(True)', self.picker)
        chooser=method_source(self.main,'_choose_plate')
        self.assertIn('if dialog.selected_asset is not None:',chooser)
        self.assertIn('if dialog.remember_default.isChecked():',chooser)
        self.assertIn('if dialog.clear_saved_default:',chooser)


if __name__=='__main__':
    unittest.main()
