"""Explicit teardown of top-level Qt test widgets before QApplication shutdown.

This module is used only by tests. ``close`` alone may hide QWidget without
freeing its native QObject; ``deleteLater`` requires a DeferredDelete flush
when tests call processEvents instead of QApplication.exec().
"""
from __future__ import annotations


def dispose_test_widget(widget):
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    import shiboken6

    if not shiboken6.isValid(widget):
        return
    # FilamentsTab.closeEvent waits for any live _Worker QThreads.
    widget.close()
    widget.deleteLater()
    # unittest never runs QApplication.exec(); process DeferredDelete explicitly
    # while a QApplication still exists, before interpreter shutdown.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    if shiboken6.isValid(widget):
        raise AssertionError('Qt test widget was not destroyed by DeferredDelete')
