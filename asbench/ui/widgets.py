"""Reusable building blocks: cards, headers, segmented controls, tiles and the metrics table."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from asbench.core import fmt
from asbench.core.history import change
from asbench.core.model import BenchmarkResult
from asbench.ui import icons, theme


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after changing a widget's objectName or a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def label(text: str = "", name: str | None = None, wrap: bool = False, selectable: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    if selectable:
        w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return w


def button(text: str, name: str | None = None, icon_name: str | None = None, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    if icon_name:
        def paint(t=None):
            t = t or theme.current()
            colour = t.accent_text if name == "Primary" else t.text
            b.setIcon(icons.icon(icon_name, colour, size=16))
        paint()
        theme.on_change(paint, b)
    return b


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class Card(QFrame):
    """A rounded panel. With clickable=True it acts like a big button."""

    clicked = pyqtSignal()

    def __init__(self, clickable: bool = False, margins: int = 18, spacing: int = 8):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("clickable", clickable)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins - 2, margins, margins)
        self.body.setSpacing(spacing)

    def mouseReleaseEvent(self, event):
        if self.property("clickable") and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Badge(QLabel):
    """A tinted icon square that repaints itself when the theme changes."""

    def __init__(self, icon_name: str, colour_key: str, size: int = 34):
        super().__init__()
        self.icon_name, self.colour_key, self.size_px = icon_name, colour_key, size
        self.setFixedSize(size, size)
        self.repaint_badge()
        theme.on_change(lambda *_: self.repaint_badge(), self)

    def repaint_badge(self):
        t = theme.current()
        colour = t.category(self.colour_key) if self.colour_key != "accent" else t.accent
        self.setPixmap(icons.badge(self.icon_name, colour, self.size_px))


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", icon_name: str | None = None, colour_key: str = "accent"):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        if icon_name:
            row.addWidget(Badge(icon_name, colour_key, 44), alignment=Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = label(title, "H1")
        self.subtitle = label(subtitle, "Muted", wrap=True)
        text.addWidget(self.title)
        if subtitle:
            text.addWidget(self.subtitle)
        row.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        row.addLayout(self.actions)


class Page(QScrollArea):
    """A scrollable page with a centred column of content."""

    def __init__(self, max_width: int = 1100):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("Page")
        outer = QHBoxLayout(inner)
        outer.setContentsMargins(32, 26, 32, 32)
        column = QWidget()
        column.setMaximumWidth(max_width)
        self.content = QVBoxLayout(column)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(16)
        outer.addWidget(column)
        self.setWidget(inner)


class Segmented(QFrame):
    """A macOS-style segmented control."""

    changed = pyqtSignal(str)

    def __init__(self, options: list[tuple[str, str]], value: str | None = None, icon_names: dict[str, str] | None = None):
        super().__init__()
        self.setObjectName("Segmented")
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        self.icon_names = icon_names or {}
        for key, text in options:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(b)
            row.addWidget(b)
            self.buttons[key] = b
        if self.icon_names:
            self._paint_icons()
            theme.on_change(lambda *_: self._paint_icons(), self)
        self.set_value(value or options[0][0])

    def _paint_icons(self):
        t = theme.current()
        for key, name in self.icon_names.items():
            self.buttons[key].setIcon(icons.icon(name, t.muted, t.text, size=14))

    def value(self) -> str:
        return next((k for k, b in self.buttons.items() if b.isChecked()), "")

    def set_value(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class DeltaLabel(QLabel):
    """'▲ 2.1% vs last run', coloured green for better and red for worse."""

    def __init__(self):
        super().__init__()
        self.setObjectName("Small")

    def set_change(self, pct: float | None, suffix: str = "vs last run") -> None:
        if pct is None:
            self.setText("")
            self.setObjectName("Small")
        elif abs(pct) < 0.5:
            self.setText(f"No change {suffix}".strip())
            self.setObjectName("Small")
        else:
            arrow = "▲" if pct > 0 else "▼"
            self.setText(f"{arrow} {fmt.delta(pct)} {suffix}".strip())
            self.setObjectName("Positive" if pct > 0 else "Negative")
        repolish(self)


class StatTile(Card):
    """A small card with a caption, a big value and a line of detail."""

    def __init__(self, caption: str):
        super().__init__(margins=16, spacing=4)
        self.caption = label(caption, "Eyebrow")
        self.value = label("—", "TileValue")
        self.detail = label("", "Small", wrap=True)
        self.body.addWidget(self.caption)
        self.body.addWidget(self.value)
        self.body.addWidget(self.detail)
        self.body.addStretch()

    def set(self, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))


class Banner(QFrame):
    """A coloured message strip, for 'unavailable' and error states."""

    def __init__(self, kind: str = "warning"):
        super().__init__()
        self.setObjectName("ErrorBanner" if kind == "error" else "Banner")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        self.text = label("", wrap=True, selectable=True)
        row.addWidget(self.text, 1)
        self.action = QPushButton()
        self.action.setObjectName("Ghost")
        self.action.hide()
        row.addWidget(self.action)
        self.hide()

    def show_message(self, text: str, action_text: str = "") -> None:
        self.text.setText(text)
        self.action.setText(action_text)
        self.action.setVisible(bool(action_text))
        self.setVisible(bool(text))


class MetricsTable(QTableWidget):
    """Test | Result | Points | Change, with group headings; sized to fit (the page scrolls)."""

    ROW = 32

    def __init__(self):
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(["Test", "Result", "Points", "Change"])
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 170)
        header.resizeSection(2, 90)
        header.resizeSection(3, 90)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col in (1, 2, 3):
            self.horizontalHeaderItem(col).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().setDefaultSectionSize(self.ROW)
        self._result = self._previous = None
        theme.on_change(lambda *_: self.set_result(self._result, self._previous), self)

    def set_result(self, result: BenchmarkResult | None, previous: BenchmarkResult | None = None) -> None:
        self._result, self._previous = result, previous
        self.setRowCount(0)
        if result is None:
            self._fit()
            return
        t = theme.current()
        show_points = any(m.score for m in result.metrics)
        self.setColumnHidden(2, not show_points)
        self.setColumnHidden(3, previous is None)
        group = None
        for m in result.metrics:
            if m.group != group:
                group = m.group
                if group:
                    heading = group + (f"  ·  {fmt.score(result.group_scores[group])} points" if group in result.group_scores else "")
                    self._add_row([heading], heading=True)
            pct = None
            if previous is not None:
                old = previous.metric(m.id)
                if old is not None:
                    pct = change(m.value, old.value) if m.higher_is_better else change(old.value, m.value)
            delta = fmt.delta(pct) if pct is not None else ""
            colour = None if pct is None or abs(pct) < 0.5 else (t.positive if pct > 0 else t.negative)
            self._add_row([m.name, fmt.value(m.value, m.unit), fmt.score(m.score) if m.score else "", delta], delta_colour=colour)
        self._fit()

    def _add_row(self, cells: list[str], heading: bool = False, delta_colour: str | None = None) -> None:
        row = self.rowCount()
        self.insertRow(row)
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if col > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if heading:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QColor(theme.current().muted))
            elif col == 0 and self._has_groups():
                item.setText("    " + text)
            if col == 3 and delta_colour:
                item.setForeground(QColor(delta_colour))
            self.setItem(row, col, item)
        if heading:
            self.setSpan(row, 0, 1, 4)
            self.setRowHeight(row, self.ROW + 6)

    def _has_groups(self) -> bool:
        return self._result is not None and any(m.group for m in self._result.metrics)

    def _fit(self) -> None:
        height = self.horizontalHeader().sizeHint().height() + self.verticalHeader().length() + 2
        self.setFixedHeight(max(height, 40))


class Divider(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet("background: palette(mid); border: none;")
