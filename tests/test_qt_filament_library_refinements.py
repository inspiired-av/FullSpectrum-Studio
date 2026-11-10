"""Regressions for compact library UI, legacy custom JSON, and Auto slot bounds."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.qt_app import filament_library_store as lib


class FilamentLibraryRefinementStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p=patch.object(lib,'settings_path',return_value=Path(self.temp.name)/'settings.json')
        p.start()
        self.addCleanup(p.stop)

    def test_original_examples_custom_palette_format_imported_without_mutation(self):
        source = Path(self.temp.name)/'custom-palette.example.json'
        # Exact structural format of examples/custom-palette.example.json.
        source.write_text(json.dumps({'filaments':[
            {'name':'Example Brand Natural White','brand':'Example Brand','series':'PLA Basic','color':'#F4F1EA'},
            {'name':'Example Brand Deep Black','brand':'Example Brand','series':'PLA Basic','color':'#101214'},
            {'name':'Example Brand Ocean Blue','brand':'Example Brand','series':'PLA Basic','color':'#2479A7'},
        ]}),encoding='utf-8')
        before=source.read_bytes()
        ident=lib.import_profile(source)
        profile=lib.get_profile(ident)
        self.assertEqual(len(profile['filaments']),3)
        self.assertEqual([x['color'] for x in profile['filaments']],
                         ['#F4F1EA','#101214','#2479A7'])
        self.assertEqual(source.read_bytes(),before)
        active=lib.activate_palette(profile['filaments'])
        obj=json.loads(active.read_text())
        self.assertEqual(len(obj['filaments']),3)
        self.assertEqual(obj['filaments'][2]['brand'],'Example Brand')

    def test_five_distinct_custom_colors_are_valid_library_selection(self):
        colors=['#08ABFB','#D93B90','#F9ED3D','#9199A4','#000000']
        records=[lib.normalize({'name':f'Spool {i}','brand':'Personal',
                 'series':'PLA Basic','color':col,'source':'personal'},personal=True)
                 for i,col in enumerate(colors)]
        path=lib.activate_palette(records)
        self.assertEqual(len(json.loads(path.read_text())['filaments']),5)


class AutoSlotCeilingTests(unittest.TestCase):
    def test_five_selected_colors_with_eight_model_colors_auto_fits(self):
        import fullspectrum_engine as engine
        pool=[{'name':f'PLA {i}', 'series':'PLA Basic', 'color':color}
              for i,color in enumerate(('#08ABFB','#D93B90','#F9ED3D','#9199A4','#000000'))]
        targets=[(str(i),color,1) for i,color in enumerate(
            ('#08ABFB','#D93B90','#F9ED3D','#9199A4','#000000',
             '#FF0000','#00FF00','#0000FF'))]
        def rank(*args,**kwargs):return (0.0,)
        with (patch.object(engine,'custom_palette',return_value=pool),
              patch.object(engine,'shortlist_anchor_pool',side_effect=lambda p,*a:list(p)),
              patch.object(engine,'weighted_color_targets',return_value=(targets,8,targets,8)),
              patch.object(engine,'anchor_score_hint_database',return_value=[[] for _ in targets]),
              patch.object(engine,'palette_selection_score',side_effect=rank)):
            anchors=engine.select_anchors(
                [t[1] for t in targets], [1]*8, 'official', {}, 'custom',
                real_slots='auto', custom_catalog_path='not-accessed',
                quality_bias=60, planner_mode='fast')
            # Auto is a quality/slot tradeoff, not a request to fill the kit.
            # It can choose fewer than five, but may never exceed inventory.
            self.assertGreaterEqual(len(anchors),2)
            self.assertLessEqual(len(anchors),5)
            self.assertEqual(len({a['color'] for a in anchors}),len(anchors))
            with self.assertRaisesRegex(RuntimeError,'fewer than 6 distinct colors'):
                engine.select_anchors([t[1] for t in targets],[1]*8,
                                      'official',{},'custom',real_slots='6',
                                      custom_catalog_path='not-accessed',planner_mode='fast')


try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QHeaderView
    from desktop.qt_app.filament_library_dialog import FilamentTableModel, FilamentLibraryDialog
except (ImportError,OSError):
    QApplication=None


@unittest.skipIf(QApplication is None, 'PySide6 not available')
class FilamentLibraryRefinementQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_color_cell_uses_swatch_decoration_not_full_background(self):
        model=FilamentTableModel(lib.generic_filaments())
        index=model.index(0,1)
        self.assertIsNone(model.data(index,Qt.ItemDataRole.BackgroundRole))
        self.assertIsInstance(model.data(index,Qt.ItemDataRole.DecorationRole),QIcon)
        self.assertTrue(model.data(index,Qt.ItemDataRole.DisplayRole).startswith('#'))

    def test_library_table_has_readable_unstriped_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(lib,'settings_path',return_value=Path(folder)/'settings.json'):
                dialog=FilamentLibraryDialog()
                self.assertFalse(dialog.table.alternatingRowColors())
                self.assertEqual(dialog.table.horizontalHeader().sectionResizeMode(2),
                                 QHeaderView.ResizeMode.Stretch)
                dialog.close()
                self.assertFalse(dialog.worker.isRunning())


if __name__=='__main__':unittest.main()
