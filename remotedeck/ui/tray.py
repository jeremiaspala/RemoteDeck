"""Icono en la bandeja del sistema y arranque automático."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .. import APP_NAME
from ..i18n import tr
from ..model import RDP, Group, Server
from . import icons
from .theme import palette

AUTOSTART_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "remotedeck.desktop"
MAX_TRAY_SERVERS = 40


def launch_command() -> str:
    """Orden que relanza la aplicación tal como se está ejecutando ahora."""
    appimage = os.environ.get("APPIMAGE")
    if appimage and Path(appimage).exists():
        return appimage
    entry = Path(sys.argv[0]).resolve()
    if entry.suffix == ".py" and entry.exists():
        return f"{sys.executable} {entry}"
    return sys.executable + " -m remotedeck.app"


def autostart_enabled() -> bool:
    return AUTOSTART_FILE.exists()


def set_autostart(enabled: bool, minimized: bool = True) -> None:
    if not enabled:
        AUTOSTART_FILE.unlink(missing_ok=True)
        return
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    command = launch_command()
    if minimized:
        command += " --minimized"
    AUTOSTART_FILE.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Conexiones RDP y VNC en pestañas\n"
        f"Exec={command}\n"
        f"Path={Path(__file__).resolve().parents[2]}\n"
        "Icon=remotedeck\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-KDE-autostart-after=panel\n"
    )


class TrayIcon(QSystemTrayIcon):
    """Acceso rápido: mostrar la ventana o conectarse a un equipo."""

    toggleWindow = pyqtSignal()
    connectServer = pyqtSignal(object)
    openSettings = pyqtSignal()
    checkStatus = pyqtSignal()
    quitRequested = pyqtSignal()

    def __init__(self, store, settings, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.setIcon(icons.app_icon(settings["accent"]))
        self.setToolTip(APP_NAME)
        self.activated.connect(self._on_activated)
        self._menu = QMenu()
        self.setContextMenu(self._menu)
        self.rebuild_menu()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    # ------------------------------------------------------------ menú
    def rebuild_menu(self, window_visible: bool = True) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])
        menu = self._menu
        menu.clear()

        show = QAction(
            icons.icon("fullscreen", c["text_dim"]),
            tr("Ocultar ventana") if window_visible else tr("Mostrar ventana"),
            menu,
        )
        show.triggered.connect(self.toggleWindow.emit)
        menu.addAction(show)

        servers = self.store.servers()
        if servers:
            connect_menu = menu.addMenu(
                icons.icon("connect", c["text_dim"]), tr("Conectar")
            )
            favourites = [s for s in servers if s.favorite]
            if favourites:
                for server in favourites[:MAX_TRAY_SERVERS]:
                    connect_menu.addAction(self._server_action(server, connect_menu, c))
                connect_menu.addSeparator()
            self._add_group(connect_menu, self.store.root, c, favourites)

        menu.addSeparator()
        status = QAction(icons.icon("network", c["text_dim"]), tr("Comprobar estado"), menu)
        status.triggered.connect(self.checkStatus.emit)
        menu.addAction(status)
        prefs = QAction(icons.icon("settings", c["text_dim"]), tr("Preferencias"), menu)
        prefs.triggered.connect(self.openSettings.emit)
        menu.addAction(prefs)
        menu.addSeparator()
        quit_action = QAction(icons.icon("close", c["text_dim"]), tr("Salir"), menu)
        quit_action.triggered.connect(self.quitRequested.emit)
        menu.addAction(quit_action)

    def _add_group(self, menu: QMenu, group: Group, colours, skip: list[Server]) -> None:
        for node in group.children:
            if isinstance(node, Group):
                if not any(True for _ in node.servers()):
                    continue
                submenu = menu.addMenu(icons.icon("group", colours["text_dim"]), node.label)
                self._add_group(submenu, node, colours, skip)
            elif node not in skip:
                menu.addAction(self._server_action(node, menu, colours))

    def _server_action(self, server: Server, menu: QMenu, colours) -> QAction:
        icon = icons.icon("rdp" if server.protocol == RDP else "vnc", colours["text_dim"])
        action = QAction(icon, server.label, menu)
        action.setToolTip(server.target)
        action.triggered.connect(lambda _checked=False, s=server: self.connectServer.emit(s))
        return action

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggleWindow.emit()

    def notify(self, title: str, message: str) -> None:
        if self.supportsMessages():
            self.showMessage(title, message, icons.app_icon(self.settings["accent"]), 4000)
