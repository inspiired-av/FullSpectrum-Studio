"""Proof-of-concept only; production rendering remains unchanged."""
from array import array
import unittest
import numpy as np
from desktop.qt_app.preview_indexing import (
    BYTES_PER_VERTEX, make_indexed_candidate,
)


def record(pos=(1, 2, 3), normal=(0, 0, 1), color=(1, 0, 0), tag=(1, 0, 0)):
    return (*pos, *normal, *color, *tag)


def records(*items):
    a = array('f')
    for item in items:
        a.extend(item)
    return a


class LosslessIndexingTests(unittest.TestCase):
    def test_duplicates_reduce_memory_including_index_overhead(self):
        a, b, c = record((0, 0, 0)), record((1, 0, 0)), record((0, 1, 0))
        source = records(a, b, c, a, c, b)
        candidate = make_indexed_candidate(source)
        self.assertEqual(candidate.unique_vertex_count, 3)
        self.assertEqual(candidate.source_vertex_count, 6)
        self.assertTrue(candidate.matches_source_bytes(source))
        self.assertLess(candidate.indexed_bytes, candidate.source_bytes)
        self.assertTrue(candidate.worth_uploading(minimum_savings_percent=10))

    def test_paint_and_normal_seams_are_distinct(self):
        a = record()
        b = record(color=(0, 1, 0), tag=(0, 1, 0))
        c = record(normal=(0, 1, 0))
        source = records(a, b, c)
        candidate = make_indexed_candidate(source)
        self.assertEqual(candidate.unique_vertex_count, 3)
        self.assertTrue(candidate.matches_source_bytes(source))
        self.assertFalse(candidate.worth_uploading())

    def test_float_bits_are_preserved_including_signed_zero(self):
        # Build from literal IEEE-754 bytes to check the exact bit pattern.
        raw = np.array([0, 0x80000000, 0x7fc00001] * 4, dtype=np.uint32).tobytes()
        a = array('f')
        a.frombytes(raw)
        candidate = make_indexed_candidate(a)
        self.assertTrue(candidate.matches_source_bytes(a))
        self.assertEqual(candidate.vertices.tobytes(), raw)

    def test_rejects_invalid_packed_data(self):
        for wrong in (array('d', [0.0] * 12), array('f', [0.0] * 11)):
            with self.assertRaises(ValueError):
                make_indexed_candidate(wrong)

    def test_empty_input(self):
        a = array('f')
        candidate = make_indexed_candidate(a)
        self.assertEqual(candidate.indexed_bytes, 0)
        self.assertTrue(candidate.matches_source_bytes(a))
        self.assertFalse(candidate.worth_uploading())

    def test_does_not_mutate_source_buffer(self):
        source = records(record(), record(color=(0,1,0)), record())
        before = source.tobytes()
        candidate = make_indexed_candidate(source)
        self.assertEqual(source.tobytes(), before)
        self.assertTrue(candidate.matches_source_bytes(source))

    def test_mutating_source_after_construction_does_not_change_indexed_candidate(self):
        source = records(record(), record(), record())
        candidate = make_indexed_candidate(source)
        bytes_before = candidate.vertices.tobytes()
        source[0] = 57
        self.assertEqual(candidate.vertices.tobytes(), bytes_before)

    def test_uint32_indices_and_48_byte_records(self):
        source = records(record(), record())
        c = make_indexed_candidate(source)
        self.assertEqual(BYTES_PER_VERTEX, 48)
        self.assertEqual(c.indices.dtype, np.dtype('uint32'))
        self.assertEqual(c.vertices.dtype.itemsize, 48)


if __name__ == '__main__':
    unittest.main()
