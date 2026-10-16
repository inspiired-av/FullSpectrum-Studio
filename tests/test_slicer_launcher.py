"""Tests for Windows slicer executable discovery and patch idempotency."""
import os
import tempfile
import unittest
from pathlib import Path

from desktop.slicer_launcher import find_windows_slicer


class SlicerLaunchTests(unittest.TestCase):
    def test_bambu_from_program_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Bambu Studio" / "bambu-studio.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            found = find_windows_slicer("Bambu Studio", environ={"ProgramFiles": tmp}, registry_candidates=[], path_lookup=lambda _: None)
            self.assertEqual(found, exe)

    def test_orca_from_program_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "OrcaSlicer" / "orca-slicer.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            self.assertEqual(find_windows_slicer("OrcaSlicer", environ={"ProgramFiles": tmp}, registry_candidates=[], path_lookup=lambda _: None), exe)

    def test_bambu_from_local_programs(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Programs" / "Bambu Studio" / "bambu-studio.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            found = find_windows_slicer("Bambu Studio", environ={"LOCALAPPDATA": tmp}, registry_candidates=[], path_lookup=lambda _: None)
            self.assertEqual(found, exe)

    def test_registry_location_has_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Portable" / "bambu-studio.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            found = find_windows_slicer("Bambu Studio", environ={}, registry_candidates=[exe], path_lookup=lambda _: None)
            self.assertEqual(found, exe)

    def test_path_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "bambu-studio.exe"
            exe.touch()
            found = find_windows_slicer("Bambu Studio", environ={}, registry_candidates=[], path_lookup=lambda name: str(exe) if name == "bambu-studio.exe" else None)
            self.assertEqual(found, exe)

    def test_missing_returns_none(self):
        self.assertIsNone(find_windows_slicer("Bambu Studio", environ={}, registry_candidates=[], path_lookup=lambda _: None))

    def test_unknown_application_fails_closed(self):
        with self.assertRaises(ValueError):
            find_windows_slicer("Windows Default Viewer", environ={}, registry_candidates=[], path_lookup=lambda _: None)
