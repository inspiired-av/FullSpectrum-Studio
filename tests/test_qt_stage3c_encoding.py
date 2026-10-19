"""Prevent Windows cp1252 failures and stale Qt stage labels."""
import ast
import re
from pathlib import Path
import unittest


class EncodingAndStageLabelTests(unittest.TestCase):
    def test_all_source_text_reads_are_explicit_utf8(self):
        path = Path(__file__).with_name('test_qt_stage3b_quality.py')
        tree = ast.parse(path.read_text(encoding='utf-8'))
        reads = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'read_text']
        self.assertGreaterEqual(len(reads), 4)
        for node in reads:
            self.assertTrue(any(k.arg == 'encoding' and isinstance(k.value, ast.Constant)
                                and k.value.value == 'utf-8' for k in node.keywords),
                            f'Implicit locale encoding in read_text() at line {node.lineno}')

    def test_stage_3c_label_tracks_installed_features(self):
        path = Path(__file__).resolve().parents[1] / 'desktop/qt_app/main_window.py'
        content = path.read_text(encoding='utf-8')
        # Lettered subphases (4D-A, 4D-B, etc.) are real stage labels.
        match = re.search(r'UI prototype · Stage (\d+)([A-Z](?:-[A-Z]\d*)?)', content)
        self.assertIsNotNone(match, 'Missing Qt development-stage badge')
        stage = (int(match.group(1)), match.group(2))
        self.assertGreaterEqual(stage, (3, 'C'))
        self.assertIn(f'Qt Stage {match.group(1)}{match.group(2)} —', content)
        self.assertNotIn('UI prototype · Stage 3B', content)


if __name__ == '__main__':
    unittest.main()
