"""Persistencia del arbol de conexiones y de los ajustes."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Optional

from .model import Group, Server
from .paths import CONNECTIONS_FILE, SETTINGS_FILE, ensure_dirs

SCHEMA_VERSION = 1

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",
    "accent": "#4c8dff",
    "connect_on_double_click": True,
    "confirm_close_session": True,
    "reconnect_on_drop": False,
    "status_check": True,
    "status_interval": 60,
    "tab_position": "top",
    "sidebar_width": 300,
    "window_geometry": "",
    "window_state": "",
    "show_thumbnails": False,
    "rdp_binary": "",
    "vnc_binary": "",
    "last_import_dir": "",
    "fullscreen_hotkey": "F11",
    "first_run_done": False,
}


def _atomic_write(path, text: str, mode: int = 0o600) -> None:
    ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


class Settings:
    def __init__(self) -> None:
        self.data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        if SETTINGS_FILE.exists():
            try:
                self.data.update(json.loads(SETTINGS_FILE.read_text()))
            except ValueError:
                pass

    def save(self) -> None:
        _atomic_write(SETTINGS_FILE, json.dumps(self.data, indent=2), 0o644)

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key, DEFAULT_SETTINGS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    get = __getitem__


class Store:
    """Arbol de conexiones. La raiz es un grupo implicito sin nombre."""

    def __init__(self) -> None:
        self.root = Group(name="Conexiones")
        self.dirty = False

    # -- E/S ------------------------------------------------------------
    def load(self) -> None:
        if not CONNECTIONS_FILE.exists():
            self.root = Group(name="Conexiones")
            return
        try:
            data = json.loads(CONNECTIONS_FILE.read_text())
        except ValueError:
            backup = CONNECTIONS_FILE.with_suffix(".json.corrupt")
            shutil.copy2(CONNECTIONS_FILE, backup)
            self.root = Group(name="Conexiones")
            return
        self.root = Group.from_dict(data.get("root", {"name": "Conexiones"}))
        self.root.parent = None

    def save(self) -> None:
        payload = {"version": SCHEMA_VERSION, "root": self.root.to_dict()}
        if CONNECTIONS_FILE.exists():
            shutil.copy2(CONNECTIONS_FILE, CONNECTIONS_FILE.with_suffix(".json.bak"))
        _atomic_write(CONNECTIONS_FILE, json.dumps(payload, indent=2))
        self.dirty = False

    # -- consultas ------------------------------------------------------
    def find(self, node_id: str) -> Optional[Any]:
        if node_id == self.root.id:
            return self.root
        for node in self.root.walk():
            if node.id == node_id:
                return node
        return None

    def servers(self) -> list[Server]:
        return list(self.root.servers())

    def groups(self) -> list[Group]:
        return [self.root] + [n for n in self.root.walk() if n.kind == "group"]

    def search(self, text: str) -> list[Server]:
        text = text.strip().lower()
        if not text:
            return []
        out = []
        for s in self.root.servers():
            haystack = " ".join(
                [s.name, s.host, s.notes, " ".join(s.tags), s.credentials.username]
            ).lower()
            if text in haystack:
                out.append(s)
        return out

    # -- mutaciones -----------------------------------------------------
    def add(self, node: Any, parent: Group | None = None, index: int | None = None):
        (parent or self.root).add(node, index)
        self.dirty = True
        return node

    def remove(self, node: Any) -> None:
        parent = node.parent or self.root
        parent.remove(node)
        self.dirty = True

    def move(self, node: Any, new_parent: Group, index: int | None = None) -> None:
        if node is new_parent or self._is_ancestor(node, new_parent):
            return
        old = node.parent or self.root
        old.remove(node)
        new_parent.add(node, index)
        self.dirty = True

    @staticmethod
    def _is_ancestor(node: Any, candidate: Group) -> bool:
        p = candidate.parent
        while p is not None:
            if p is node:
                return True
            p = p.parent
        return False
