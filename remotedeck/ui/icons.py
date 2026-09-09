"""Iconos SVG generados en memoria (sin ficheros externos)."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# Trazos estilo Feather, lienzo 24x24.
PATHS: dict[str, str] = {
    "server": "M4 5.5h16v5H4z M4 13.5h16v5H4z M7.5 8h.01 M7.5 16h.01",
    "group": "M3 7.5a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
    "rdp": "M3 5h18v11H3z M8 20h8 M12 16v4",
    "vnc": "M4 6h16v12H4z M9 10l4 2-4 2z",
    "connect": "M5 12h9 M11 8l4 4-4 4 M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3",
    "disconnect": "M14 12H5 M9 8l-4 4 4 4 M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3",
    "add": "M12 5v14 M5 12h14",
    "folder-add": "M3 7.5a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M12 11v6 M9 14h6",
    "edit": "M4 20h4L19 9a2 2 0 0 0-3-3L5 17z M14 6l4 4",
    "delete": "M4 7h16 M9 7V5h6v2 M6 7l1 13h10l1-13 M10 11v6 M14 11v6",
    "copy": "M9 9h11v11H9z M5 15H4V4h11v1",
    "search": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M16 16l4 4",
    "settings": "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 13.7H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 8a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 9 3.7V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.6 1.6 0 0 0 20.3 9H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z",
    "import": "M12 3v11 M8 10l4 4 4-4 M4 19h16",
    "export": "M12 15V4 M8 8l4-4 4 4 M4 19h16",
    "fullscreen": "M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5",
    "power": "M12 4v8 M7.5 6.5a7 7 0 1 0 9 0",
    "refresh": "M20 12a8 8 0 1 1-2.6-5.9 M20 4v5h-5",
    "close": "M6 6l12 12 M18 6L6 18",
    "chevron-right": "M9 6l6 6-6 6",
    "star": "M12 4l2.5 5.2 5.5.8-4 3.9 1 5.6-5-2.7-5 2.7 1-5.6-4-3.9 5.5-.8z",
    "terminal": "M5 5h14v14H5z M8.5 9.5l2.5 2.5-2.5 2.5 M13 15h3",
    "info": "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16 M12 11v5 M12 8h.01",
    "lock": "M6 11h12v9H6z M9 11V8a3 3 0 0 1 6 0v3",
    "network": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M3 12h18 M12 3c2.5 3 2.5 15 0 18 M12 3c-2.5 3-2.5 15 0 18",
}

_FILLED = {"star"}

_cache: dict[tuple[str, str, int], QIcon] = {}


def _svg(name: str, color: str) -> bytes:
    path = PATHS.get(name, PATHS["info"])
    fill = color if name in _FILLED else "none"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
        f'<path d="{path}" fill="{fill}" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    ).encode()


def icon(name: str, color: str = "#c9d1e4", size: int = 20) -> QIcon:
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    renderer = QSvgRenderer(QByteArray(_svg(name, color)))
    pixmap = QPixmap(QSize(size, size) * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    result = QIcon(pixmap)
    _cache[key] = result
    return result


def app_icon_svg(accent: str = "#4c8dff") -> bytes:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="#8b5cf6"/>'
        "</linearGradient></defs>"
        '<rect x="16" y="16" width="224" height="224" rx="52" fill="#12151f"/>'
        '<rect x="16" y="16" width="224" height="224" rx="52" fill="none" stroke="url(#g)" stroke-width="6"/>'
        '<rect x="52" y="66" width="152" height="98" rx="12" fill="none" stroke="url(#g)" stroke-width="12"/>'
        '<path d="M100 190h56" stroke="url(#g)" stroke-width="12" stroke-linecap="round"/>'
        '<path d="M128 164v26" stroke="url(#g)" stroke-width="12" stroke-linecap="round"/>'
        '<path d="M92 115h56M128 95l24 20-24 20" fill="none" stroke="url(#g)" '
        'stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ).encode()


def app_icon(accent: str = "#4c8dff") -> QIcon:
    renderer = QSvgRenderer(QByteArray(app_icon_svg(accent)))
    result = QIcon()
    for size in (32, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    return result
