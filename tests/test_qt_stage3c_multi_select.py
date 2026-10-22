"""Stage 3C selection UX: multi-color selection is safe, explicit and reversible."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CodeContracts(unittest.TestCase):
    def test_table_toggles_and_extended_selection(self):
        text=(ROOT/'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        self.assertIn('class ToggleSourceTable(QTableWidget):',text)
        self.assertIn('SelectionMode.ExtendedSelection',text)
        self.assertIn('self.solid_table.clearSelection()',text)
        self.assertIn('def select_source_colors(self, colors):',text)
        self.assertIn('def _selected_colors(self):',text)
        self.assertIn('model.SelectionFlag',text.replace('QItemSelectionModel.SelectionFlag','model.SelectionFlag'))

    def test_explicit_protection_with_multi_assignment_warning(self):
        text=(ROOT/'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        self.assertIn('Multiple source colors assigned to one filament',text)
        self.assertIn('for color in colors:',text)
        self.assertIn('self.preferences.protect(color, key, self.source_colors, self.options)',text)
        self.assertIn('self.preferences.unprotect(color)',text)

    def test_palette_click_modes_and_shader_highlights(self):
        palette=(ROOT/'desktop/qt_app/source_palette.py').read_text(encoding='utf-8')
        ui=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        shader=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8')
        self.assertIn('multi_chosen = Signal(str)',palette)
        self.assertIn('Qt.KeyboardModifier.ControlModifier',palette)
        self.assertIn('chip.multi_chosen.connect(self._toggle_palette_multi)',ui)
        self.assertIn('def _select_palette_colors(self, colors, sync_table=True):',ui)
        self.assertIn('selectedExtraColors[64]',shader)
        self.assertIn('self.preview_surface.set_highlights(self._source_palette_selected_colors,',ui)

    def test_source_code_compiles(self):
        for name in ('main_window.py','filaments_tab.py','source_palette.py','gl_viewport.py'):
            compile((ROOT/'desktop/qt_app'/name).read_bytes(),name,'exec')

try:
    from PySide6.QtCore import Qt, QPoint, QItemSelectionModel
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from desktop.qt_app.main_window import MainWindow
except ImportError:
    QApplication=None

@unittest.skipUnless(QApplication is not None,'PySide6 not installed')
class QtBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile
        self.tmp=tempfile.TemporaryDirectory()
        self.window=MainWindow(settings_path=Path(self.tmp.name)/'settings.json')
        self.tab=self.window.filaments_panel
        colors={'#110000':20,'#002200':30,'#000033':40,'#FFFFFF':50}
        self.tab.source_colors=colors
        self.tab._populate_solid_colors()
        self.window._source_palette_counts=colors
        self.tab.options=[{'key':'a','color':'#000000','name':'Black'},
                          {'key':'b','color':'#FFFFFF','name':'White'}]
        self.tab.target.clear()
        self.tab.target.addItem('Black','a')
        self.tab.target.addItem('White','b')
        self.tab._accept_table=lambda show_error: True
        self.window._select_palette_color(None)

    def tearDown(self):
        self.window.close()
        self.tmp.cleanup()

    def test_select_multiple_and_bulk_protect_then_unprotect(self):
        self.window._toggle_palette_color('#110000')
        self.window._toggle_palette_multi('#002200')
        self.assertEqual(set(self.tab._selected_colors()),{'#110000','#002200'})
        self.assertEqual(set(self.window._source_palette_selected_colors),{'#110000','#002200'})
        self.assertTrue(self.tab.bulk_hint.isVisibleTo(self.tab) or not self.tab.isVisible())
        self.tab._protect()
        self.assertEqual(self.tab.preferences.solid_assignments,
                         {'#110000':'a','#002200':'a'})
        self.assertEqual(set(self.tab._selected_colors()),{'#110000','#002200'})
        self.tab._remove_protection()
        self.assertEqual(self.tab.preferences.solid_assignments,{})
        self.assertEqual(set(self.tab._selected_colors()),{'#110000','#002200'})

    def test_table_selection_synchronizes_and_clear(self):
        model=self.tab.solid_table.selectionModel()
        for row in (0,1):
            model.select(self.tab.solid_table.model().index(row,0),
                         QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.assertEqual(len(self.window._source_palette_selected_colors),2)
        self.window._clear_palette_selection()
        self.assertEqual(self.tab._selected_colors(),())
        self.assertEqual(self.window._source_palette_selected_colors,())

    def test_plain_palette_click_clears_single_and_ctrl_toggles_set(self):
        self.window._toggle_palette_color('#110000')
        self.window._toggle_palette_color('#110000')
        self.assertEqual(self.tab._selected_colors(),())
        self.window._toggle_palette_multi('#110000')
        self.window._toggle_palette_multi('#002200')
        self.window._toggle_palette_multi('#110000')
        self.assertEqual(self.tab._selected_colors(),('#002200',))
        self.window._toggle_palette_color('#002200')
        self.assertEqual(self.tab._selected_colors(),())

if __name__=='__main__': unittest.main()
