import tempfile
import unittest
from pathlib import Path
try:
    from desktop.windows_mesh_preview import read_colored_obj, projected_faces
except ModuleNotFoundError:
    from windows_mesh_preview import read_colored_obj, projected_faces

class WindowsPreviewMeshTests(unittest.TestCase):
    def test_reads_triangles_and_mtl_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'color.mtl').write_text('newmtl slot_1\nKd 0.8 0.6 0.4\n')
            (root/'color.obj').write_text('mtllib color.mtl\n'
                'v 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl slot_1\nf 1 2 3\n')
            vertices, faces, count = read_colored_obj(root/'color.obj')
            self.assertEqual(count, 1)
            self.assertEqual(faces[0][3], (204,153,102))
            self.assertEqual(len(projected_faces(vertices, faces, 500, 300)), 1)
    def test_deterministic_sampling_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'large.obj'
            path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\n'+'f 1 2 3\n'*200)
            a = read_colored_obj(path, max_faces=10)
            b = read_colored_obj(path, max_faces=10)
            self.assertEqual(a,b)
            self.assertEqual(len(a[1]),10)
            self.assertEqual(a[2],200)
    def test_rejects_invalid_face_indices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.obj'
            path.write_text('v 0 0 0\nf 1 5 9\n')
            with self.assertRaises(ValueError):
                read_colored_obj(path)

if __name__ == '__main__': unittest.main()
