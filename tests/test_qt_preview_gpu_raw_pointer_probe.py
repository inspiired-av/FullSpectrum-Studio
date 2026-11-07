"""Exact-byte raw OpenGL upload probe and backward-compatible default behavior.

Isolates ModelViewport._upload from its AST, without requiring a Qt window or GPU.
"""
from __future__ import annotations

import ast
from array import array
import ctypes
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from desktop.qt_app.preview_performance import (
    preview_performance_snapshot, format_preview_performance, require_upload_budget)

ROOT=Path(__file__).resolve().parents[1]


class StubGL:
    GL_ARRAY_BUFFER=34962
    GL_STATIC_DRAW=35044
    GL_FLOAT=5126
    GL_FALSE=0
    GL_NO_ERROR=0

    def __init__(self):
        self.storage=b''
        self.operations=[]
        self.error=0

    def glBindVertexArray(self,*_):pass
    def glBindBuffer(self,*_):pass
    def glEnableVertexAttribArray(self,*_):pass
    def glVertexAttribPointer(self,*_):pass
    def glGetError(self):return self.error

    def _read(self,pointer,size):
        return ctypes.string_at(pointer,size) if pointer is not None and size else b''

    def glBufferData(self,target,size,pointer,usage):
        self.operations.append(('data',int(size),pointer is not None))
        self.storage=self._read(pointer,size) if pointer is not None else bytes(size)

    def glBufferSubData(self,target,offset,size,pointer):
        self.operations.append(('subdata',int(size)))
        b=bytearray(self.storage)
        b[offset:offset+size]=self._read(pointer,size)
        self.storage=bytes(b)


def isolate_upload():
    source=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ModelViewport')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_upload')
    module=ast.Module(body=[method],type_ignores=[])
    ast.fix_missing_locations(module)
    namespace={'ctypes':ctypes,'perf_counter':time.perf_counter,
               'require_upload_budget':require_upload_budget}
    exec(compile(module,'<isolated GPU upload>','exec'),namespace)
    return namespace['_upload']


class RawUploadProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upload=staticmethod(isolate_upload())

    def state(self,mode,values):
        gl=StubGL()
        data=array('f',values) if values is not None else None
        state=SimpleNamespace(_gl=gl,_vao=1,_vbo=2,_data=data,_dirty=True,
                              _preview_upload_bytes=0,_preview_upload_ms=None,
                              _preview_upload_detail=None,_preview_upload_mode=mode)
        return state

    def run_mode(self,mode,values):
        state=self.state(mode,values)
        # The real raw function has the same OpenGL 1.5 signature. The stub reads
        # from its raw void* address, so no float format conversion can hide errors.
        package={}
        names=['OpenGL','OpenGL.raw','OpenGL.raw.GL',
               'OpenGL.raw.GL.VERSION','OpenGL.raw.GL.VERSION.GL_1_5']
        for name in names:
            pkg=types.ModuleType(name)
            if name != names[-1]:pkg.__path__=[]
            package[name]=pkg
        raw=package[names[-1]]
        raw.glBufferData=state._gl.glBufferData
        raw.glBufferSubData=state._gl.glBufferSubData
        with patch.dict(sys.modules,package):
            self.upload(state)
        return state

    def test_raw_direct_matches_wrapped_direct_exact_bytes(self):
        values=[0.0,-0.0,1.0,-2.5,1e-35,3.125,99.875]*13
        classic=self.run_mode('direct',values)
        raw=self.run_mode('raw-direct',values)
        self.assertEqual(raw._gl.storage,classic._gl.storage)
        self.assertEqual(raw._gl.storage,array('f',values).tobytes())
        self.assertEqual(raw._gl.operations,[('data',len(values)*4,True)])
        self.assertEqual(raw._preview_upload_detail['mode'],'raw-direct')
        self.assertFalse(raw._dirty)

    def test_raw_split_matches_wrapped_split_exact_bytes(self):
        values=[-0.0,0.125,0.5,1.0,-3.0]*20
        classic=self.run_mode('split',values)
        raw=self.run_mode('raw-split',values)
        self.assertEqual(raw._gl.storage,classic._gl.storage)
        self.assertEqual(raw._gl.operations,[('data',len(values)*4,False),
                                              ('subdata',len(values)*4)])
        self.assertGreaterEqual(raw._preview_upload_detail['allocation_ms'],0)
        self.assertGreaterEqual(raw._preview_upload_detail['transfer_ms'],0)

    def test_zero_byte_raw_mode(self):
        for mode in ('raw-direct','raw-split'):
            with self.subTest(mode=mode):
                state=self.run_mode(mode,None)
                self.assertEqual(state._gl.storage,b'')
                self.assertEqual(state._preview_upload_bytes,0)
                self.assertEqual(state._gl.operations,[('data',0,False)])

    def test_raw_driver_error_preserves_dirty_state(self):
        state=self.state('raw-direct',[1.0,2.0])
        state._gl.error=0x0501
        names=['OpenGL','OpenGL.raw','OpenGL.raw.GL',
               'OpenGL.raw.GL.VERSION','OpenGL.raw.GL.VERSION.GL_1_5']
        modules={name:types.ModuleType(name) for name in names}
        for name in names[:-1]:modules[name].__path__=[]
        modules[names[-1]].glBufferData=state._gl.glBufferData
        modules[names[-1]].glBufferSubData=state._gl.glBufferSubData
        with patch.dict(sys.modules,modules):
            with self.assertRaisesRegex(RuntimeError,'0x0501'):
                self.upload(state)
        self.assertTrue(state._dirty)
        self.assertEqual(state._preview_upload_bytes,0)

    def test_invalid_mode_still_uses_wrapped_direct(self):
        state=self.run_mode('surprise',[0.0,1.0])
        self.assertEqual(state._preview_upload_detail['mode'],'direct')
        self.assertEqual(state._gl.operations,[('data',8,True)])

    def test_raw_mode_is_explicit_opt_in(self):
        source=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
        self.assertIn("'raw-direct'",source)
        self.assertIn("'raw-split'",source)
        self.assertIn('FULLSPECTRUM_PREVIEW_UPLOAD',source)
        self.assertIn('from OpenGL.raw.GL.VERSION.GL_1_5 import',source)
        self.assertNotIn('.tobytes()',ast.get_source_segment(source,
            next(n for n in next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef)
                and n.name=='ModelViewport').body if isinstance(n,ast.FunctionDef)
                and n.name=='_upload')))

    def test_raw_mode_is_labeled_without_changing_existing_labels(self):
        mesh=SimpleNamespace(vertices=[(0,0,0)]*3,triangles=[(0,1,2)],
                             source_triangles=1,face_colors=(),corner_colors=(),
                             load_profile=None)
        for mode,label in [('direct','Direct (indexing disabled)'),('split','Split diagnostic (opt-in)'),
                           ('raw-direct','Raw direct diagnostic (opt-in)'),
                           ('raw-split','Raw split diagnostic (opt-in)')]:
            snap=preview_performance_snapshot(mesh,upload_submit_ms=3.2,
                  upload_detail={'mode':mode,'direct_ms':1.0,'allocation_ms':1.0,
                                 'transfer_ms':2.0,'pointer_ms':0.0})
            self.assertIn(label,format_preview_performance(snap))
        for mode, preferred, expected in [
                ('direct', True, 'Direct (fallback)'),
                ('indexed-direct', False, 'Indexed Direct (default)')]:
            snap=preview_performance_snapshot(mesh,upload_submit_ms=3.2,
                  upload_detail={'mode':mode,'indexed_preferred':preferred,
                                 'direct_ms':1.0,'pointer_ms':0.0})
            self.assertIn(expected,format_preview_performance(snap))


if __name__=='__main__':
    unittest.main()
