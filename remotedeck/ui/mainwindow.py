"""Ventana principal."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__, importers, net
from ..model import RDP, VNC, Group, Server
from ..store import Settings, Store
from ..vault import vault
from . import icons
from .dialogs import (
    CredentialsPrompt,
    GroupDialog,
    MasterPasswordDialog,
    ServerDialog,
    SettingsDialog,
)
from .session import SessionView, State
from .theme import palette, stylesheet
from .tree import ConnectionTree


class ImportPreviewDialog(QDialog):
    """Previsualiza lo importado y deja elegir que se anade."""

    def __init__(self, result: importers.ImportResult, source: str, settings, parent=None):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle(f"Importar desde {source}")
        self.setMinimumSize(560, 480)
        c = palette(settings["theme"], settings["accent"])

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        header = QLabel(
            f"Se encontraron <b>{result.count}</b> conexiones"
            + (f" y {len(result.groups)} grupos." if result.groups else ".")
        )
        layout.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Nombre", "Destino", "Usuario"])
        self.tree.setColumnWidth(0, 240)
        self._items: dict[str, QTreeWidgetItem] = {}
        for group in result.groups:
            self._add_group(group, self.tree.invisibleRootItem(), c)
        for server in result.servers:
            if server.parent is None:
                self._add_server(server, self.tree.invisibleRootItem(), c)
        self.tree.expandAll()
        layout.addWidget(self.tree, 1)

        self.merge_check = QCheckBox("Fusionar con los grupos existentes del mismo nombre")
        self.merge_check.setChecked(True)
        layout.addWidget(self.merge_check)

        if result.skipped:
            skipped = QLabel("Omitidos (protocolo no soportado): " + ", ".join(result.skipped[:8]))
            skipped.setObjectName("SessionMsg")
            skipped.setWordWrap(True)
            layout.addWidget(skipped)
        if result.warnings:
            warn = QLabel("\n".join(result.warnings[:6]))
            warn.setObjectName("SessionMsg")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Importar")
        ok.setProperty("accent", True)
        ok.setEnabled(result.count > 0)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_group(self, group: Group, parent, c) -> None:
        item = QTreeWidgetItem(parent, [group.label, "", group.credentials.username])
        item.setIcon(0, icons.icon("group", c["text_dim"]))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        self._items[group.id] = item
        for child in group.children:
            if child.kind == "group":
                self._add_group(child, item, c)
            else:
                self._add_server(child, item, c)

    def _add_server(self, server: Server, parent, c) -> None:
        item = QTreeWidgetItem(
            parent, [server.label, server.target, server.credentials.username]
        )
        item.setIcon(0, icons.icon("rdp" if server.protocol == RDP else "vnc", c["accent"]))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        self._items[server.id] = item

    def is_selected(self, node) -> bool:
        item = self._items.get(node.id)
        return item is None or item.checkState(0) == Qt.CheckState.Checked

    @property
    def merge(self) -> bool:
        return self.merge_check.isChecked()


class WelcomePage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.setObjectName("Welcome")
        c = palette(window.settings["theme"], window.settings["accent"])
        layout = QVBoxLayout(self)
        layout.addStretch(1)

        logo = QLabel()
        logo.setPixmap(icons.app_icon(c["accent"]).pixmap(QSize(96, 96)))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        title = QLabel(APP_NAME)
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Gestiona tus conexiones RDP y VNC en pestanas. "
            "Haz doble clic en un equipo de la izquierda para conectarte."
        )
        subtitle.setObjectName("WelcomeSub")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        row.addStretch(1)
        new_btn = QPushButton(icons.icon("add", "#ffffff"), "  Nuevo servidor")
        new_btn.setProperty("accent", True)
        new_btn.clicked.connect(window.new_server)
        row.addWidget(new_btn)
        import_btn = QPushButton(icons.icon("import", c["text"]), "  Importar de Remmina")
        import_btn.clicked.connect(window.import_remmina)
        row.addWidget(import_btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self, store: Store, settings: Settings):
        super().__init__()
        self.store = store
        self.settings = settings
        self.sessions: list[SessionView] = []

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon(settings["accent"]))
        self.resize(1400, 880)

        self._build_ui()
        self._build_actions()
        self._restore_geometry()
        self.tree.rebuild()
        self.tree.start_status_checks()
        self._update_actions()
        QTimer.singleShot(800, self._connect_startup_servers)

    # ------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 12, 8, 10)
        side_layout.setSpacing(10)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon(c["accent"]).pixmap(QSize(28, 28)))
        brand.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("BrandLabel")
        sub = QLabel("RDP · VNC")
        sub.setObjectName("BrandSub")
        titles.addWidget(name)
        titles.addWidget(sub)
        brand.addLayout(titles)
        brand.addStretch(1)
        add_btn = QPushButton(icons.icon("add", c["text_dim"]), "")
        add_btn.setProperty("flat", True)
        add_btn.setToolTip("Nuevo servidor")
        add_btn.clicked.connect(self.new_server)
        brand.addWidget(add_btn)
        folder_btn = QPushButton(icons.icon("folder-add", c["text_dim"]), "")
        folder_btn.setProperty("flat", True)
        folder_btn.setToolTip("Nuevo grupo")
        folder_btn.clicked.connect(self.new_group)
        brand.addWidget(folder_btn)
        side_layout.addLayout(brand)

        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("Buscar equipo, IP, etiqueta...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        side_layout.addWidget(self.search)

        self.tree = ConnectionTree(self.store, self.settings)
        self.tree.connectRequested.connect(self.connect_server)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.selectionChangedNode.connect(lambda _n: self._update_actions())
        self.tree.treeChanged.connect(self.save_store)
        side_layout.addWidget(self.tree, 1)

        self.count_label = QLabel("")
        self.count_label.setObjectName("BrandSub")
        side_layout.addWidget(self.count_label)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setTabPosition(
            QTabWidget.TabPosition.South
            if self.settings["tab_position"] == "bottom"
            else QTabWidget.TabPosition.North
        )
        self.tabs.tabCloseRequested.connect(self._close_tab_index)
        self.tabs.currentChanged.connect(self._tab_changed)

        self.welcome = WelcomePage(self)
        self.stack_host = QWidget()
        host_layout = QVBoxLayout(self.stack_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.addWidget(self.welcome)
        host_layout.addWidget(self.tabs)
        self.tabs.hide()

        self.splitter.addWidget(sidebar)
        self.splitter.addWidget(self.stack_host)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([int(self.settings["sidebar_width"]), 1000])

        self.status = self.statusBar()
        self.status_label = QLabel("")
        self.status.addPermanentWidget(self.status_label)
        self._refresh_counts()

    def _build_actions(self) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])

        def action(name, text, slot, shortcut=None, tip=""):
            act = QAction(icons.icon(name, c["text_dim"]), text, self)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.setToolTip(tip or text)
            return act

        self.act_new_server = action("add", "Nuevo servidor", self.new_server, "Ctrl+N")
        self.act_new_group = action("folder-add", "Nuevo grupo", self.new_group, "Ctrl+Shift+N")
        self.act_connect = action("connect", "Conectar", self.connect_selected, "Return")
        self.act_disconnect = action("disconnect", "Desconectar", self.disconnect_current, "Ctrl+W")
        self.act_edit = action("edit", "Editar", self.edit_selected, "F2")
        self.act_duplicate = action("copy", "Duplicar", self.duplicate_selected, "Ctrl+D")
        self.act_delete = action("delete", "Eliminar", self.delete_selected, "Del")
        self.act_wake = action("power", "Wake-on-LAN", self.wake_selected, "Ctrl+Shift+W")
        self.act_fullscreen = action("fullscreen", "Pantalla completa", self.toggle_fullscreen, "F11")
        self.act_reconnect = action("refresh", "Reconectar", self.reconnect_current, "Ctrl+R")
        self.act_settings = action("settings", "Preferencias", self.open_settings, "Ctrl+,")
        self.act_import_remmina = action("import", "Importar de Remmina", self.import_remmina)
        self.act_import_file = action("import", "Importar fichero (.rdg, .rdp, .json)", self.import_file)
        self.act_export = action("export", "Exportar conexiones", self.export_file)
        self.act_refresh_status = action("network", "Comprobar estado", self.tree.refresh_status, "F5")
        self.act_quit = action("close", "Salir", self.close, "Ctrl+Q")
        self.act_about = action("info", "Acerca de", self.show_about)

        toolbar = self.addToolBar("Principal")
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for act in (
            self.act_new_server, self.act_new_group, self.act_connect,
            self.act_disconnect, self.act_reconnect, self.act_fullscreen,
        ):
            toolbar.addAction(act)
        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy().Expanding,
            spacer.sizePolicy().verticalPolicy(),
        )
        toolbar.addWidget(spacer)
        toolbar.addAction(self.act_refresh_status)
        toolbar.addAction(self.act_settings)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("&Archivo")
        file_menu.addAction(self.act_new_server)
        file_menu.addAction(self.act_new_group)
        file_menu.addSeparator()
        file_menu.addAction(self.act_import_remmina)
        file_menu.addAction(self.act_import_file)
        file_menu.addAction(self.act_export)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        session_menu = menubar.addMenu("&Sesion")
        session_menu.addAction(self.act_connect)
        session_menu.addAction(self.act_reconnect)
        session_menu.addAction(self.act_disconnect)
        session_menu.addSeparator()
        session_menu.addAction(self.act_fullscreen)
        session_menu.addAction(self.act_wake)

        edit_menu = menubar.addMenu("&Editar")
        edit_menu.addAction(self.act_edit)
        edit_menu.addAction(self.act_duplicate)
        edit_menu.addAction(self.act_delete)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_settings)

        help_menu = menubar.addMenu("A&yuda")
        help_menu.addAction(self.act_about)

    # ------------------------------------------------------- utilidades
    def save_store(self) -> None:
        self.store.save()
        self._refresh_counts()

    def _refresh_counts(self) -> None:
        total = len(self.store.servers())
        active = sum(1 for s in self.sessions if s.state == State.CONNECTED)
        self.count_label.setText(f"{total} equipos · {active} sesiones activas")

    def _on_search(self, text: str) -> None:
        self.tree.set_filter(text)

    def _restore_geometry(self) -> None:
        geometry = self.settings["window_geometry"]
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        state = self.settings["window_state"]
        if state:
            self.restoreState(QByteArray.fromBase64(state.encode()))

    def _update_actions(self) -> None:
        node = self.tree.current_node()
        is_server = isinstance(node, Server)
        has_session = self.current_session() is not None
        self.act_connect.setEnabled(bool(self.tree.selected_servers()))
        self.act_edit.setEnabled(node is not None)
        self.act_duplicate.setEnabled(is_server)
        self.act_delete.setEnabled(node is not None)
        self.act_wake.setEnabled(is_server and bool(node.wol.enabled))
        self.act_disconnect.setEnabled(has_session)
        self.act_reconnect.setEnabled(has_session)
        self.act_fullscreen.setEnabled(has_session)
        self._refresh_counts()

    # ------------------------------------------------------------ alta
    def _target_group(self) -> Group:
        node = self.tree.current_node()
        if isinstance(node, Group):
            return node
        if node is not None and node.parent is not None:
            return node.parent
        return self.store.root

    def new_server(self) -> None:
        server = Server(name="", protocol=RDP)
        parent = self._target_group()
        server.parent = parent
        dialog = ServerDialog(server, self.store, self.settings, self, is_new=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = self.store.find(dialog.selected_group_id) or self.store.root
        server.parent = None
        self.store.add(server, target)
        self.save_store()
        self.tree.rebuild()
        item = self.tree.item_for(server.id)
        if item:
            self.tree.setCurrentItem(item)

    def new_group(self) -> None:
        group = Group(name="")
        dialog = GroupDialog(group, self.settings, self, is_new=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.store.add(group, self._target_group())
        self.save_store()
        self.tree.rebuild()

    def edit_selected(self) -> None:
        node = self.tree.current_node()
        if node is None:
            return
        if isinstance(node, Group):
            if GroupDialog(node, self.settings, self).exec() == QDialog.DialogCode.Accepted:
                self.save_store()
                self.tree.rebuild()
            return
        dialog = ServerDialog(node, self.store, self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = self.store.find(dialog.selected_group_id) or self.store.root
        if node.parent is not target:
            self.store.move(node, target)
        self.save_store()
        self.tree.rebuild()

    def duplicate_selected(self) -> None:
        node = self.tree.current_node()
        if not isinstance(node, Server):
            return
        copy = node.clone()
        self.store.add(copy, node.parent or self.store.root)
        self.save_store()
        self.tree.rebuild()

    def delete_selected(self) -> None:
        nodes = self.tree.selected_nodes()
        if not nodes:
            return
        names = ", ".join(n.label for n in nodes[:5])
        extra = f" y {len(nodes) - 5} mas" if len(nodes) > 5 else ""
        answer = QMessageBox.question(
            self,
            "Eliminar",
            f"Se eliminaran: {names}{extra}.\nLos grupos borran tambien su contenido.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for node in nodes:
            self.store.remove(node)
        self.save_store()
        self.tree.rebuild()

    # -------------------------------------------------------- conexion
    def connect_selected(self) -> None:
        servers = self.tree.selected_servers()
        if not servers:
            return
        if len(servers) > 6:
            answer = QMessageBox.question(
                self,
                "Conectar",
                f"Se abriran {len(servers)} sesiones. Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        for server in servers:
            self.connect_server(server)

    def connect_server(self, server: Server) -> None:
        existing = next((s for s in self.sessions if s.server.id == server.id), None)
        if existing is not None and existing.state in (State.CONNECTED, State.STARTING):
            self.tabs.setCurrentWidget(existing)
            return

        creds = server.effective_credentials()
        username, domain, password = creds.username, creds.domain, creds.password()
        needs_prompt = not password or (server.protocol == RDP and not username)
        if needs_prompt:
            prompt = CredentialsPrompt(server, creds, self)
            if prompt.exec() != QDialog.DialogCode.Accepted:
                return
            username, domain, password, store_it = prompt.values()
            if store_it:
                server.credentials.inherit = False
                server.credentials.username = username or server.credentials.username
                server.credentials.domain = domain or server.credentials.domain
                server.credentials.set_password(password)
                self.save_store()

        view = SessionView(server, username, domain, password, self.settings)
        view.stateChanged.connect(self._session_state_changed)
        view.requestClose.connect(self.close_session)
        view.restore_cb = self.restore_session
        self.sessions.append(view)

        c = palette(self.settings["theme"], self.settings["accent"])
        index = self.tabs.addTab(
            view, icons.icon("rdp" if server.protocol == RDP else "vnc", c["text_dim"]),
            server.label,
        )
        self.tabs.setTabToolTip(index, f"{server.protocol.upper()} · {server.target}")
        self.tabs.setCurrentIndex(index)
        self.welcome.hide()
        self.tabs.show()
        view.start()
        self._update_actions()

    def current_session(self) -> SessionView | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, SessionView) else None

    def _tab_changed(self, _index: int) -> None:
        session = self.current_session()
        if session is not None:
            QTimer.singleShot(120, session.focus_session)
            self.status.showMessage(
                f"{session.server.label} · {session.server.target} · {session.status_text}"
            )
        self._update_actions()

    def _session_state_changed(self, session: SessionView) -> None:
        index = self.tabs.indexOf(session)
        c = palette(self.settings["theme"], self.settings["accent"])
        color = {
            State.CONNECTED: c["ok"],
            State.FAILED: c["error"],
            State.WAKING: c["warn"],
        }.get(session.state, c["text_dim"])
        if index >= 0:
            self.tabs.setTabIcon(
                index,
                icons.icon("rdp" if session.server.protocol == RDP else "vnc", color),
            )
        if session is self.current_session():
            self.status.showMessage(
                f"{session.server.label} · {session.server.target} · {session.status_text}"
            )
        self._update_actions()

    def disconnect_current(self) -> None:
        session = self.current_session()
        if session is not None:
            self.close_session(session)

    def reconnect_current(self) -> None:
        session = self.current_session()
        if session is not None:
            session.reconnect()

    def close_session(self, session: SessionView) -> None:
        if (
            self.settings["confirm_close_session"]
            and session.state == State.CONNECTED
        ):
            answer = QMessageBox.question(
                self,
                "Cerrar sesion",
                f"La sesion con {session.server.label} esta activa. Cerrarla?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        session.stop()
        index = self.tabs.indexOf(session)
        if index >= 0:
            self.tabs.removeTab(index)
        if session in self.sessions:
            self.sessions.remove(session)
        session.deleteLater()
        if self.tabs.count() == 0:
            self.tabs.hide()
            self.welcome.show()
        self._update_actions()

    def _close_tab_index(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, SessionView):
            self.close_session(widget)

    def toggle_fullscreen(self) -> None:
        session = self.current_session()
        if session is not None:
            session.toggle_fullscreen()

    def restore_session(self, session: SessionView) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])
        index = self.tabs.addTab(
            session,
            icons.icon("rdp" if session.server.protocol == RDP else "vnc", c["ok"]),
            session.server.label,
        )
        self.tabs.setCurrentIndex(index)
        self.tabs.show()
        self.welcome.hide()

    def _connect_startup_servers(self) -> None:
        for server in self.store.servers():
            if server.connect_on_startup:
                self.connect_server(server)

    # ------------------------------------------------------------- WoL
    def wake_selected(self) -> None:
        servers = [s for s in self.tree.selected_servers() if s.wol.enabled]
        if not servers:
            QMessageBox.information(
                self, "Wake-on-LAN",
                "Ningun equipo seleccionado tiene una MAC configurada.",
            )
            return
        sent = []
        for server in servers:
            try:
                net.wake(server.wol.mac, server.wol.broadcast, server.wol.port)
                sent.append(server.label)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "Wake-on-LAN", f"{server.label}: {exc}")
        if sent:
            self.status.showMessage("Magic packet enviado a: " + ", ".join(sent), 6000)

    # -------------------------------------------------------- importar
    def import_remmina(self) -> None:
        result = importers.import_remmina()
        self._apply_import(result, "Remmina")

    def import_file(self) -> None:
        start = self.settings["last_import_dir"] or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar conexiones",
            start,
            "Conexiones (*.rdg *.rdp *.remmina *.json);;Todos (*)",
        )
        if not path:
            return
        self.settings["last_import_dir"] = str(Path(path).parent)
        self.settings.save()
        result = importers.detect_and_import(Path(path))
        self._apply_import(result, Path(path).name)

    def _apply_import(self, result: importers.ImportResult, source: str) -> None:
        if result.count == 0:
            QMessageBox.information(
                self,
                "Importar",
                "No se encontraron conexiones compatibles.\n"
                + "\n".join(result.warnings[:5]),
            )
            return
        dialog = ImportPreviewDialog(result, source, self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        existing = {g.name.lower(): g for g in self.store.groups() if g is not self.store.root}
        added = 0
        for group in result.groups:
            if not dialog.is_selected(group):
                continue
            target = existing.get(group.name.lower()) if dialog.merge else None
            if target is not None:
                for child in list(group.children):
                    if dialog.is_selected(child):
                        group.remove(child)
                        self.store.add(child, target)
                        added += 1
            else:
                self._prune(group, dialog)
                self.store.add(group, self.store.root)
                added += len(list(group.servers()))
        for server in result.servers:
            if server.parent is None and dialog.is_selected(server):
                self.store.add(server, self.store.root)
                added += 1
        self.save_store()
        self.tree.rebuild()
        QMessageBox.information(
            self, "Importar", f"Se importaron {added} conexiones desde {source}."
        )

    def _prune(self, group: Group, dialog: ImportPreviewDialog) -> None:
        for child in list(group.children):
            if not dialog.is_selected(child):
                group.remove(child)
            elif child.kind == "group":
                self._prune(child, dialog)

    def export_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar conexiones", str(Path.home() / "remotedeck.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        import json

        payload = {"version": 1, "root": self.store.root.to_dict()}
        Path(path).write_text(json.dumps(payload, indent=2))
        QMessageBox.information(
            self,
            "Exportar",
            "Conexiones exportadas.\nLas contrasenas van cifradas con la clave de "
            "este equipo: en otro equipo habra que volver a introducirlas.",
        )

    # ------------------------------------------------------ preferencias
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        dialog.master_btn.clicked.connect(lambda: self._toggle_master(dialog))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        QApplication.instance().setStyleSheet(
            stylesheet(self.settings["theme"], self.settings["accent"])
        )
        self.tabs.setTabPosition(
            QTabWidget.TabPosition.South
            if self.settings["tab_position"] == "bottom"
            else QTabWidget.TabPosition.North
        )
        self.tree.rebuild()
        self.tree.start_status_checks()

    def _toggle_master(self, dialog) -> None:
        if vault.mode == "master":
            answer = QMessageBox.question(
                self,
                "Contrasena maestra",
                "Se quitara la contrasena maestra y las credenciales pasaran a "
                "cifrarse con una clave local. Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            secrets = self._collect_secrets()
            vault.clear_master_password()
            self._restore_secrets(secrets)
        else:
            prompt = MasterPasswordDialog("set", self)
            if prompt.exec() != QDialog.DialogCode.Accepted:
                return
            secrets = self._collect_secrets()
            vault.set_master_password(prompt.password())
            self._restore_secrets(secrets)
        self.save_store()
        dialog.master_btn.setText(
            "Quitar contrasena maestra" if vault.mode == "master"
            else "Definir contrasena maestra"
        )

    def _collect_secrets(self) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        for node in [self.store.root, *self.store.root.walk()]:
            creds = getattr(node, "credentials", None)
            if creds is not None:
                out[node.id] = (creds.password(), "")
            if isinstance(node, Server):
                out[node.id] = (node.credentials.password(), node.rdp.gateway_password())
        return out

    def _restore_secrets(self, secrets: dict[str, tuple[str, str]]) -> None:
        from ..vault import vault as v

        for node in [self.store.root, *self.store.root.walk()]:
            data = secrets.get(node.id)
            if not data:
                continue
            password, gateway = data
            creds = getattr(node, "credentials", None)
            if creds is not None:
                creds.set_password(password)
            if isinstance(node, Server) and gateway:
                node.rdp.gateway_secret = v.encrypt(gateway)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"Acerca de {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Gestor de conexiones RDP y VNC con sesiones embebidas en pestanas.</p>"
            "<p>Usa <b>xfreerdp</b> (FreeRDP 3) para RDP y <b>vncviewer</b> "
            "(TigerVNC) para VNC.</p>"
            "<p>Atajos: F11 pantalla completa · Ctrl+R reconectar · "
            "Ctrl+W cerrar sesion · F5 comprobar estado.</p>",
        )

    # -------------------------------------------------------- contexto
    def _tree_menu(self, position) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])
        node = self.tree.current_node()
        menu = QMenu(self)
        servers = self.tree.selected_servers()
        if servers:
            label = "Conectar" if len(servers) == 1 else f"Conectar {len(servers)} equipos"
            menu.addAction(icons.icon("connect", c["text_dim"]), label, self.connect_selected)
        if isinstance(node, Server) and node.wol.enabled:
            menu.addAction(icons.icon("power", c["text_dim"]), "Wake-on-LAN", self.wake_selected)
        menu.addSeparator()
        menu.addAction(icons.icon("add", c["text_dim"]), "Nuevo servidor aqui", self.new_server)
        menu.addAction(icons.icon("folder-add", c["text_dim"]), "Nuevo grupo aqui", self.new_group)
        if node is not None:
            menu.addSeparator()
            menu.addAction(icons.icon("edit", c["text_dim"]), "Editar", self.edit_selected)
            if isinstance(node, Server):
                menu.addAction(icons.icon("copy", c["text_dim"]), "Duplicar", self.duplicate_selected)
                menu.addAction(
                    icons.icon("star", c["accent"] if node.favorite else c["text_dim"]),
                    "Quitar de favoritos" if node.favorite else "Marcar como favorito",
                    self._toggle_favorite,
                )
            menu.addAction(icons.icon("delete", c["text_dim"]), "Eliminar", self.delete_selected)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _toggle_favorite(self) -> None:
        node = self.tree.current_node()
        if isinstance(node, Server):
            node.favorite = not node.favorite
            self.save_store()
            self.tree.rebuild()

    # ---------------------------------------------------------- cierre
    def closeEvent(self, event) -> None:  # noqa: N802
        active = [s for s in self.sessions if s.state == State.CONNECTED]
        if active:
            answer = QMessageBox.question(
                self,
                "Salir",
                f"Hay {len(active)} sesiones activas. Cerrar todo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        for session in list(self.sessions):
            session.stop()
        self.tree.shutdown()
        self.settings["window_geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self.settings["window_state"] = bytes(self.saveState().toBase64()).decode()
        self.settings["sidebar_width"] = self.splitter.sizes()[0]
        self.settings.save()
        self.store.save()
        event.accept()
