"""Arbol lateral de grupos y servidores."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from .. import net
from ..model import RDP, Group, Server
from . import icons
from .theme import palette

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_KIND = Qt.ItemDataRole.UserRole + 1


class StatusChecker(QThread):
    """Comprueba puertos en segundo plano para pintar el punto de estado."""

    result = pyqtSignal(str, bool)

    def __init__(self, targets: list[tuple[str, str, int]], parent=None) -> None:
        super().__init__(parent)
        self.targets = targets
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        net.scan_ports(
            self.targets,
            self.result.emit,
            timeout=1.2,
            should_stop=lambda: self._stop,
        )


class ConnectionTree(QTreeWidget):
    connectRequested = pyqtSignal(object)
    editRequested = pyqtSignal(object)
    selectionChangedNode = pyqtSignal(object)
    treeChanged = pyqtSignal()

    def __init__(self, store, settings, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.status: dict[str, bool] = {}
        self._checker: StatusChecker | None = None
        self._filter = ""

        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setIconSize(QSize(18, 18))
        self.setUniformRowHeights(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setExpandsOnDoubleClick(False)

        self.itemDoubleClicked.connect(self._on_double_click)
        self.itemSelectionChanged.connect(self._on_selection)
        self.itemExpanded.connect(self._on_expanded)
        self.itemCollapsed.connect(self._on_collapsed)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.refresh_status)

    # ------------------------------------------------------- contenido
    def rebuild(self, keep_selection: bool = True) -> None:
        selected = self.current_node_id() if keep_selection else None
        expanded = {
            item.data(0, ROLE_ID)
            for item in self._iter_items()
            if item.isExpanded()
        }
        self.clear()
        self._add_children(self.store.root, self.invisibleRootItem())
        nodes = self.store.index()
        for item in self._iter_items():
            node_id = item.data(0, ROLE_ID)
            node = nodes.get(node_id)
            if item.data(0, ROLE_KIND) == "group":
                should = node_id in expanded if expanded else getattr(node, "expanded", True)
                item.setExpanded(bool(should) or bool(self._filter))
            if node_id == selected:
                self.setCurrentItem(item)
        self.apply_status_colors()

    def _add_children(self, group: Group, parent_item) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])
        for node in group.children:
            if node.kind == "group":
                if self._filter and not self._group_matches(node):
                    continue
                item = QTreeWidgetItem(parent_item)
                item.setText(0, node.label)
                item.setIcon(0, icons.icon("group", c["text_dim"]))
                item.setData(0, ROLE_ID, node.id)
                item.setData(0, ROLE_KIND, "group")
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsDropEnabled
                )
                self._add_children(node, item)
            else:
                if self._filter and not self._server_matches(node):
                    continue
                item = QTreeWidgetItem(parent_item)
                item.setText(0, node.label)
                item.setData(0, ROLE_ID, node.id)
                item.setData(0, ROLE_KIND, "server")
                item.setToolTip(
                    0,
                    f"{node.protocol.upper()} · {node.target}"
                    + (f"\n{node.notes}" if node.notes else ""),
                )
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                )
                self._decorate_server(item, node, c)

    def _decorate_server(self, item: QTreeWidgetItem, node: Server, colours=None) -> None:
        c = colours or palette(self.settings["theme"], self.settings["accent"])
        online = self.status.get(node.id)
        color = c["text_dim"] if online is None else (c["ok"] if online else c["error"])
        item.setIcon(0, icons.icon("rdp" if node.protocol == RDP else "vnc", color))
        if node.favorite:
            item.setForeground(0, QBrush(QColor(c["accent"])))

    def _server_matches(self, node: Server) -> bool:
        text = self._filter
        if not text:
            return True
        haystack = " ".join(
            [node.name, node.host, node.notes, " ".join(node.tags),
             node.credentials.username]
        ).lower()
        return text in haystack

    def _group_matches(self, group: Group) -> bool:
        if self._filter in group.name.lower():
            return True
        return any(self._server_matches(s) for s in group.servers())

    def set_filter(self, text: str) -> None:
        self._filter = text.strip().lower()
        self.rebuild()
        if self._filter:
            self.expandAll()

    # -------------------------------------------------------- seleccion
    def _iter_items(self):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            yield item
            stack.extend(item.child(i) for i in range(item.childCount()))

    def item_for(self, node_id: str) -> QTreeWidgetItem | None:
        for item in self._iter_items():
            if item.data(0, ROLE_ID) == node_id:
                return item
        return None

    def current_node_id(self) -> str | None:
        item = self.currentItem()
        return item.data(0, ROLE_ID) if item else None

    def current_node(self):
        node_id = self.current_node_id()
        return self.store.find(node_id) if node_id else None

    def selected_nodes(self) -> list:
        nodes = []
        for item in self.selectedItems():
            node = self.store.find(item.data(0, ROLE_ID))
            if node is not None:
                nodes.append(node)
        return nodes

    def selected_servers(self) -> list[Server]:
        out: list[Server] = []
        for node in self.selected_nodes():
            if node.kind == "server":
                out.append(node)
            else:
                out.extend(node.servers())
        seen = set()
        unique = []
        for s in out:
            if s.id not in seen:
                seen.add(s.id)
                unique.append(s)
        return unique

    def _on_selection(self) -> None:
        self.selectionChangedNode.emit(self.current_node())

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        node = self.store.find(item.data(0, ROLE_ID))
        if node is None:
            return
        if node.kind == "server":
            self.connectRequested.emit(node)
        else:
            item.setExpanded(not item.isExpanded())

    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        node = self.store.find(item.data(0, ROLE_ID))
        if node is not None and node.kind == "group":
            node.expanded = True

    def _on_collapsed(self, item: QTreeWidgetItem) -> None:
        node = self.store.find(item.data(0, ROLE_ID))
        if node is not None and node.kind == "group":
            node.expanded = False

    # ------------------------------------------------------ drag & drop
    def dropEvent(self, event) -> None:  # noqa: N802
        target = self.itemAt(event.position().toPoint())
        indicator = self.dropIndicatorPosition()
        dragged = self.selected_nodes()
        if not dragged:
            return

        if target is None:
            new_parent, index = self.store.root, None
        else:
            target_node = self.store.find(target.data(0, ROLE_ID))
            if target_node is None:
                return
            if (
                target_node.kind == "group"
                and indicator == QAbstractItemView.DropIndicatorPosition.OnItem
            ):
                new_parent, index = target_node, None
            else:
                new_parent = target_node.parent or self.store.root
                siblings = new_parent.children
                base = siblings.index(target_node) if target_node in siblings else len(siblings)
                index = base + (
                    1
                    if indicator == QAbstractItemView.DropIndicatorPosition.BelowItem
                    else 0
                )

        for node in dragged:
            self.store.move(node, new_parent, index)
            if index is not None:
                index += 1
        event.accept()
        self.rebuild()
        self.treeChanged.emit()

    # ---------------------------------------------------------- estado
    def start_status_checks(self) -> None:
        interval = max(15, int(self.settings["status_interval"] or 60)) * 1000
        self._status_timer.stop()
        if self.settings["status_check"]:
            self._status_timer.start(interval)
            QTimer.singleShot(600, self.refresh_status)

    def refresh_status(self) -> None:
        if self._checker is not None and self._checker.isRunning():
            return
        targets = [
            (s.id, s.host, s.effective_port)
            for s in self.store.servers()
            if s.host
        ]
        if not targets:
            return
        self._checker = StatusChecker(targets, self)
        self._checker.result.connect(self._on_status)
        self._checker.finished.connect(self.apply_status_colors)
        self._checker.start()

    def _on_status(self, node_id: str, online: bool) -> None:
        self.status[node_id] = online

    def apply_status_colors(self) -> None:
        nodes = self.store.index()
        colours = palette(self.settings["theme"], self.settings["accent"])
        for item in self._iter_items():
            if item.data(0, ROLE_KIND) != "server":
                continue
            node = nodes.get(item.data(0, ROLE_ID))
            if isinstance(node, Server):
                self._decorate_server(item, node, colours)

    def shutdown(self) -> None:
        self._status_timer.stop()
        if self._checker is not None:
            self._checker.stop()
            self._checker.wait(1500)
