"""A small set of line icons, drawn as inline SVG and tinted to the current theme."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_PATHS = {
    "overview": '<path d="M4 16.5a8 8 0 1 1 16 0"/><path d="M12 16.5l3.6-4.8"/><circle cx="12" cy="16.5" r="1.3" fill="currentColor"/>',
    "cpu": '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/><rect x="9.8" y="9.8" width="4.4" height="4.4" rx=".6"/>'
    '<path d="M9.5 3v3.5M14.5 3v3.5M9.5 17.5V21M14.5 17.5V21M3 9.5h3.5M3 14.5h3.5M17.5 9.5H21M17.5 14.5H21"/>',
    "gpu": '<rect x="2.5" y="6" width="19" height="11" rx="2"/><circle cx="9" cy="11.5" r="3"/><path d="M9 8.5v6M6 11.5h6"/>'
    '<path d="M15.5 9.5h3M15.5 12h3M15.5 14.5h3M6 17v2.5M10 17v2.5M14 17v2.5"/>',
    "memory": '<rect x="2.5" y="7" width="19" height="9.5" rx="1.5"/><path d="M6.5 10v3.5M10 10v3.5M14 10v3.5M17.5 10v3.5"/>'
    '<path d="M5 16.5V19M9 16.5V19M15 16.5V19M19 16.5V19"/>',
    "storage": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3 13.5h18"/><circle cx="16.8" cy="16.3" r=".9" fill="currentColor"/>'
    '<path d="M6.5 16.3h5"/>',
    "neural": '<circle cx="5.5" cy="6.5" r="2"/><circle cx="5.5" cy="17.5" r="2"/><circle cx="18.5" cy="12" r="2"/>'
    '<circle cx="12" cy="12" r="1.8"/><path d="M7.3 7.6l3.2 3.1M7.3 16.4l3.2-3.1M13.8 12h2.7"/>'
    '<path d="M18.5 4v2M17.5 5h2" stroke-width="1.4"/>',
    "sustained": '<path d="M10 14.2V5a2 2 0 1 1 4 0v9.2a4 4 0 1 1-4 0z"/><path d="M12 9.5v6.5"/><circle cx="12" cy="17.3" r="1.6" fill="currentColor"/>',
    "history": '<path d="M3.8 12a8.2 8.2 0 1 0 2.4-5.8"/><path d="M3.5 4v4h4"/><path d="M12 8v4.3l3 1.9"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none"/>',
    "bolt": '<path d="M13 2.5L5 13.5h6.2L10.5 21.5 19 10.5h-6.2z"/>',
    "export": '<path d="M12 3.5v11M7.5 8L12 3.5 16.5 8"/><path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>',
    "folder": '<path d="M3 7.5a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>',
    "compare": '<path d="M7 7h12M16 4l3 3-3 3"/><path d="M17 17H5M8 14l-3 3 3 3"/>',
    "auto": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>',
    "light": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4'
    'M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "dark": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r="1" fill="currentColor"/>',
    "report": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 15.5h6M9 8.5h2"/>',
}


def svg(name: str, colour: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" color="{colour}">'
        f"{_PATHS[name]}</svg>"
    ).replace("currentColor", colour)


def pixmap(name: str, colour: str, size: int = 18, ratio: float = 2.0) -> QPixmap:
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, colour).encode()))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, colour: str, checked_colour: str | None = None, size: int = 18) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, colour, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, checked_colour or colour, size), QIcon.Mode.Normal, QIcon.State.On)
    return ic


def badge(name: str, colour: str, size: int = 34, ratio: float = 2.0) -> QPixmap:
    """The icon on a softly tinted rounded square, as used on cards and page headers."""
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(ratio)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    tint = QColor(colour)
    tint.setAlphaF(0.16)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tint)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    inner = pixmap(name, colour, int(size * 0.58), ratio)
    offset = (size - size * 0.58) / 2
    painter.drawPixmap(QRectF(offset, offset, size * 0.58, size * 0.58), inner, QRectF(inner.rect()))
    painter.end()
    return pm


def app_mark(size: int = 64) -> QPixmap:
    """The app's logo: a gauge on a blue-to-purple rounded square."""
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(ratio)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor("#0a84ff"))
    gradient.setColorAt(1, QColor("#bf5af2"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.26, size * 0.26)
    painter.fillPath(path, gradient)
    glyph = pixmap("overview", "#ffffff", int(size * 0.62), ratio)
    offset = size * 0.19
    painter.drawPixmap(QRectF(offset, offset, size * 0.62, size * 0.62), glyph, QRectF(glyph.rect()))
    painter.end()
    return pm
