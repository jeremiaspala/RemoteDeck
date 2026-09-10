"""Punto de entrada."""

from __future__ import annotations

import os
import sys


def _force_x11() -> None:
    """El embebido de ventanas necesita XCB (bajo Wayland se usa XWayland)."""
    if os.environ.get("REMOTEDECK_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = os.environ["REMOTEDECK_PLATFORM"]
    elif os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    # Los dialogos nativos de KDE/GNOME y el portal xdg añaden latencia (y a
    # veces bloqueos de varios segundos) al abrir menus y ventanas de opciones.
    os.environ.setdefault("QT_NO_XDG_DESKTOP_PORTAL", "1")
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "")


def main(argv: list[str] | None = None) -> int:
    _force_x11()

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

    from . import APP_NAME, importers
    from .i18n import set_language, tr
    from .paths import ensure_dirs
    from .store import Settings, Store
    from .vault import BadPassword, vault
    from .ui import icons
    from .ui.dialogs import MasterPasswordDialog
    from .ui.mainwindow import MainWindow
    from .ui.theme import stylesheet

    ensure_dirs()
    settings = Settings()
    set_language(settings["language"])

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    app = QApplication(argv if argv is not None else sys.argv)
    _disable_animations(app)
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
                QMessageBox.warning(None, APP_NAME, tr("Contraseña maestra incorrecta."))
        else:
            return 1
    else:
        vault.initialize()
        vault.unlock()

    store = Store()
    store.load()

    while True:
        window = MainWindow(store, settings)
        window.show()

        if not store.servers() and not settings["first_run_done"]:
            settings["first_run_done"] = True
            settings.save()
            _offer_first_import(window, store, importers)

        code = app.exec()
        if not getattr(window, "restart_requested", False):
            return code
        # cambio de idioma: se reconstruye la ventana con los textos nuevos
        set_language(settings["language"])
        app.setStyleSheet(stylesheet(settings["theme"], settings["accent"]))
        window.deleteLater()
        store = Store()
        store.load()


def _disable_animations(app) -> None:
    """Sin animaciones de menu: en XWayland se perciben como tirones."""
    from PyQt6.QtCore import Qt

    for effect in (
        Qt.UIEffect.UI_AnimateMenu,
        Qt.UIEffect.UI_FadeMenu,
        Qt.UIEffect.UI_AnimateCombo,
        Qt.UIEffect.UI_AnimateTooltip,
        Qt.UIEffect.UI_FadeTooltip,
        Qt.UIEffect.UI_AnimateToolBox,
    ):
        app.setEffectEnabled(effect, False)


def _offer_first_import(window, store, importers) -> None:
    from PyQt6.QtWidgets import QMessageBox

    from . import APP_NAME

    profiles = importers._remmina_files()
    if not profiles:
        return
    from .i18n import tr

    answer = QMessageBox.question(
        window,
        APP_NAME,
        f"{tr('Se detectaron')} {len(profiles)} "
        + tr("perfiles de Remmina en este equipo.") + "\n"
        + tr("¿Quieres importarlos ahora?"),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if answer == QMessageBox.StandardButton.Yes:
        window.import_remmina()


if __name__ == "__main__":
    raise SystemExit(main())
