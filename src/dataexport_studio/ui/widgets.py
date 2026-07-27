import qtawesome as qta
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QCompleter, QStyle, QStyleOptionButton


class DropdownBox(QComboBox):
    """A searchable selection box with a disclosure icon that tracks popup state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_open = False
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.lineEdit().setFrame(False)
        self.lineEdit().setStyleSheet("border: 0; background: transparent; padding: 0;")
        completer = QCompleter(self.model(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)

    def setCurrentText(self, text):
        index = self.findText(text, Qt.MatchFlag.MatchExactly)
        if index >= 0:
            self.setCurrentIndex(index)
            return
        super().setCurrentText(text)

    def showPopup(self):
        self._popup_open = True
        self.update()
        super().showPopup()

    def hidePopup(self):
        super().hidePopup()
        self._popup_open = False
        self.update()

    def wheelEvent(self, event):
        # Let the containing scroll area handle the wheel instead of changing selection.
        event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        color = "#1A2A43" if self.isEnabled() else "#9AA4B3"
        icon_name = "fa5s.chevron-up" if self._popup_open else "fa5s.chevron-down"
        icon = qta.icon(icon_name, color=color)
        painter = QPainter(self)
        icon.paint(painter, QRect(self.width() - 20, (self.height() - 10) // 2, 10, 10))
        painter.end()


class StyledCheckBox(QCheckBox):
    """Checkbox with consistent borders and an explicit selected mark."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width() + 7, max(hint.height(), 22))

    def paintEvent(self, _event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        native_indicator = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        indicator = QRect(native_indicator.left(), (self.height() - 20) // 2, 20, 20)
        contents = QRect(indicator.right() + 9, 0, self.width() - indicator.right() - 9, self.height())
        checked = self.isChecked()
        enabled = self.isEnabled()
        hovered = self.underMouse() and enabled
        border = "#5D5CE2" if checked or hovered else "#A8B0BC"
        background = "#FFFFFF" if checked else "#ECEBE5"
        if not enabled:
            border, background = "#C5CAD3", "#E6E4DC"

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(border), 2))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(indicator.adjusted(1, 1, -1, -1), 3, 3)
        if checked:
            qta.icon("fa5s.check", color="#5D5CE2").paint(painter, indicator.adjusted(4, 4, -4, -4))
        text_color = "#182843" if enabled else "#9AA4B3"
        painter.setPen(QColor(text_color))
        painter.setFont(self.font())
        painter.drawText(contents, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        painter.end()
