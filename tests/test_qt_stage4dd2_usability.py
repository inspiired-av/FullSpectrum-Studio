"""D2 usability: source assignment inspector, Shift ranges and bulk removal."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest
from qt_test_cleanup import dispose_test_widget
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
UI=ROOT/'desktop/qt_app'


def extract_main_method(name):
    tree=ast.parse((UI/'main_window.py').read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MainWindow')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    namespace={}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),
                 str(UI/'main_window.py'),'exec'), namespace)
    return namespace[name]


class StaticContracts(unittest.TestCase):
    def test_d2_usability_code_parses(self):
        for p in ('main_window.py','source_palette.py','filaments_tab.py',
                  'source_assignments_panel.py'):
            with self.subTest(path=p):
                ast.parse((UI/p).read_text(encoding='utf-8'))

    def test_old_summary_replaced_with_grouped_inspector(self):
        text=(UI/'main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.assignment_panel.set_assignments(',text)
        self.assertIn('self.assignment_panel.clear_requested.connect(',text)
        self.assertIn('self.assignment_panel.remove_requested.connect(',text)
        self.assertIn('self._confirm_clear_all_assignments()',text)
        self.assertNotIn("preview=' · '.join(lines[:3])",text)

    def test_legacy_modal_test_was_replaced(self):
        stage3c=(ROOT/'tests/test_qt_stage3c_interaction.py').read_text(encoding='utf-8')
        self.assertIn("patch.object(w.filaments_panel, 'open_assignment_dialog')",stage3c)
        self.assertNotIn("patch.object(w.filaments_panel, 'prepare_source_assignments')",stage3c)

    def test_range_anchor_and_ctrl_shift_union(self):
        select_range=extract_main_method('_select_palette_range')
        colors=['#111111','#222222','#333333','#444444','#555555']
        state=SimpleNamespace(
            _source_palette_cells=[SimpleNamespace(hex_color=c) for c in colors],
            _source_palette_anchor='#222222',
            _source_palette_selected_colors=('#222222',),
            _select_palette_colors=Mock(),
        )
        select_range(state,'#444444')
        state._select_palette_colors.assert_called_once_with(colors[1:4])
        self.assertEqual(state._source_palette_anchor, '#222222')
        state._select_palette_colors.reset_mock()
        state._source_palette_selected_colors=('#111111','#222222')
        select_range(state,'#444444',True)
        state._select_palette_colors.assert_called_once_with(
            ['#111111','#222222','#333333','#444444'])

    def test_range_with_no_anchor_selects_clicked_color(self):
        select_range=extract_main_method('_select_palette_range')
        state=SimpleNamespace(
            _source_palette_cells=[SimpleNamespace(hex_color=c) for c in ('#AAAAAA','#BBBBBB')],
            _source_palette_anchor=None,
            _source_palette_selected_colors=(),
            _select_palette_colors=Mock(),
        )
        select_range(state,'#BBBBBB')
        state._select_palette_colors.assert_called_once_with(['#BBBBBB'])
        self.assertEqual(state._source_palette_anchor,'#BBBBBB')


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 unavailable')
class QtBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_shift_click_emits_range_signal(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from desktop.qt_app.source_palette import PaletteSwatch
        swatch=PaletteSwatch('#ABCDEF',10)
        self.addCleanup(dispose_test_widget, swatch)
        swatch.show()
        calls=[]
        swatch.range_chosen.connect(lambda *values:calls.append(values))
        QTest.mouseClick(swatch,Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ShiftModifier)
        QTest.mouseClick(swatch,Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(calls,[('#ABCDEF',False),('#ABCDEF',True)])

    def test_inspector_groups_displays_and_bulk_removes(self):
        from desktop.qt_app.source_assignments_panel import SourceAssignmentsPanel
        from PySide6.QtCore import Qt
        panel=SourceAssignmentsPanel()
        self.addCleanup(dispose_test_widget, panel)
        options=[{'key':'white','name':'White PLA','color':'#FFFFFF'},
                 {'key':'cyan','name':'Cyan PLA','color':'#08ABFB'}]
        panel.set_assignments({'#FFFFFF':'white','#F0F0F0':'white','#112233':'cyan'},
                              options,{'#FFFFFF':10,'#F0F0F0':20,'#112233':30})
        self.assertEqual(panel.tree.topLevelItemCount(),2)
        self.assertEqual(panel.toggle.text(),'Assigned Colors (3) ▸')
        panel.toggle.click()
        self.assertTrue(panel.details.isVisible() if panel.isVisible() else panel.toggle.isChecked())
        self.assertFalse(hasattr(panel, 'search'))
        self.assertEqual(panel.tree.topLevelItemCount(), 2)
        found=[]
        for i in range(panel.tree.topLevelItemCount()):
            parent=panel.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child=parent.child(j)
                if child.text(0)=='#FFFFFF':
                    found.append(child)
        self.assertEqual(len(found),1)
        panel.tree.setCurrentItem(found[0])
        received=[]
        panel.remove_requested.connect(received.append)
        panel.remove_button.click()
        self.assertEqual(received,[('#FFFFFF',)])

    def test_pending_library_does_not_open_modal_dialog(self):
        from desktop.qt_app.filaments_tab import FilamentsTab
        from desktop.qt_app.plan_preferences import PlanPreferences
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            tab=FilamentsTab(PlanPreferences(Path(temp)/'s.json'),
                             settings_path=Path(temp)/'s.json')
            self.addCleanup(dispose_test_widget, tab)
            tab.model_path='sample.3mf'
            messages=[]
            tab.activity_event.connect(lambda *a:messages.append(a))
            with patch('desktop.qt_app.filaments_tab.QMessageBox.information') as modal:
                tab.open_assignment_dialog(('#FFFFFF',))
            modal.assert_not_called()
            self.assertEqual(len(messages),1)
            self.assertIn('finish loading',messages[0][2])


if __name__=='__main__':
    unittest.main()
