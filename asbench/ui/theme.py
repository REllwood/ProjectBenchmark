"""Light and dark themes: colour tokens, the Qt stylesheet and palette, and system tracking."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPalette

from asbench.core.style import colour


@dataclass(frozen=True)
class Theme:
    dark: bool
    window: str
    sidebar: str
    card: str
    card_alt: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_text: str
    hover: str
    selected: str
    selected_text: str
    track: str
    positive: str
    negative: str
    warning_bg: str
    warning_text: str
    error_bg: str
    error_text: str

    def category(self, key: str) -> str:
        return colour(key, self.dark)


LIGHT = Theme(
    dark=False,
    window="#f5f5f7",
    sidebar="#ebedf0",
    card="#ffffff",
    card_alt="#f7f7f9",
    border="#e1e1e6",
    text="#1d1d1f",
    muted="#6e6e73",
    faint="#a1a1a6",
    accent="#007aff",
    accent_hover="#0066d6",
    accent_text="#ffffff",
    hover="#e1e3e8",
    selected="#dce9ff",
    selected_text="#0058cc",
    track="#e6e6eb",
    positive="#1f8a3b",
    negative="#d70015",
    warning_bg="#fff3e0",
    warning_text="#8a4b00",
    error_bg="#ffe9e8",
    error_text="#b3261e",
)

DARK = Theme(
    dark=True,
    window="#111317",
    sidebar="#16181d",
    card="#1c1f25",
    card_alt="#22262d",
    border="#2b2f37",
    text="#f2f2f7",
    muted="#9a9aa3",
    faint="#65656d",
    accent="#0a84ff",
    accent_hover="#3398ff",
    accent_text="#ffffff",
    hover="#23272e",
    selected="#1c2d47",
    selected_text="#7ab8ff",
    track="#2c3038",
    positive="#30d158",
    negative="#ff6961",
    warning_bg="#3a2a12",
    warning_text="#ffcf8a",
    error_bg="#3b1a1a",
    error_text="#ff8a80",
)

MODES = ("auto", "light", "dark")


class ThemeManager(QObject):
    """Holds the current theme and re-applies it when the mode or the system setting changes."""

    changed = pyqtSignal(object)  # Theme

    def __init__(self, app, mode: str = "auto"):
        super().__init__()
        self.app = app
        self.mode = mode if mode in MODES else "auto"
        self.theme = self._resolve()
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):  # Qt 6.5+
            hints.colorSchemeChanged.connect(lambda *_: self.set_mode(self.mode))
        self.apply()

    def _system_is_dark(self) -> bool:
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
        return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def _resolve(self) -> Theme:
        if self.mode == "dark" or (self.mode == "auto" and self._system_is_dark()):
            return DARK
        return LIGHT

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "auto"
        self.theme = self._resolve()
        self.apply()
        self.changed.emit(self.theme)

    def apply(self) -> None:
        self.app.setPalette(palette(self.theme))
        self.app.setStyleSheet(stylesheet(self.theme))


def palette(t: Theme) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.window,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.card,
        QPalette.ColorRole.AlternateBase: t.card_alt,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.card,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_text,
        QPalette.ColorRole.ToolTipBase: t.card_alt,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.PlaceholderText: t.faint,
        QPalette.ColorRole.Link: t.accent,
        QPalette.ColorRole.Mid: t.border,
    }
    for role, value in roles.items():
        p.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.faint))
    return p


def stylesheet(t: Theme) -> str:
    return f"""
QWidget {{ color: {t.text}; font-size: 13px; }}
QMainWindow, #Content, #Page, QScrollArea > QWidget > QWidget#Page {{ background: {t.window}; }}
QScrollArea {{ background: transparent; border: none; }}
#Sidebar {{ background: {t.sidebar}; border-right: 1px solid {t.border}; }}
#Card {{ background: {t.card}; border: 1px solid {t.border}; border-radius: 14px; }}
#Card[clickable="true"]:hover {{ border-color: {t.faint}; }}
#InfoPanel {{ background: {t.card_alt}; border: 1px solid {t.border}; border-radius: 12px; }}
#RunBar {{ background: {t.card}; border-top: 1px solid {t.border}; }}

