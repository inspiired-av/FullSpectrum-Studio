"""UI-only forecast snapshot: retain stale results for the same source model.

This module is independent of PySide6 and the conversion engine. Its state is
session-only and never written to preferences or into a source 3MF.
"""
from __future__ import annotations


class ForecastViewState:
    def __init__(self):
        self.model_path = ''
        self.previous = None
        self.stale = False

    @property
    def has_previous(self):
        return self.previous is not None

    def reset(self, model_path):
        self.model_path = str(model_path or '')
        self.previous = None
        self.stale = False

    def invalidate(self):
        self.stale = self.has_previous

    def accept(self, model_path, result):
        if str(model_path or '') != self.model_path:
            return False
        self.previous = result
        self.stale = False
        return True
