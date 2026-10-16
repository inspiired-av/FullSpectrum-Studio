"""Combobox that does not change a saved planning choice when the page scrolls."""
from PySide6.QtWidgets import QComboBox


class WheelSafeComboBox(QComboBox):
    """Let the enclosing scroll view handle wheel input unless the popup is open.

    Mouse clicks and keyboard navigation retain ordinary QComboBox behavior.
    QListView handles wheel motion normally when its dropdown is open.
    """

    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()
