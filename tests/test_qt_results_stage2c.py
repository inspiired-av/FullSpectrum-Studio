"""Stage 2C pure and conditional Qt tests (safe to run on CI without PySide6)."""
import os
from pathlib import Path
import tempfile
import unittest
from desktop.qt_app.results_state import (MAX_REPORT_BYTES, event_tail,
                                           model_summary, read_existing_report, shorten)

class ResultDataTests(unittest.TestCase):
    def test_empty_state_does_not_claim_conversion(self):
        data=model_summary('', '', 'Bambu Studio')
        self.assertIn('Not run',data['conversion'])
        self.assertIn('Not run',data['validation'])
        self.assertEqual(data['template'],'Not selected')

    def test_context_shows_short_names_and_dirty_state(self):
        data=model_summary(r'C:\Models\Demo.3mf',r'C:\Templates\H2C.3mf','OrcaSlicer',True)
        self.assertEqual(data['model'],'Demo.3mf')
        self.assertEqual(data['template'],'H2C.3mf')
        self.assertEqual(data['settings'],'Unsaved changes')
        self.assertEqual(data['slicer'],'OrcaSlicer')

    def test_read_report_utf8_without_modification(self):
        with tempfile.TemporaryDirectory() as temp:
            f=Path(temp)/'report.txt'
            raw='FullSpectrum Studio\nAccuracy: 93%\n'.encode('utf-8')
            f.write_bytes(raw)
            self.assertEqual(read_existing_report(f),raw.decode('utf-8'))
            self.assertEqual(f.read_bytes(),raw)

    def test_read_report_utf16(self):
        with tempfile.TemporaryDirectory() as temp:
            f=Path(temp)/'slicer.log'
            f.write_bytes('Validation: PASS'.encode('utf-16'))
            self.assertEqual(read_existing_report(f),'Validation: PASS')

    def test_report_rejects_unsupported_or_missing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            f=Path(temp)/'mesh.3mf'
            f.write_text('not a report',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Select an existing'):
                read_existing_report(f)
            with self.assertRaisesRegex(ValueError,'not found'):
                read_existing_report(Path(temp)/'missing.txt')

    def test_report_size_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            f=Path(temp)/'huge.txt'
            with f.open('wb') as fp: fp.truncate(MAX_REPORT_BYTES+1)
            with self.assertRaisesRegex(ValueError,'2 MiB'):
                read_existing_report(f)

    def test_bounded_activity_and_single_line_output(self):
        self.assertEqual(event_tail(range(180)),list(range(80,180)))
        self.assertEqual(shorten('A\r\nB'),'A  B')
        self.assertLessEqual(len(shorten('x'*500)),96)

try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.results_tab import ResultsTab
except ImportError:
    QApplication=None

@unittest.skipUnless(QApplication is not None,'PySide6 not installed in test environment')
class ResultsQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_viewer_is_read_only_and_reports_not_run(self):
        panel=ResultsTab()
        self.assertTrue(panel.report_view.isReadOnly())
        self.assertFalse(panel.copy_report_button.isEnabled())
        self.assertIn('Not run',panel.fields['conversion'].text())
        panel.close()

    def test_copy_and_clear_existing_report(self):
        panel=ResultsTab()
        with tempfile.TemporaryDirectory() as temp:
            f=Path(temp)/'previous_report.md'
            f.write_text('Some old report',encoding='utf-8')
            self.assertTrue(panel.load_report(f))
            panel.copy_report()
            self.assertEqual(QApplication.clipboard().text(),'Some old report')
            panel.clear_report()
            self.assertFalse(panel.copy_report_button.isEnabled())
        panel.close()

    def test_activity_indicator_only_for_busy_tasks(self):
        panel=ResultsTab()
        panel.show()
        panel.record_event('Filaments','Loading', 'busy')
        self.assertTrue(panel.activity_progress.isVisible())
        panel.record_event('Filaments','Loaded','success')
        self.assertFalse(panel.activity_progress.isVisible())
        panel.close()

if __name__=='__main__':unittest.main()
