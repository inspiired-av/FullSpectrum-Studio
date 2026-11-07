"""Direct-upload OpenGL contract: no split-only method is needed.

The older baseline mock deliberately implements glBufferData, not glBufferSubData.
Extract only _upload from its source AST so these tests work headlessly.
"""
from __future__ import annotations

from array import array
import ast
import ctypes
import os
from pathlib import Path
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from desktop.qt_app.preview_performance import require_upload_budget

ROOT=Path(__file__).resolve().parents[1]


def isolated_upload():
    source=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
    cls=next(n for n in ast.parse(source).body
             if isinstance(n,ast.ClassDef) and n.name=='ModelViewport')
    func=next(n for n in cls.body
              if isinstance(n,ast.FunctionDef) and n.name=='_upload')
    tree=ast.Module(body=[func],type_ignores=[])
    ast.fix_missing_locations(tree)
    namespace={'ctypes':ctypes,'perf_counter':time.perf_counter,
               'require_upload_budget':require_upload_budget}
    exec(compile(tree,'<isolated GPU upload>','exec'),namespace)
    return namespace['_upload']


class DirectOnlyGL:
    GL_ARRAY_BUFFER=34962
    GL_STATIC_DRAW=35044
    GL_FLOAT=5126
    GL_FALSE=0

    def __init__(self):
        self.calls=[]
        self.bytes_seen=None

    def glBindVertexArray(self,*args):pass
    def glBindBuffer(self,*args):pass
    def glEnableVertexAttribArray(self,*args):pass
    def glVertexAttribPointer(self,*args):pass

    def glBufferData(self,target,size,pointer,usage):
        self.calls.append(('glBufferData',size))
        self.bytes_seen=ctypes.string_at(pointer,size) if pointer is not None and size else b''


class DirectUploadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upload=staticmethod(isolated_upload())

    def _state(self, data, mode=None):
        gl=DirectOnlyGL()  # Intentionally no glBufferSubData.
        kws={'_gl':gl,'_vao':1,'_vbo':2,'_data':data,'_dirty':True,
             '_preview_upload_ms':None,'_preview_upload_bytes':0,
             '_preview_upload_detail':None}
        if mode is not None:
            kws['_preview_upload_mode']=mode
        return SimpleNamespace(**kws)

    def test_direct_upload_without_split_driver_api(self):
        arr=array('f',[0.,-0.,1.,-2.5,3.125]*7)
        state=self._state(arr,'direct')
        self.upload(state)
        self.assertEqual(state._gl.bytes_seen,arr.tobytes())
        self.assertEqual(state._gl.calls,[('glBufferData',len(arr)*4)])
        self.assertFalse(state._dirty)
        self.assertEqual(state._preview_upload_detail['mode'],'direct')

    def test_default_direct_mode_even_with_diagnostic_environment(self):
        arr=array('f',[1.25])
        state=self._state(arr)
        with patch.dict(os.environ, {'FULLSPECTRUM_PREVIEW_UPLOAD':'raw-split'}):
            self.upload(state)
        self.assertEqual(state._gl.bytes_seen,arr.tobytes())
        self.assertEqual(state._preview_upload_detail['mode'],'direct')

    def test_empty_direct_upload_without_split_driver_api(self):
        state=self._state(None,'direct')
        self.upload(state)
        self.assertEqual(state._gl.bytes_seen,b'')
        self.assertEqual(state._preview_upload_bytes,0)
        self.assertFalse(state._dirty)

    def test_bad_mode_falls_back_to_direct_without_split_driver_api(self):
        state=self._state(array('f',[10.]),'not-a-mode')
        self.upload(state)
        self.assertEqual(state._preview_upload_detail['mode'],'direct')
        self.assertEqual(state._gl.calls,[('glBufferData',4)])


if __name__=='__main__':
    unittest.main()
