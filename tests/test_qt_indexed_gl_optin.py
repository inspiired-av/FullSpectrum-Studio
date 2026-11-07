"""Lossless indexing GL contract tests; no Qt context or GPU required."""
from __future__ import annotations

from array import array
import ast
import ctypes
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np

from desktop.qt_app.preview_indexing import make_indexed_candidate
from desktop.qt_app.preview_indexed_mode import enabled, prepare_indexed_preview


class FakeGL:
    GL_ARRAY_BUFFER=0x8892
    GL_ELEMENT_ARRAY_BUFFER=0x8893
    GL_STATIC_DRAW=0x88E4
    GL_FLOAT=0x1406
    GL_FALSE=False

    def __init__(self):
        self.calls=[]
        self.bound={}
        self.data={}
    def glGenBuffers(self, n):
        self.calls.append(('gen',n))
        return 42
    def glBindVertexArray(self, vao):
        self.calls.append(('vao',vao))
    def glBindBuffer(self, target, name):
        self.bound[target]=name
        self.calls.append(('bind',target,name))
    def glBufferData(self, target, size, pointer, usage):
        self.data[target]=(size, ctypes.string_at(ctypes.addressof(pointer),size) if size else b'')
        self.calls.append(('upload',target,size))
    def glEnableVertexAttribArray(self, n):
        self.calls.append(('enable',n))
    def glVertexAttribPointer(self, *args):
        self.calls.append(('attrib', args[0]))


def packed():
    x=array('f')
    def row(pos, color):
        return (*pos, 0,0,1, *color, *color)
    a=row((0,0,0),(1,0,0))
    b=row((1,0,0),(0,1,0))
    c=row((0,1,0),(0,0,1))
    x.extend((*a,*b,*c,*a,*c,*b))
    return x


class IndexedWorkerModeTests(unittest.TestCase):
    def test_default_production_path_uses_lossless_indexing(self):
        with mock.patch.dict(os.environ,{},clear=True):
            self.assertTrue(enabled())
            candidate = prepare_indexed_preview(packed())
            self.assertIsNotNone(candidate)
            self.assertTrue(candidate.matches_source_bytes(packed()))

    def test_raw_and_split_diagnostics_excluded(self):
        for mode in ('split','raw-direct','raw-split'):
            with self.subTest(mode=mode),mock.patch.dict(os.environ,{
                    'FULLSPECTRUM_PREVIEW_INDEXED':'1',
                    'FULLSPECTRUM_PREVIEW_UPLOAD':mode},clear=True):
                self.assertFalse(enabled())
                self.assertIsNone(prepare_indexed_preview(packed()))

    def test_optin_candidate_exact_and_saves_bytes(self):
        source=packed()
        with mock.patch.dict(os.environ,{'FULLSPECTRUM_PREVIEW_INDEXED':'1'},clear=True):
            candidate=prepare_indexed_preview(source)
        self.assertIsNotNone(candidate)
        self.assertTrue(candidate.matches_source_bytes(source))
        self.assertEqual(candidate.unique_vertex_count,3)
        self.assertEqual(candidate.indices.size,6)

    def test_cancellation_skips_and_discards(self):
        with mock.patch.dict(os.environ,{'FULLSPECTRUM_PREVIEW_INDEXED':'1'},clear=True):
            self.assertIsNone(prepare_indexed_preview(packed(), cancelled=lambda:True))
            self.assertIsNone(prepare_indexed_preview(packed(), cancelled=iter([False,True]).__next__))

    def test_memory_cap_prevents_unbounded_indexing(self):
        with mock.patch.dict(os.environ,{'FULLSPECTRUM_PREVIEW_INDEXED':'1'},clear=True):
            with mock.patch('desktop.qt_app.preview_indexed_mode.MAX_INDEX_SOURCE_BYTES',16):
                self.assertIsNone(prepare_indexed_preview(packed()))

    def test_nonrepeating_vertices_do_not_get_uploaded_as_indexed(self):
        a=array('f')
        for i in range(6):
            a.extend((float(i),float(i+1),0.,0.,0.,1.,1.,0.,0.,1.,0.,0.))
        with mock.patch.dict(os.environ,{'FULLSPECTRUM_PREVIEW_INDEXED':'1'},clear=True):
            self.assertIsNone(prepare_indexed_preview(a))


class IndexedOpenGLUploadTests(unittest.TestCase):
    def test_gl_upload_exact_reconstruction_and_layout(self):
        # Isolate actual GL method from installed source; QOpenGLWidget not required.
        path=Path(__file__).resolve().parents[1]/'desktop'/'qt_app'/'gl_viewport.py'
        source=path.read_text(encoding='utf-8-sig')
        tree=ast.parse(source)
        methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
                 and n.name=='_upload_indexed_candidate']
        self.assertEqual(len(methods),1)
        fn=ast.fix_missing_locations(ast.Module(body=[methods[0]],type_ignores=[]))
        namespace={'ctypes':ctypes,'perf_counter':__import__('time').perf_counter,
                   'require_upload_budget':lambda n: n}
        exec(compile(fn,'<isolated indexed GL method>','exec'),namespace)
        method=namespace['_upload_indexed_candidate']
        class View:
            _ebo=0
            _vao=3
            _vbo=4
            _dirty=True
        view=View()
        source_data=packed()
        candidate=make_indexed_candidate(source_data)
        gl=FakeGL()
        method(view,gl,candidate)
        self.assertTrue(view._indexed_active)
        self.assertFalse(view._dirty)
        self.assertEqual(view._ebo,42)
        self.assertEqual(view._preview_upload_bytes,candidate.indexed_bytes)
        self.assertEqual(view._preview_upload_detail['mode'],'indexed-direct')
        v_size,v_bytes=gl.data[gl.GL_ARRAY_BUFFER]
        i_size,i_bytes=gl.data[gl.GL_ELEMENT_ARRAY_BUFFER]
        self.assertEqual(v_size,candidate.vertices.nbytes)
        self.assertEqual(i_size,candidate.indices.nbytes)
        unique=np.frombuffer(v_bytes,dtype='V48')
        indices=np.frombuffer(i_bytes,dtype=np.uint32)
        self.assertEqual(unique[indices].tobytes(),source_data.tobytes())
        self.assertEqual(sum(1 for x in gl.calls if x[0]=='upload'),2)
        self.assertEqual({x[1] for x in gl.calls if x[0]=='attrib'},{0,1,2,3})

    def test_gl_vbo_ebo_cleanup_and_draw_elements_wiring(self):
        path=Path(__file__).resolve().parents[1]/'desktop'/'qt_app'/'gl_viewport.py'
        text=path.read_text(encoding='utf-8-sig')
        self.assertIn('gl.glDrawElements(gl.GL_TRIANGLES,self._verts,gl.GL_UNSIGNED_INT,None)',text)
        self.assertIn('gl.glDrawArrays(gl.GL_TRIANGLES,0,self._verts)',text)
        self.assertIn('if self._ebo:self._gl.glDeleteBuffers(1,[self._ebo]);self._ebo=0',text)
        self.assertIn("and getattr(self, '_preview_upload_mode', 'direct') == 'direct'",text)


if __name__=='__main__':
    unittest.main()
