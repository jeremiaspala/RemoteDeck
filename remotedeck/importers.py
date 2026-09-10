"""Importadores: Remmina, RDCMan (.rdg) y ficheros .rdp."""

from __future__ import annotations

import base64
import configparser
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .model import RDP, VNC, Credentials, Group, Server
from .vault import vault

REMMINA_DIRS = [
    Path.home() / ".local/share/remmina",
    Path.home() / ".remmina",
]
REMMINA_PREF = Path.home() / ".config/remmina/remmina.pref"


@dataclass
class ImportResult:
    groups: list[Group] = field(default_factory=list)
    servers: list[Server] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.servers)


# ------------------------------------------------------------- Remmina
def _remmina_secret() -> bytes | None:
    if not REMMINA_PREF.exists():
        return None
    for line in REMMINA_PREF.read_text(errors="replace").splitlines():
        if line.startswith("secret="):
            try:
                raw = base64.b64decode(line.split("=", 1)[1].strip())
            except Exception:
                return None
            return raw if len(raw) >= 32 else None
    return None


def _remmina_decrypt(secret: bytes, token: str) -> str:
    from .d3des import des3_cbc_decrypt

    try:
        data = base64.b64decode(token)
    except Exception:
        return ""
    if not data:
        return ""
    plain = des3_cbc_decrypt(secret[:24], secret[24:32], data)
    return plain.rstrip(b"\x00").decode("utf-8", "replace")


