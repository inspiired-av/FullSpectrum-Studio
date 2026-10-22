"""Experimental PySide6 frontend; the existing Tkinter frontend is unchanged."""

__all__ = ["main"]


def main(argv=None):
    """Lazy import so the engine and existing tests never require PySide6."""
    from .__main__ import main as run
    return run(argv)
