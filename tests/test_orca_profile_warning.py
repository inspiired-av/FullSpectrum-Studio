import unittest
from orca_profile_warning import orca_h2c_warning


class OrcaWarningTests(unittest.TestCase):
    def test_h2c_orca_2_5_generation_does_not_warn(self):
        msg=orca_h2c_warning({'slicer':'OrcaSlicer','slicerVersion':'2.5.0-dev',
                              'printerPreset':'Bambu Lab H2C 0.2 nozzle'},'OrcaSlicer')
        self.assertEqual('', msg)

    def test_warns_cross_slicer_template(self):
        msg=orca_h2c_warning({'slicer':'OrcaSlicer','slicerVersion':'2.5.0-dev',
                              'printerPreset':'Bambu Lab H2C 0.2 nozzle'},'Bambu Studio')
        self.assertIn('Template was saved by OrcaSlicer',msg)

    def test_older_orca_template_warns_separately(self):
        msg=orca_h2c_warning({'slicer':'OrcaSlicer','slicerVersion':'2.4.0',
                              'printerPreset':'H2C'},'OrcaSlicer')
        self.assertIn('older than 2.5.0',msg)

    def test_other_printers_do_not_warn_with_matching_slicer(self):
        self.assertEqual('',orca_h2c_warning({'slicer':'OrcaSlicer','printerPreset':'H2D'},'OrcaSlicer'))

    def test_unknown_template_no_warning(self):
        self.assertEqual('',orca_h2c_warning(None,'OrcaSlicer'))