QLabel {{ background: transparent; }}
QLabel#AppName {{ font-size: 14px; font-weight: 700; }}
QLabel#H1 {{ font-size: 24px; font-weight: 700; }}
QLabel#H2 {{ font-size: 15px; font-weight: 600; }}
QLabel#H3 {{ font-size: 13px; font-weight: 600; }}
QLabel#Muted {{ color: {t.muted}; }}
QLabel#Small {{ color: {t.muted}; font-size: 12px; }}
QLabel#Section {{ color: {t.muted}; font-size: 11px; font-weight: 700; padding: 10px 10px 2px 10px; }}
QLabel#Eyebrow {{ color: {t.muted}; font-size: 12px; font-weight: 600; }}
QLabel#BigScore {{ font-size: 60px; font-weight: 700; }}
QLabel#CardScore {{ font-size: 30px; font-weight: 700; }}
QLabel#TileValue {{ font-size: 22px; font-weight: 700; }}
QLabel#Positive {{ color: {t.positive}; font-weight: 600; }}
QLabel#Negative {{ color: {t.negative}; font-weight: 600; }}
QLabel#Pill {{ background: {t.warning_bg}; color: {t.warning_text}; border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
QLabel#ErrorText {{ color: {t.error_text}; }}
#Banner {{ background: {t.warning_bg}; border-radius: 12px; }}
#Banner QLabel {{ color: {t.warning_text}; }}
#ErrorBanner {{ background: {t.error_bg}; border-radius: 12px; }}
#ErrorBanner QLabel {{ color: {t.error_text}; }}

QPushButton {{ background: {t.card}; border: 1px solid {t.border}; border-radius: 8px; padding: 6px 14px; }}
QPushButton:hover {{ background: {t.hover}; }}
QPushButton:pressed {{ background: {t.track}; }}
QPushButton:disabled {{ color: {t.faint}; background: {t.card_alt}; }}
QPushButton#Primary {{ background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent}; font-weight: 600; padding: 7px 18px; }}
QPushButton#Primary:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton#Primary:disabled {{ background: {t.track}; border-color: {t.track}; color: {t.faint}; }}
QPushButton#Nav {{ text-align: left; border: none; background: transparent; padding: 7px 10px; border-radius: 8px; }}
QPushButton#Nav:hover {{ background: {t.hover}; }}
QPushButton#Nav:checked {{ background: {t.selected}; color: {t.selected_text}; font-weight: 600; }}
QPushButton#Link {{ border: none; background: transparent; color: {t.accent}; padding: 0; text-align: left; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid {t.border}; padding: 4px 12px; }}
QPushButton#Ghost:hover {{ background: {t.hover}; }}

#Segmented {{ background: {t.track}; border-radius: 8px; }}
#Segmented QPushButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px 12px; color: {t.muted}; }}
#Segmented QPushButton:hover {{ color: {t.text}; }}
#Segmented QPushButton:checked {{ background: {t.card}; color: {t.text}; font-weight: 600; border: 1px solid {t.border}; }}
#Segmented QPushButton:disabled {{ color: {t.faint}; }}

QComboBox {{ background: {t.card}; border: 1px solid {t.border}; border-radius: 8px; padding: 5px 10px; min-width: 90px; }}
QComboBox:hover {{ background: {t.hover}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {t.card}; border: 1px solid {t.border}; selection-background-color: {t.selected}; selection-color: {t.text}; }}

QProgressBar {{ background: {t.track}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}

QTableWidget {{ background: transparent; border: none; gridline-color: transparent; alternate-background-color: {t.card_alt}; selection-background-color: {t.selected}; selection-color: {t.text}; outline: 0; }}
QTableWidget::item {{ padding: 2px 6px; border: none; }}
QTableWidget::item:selected {{ background: {t.selected}; color: {t.text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {t.muted}; border: none; border-bottom: 1px solid {t.border}; padding: 6px; font-size: 12px; font-weight: 600; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.track}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.faint}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.track}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{ background: {t.card_alt}; color: {t.text}; border: 1px solid {t.border}; padding: 6px; border-radius: 6px; }}
QPlainTextEdit, QTextBrowser {{ background: {t.card_alt}; border: 1px solid {t.border}; border-radius: 8px; padding: 8px; }}
QDialog {{ background: {t.window}; }}
QMenu {{ background: {t.card}; border: 1px solid {t.border}; padding: 4px; }}
QMenu::item {{ padding: 5px 16px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t.selected}; color: {t.text}; }}
"""


_manager: ThemeManager | None = None


def install(app, mode: str = "auto") -> ThemeManager:
    global _manager
    _manager = ThemeManager(app, mode)
    return _manager


def manager() -> ThemeManager | None:
    return _manager


def current() -> Theme:
    return _manager.theme if _manager else LIGHT


def on_change(callback, owner: QObject) -> None:
    """Call callback(theme) whenever the theme changes, until `owner` is destroyed.

    Used by widgets that paint their own colours (icons, charts). Disconnecting when the
    owner goes away matters: calling into a deleted Qt object would crash the app.
    """
    if not _manager:
        return
    manager_ = _manager
    manager_.changed.connect(callback)

    def disconnect(*_):
        try:
            manager_.changed.disconnect(callback)
        except (TypeError, RuntimeError):
            pass

    owner.destroyed.connect(disconnect)
