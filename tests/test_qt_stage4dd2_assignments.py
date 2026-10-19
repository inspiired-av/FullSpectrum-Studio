"""Stage 4D-D2: assignment visibility, automatic requirements and recipe reservations."""
from __future__ import annotations
import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class SourceContracts(unittest.TestCase):
    def test_engine_paths_have_reservation_and_final_guard(self):
        src=(ROOT/'fullspectrum_engine.py').read_text(encoding='utf-8')
        self.assertIn('reserved_filament_keys=set(solid_color_overrides.values())',src)
        self.assertIn('reserved_filament_keys=reserved_filament_keys',src)
        self.assertIn('for a,b in combinations(mixing_slots,2):',src)
        self.assertIn('for a,b,c in combinations(mixing_slots,3):',src)
        self.assertIn('Mixed slot {slot} illegally references',src)

    def test_source_palette_controls_replace_protection_tab(self):
        src=(ROOT/'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        ui=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        swatch=(ROOT/'desktop/qt_app/source_palette.py').read_text(encoding='utf-8')
        self.assertIn('self._assignment_compat.hide()',src)
        self.assertNotIn("lay.addWidget(help_heading('protect_solid_colors'",src)
        self.assertIn('def open_assignment_dialog(self, colors):',src)
        self.assertIn('def remove_source_assignments(self, colors):',src)
        self.assertIn('chip.context_requested.connect(self._source_palette_context_menu)',ui)
        self.assertIn("f'Remove Selected Assignments ({len(selected_assigned)})'", ui)
        self.assertIn('self.filaments_panel.remove_source_assignments(selected_assigned)', ui)
        self.assertIn('self.assignment_panel.set_assignments',ui)
        self.assertIn('context_requested = Signal(str)',swatch)

    def test_all_changed_files_parse(self):
        paths=['fullspectrum_engine.py','desktop/qt_app/filament_preferences.py',
               'desktop/qt_app/filaments_tab.py','desktop/qt_app/main_window.py',
               'desktop/qt_app/source_palette.py','desktop/qt_app/source_color_assignment_dialog.py']
        for path in paths:
            with self.subTest(path=path):
                ast.parse((ROOT/path).read_text(encoding='utf-8'))


class AutoRequiredTests(unittest.TestCase):
    def setUp(self):
        from desktop.qt_app.filament_preferences import FilamentPreferences
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'settings.json'
        self.pref=FilamentPreferences(self.path)
        self.options=[{'key':'white','name':'White','color':'#FFFFFF'},
                      {'key':'cyan','name':'Cyan','color':'#08ABFB'},
                      {'key':'magenta','name':'Magenta','color':'#D93B90'}]
        self.source={'#000000':10,'#FFFFFF':10}
        self.pref.use_model('sample.3mf')

    def test_assignment_auto_enables_without_manual_pin(self):
        self.pref.apply(self.options,{'cyan','magenta'},set(),max_slots=2)
        self.pref.assign('#000000','white',self.source,self.options,max_slots=2)
        self.assertTrue(self.pref.selected('white'))
        self.assertEqual(self.pref.solid_assignments,{'#000000':'white'})
        self.assertNotIn('white',self.pref.pinned)
        # The assignment creates an automatic physical requirement, not a saved pin.
        self.pref.save()
        from desktop.settings_store import load_settings
        self.assertNotIn('white',load_settings(self.path).get('pinned_anchor_keys',[]))

    def test_assignment_prevents_excluding_filament(self):
        self.pref.assign('#000000','white',self.source,self.options,max_slots=2)
        with self.assertRaisesRegex(ValueError,'assigned filament cannot be excluded'):
            self.pref.apply(self.options,{'cyan','magenta'},set(),max_slots=2)
        self.assertIn('#000000',self.pref.solid_assignments)

    def test_manual_requirement_survives_last_assignment_removed(self):
        self.pref.apply(self.options,{'white','cyan','magenta'},{'white'},max_slots=2)
        self.pref.assign('#000000','white',self.source,self.options,max_slots=2)
        self.pref.unprotect('#000000')
        self.assertTrue(self.pref.is_pinned('white'))

    def test_conflicting_auto_and_manual_slot_budget_rejected_atomically(self):
        self.pref.apply(self.options,{'white','cyan','magenta'},{'cyan'},max_slots=1)
        with self.assertRaisesRegex(ValueError,'Physical slots'):
            self.pref.assign('#FFFFFF','white',self.source,self.options,max_slots=1)
        self.assertEqual(self.pref.solid_assignments,{})

    def test_assignment_is_model_only(self):
        self.pref.assign('#000000','white',self.source,self.options,max_slots=2)
        self.pref.use_model('different.3mf')
        self.assertEqual(self.pref.solid_assignments,{})


class RecipeReservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fullspectrum_engine as engine
        cls.engine=engine
        cls.anchors=[
            {'name':'White','series':'Test PLA','color':'#FFFFFF'},
            {'name':'Cyan','series':'Test PLA','color':'#08ABFB'},
            {'name':'Magenta','series':'Test PLA','color':'#D93B90'},
        ]
        cls.white=engine.anchor_key(cls.anchors[0])

    def test_cached_pairs_and_triples_exclude_assigned_filament(self):
        engine=self.engine
        for pair,triple in [('standard2','none'),('none','standard3')]:
            with self.subTest(pair=pair,triple=triple):
                recipes=engine.mix_recipe_index(self.anchors,'bambu',pair,triple,{self.white})
                self.assertTrue(all(1 not in components for components,_,_ in recipes))
        self.assertTrue(engine.mix_recipe_index(self.anchors,'bambu','standard2','none'))

    def test_direct_white_still_available_while_reserved(self):
        err,slot,*_=self.engine.nearest_anchor_error('#FFFFFF',self.anchors)
        self.assertEqual(slot,1)
        self.assertLess(err,0.01)

    def test_palette_recipe_components_never_reference_white(self):
        engine=self.engine
        palette=engine.build_palette(
            ['#FFFFFF','#2366BC','#A34AAE'],self.anchors,
            usage={1:10,2:100,3:100},quality_bias=90,
            protected_slots={1:self.white},max_output_colors=16)
        _colors,flags,component_text,_ratio,_map,rows=palette
        self.assertEqual(rows[0][3],'SOLID')
        for flag,components in zip(flags,component_text):
            if flag=='1':
                self.assertNotIn('1',components.split(','))


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed')
class QtAssignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_dialog_searches_hex_and_brand(self):
        from desktop.qt_app.source_color_assignment_dialog import SourceColorAssignmentDialog
        options=[{'key':'panchroma-cyan','name':'Cyan','brand':'Polymaker',
                  'series':'Translucent','color':'#08ABFB'},
                 {'key':'white','name':'White','color':'#FFFFFF'}]
        dialog=SourceColorAssignmentDialog(('#000000',),options,{},None)
        self.addCleanup(dialog.close)
        dialog.search.setText('polymaker')
        self.assertFalse(dialog.list.item(0).isHidden())
        self.assertTrue(dialog.list.item(1).isHidden())
        dialog.list.setCurrentRow(0)
        self.assertEqual(dialog.selected_key(),'panchroma-cyan')

    def test_swatch_has_right_click_signal(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from desktop.qt_app.source_palette import PaletteSwatch
        swatch=PaletteSwatch('#9199A4',42)
        self.addCleanup(swatch.close)
        swatch.show()
        seen=[]
        swatch.context_requested.connect(seen.append)
        QTest.mouseClick(swatch,Qt.MouseButton.RightButton)
        self.assertEqual(seen,['#9199A4'])


if __name__=='__main__':
    unittest.main()
