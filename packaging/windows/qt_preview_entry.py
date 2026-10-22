"""Standalone PyInstaller entry for the Qt preview; never opens legacy Tkinter.

Built only by the release/windows-qt-preview packaging workflow. The optional
smoke test validates that the frozen Qt frontend imports and constructs without
requiring a physical screen or starting an infinite GUI event loop.
"""
from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> int:
    if '--smoke-test' not in sys.argv:
        from desktop.qt_app.__main__ import main as qt_main
        return qt_main()

    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.main_window import MainWindow
    from desktop.qt_app.theme import apply_theme

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    apply_theme(app)
    with TemporaryDirectory(prefix='fullspectrum_qt_smoke_') as directory:
        window = MainWindow(settings_path=Path(directory) / 'settings.json')
        if not window.windowTitle():
            raise RuntimeError('Qt window failed to initialize')
        window.close()
        app.processEvents()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
