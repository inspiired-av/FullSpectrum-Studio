import unittest
from phase3_ui_guard import strategy_protection_conflict, optimizer_decision_summary


class Phase3UiGuardTests(unittest.TestCase):
    def test_official_strategy_accepts_protected_grey(self):
        self.assertIsNone(strategy_protection_conflict('official', {'#9098A8':'Panchroma Grey'}))

    def test_cmykw_without_protection_is_allowed(self):
        self.assertIsNone(strategy_protection_conflict('cmykw', {}))

    def test_cmykw_protected_colors_explained(self):
        warning = strategy_protection_conflict('cmykw', {'#9098A8':'Panchroma Grey'})
        self.assertIn('1 protected solid-color assignment',warning)
        self.assertIn('official',warning)

    def test_plural_protection_message(self):
        warning = strategy_protection_conflict('cmykw', {'#000000':'a','#FFFFFF':'b'})
        self.assertIn('2 protected solid-color assignments',warning)

    def test_optimizer_rejection_visible(self):
        warning = 'Phase 3 global recipe selection: Retained earlier palette: no safe global improvement; weighted mean dE 3.74 -> 3.70'
        summary = optimizer_decision_summary([warning])
        self.assertIn('NOT APPLIED',summary)
        self.assertIn('Retained earlier palette',summary)

    def test_optimizer_acceptance_visible(self):
        warning = 'Phase 3 global recipe selection: Global recipe selection improved mean and maintained worst error'
        summary = optimizer_decision_summary([warning])
        self.assertIn('APPLIED',summary)

    def test_no_optimizer_info(self):
        self.assertIsNone(optimizer_decision_summary(['Another warning']))

    def test_malformed_warnings_ignored(self):
        self.assertIsNone(optimizer_decision_summary([None, {'bad':1}]))


if __name__ == '__main__':
    unittest.main()
