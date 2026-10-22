"""Stage 4B stability regression checks, runnable even without PySide6."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
QT = ROOT / 'desktop' / 'qt_app'


class SourceContractTests(unittest.TestCase):
    def test_files_parse_and_contain_no_duplicate_optimizer(self):
        for name in ('main_window.py', 'filaments_tab.py', 'planning_details_panel.py', 'wheel_safe_combo.py'):
            ast.parse((QT / name).read_text(encoding='utf-8'))
        text = (QT / 'wheel_safe_combo.py').read_text(encoding='utf-8')
        self.assertIn('event.ignore()', text)
        self.assertIn('self.view().isVisible()', text)

    def test_filter_waits_for_batched_load(self):
        txt = (QT / 'filaments_tab.py').read_text(encoding='utf-8')
        self.assertIn('self._population_active', txt)
        self.assertIn('QTimer.singleShot(0,', txt)
        self.assertIn('self._populate_batch(', txt)
        self.assertIn("self.load_progress.setRange(0, 0)", txt)
        self.assertIn("if self._population_active:", txt)

    def test_forecast_harness_and_stale_panel_remain_separable(self):
        txt = (QT / 'main_window.py').read_text(encoding='utf-8')
        self.assertIn("getattr(self, 'planning_details_panel', None)", txt)
        self.assertIn('self._forecast_heartbeat', txt)
        self.assertIn('WheelSafeComboBox()', txt)
        panel = (QT / 'planning_details_panel.py').read_text(encoding='utf-8')
        self.assertIn('OUTDATED FORECAST', panel)
        self.assertIn('self.review.setVisible(physical_tab)', panel)


class QtBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest('PySide6 unavailable; run Qt behavior checks on Windows')
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def test_wheel_on_closed_combo_does_not_change_choice(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from desktop.qt_app.wheel_safe_combo import WheelSafeComboBox
        combo = WheelSafeComboBox()
        try:
            combo.addItems(['First', 'Second', 'Third'])
            combo.setCurrentIndex(1)
            wheel = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(), QPoint(0, -120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.ScrollUpdate, False)
            self.app.sendEvent(combo, wheel)
            self.assertEqual(combo.currentIndex(), 1)
        finally:
            combo.close()

    def test_large_library_filter_is_safe_during_loading(self):
        from desktop.qt_app.plan_preferences import PlanPreferences
        from desktop.qt_app.filaments_tab import FilamentsTab
        with tempfile.TemporaryDirectory() as tmp:
            tab = FilamentsTab(PlanPreferences(Path(tmp) / 'settings.json'))
            try:
                tab._load_serial = 1
                rows = [{'key': f'PLA Basic|#{i:06X}', 'name': f'Material {i}',
                         'series': 'PLA Basic', 'color': f'#{i:06X}'} for i in range(165)]
                tab._options_loaded(1, rows, None)
                self.assertTrue(tab._population_active)
                tab.search.setText('Material 125')
                for _ in range(300):
                    if not tab._population_active:
                        break
                    self.app.processEvents()
                self.assertFalse(tab._population_active)
                self.assertEqual(len(tab._rows), len(rows))
                self.assertFalse(tab.filaments.isRowHidden(125))
                self.assertTrue(tab.filaments.isRowHidden(0))
                self.assertFalse(tab.load_progress.isVisible())
            finally:
                tab.close()

    def test_mixed_recipes_have_no_lookup_button_and_stale_is_visible(self):
        from desktop.qt_app.planning_details_panel import PlanningDetailsPanel
        panel = PlanningDetailsPanel()
        try:
            payload = {'realSlots': 1, 'outputSlots': 2, 'maxOutputColors': 'auto',
                       'anchors': [{'slot': 1, 'key': 'PLA Basic|#000000',
                                    'color': '#000000', 'name': 'Black'}],
                       'recipes': [{'kind': 'MIX', 'oldSlot': 1, 'newSlot': 2,
                                    'preview': '#777777', 'components': '1,1',
                                    'ratios': '0.5,0.5', 'deltaE': 2.0}]}
            panel.set_result(payload)
            panel.set_stale(True)
            self.assertFalse(panel.stale_notice.isHidden())
            panel.tabs.setCurrentIndex(1)
            self.assertTrue(panel.review.isHidden())
            self.assertIn('physical slots', panel.hint.text().lower())
        finally:
            panel.close()


if __name__ == '__main__':
    unittest.main()
