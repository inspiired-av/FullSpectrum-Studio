"""UI-only view state. Never mutate an input model or call the conversion engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

MODEL_FILE_FILTER = "3D models (*.3mf *.obj *.glb);;All files (*)"
REFERENCE_FILE_FILTER = "Reference images and models (*.png *.jpg *.jpeg *.webp *.obj *.glb *.3mf);;All files (*)"


@dataclass
class ShellState:
    model_path: str = ""
    reference_path: str = ""

    def select_model(self, path: str) -> bool:
        if not path or "\x00" in path:
            return False
        self.model_path = str(path)
        return True

    def select_reference(self, path: str) -> bool:
        if not path or "\x00" in path:
            return False
        self.reference_path = str(path)
        return True


def display_filename(path: str) -> str:
    """Allow Windows filenames to display consistently on all test hosts."""
    if not path:
        return "No model selected"
    if "\\" in path:
        return PureWindowsPath(path).name
    return PurePosixPath(path).name
