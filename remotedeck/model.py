"""Modelo de datos: arbol de grupos y servidores, con herencia estilo RDCMan."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict, fields
from typing import Any, Iterator, Optional

from .vault import vault

RDP = "rdp"
VNC = "vnc"
PROTOCOLS = (RDP, VNC)
DEFAULT_PORTS = {RDP: 3389, VNC: 5900}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _from_dict(cls, data: dict[str, Any]):
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class Credentials:
    username: str = ""
    domain: str = ""
    secret: str = ""  # token cifrado
    inherit: bool = True

    def set_password(self, plain: str) -> None:
        self.secret = vault.encrypt(plain or "")

    def password(self) -> str:
        try:
            return vault.decrypt(self.secret)
        except Exception:
            return ""

    def is_empty(self) -> bool:
        return not (self.username or self.secret)


@dataclass
class RdpOptions:
    console: bool = False
    clipboard: bool = True
    sound: str = "local"  # off | local | remote
    microphone: bool = False
    redirect_drives: bool = False
    home_drive: bool = False
    shared_folder: str = ""
    printers: bool = False
    smartcard: bool = False
    multimon: bool = False
    security: str = "auto"  # auto | nla | tls | rdp
    color_depth: int = 32
    network: str = "auto"
    gfx: bool = True
    dynamic_resolution: bool = True
    smart_sizing: bool = False
    scale: int = 100
    keyboard_layout: str = ""
    gateway: str = ""
    gateway_username: str = ""
    gateway_domain: str = ""
    gateway_secret: str = ""
    ignore_cert: bool = True
    extra_args: str = ""

    def gateway_password(self) -> str:
        try:
            return vault.decrypt(self.gateway_secret)
        except Exception:
            return ""


@dataclass
class VncOptions:
    view_only: bool = False
    shared: bool = True
    quality: int = 8
    compression: int = 2
    encoding: str = "Tight"  # Tight | ZRLE | Hextile | Raw
    full_color: bool = True
    remote_resize: bool = True
    scaling: str = "Auto"  # Auto | FixedRatio | 100
    username: str = ""  # para VeNCrypt/Plain
    extra_args: str = ""


@dataclass
class Wol:
    """Wake-on-LAN por servidor."""

    mac: str = ""
    broadcast: str = "255.255.255.255"
    port: int = 9
    auto: bool = False  # despertar automáticamente antes de conectar
    wait_seconds: int = 90  # espera máxima a que el puerto responda

    @property
    def enabled(self) -> bool:
        return bool(self.mac.strip())


@dataclass
class Display:
    mode: str = "fit"  # fit | fixed | fullscreen
    width: int = 1920
    height: int = 1080
    embed: bool = True  # embebido en pestaña o ventana externa


@dataclass
class Server:
    id: str = field(default_factory=new_id)
    name: str = ""
    host: str = ""
    port: int = 0  # 0 -> puerto por defecto del protocolo
    protocol: str = RDP
    credentials: Credentials = field(default_factory=Credentials)
    display: Display = field(default_factory=Display)
    rdp: RdpOptions = field(default_factory=RdpOptions)
    vnc: VncOptions = field(default_factory=VncOptions)
    wol: Wol = field(default_factory=Wol)
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    connect_on_startup: bool = False

    kind = "server"
    parent: Optional["Group"] = None

    # -- helpers --------------------------------------------------------
    @property
    def effective_port(self) -> int:
        return self.port or DEFAULT_PORTS.get(self.protocol, 3389)

    @property
    def label(self) -> str:
        return self.name or self.host or "(sin nombre)"

    @property
    def target(self) -> str:
        return f"{self.host}:{self.effective_port}"

    def path(self) -> str:
        parts = [self.label]
        node = self.parent
        while node is not None and node.parent is not None:
            parts.append(node.name)
            node = node.parent
        return " / ".join(reversed(parts))

    def effective_credentials(self) -> Credentials:
        """Resuelve la herencia de credenciales por la cadena de grupos."""
        if not self.credentials.inherit:
            return self.credentials
        node = self.parent
        while node is not None:
            if not node.credentials.is_empty():
                merged = Credentials(
                    username=self.credentials.username or node.credentials.username,
                    domain=self.credentials.domain or node.credentials.domain,
                    secret=self.credentials.secret or node.credentials.secret,
                    inherit=False,
                )
                return merged
            node = node.parent
        return self.credentials

    # -- serializacion --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = {
            "kind": "server",
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "credentials": asdict(self.credentials),
            "display": asdict(self.display),
            "rdp": asdict(self.rdp),
            "vnc": asdict(self.vnc),
            "wol": asdict(self.wol),
            "notes": self.notes,
            "tags": list(self.tags),
            "favorite": self.favorite,
            "connect_on_startup": self.connect_on_startup,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Server":
        s = cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            host=data.get("host", ""),
            port=int(data.get("port") or 0),
            protocol=data.get("protocol", RDP),
            credentials=_from_dict(Credentials, data.get("credentials")),
            display=_from_dict(Display, data.get("display")),
            rdp=_from_dict(RdpOptions, data.get("rdp")),
            vnc=_from_dict(VncOptions, data.get("vnc")),
            wol=_from_dict(Wol, data.get("wol")),
            notes=data.get("notes", ""),
            tags=list(data.get("tags") or []),
            favorite=bool(data.get("favorite", False)),
            connect_on_startup=bool(data.get("connect_on_startup", False)),
        )
        return s

    def clone(self) -> "Server":
        copy = Server.from_dict(self.to_dict())
        copy.id = new_id()
        copy.name = f"{self.label} (copia)"
        return copy


@dataclass
class Group:
    id: str = field(default_factory=new_id)
    name: str = ""
    credentials: Credentials = field(default_factory=Credentials)
    children: list[Any] = field(default_factory=list)
    expanded: bool = True
    notes: str = ""

    kind = "group"
    parent: Optional["Group"] = None

    @property
    def label(self) -> str:
        return self.name or "(grupo)"

    def add(self, node: Any, index: int | None = None) -> None:
        node.parent = self
        if index is None:
            self.children.append(node)
        else:
            self.children.insert(index, node)

    def remove(self, node: Any) -> None:
        if node in self.children:
            self.children.remove(node)
            node.parent = None

    def servers(self) -> Iterator[Server]:
        for child in self.children:
            if child.kind == "server":
                yield child
            else:
                yield from child.servers()

    def walk(self) -> Iterator[Any]:
        for child in self.children:
            yield child
            if child.kind == "group":
                yield from child.walk()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "group",
            "id": self.id,
            "name": self.name,
            "credentials": asdict(self.credentials),
            "expanded": self.expanded,
            "notes": self.notes,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Group":
        g = cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            credentials=_from_dict(Credentials, data.get("credentials")),
            expanded=bool(data.get("expanded", True)),
            notes=data.get("notes", ""),
        )
        for child in data.get("children") or []:
            node = (
                Group.from_dict(child)
                if child.get("kind") == "group"
                else Server.from_dict(child)
            )
            g.add(node)
        return g
