"""Run the independent Qt UI shell: python -m desktop.qt_app."""
from __future__ import annotations

import sys


def main(argv=None):
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is not installed. Run: python -m pip install -r requirements-qt.txt",
            file=sys.stderr,
        )
        return 2

    from desktop.qt_app.main_window import MainWindow
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("FullSpectrum Studio")
    app.setOrganizationName("FullSpectrum Studio")
    from desktop.qt_app.theme import apply_theme
    apply_theme(app)

    window = MainWindow()
    window.show()
    # QApplication normally owns the event loop. Reuse an existing QApplication
    # for embedded testing without trying to nest an event loop.
    if owns_app:
        return app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
