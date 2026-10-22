"""D2 v7: a compact grouped inspector and atomic parent/child assignment removal."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / 'desktop/qt_app/source_assignments_panel.py'


def extract_selected_sources():
    code = PANEL.read_text(encoding='utf-8')
    tree = ast.parse(code)
    klass = next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='SourceAssignmentsPanel')
    method = next(x for x in klass.body if isinstance(x,ast.FunctionDef) and x.name=='_selected_sources')
    ns = {'Qt': SimpleNamespace(ItemDataRole=SimpleNamespace(UserRole=32))}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),
                 str(PANEL),'exec'), ns)
    return ns['_selected_sources']


class Item:
    def __init__(self, value=None, children=()):
        self.value = value
        self.children = list(children)

    def data(self, col, role):
        return self.value

    def childCount(self):
        return len(self.children)

    def child(self, index):
        return self.children[index]


class SourceContracts(unittest.TestCase):
    def test_no_search_control_or_obsolete_filter(self):
        source = PANEL.read_text(encoding='utf-8')
        ast.parse(source)
        self.assertNotIn("QLineEdit", source)
        self.assertNotIn("assignedColorsSearch", source)
        self.assertNotIn("self.search", source)
        self.assertNotIn('def _filter(self, text):', source)
        self.assertIn('self._resize_tree_to_contents()', source)
        self.assertNotIn('group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)', source)

    def test_selected_parent_collects_all_source_colors(self):
        selected = extract_selected_sources()
        parent = Item(children=(Item('#112233'),Item('#445566')))
        state = SimpleNamespace(tree=SimpleNamespace(selectedItems=lambda:[parent]))
        self.assertEqual(selected(state), ('#112233','#445566'))

    def test_mixed_parent_and_child_deduplicates(self):
        selected = extract_selected_sources()
        child1, child2 = Item('#112233'), Item('#445566')
        group = Item(children=(child1,child2))
        standalone = Item('#778899')
        state = SimpleNamespace(tree=SimpleNamespace(selectedItems=lambda:[group, child1, standalone]))
        self.assertEqual(selected(state), ('#112233','#445566','#778899'))

    def test_child_selection_only_removes_one_color(self):
        selected = extract_selected_sources()
        state = SimpleNamespace(tree=SimpleNamespace(selectedItems=lambda:[Item('#112233')]))
        self.assertEqual(selected(state), ('#112233',))

    def test_empty_selection_is_noop(self):
        selected = extract_selected_sources()
        state = SimpleNamespace(tree=SimpleNamespace(selectedItems=lambda:[]))
        self.assertEqual(selected(state), ())


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class QtInspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.source_assignments_panel import SourceAssignmentsPanel
        self.panel = SourceAssignmentsPanel()
        self.addCleanup(self.panel.close)
        self.panel.resize(550,240)
        self.panel.set_assignments(
            {'#112233':'white','#445566':'white','#778899':'cyan'},
            [{'key':'white','name':'White PLA','color':'#FFFFFF'},
             {'key':'cyan','name':'Cyan PLA','color':'#08ABFB'}],
            {'#112233':5,'#445566':7,'#778899':3})
        self.panel.show()
        self.panel.toggle.setChecked(True)
        self.app.processEvents()

    def _group(self, name):
        for i in range(self.panel.tree.topLevelItemCount()):
            item = self.panel.tree.topLevelItem(i)
            if name in item.text(0):
                return item
        self.fail(f'Group {name} missing')

    def test_parent_group_select_and_remove_all_its_children(self):
        from PySide6.QtCore import Qt
        group = self._group('White PLA')
        self.assertTrue(bool(group.flags() & Qt.ItemFlag.ItemIsSelectable))
        self.panel.tree.setCurrentItem(group)
        self.assertTrue(self.panel.remove_button.isEnabled())
        emitted = []
        self.panel.remove_requested.connect(emitted.append)
        self.panel.remove_button.click()
        self.assertEqual(len(emitted),1)
        self.assertEqual(set(emitted[0]),{'#112233','#445566'})
        self.assertNotIn('#778899',emitted[0])

    def test_child_selection_keeps_its_parent_siblings(self):
        group = self._group('White PLA')
        self.panel.tree.setCurrentItem(group.child(0))
        emitted = []
        self.panel.remove_requested.connect(emitted.append)
        self.panel.remove_button.click()
        self.assertEqual(emitted, [(group.child(0).text(0),)])


if __name__ == '__main__':
    unittest.main()