def _keyring_lookup(profile: Path) -> str:
    """Remmina >= 1.4 guarda las contrasenas en libsecret."""
    found = _keyring_lookup_gi(profile)
    if found:
        return found
    for attrs in (
        ["filename", str(profile), "key", "password"],
        ["filename", str(profile)],
    ):
        try:
            out = subprocess.run(
                ["secret-tool", "lookup", *attrs],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.rstrip("\n")
    return ""


def _keyring_lookup_gi(profile: Path) -> str:
    """Consulta libsecret directamente (no depende de secret-tool)."""
    try:
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except (ImportError, ValueError):
        return ""
    schema = Secret.Schema.new(
        "org.remmina.Password",
        Secret.SchemaFlags.NONE,
        {
            "filename": Secret.SchemaAttributeType.STRING,
            "key": Secret.SchemaAttributeType.STRING,
        },
    )
    for attrs in ({"filename": str(profile), "key": "password"}, {"filename": str(profile)}):
        try:
            password = Secret.password_lookup_sync(schema, attrs, None)
        except Exception:
            return ""
        if password:
            return password
    return ""


def _remmina_files() -> list[Path]:
    files: list[Path] = []
    for d in REMMINA_DIRS:
        if d.is_dir():
            files.extend(sorted(d.glob("*.remmina")))
    return files


def import_remmina(paths: list[Path] | None = None, use_keyring: bool = True) -> ImportResult:
    result = ImportResult()
    files = paths if paths is not None else _remmina_files()
    if not files:
        result.warnings.append("No se encontraron perfiles de Remmina.")
        return result

    secret = _remmina_secret()
    groups: dict[str, Group] = {}

    for path in files:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(path, encoding="utf-8")
        except (OSError, configparser.Error) as exc:
            result.warnings.append(f"{path.name}: {exc}")
            continue
        if not parser.has_section("remmina"):
            continue
        cfg = parser["remmina"]
        proto = (cfg.get("protocol", "") or "").upper()
        if proto == "RDP":
            protocol = RDP
        elif proto in ("VNC", "VNCI"):
            protocol = VNC
        else:
            result.skipped.append(f"{cfg.get('name', path.stem)} ({proto or '?'})")
            continue

        server_field = cfg.get("server", "").strip()
        host, port = _split_host_port(server_field)
        srv = Server(
            name=cfg.get("name", "") or host,
            host=host,
            port=port,
            protocol=protocol,
        )
        srv.notes = (cfg.get("notes_text", "") or "").replace("\\n", "\n")

        creds = srv.credentials
        creds.username = cfg.get("username", "") or ""
        creds.domain = cfg.get("domain", "") or ""
        creds.inherit = not creds.username

        raw_pw = cfg.get("password", "") or ""
        plain = ""
        if raw_pw and raw_pw != ".":
            if secret:
                plain = _remmina_decrypt(secret, raw_pw)
        elif raw_pw == "." and use_keyring:
            plain = _keyring_lookup(path)
        if plain:
            creds.set_password(plain)
        elif raw_pw:
            result.warnings.append(
                f"{srv.label}: contrasena no recuperable (guardada en el llavero)"
            )

        _apply_remmina_display(srv, cfg)
        if protocol == RDP:
            _apply_remmina_rdp(srv, cfg)
        else:
            _apply_remmina_vnc(srv, cfg)

        group_name = (cfg.get("group", "") or "").strip()
        if group_name:
            parent: Group | None = None
            trail = ""
            for part in [p for p in group_name.split("/") if p]:
                trail = f"{trail}/{part}" if trail else part
                if trail not in groups:
                    g = Group(name=part)
                    groups[trail] = g
                    if parent is not None:
                        parent.add(g)
                    else:
                        result.groups.append(g)
                parent = groups[trail]
            parent.add(srv)
        else:
            result.servers.append(srv)

    # todos los servidores, esten sueltos o dentro de grupos
    all_servers = list(result.servers)
    for g in result.groups:
        all_servers.extend(g.servers())
    result.servers = all_servers
    return result


def _split_host_port(value: str) -> tuple[str, int]:
    value = value.strip()
    if not value:
        return "", 0
    if value.startswith("["):  # IPv6 [::1]:3389
        match = re.match(r"^\[(.+)\](?::(\d+))?$", value)
        if match:
            return match.group(1), int(match.group(2) or 0)
    if value.count(":") == 1:
        host, _, port = value.partition(":")
        if port.isdigit():
            return host, int(port)
    return value, 0


def _apply_remmina_display(srv: Server, cfg) -> None:
    width = _int(cfg.get("resolution_width"))
    height = _int(cfg.get("resolution_height"))
    mode = cfg.get("resolution_mode", "")
    if width and height:
        srv.display.mode = "fixed"
        srv.display.width = width
        srv.display.height = height
    elif mode == "1":
        srv.display.mode = "fullscreen"
    else:
        srv.display.mode = "fit"


def _apply_remmina_rdp(srv: Server, cfg) -> None:
    o = srv.rdp
    depth = _int(cfg.get("colordepth"))
    o.color_depth = depth if depth in (8, 15, 16, 24, 32) else 32
    sec = (cfg.get("security", "") or "").lower()
    o.security = sec if sec in ("nla", "tls", "rdp") else "auto"
    o.console = cfg.get("console", "0") == "1"
    o.clipboard = cfg.get("disableclipboard", "0") != "1"
    sound = (cfg.get("sound", "") or "").lower()
    o.sound = {"local": "local", "remote": "remote", "off": "off"}.get(sound, "off")
    o.microphone = bool(cfg.get("microphone", ""))
    o.shared_folder = cfg.get("sharefolder", "") or ""
    o.printers = cfg.get("shareprinter", "0") == "1"
    o.smartcard = cfg.get("sharesmartcard", "0") == "1"
    o.multimon = cfg.get("multimon", "0") == "1"
    o.ignore_cert = True
    o.keyboard_layout = cfg.get("keymap", "") or ""
    gw = cfg.get("gateway_server", "") or ""
    if gw:
        o.gateway = gw
        o.gateway_username = cfg.get("gateway_username", "") or ""
        o.gateway_domain = cfg.get("gateway_domain", "") or ""


def _apply_remmina_vnc(srv: Server, cfg) -> None:
    o = srv.vnc
    o.view_only = cfg.get("viewonly", "0") == "1"
    o.shared = cfg.get("disableserverinput", "0") != "1"
    quality = _int(cfg.get("quality"))
    o.quality = {0: 3, 1: 6, 2: 8, 9: 9}.get(quality, 8)
    o.full_color = _int(cfg.get("colordepth")) >= 24 or not cfg.get("colordepth")


def _int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# -------------------------------------------------------------- RDCMan
def import_rdg(path: Path) -> ImportResult:
    """Importa un fichero .rdg de Remote Desktop Connection Manager."""
    result = ImportResult()
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        result.warnings.append(f"{path.name}: {exc}")
        return result
    root = tree.getroot()
    file_node = root.find("file")
    if file_node is None:
        result.warnings.append("El fichero no tiene un nodo <file>.")
        return result

    top = Group(name=_text(file_node.find("properties/name")) or path.stem)
    _rdg_children(file_node, top, result)
    result.groups.append(top)
    result.servers = list(top.servers())
    return result


def _rdg_children(node: ET.Element, parent: Group, result: ImportResult) -> None:
    creds = _rdg_credentials(node)
    if creds is not None and parent.credentials.is_empty():
        parent.credentials = creds
    for child in node:
        if child.tag == "group":
            g = Group(name=_text(child.find("properties/name")) or "grupo")
            g.expanded = _text(child.find("properties/expanded")) != "False"
            parent.add(g)
            _rdg_children(child, g, result)
        elif child.tag == "server":
            parent.add(_rdg_server(child, result))


def _rdg_server(node: ET.Element, result: ImportResult) -> Server:
    host = _text(node.find("properties/name"))
    display = _text(node.find("properties/displayName"))
    host, port = _split_host_port(host)
    srv = Server(name=display or host, host=host, port=port, protocol=RDP)
    srv.notes = _text(node.find("properties/comment"))
    creds = _rdg_credentials(node)
    if creds is not None:
        srv.credentials = creds
    size = _text(node.find("connectionSettings/desktopSize"))
    match = re.match(r"(\d+)\s*x\s*(\d+)", size or "")
    if match:
        srv.display.mode = "fixed"
        srv.display.width = int(match.group(1))
        srv.display.height = int(match.group(2))
    if _text(node.find("connectionSettings/connectToConsole")) == "True":
        srv.rdp.console = True
    return srv


def _rdg_credentials(node: ET.Element) -> Credentials | None:
    logon = node.find("logonCredentials")
    if logon is None:
        return None
    inherit = (logon.get("inherit") or "").lower()
    creds = Credentials(
        username=_text(logon.find("userName")),
        domain=_text(logon.find("domain")),
        inherit=inherit not in ("none", "false"),
    )
    pw = logon.find("password")
    if pw is not None and (pw.get("storeAsClearText") or "").lower() == "true":
        creds.set_password(_text(pw))
    return creds if (creds.username or creds.domain) else None


def _text(node: ET.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


# ----------------------------------------------------------- .rdp file
def import_rdp_file(path: Path) -> ImportResult:
    result = ImportResult()
    try:
        lines = path.read_text(encoding="utf-16", errors="strict").splitlines()
    except (UnicodeError, OSError):
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError as exc:
            result.warnings.append(f"{path.name}: {exc}")
            return result
    values: dict[str, str] = {}
    for line in lines:
        parts = line.split(":", 2)
        if len(parts) == 3:
            values[parts[0].strip().lower()] = parts[2].strip()
    host, port = _split_host_port(values.get("full address", ""))
    if not host:
        result.warnings.append(f"{path.name}: sin 'full address'")
        return result
    srv = Server(name=path.stem, host=host, port=port, protocol=RDP)
    srv.credentials.username = values.get("username", "")
    srv.credentials.inherit = not srv.credentials.username
    width = _int(values.get("desktopwidth"))
    height = _int(values.get("desktopheight"))
    if values.get("screen mode id") == "2":
        srv.display.mode = "fullscreen"
    elif width and height:
        srv.display.mode = "fixed"
        srv.display.width, srv.display.height = width, height
    depth = _int(values.get("session bpp"), 32)
    srv.rdp.color_depth = depth if depth in (8, 15, 16, 24, 32) else 32
    srv.rdp.console = values.get("administrative session") == "1"
    srv.rdp.clipboard = values.get("redirectclipboard", "1") == "1"
    srv.rdp.printers = values.get("redirectprinters", "0") == "1"
    srv.rdp.smartcard = values.get("redirectsmartcards", "0") == "1"
    srv.rdp.multimon = values.get("use multimon") == "1"
    gw = values.get("gatewayhostname", "")
    if gw and values.get("gatewayusagemethod", "0") != "0":
        srv.rdp.gateway = gw
    result.servers.append(srv)
    return result


def detect_and_import(path: Path) -> ImportResult:
    suffix = path.suffix.lower()
    if suffix == ".rdg":
        return import_rdg(path)
    if suffix == ".rdp":
        return import_rdp_file(path)
    if suffix == ".remmina":
        return import_remmina([path])
    if suffix == ".json":
        return _import_json(path)
    result = ImportResult()
    result.warnings.append(f"Formato no reconocido: {path.name}")
    return result


def _import_json(path: Path) -> ImportResult:
    import json

    result = ImportResult()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        result.warnings.append(f"{path.name}: {exc}")
        return result
    root = data.get("root", data)
    group = Group.from_dict(root)
    group.name = group.name or path.stem
    result.groups.append(group)
    result.servers = list(group.servers())
    return result
