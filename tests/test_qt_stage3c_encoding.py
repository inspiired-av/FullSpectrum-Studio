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

    def test_header_displays_release_version_without_prototype_badge(self):
        path = Path(__file__).resolve().parents[1] / 'desktop/qt_app/main_window.py'
        content = path.read_text(encoding='utf-8')
        main = next(node for node in ast.parse(content).body
                    if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
        build = next(node for node in main.body
                     if isinstance(node, ast.FunctionDef) and node.name == '_build')
        header = ast.get_source_segment(content, build)
        # Stage 5 intentionally removed the development-stage badge. Retain
        # the release version and existing Open Model entry point instead.
        self.assertNotIn('UI prototype · Stage', header)
        self.assertIn('h.addWidget(_label("v" + APP_VERSION, "bodyMuted"))', header)
        self.assertIn('self.open_button = QPushButton("Open Model")', header)


if __name__ == '__main__':
    unittest.main()
