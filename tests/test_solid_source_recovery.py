import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from desktop.source_path_utils import find_original_material_source


def create_3mf(path, native=False):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", "<model/>")
        if native:
            archive.writestr("Metadata/project_settings.config", "{}")


def is_material_source(path):
    with ZipFile(path) as archive:
        return "Metadata/project_settings.config" not in archive.namelist()


class OriginalMaterialSourceTests(unittest.TestCase):
    def test_finds_original_for_official_bambu_derived_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "VSLA v4_SOLID_NoFilter.3mf"
            derived = root / "VSLA v4_SOLID_NoFilter_FullSpectrum_OFFICIAL_BAMBU_DERIVED_v0.5.1.3mf"
            create_3mf(original)
            create_3mf(derived, native=True)
            self.assertEqual(
                find_original_material_source(derived, is_material_source), original
            )

    def test_no_original_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            derived = Path(directory) / "example_FullSpectrum_OFFICIAL_BAMBU_DERIVED_v0.5.1.3mf"
            create_3mf(derived, native=True)
            self.assertIsNone(find_original_material_source(derived, is_material_source))

    def test_refuses_slicer_native_lookalike_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "example.3mf"
            derived = root / "example_FullSpectrum_OFFICIAL_BAMBU_DERIVED_v0.5.1.3mf"
            create_3mf(original, native=True)
            create_3mf(derived, native=True)
            self.assertIsNone(find_original_material_source(derived, is_material_source))

    def test_does_not_guess_other_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "example.3mf"
            create_3mf(original)
            for name in ("other.3mf", "example_FullSpectrum.3mf", "example.obj"):
                self.assertIsNone(find_original_material_source(root / name, is_material_source))

    def test_invalid_candidate_archive_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "example.3mf").write_bytes(b"not a zip")
            self.assertIsNone(find_original_material_source(
                root / "example_FullSpectrum_OUTPUT.3mf", is_material_source
            ))


if __name__ == "__main__":
    unittest.main()
