"""Regression coverage for UI-only plate deduplication and source preference."""
from __future__ import annotations

from dataclasses import dataclass
import unittest

from desktop.qt_app.plate_picker_policy import preferred_plate_assets


@dataclass(frozen=True)
class Plate:
    printer: str
    vendor: str
    source: str
    texture: str | None = None
    profile: str = 'printer.json'


class PreferredPlateTests(unittest.TestCase):
    def test_shared_non_bambu_prefers_orca(self):
        bambu=Plate('Creality K1', 'Creality', 'Bambu Studio')
        orca=Plate('Creality K1', 'Creality', 'OrcaSlicer')
        self.assertEqual(preferred_plate_assets((bambu, orca)), (orca,))
        self.assertEqual(preferred_plate_assets((orca, bambu)), (orca,))

    def test_shared_bambu_prefers_bambu_studio(self):
        orca=Plate('Bambu Lab H2C', 'BBL', 'OrcaSlicer')
        bambu=Plate('Bambu Lab H2C', 'BBL', 'Bambu Studio')
        self.assertEqual(preferred_plate_assets((orca, bambu)), (bambu,))

    def test_single_slicer_retains_full_printer_catalog(self):
        assets=(Plate('Anycubic Kobra', 'Anycubic', 'Bambu Studio'),
                Plate('Creality K1', 'Creality', 'Bambu Studio'),
                Plate('Bambu Lab H2C', 'BBL', 'Bambu Studio'))
        self.assertEqual(set(preferred_plate_assets(assets)), set(assets))

    def test_bambu_only_non_bambu_is_preserved_with_orca_installed(self):
        unique=Plate('Anycubic 4Max Pro', 'Anycubic', 'Bambu Studio')
        other=Plate('Qidi Q2', 'Qidi', 'OrcaSlicer')
        self.assertEqual(set(preferred_plate_assets((unique,other))),{unique,other})

    def test_identity_is_vendor_and_model_not_just_printer(self):
        a=Plate('Mini', 'Vendor1', 'OrcaSlicer')
        b=Plate('Mini', 'Vendor2', 'OrcaSlicer')
        self.assertEqual(set(preferred_plate_assets((a,b))),{a,b})

    def test_duplicate_same_source_prefers_textured(self):
        a=Plate('K1','Creality','OrcaSlicer')
        b=Plate('K1','Creality','OrcaSlicer','texture.svg')
        self.assertEqual(preferred_plate_assets((a,b)),(b,))

    def test_readonly_catalog(self):
        items=[Plate('H2C','BBL','OrcaSlicer'),Plate('H2C','BBL','Bambu Studio')]
        self.assertEqual(len(preferred_plate_assets(items)),1)
        self.assertEqual(len(items),2)

if __name__ == '__main__':
    unittest.main()
