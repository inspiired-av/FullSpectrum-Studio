"""Automatic indexed Direct defaults and regressions; no GPU/Qt required."""
from __future__ import annotations

from array import array
import ast
import os
from pathlib import Path
import unittest
from unittest import mock

from desktop.qt_app.preview_indexed_mode import enabled, prepare_indexed_preview


def repeated_mesh():
    face = (
        (0.,0.,0., 0.,0.,1., 1.,0.,0., 1.,0.,0.),
        (1.,0.,0., 0.,0.,1., 0.,1.,0., 0.,1.,0.),
        (0.,1.,0., 0.,0.,1., 0.,0.,1., 0.,0.,1.),
    )
    return array('f', (*face[0], *face[1], *face[2]) * 2)


class DefaultIndexingTests(unittest.TestCase):
    def test_default_indexing_is_enabled_and_exact(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(enabled())
            src = repeated_mesh()
            candidate = prepare_indexed_preview(src)
        self.assertIsNotNone(candidate)
        self.assertTrue(candidate.matches_source_bytes(src))

    def test_manual_opt_outs(self):
        for flag in ('0', 'false', 'off', 'no'):
            with self.subTest(flag=flag), mock.patch.dict(os.environ, {
                    'FULLSPECTRUM_PREVIEW_INDEXED': flag}, clear=True):
                self.assertFalse(enabled())
                self.assertIsNone(prepare_indexed_preview(repeated_mesh()))

    def test_explicit_opt_in_works(self):
        for flag in ('1', 'auto', 'true', 'on', 'yes'):
            with self.subTest(flag=flag), mock.patch.dict(os.environ, {
                    'FULLSPECTRUM_PREVIEW_INDEXED': flag}, clear=True):
                self.assertTrue(enabled())

    def test_other_upload_diagnostics_remain_unindexed(self):
        for upload in ('split', 'raw-direct', 'raw-split'):
            with self.subTest(upload=upload), mock.patch.dict(os.environ, {
                    'FULLSPECTRUM_PREVIEW_UPLOAD': upload}, clear=True):
                self.assertFalse(enabled())
                self.assertIsNone(prepare_indexed_preview(repeated_mesh()))

    def test_inapplicable_mesh_uses_direct_fallback(self):
        src = array('f')
        for i in range(9):
            src.extend((float(i), 0.,0., 0.,0.,1., 1.,0.,0., 1.,0.,0.))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(prepare_indexed_preview(src))

    def test_indexing_exception_does_not_break_model_load(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch('desktop.qt_app.preview_indexing.make_indexed_candidate',
                            side_effect=RuntimeError('fake indexing failure')):
                self.assertIsNone(prepare_indexed_preview(repeated_mesh()))

    def test_indexing_state_and_display_labels_are_consistent(self):
        root = Path(__file__).resolve().parents[1]
        src = (root / 'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
        fmt = (root / 'desktop/qt_app/preview_performance.py').read_text(encoding='utf-8-sig')
        ast.parse(src)
        self.assertIn('self._preview_index_enabled=indexing_enabled()', src)
        self.assertIn('"_indexed_active"', src.replace("'_indexed_active'", '"_indexed_active"'))
        self.assertIn("'indexed_preferred'", src)
        self.assertIn('Indexed Direct (default)', fmt)
        self.assertIn('Direct (fallback)', fmt)
        self.assertIn('Direct (indexing disabled)', fmt)


if __name__ == '__main__':
    unittest.main()
