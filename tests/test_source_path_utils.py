"""Regression coverage for Windows/Tk path spelling differences."""
import unittest

from desktop.source_path_utils import same_source_path


class SourcePathEqualityTests(unittest.TestCase):
    def test_windows_tk_forward_slashes_equal_native_backslashes(self):
        self.assertTrue(same_source_path(
            'C:/Users/Alex/Downloads/3D Prints/VSLA v4_SOLID_NoFilter.3mf',
            r'C:\Users\Alex\Downloads\3D Prints\VSLA v4_SOLID_NoFilter.3mf',
        ))

    def test_windows_path_case_insensitivity(self):
        self.assertTrue(same_source_path(
            'c:/USERS/Alex/Downloads/Source.3mf',
            r'C:\users\alex\downloads\source.3mf',
        ))

    def test_different_windows_models_are_not_equal(self):
        self.assertFalse(same_source_path(
            'C:/Users/Alex/Downloads/first.3mf',
            'C:/Users/Alex/Downloads/second.3mf',
        ))

    def test_different_drives_are_not_equal(self):
        self.assertFalse(same_source_path('C:/Temp/model.3mf', 'D:/Temp/model.3mf'))

    def test_missing_paths_are_not_equal(self):
        self.assertFalse(same_source_path(None, r'C:\model.3mf'))
        self.assertFalse(same_source_path('', r'C:\model.3mf'))
        self.assertFalse(same_source_path(None, None))

    def test_unc_paths(self):
        self.assertTrue(same_source_path('//server/share/models/part.3mf',
                                         r'\\server\share\models\part.3mf'))


if __name__ == "__main__":
    unittest.main()
