"""Punto de entrada."""

from __future__ import annotations

import os
import sys


def _force_x11() -> None:
    """El embebido de ventanas necesita XCB (bajo Wayland se usa XWayland)."""
    if os.environ.get("REMOTEDECK_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = os.environ["REMOTEDECK_PLATFORM"]
        return
    if os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def main(argv: list[str] | None = None) -> int:
    _force_x11()

    from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

    from . import APP_NAME, importers
    from .paths import ensure_dirs
    from .store import Settings, Store
    from .vault import BadPassword, vault
    from .ui import icons
    from .ui.dialogs import MasterPasswordDialog
    from .ui.mainwindow import MainWindow
    from .ui.theme import stylesheet

    ensure_dirs()
    settings = Settings()

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("remotedeck")
    app.setStyleSheet(stylesheet(settings["theme"], settings["accent"]))
    app.setWindowIcon(icons.app_icon(settings["accent"]))

    if vault.needs_password():
        for _ in range(3):
            dialog = MasterPasswordDialog("ask")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return 0
            try:
                vault.unlock(dialog.password())
                break
            except BadPassword:
                QMessageBox.warning(None, APP_NAME, "Contrasena maestra incorrecta.")
        else:
            return 1
    else:
        vault.initialize()
        vault.unlock()

    store = Store()
    store.load()

    window = MainWindow(store, settings)
    window.show()

    if not store.servers():
        _offer_first_import(window, store, importers)

    return app.exec()


def _offer_first_import(window, store, importers) -> None:
    from PyQt6.QtWidgets import QMessageBox

    from . import APP_NAME

    profiles = importers._remmina_files()
    if not profiles:
        return
    answer = QMessageBox.question(
        window,
        APP_NAME,
        f"Se detectaron {len(profiles)} perfiles de Remmina en este equipo.\n"
        "Quieres importarlos ahora?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if answer == QMessageBox.StandardButton.Yes:
        window.import_remmina()


if __name__ == "__main__":
    raise SystemExit(main())
