"""CPU-call GPU upload diagnostics: default behavior and opt-in split comparison.

Runs without a Qt window, GPU, or PyOpenGL installation. We isolate the real
ModelViewport._upload method so both modes execute the exact production code.
"""
from __future__ import annotations

import ast
from array import array
import ctypes
from pathlib import Path
import struct
import time
import unittest
from types import SimpleNamespace

from desktop.qt_app.preview_performance import (
    preview_performance_snapshot, format_preview_performance,
    require_upload_budget,
)

ROOT = Path(__file__).resolve().parents[1]


class MockGL:
    GL_ARRAY_BUFFER=34962
    GL_STATIC_DRAW=35044
    GL_FLOAT=5126
    GL_FALSE=0

    def __init__(self):
        self.storage=bytearray()
        self.calls=[]
        self.fail_transfer=False

    def glBindVertexArray(self,*args):pass
    def glBindBuffer(self,*args):pass
    def glEnableVertexAttribArray(self,*args):pass
    def glVertexAttribPointer(self,*args):pass

    def glBufferData(self,target,size,pointer,usage):
        self.calls.append(('data',size,pointer is not None))
        self.storage=bytearray(size)
        if pointer is not None and size:
            self.storage[:]=bytes(pointer)

    def glBufferSubData(self,target,offset,size,pointer):
        self.calls.append(('subdata',size))
        if self.fail_transfer:
            raise RuntimeError('simulated upload failure')
        if offset<0 or size<0 or offset+size>len(self.storage):
            raise RuntimeError('buffer bounds')
        self.storage[offset:offset+size]=bytes(pointer)


def isolated_upload():
    source=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
    tree=ast.parse(source)
    view=next(n for n in tree.body if isinstance(n,ast.ClassDef)
              and n.name=='ModelViewport')
    method=next(n for n in view.body if isinstance(n,ast.FunctionDef)
                and n.name=='_upload')
    module=ast.Module(body=[method],type_ignores=[])
    ast.fix_missing_locations(module)
    namespace={'ctypes':ctypes,'perf_counter':time.perf_counter,
               'require_upload_budget':require_upload_budget}
    exec(compile(module,'<viewport upload>','exec'),namespace)
    return namespace['_upload']


class PreviewGpuUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upload=staticmethod(isolated_upload())

    def view(self,values,mode=None):
        gpu=MockGL()
        data=array('f',values) if values is not None else None
        state=SimpleNamespace(_gl=gpu,_vao=1,_vbo=2,_data=data,
                              _dirty=True,_preview_upload_ms=None,
                              _preview_upload_bytes=0,
                              _preview_upload_detail=None)
        if mode is not None:
            state._preview_upload_mode=mode
        return state,gpu,data

    def test_default_uses_existing_single_call_upload(self):
        state,gl,data=self.view([1.,2.,3.,-0.,4.25])
        original=data.tobytes()
        self.upload(state)
        self.assertEqual(gl.calls,[('data',len(original),True)])
        self.assertEqual(bytes(gl.storage),original)
        self.assertEqual(data.tobytes(),original)
        self.assertEqual(state._preview_upload_detail['mode'],'direct')
        self.assertIsNone(state._preview_upload_detail['transfer_ms'])
        self.assertGreaterEqual(state._preview_upload_detail['direct_ms'],0)
        self.assertFalse(state._dirty)

    def test_split_allocates_then_transfers_exact_same_bytes(self):
        values=[0.,-0.,1.0,-2.,0.001,1e-20,123456.0]*9
        baseline,gl1,arr1=self.view(values,'direct')
        candidate,gl2,arr2=self.view(values,'split')
        self.upload(baseline)
        self.upload(candidate)
        self.assertEqual(bytes(gl2.storage),bytes(gl1.storage))
        self.assertEqual(gl2.calls,[('data',len(arr2)*4,False),
                                    ('subdata',len(arr2)*4)])
        self.assertEqual(candidate._preview_upload_bytes,baseline._preview_upload_bytes)
        self.assertGreaterEqual(candidate._preview_upload_detail['allocation_ms'],0)
        self.assertGreaterEqual(candidate._preview_upload_detail['transfer_ms'],0)
        self.assertFalse(candidate._dirty)

    def test_no_data_safe_in_both_modes(self):
        for mode in ('direct','split'):
            with self.subTest(mode=mode):
                state,gl,_=self.view(None,mode)
                self.upload(state)
                self.assertEqual(gl.storage,bytearray())
                self.assertEqual(state._preview_upload_bytes,0)
                self.assertNotIn('subdata',[call[0] for call in gl.calls])

    def test_invalid_mode_falls_back_to_direct(self):
        state,gl,_=self.view([7.],'unexpected')
        self.upload(state)
        self.assertEqual(state._preview_upload_detail['mode'],'direct')
        self.assertEqual(len(gl.calls),1)

    def test_failed_transfer_does_not_mark_upload_success(self):
        state,gl,_=self.view([1.,2.,3.],'split')
        gl.fail_transfer=True
        with self.assertRaisesRegex(RuntimeError,'simulated upload failure'):
            self.upload(state)
        self.assertTrue(state._dirty)
        self.assertEqual(state._preview_upload_bytes,0)

    def test_wrong_float_width_is_rejected_before_upload(self):
        state,gl,_=self.view([1.,2.])
        state._data=array('d',[1.,2.])
        with self.assertRaisesRegex(ValueError,'float32'):
            self.upload(state)
        self.assertEqual(gl.calls,[])

    def test_preflight_budget_still_applies(self):
        state,gl,_=self.view([1.,2.,3.])
        # Stub a pathological array shape without ever allocating memory.
        class HugeBuffer:
            itemsize=4
            def __len__(self):return 512*1024*1024
        state._data=HugeBuffer()
        with self.assertRaises(ValueError):
            self.upload(state)
        self.assertEqual(gl.calls,[])

    def test_mode_selection_and_diagnostics_reset_are_wired(self):
        source=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
        tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ModelViewport')
        init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
        setter=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='set_mesh')
        snap=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='preview_performance_snapshot')
        self.assertIn('FULLSPECTRUM_PREVIEW_UPLOAD',ast.get_source_segment(source,init))
        self.assertIn('self._preview_upload_detail=None',ast.get_source_segment(source,setter))
        self.assertIn('upload_detail=self._preview_upload_detail',ast.get_source_segment(source,snap))

    def test_isolated_upload_still_has_no_full_byte_copy(self):
        source=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
        ast.parse(source)
        method=next(n for n in next(n for n in ast.parse(source).body
                                    if isinstance(n,ast.ClassDef) and n.name=='ModelViewport').body
                    if isinstance(n,ast.FunctionDef) and n.name=='_upload')
        self.assertNotIn('.tobytes(',ast.get_source_segment(source,method))


class GpuDiagnosticsPresentationTests(unittest.TestCase):
    def test_snapshot_keeps_original_fields(self):
        mesh=SimpleNamespace(vertices=[(0,0,0)]*3,triangles=[(0,1,2)],source_triangles=1,
                             face_colors=(),corner_colors=(),load_profile=None)
        detail={'mode':'split','pointer_ms':0.01,'allocation_ms':4.0,
                'transfer_ms':21.0,'direct_ms':None}
        result=preview_performance_snapshot(mesh,upload_submit_ms=25.1,
                                             upload_bytes=144,upload_detail=detail)
        self.assertEqual(result['gpu_buffer_bytes'],144)
        self.assertEqual(result['upload_submit_ms'],25.1)
        self.assertEqual(result['upload_detail']['mode'],'split')
        detail['mode']='direct'  # snapshot must not share mutable reference
        self.assertEqual(result['upload_detail']['mode'],'split')
        shown=format_preview_performance(result)
        self.assertIn('GPU allocation submission: 4.0 ms',shown)
        self.assertIn('GPU transfer submission: 21.0 ms',shown)
        self.assertIn('not GPU completion',shown)

    def test_default_format_does_not_claim_gpu_completion(self):
        mesh=SimpleNamespace(vertices=[(0,0,0)]*3,triangles=[(0,1,2)],source_triangles=1,
                             face_colors=(),corner_colors=(),load_profile=None)
        result=preview_performance_snapshot(mesh,upload_submit_ms=2,
                                            upload_detail={'mode':'direct','direct_ms':2})
        message=format_preview_performance(result)
        self.assertIn('Direct (indexing disabled)',message)
        self.assertIn('Combined GPU allocation/transfer submission',message)
        self.assertIn('not GPU completion',message)
        fallback=preview_performance_snapshot(mesh,upload_submit_ms=2,
                 upload_detail={'mode':'direct','direct_ms':2,
                                'indexed_preferred':True})
        self.assertIn('Direct (fallback)',format_preview_performance(fallback))


if __name__=='__main__':
    unittest.main()
