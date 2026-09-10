"""Construccion de las lineas de comando de los visores RDP y VNC."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .model import RDP, VNC, Server
from .paths import runtime_dir

RDP_BINARIES = ("xfreerdp3", "xfreerdp", "freerdp3", "wlfreerdp")
VNC_BINARIES = ("vncviewer", "xtigervncviewer", "tigervncviewer")


class BackendMissing(Exception):
    pass


def _appdir_bin(name: str) -> str | None:
    appdir = os.environ.get("APPDIR")
    if not appdir:
        return None
    candidate = Path(appdir) / "usr" / "bin" / name
    return str(candidate) if candidate.exists() else None


def find_binary(candidates: tuple[str, ...], override: str = "") -> str:
    if override:
        if os.path.isabs(override) and os.access(override, os.X_OK):
            return override
        found = shutil.which(override)
        if found:
            return found
    for name in candidates:
        bundled = _appdir_bin(name)
        if bundled:
            return bundled
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    raise BackendMissing(
        "No se encontro ninguno de: " + ", ".join(candidates)
    )


@dataclass
class Launch:
    argv: list[str]
    stdin_data: bytes | None = None
    env: dict[str, str] = field(default_factory=dict)
    tempfiles: list[Path] = field(default_factory=list)
    reparent_needed: bool = False  # True cuando el visor no soporta parent-window

    def cleanup(self) -> None:
        for path in self.tempfiles:
            try:
                path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- RDP
def build_rdp(
    server: Server,
    username: str,
    domain: str,
    password: str,
    parent_xid: int | None,
    width: int,
    height: int,
    fullscreen: bool = False,
    binary_override: str = "",
) -> Launch:
    binary = find_binary(RDP_BINARIES, binary_override)
    o = server.rdp
    args: list[str] = [f"/v:{server.host}", f"/port:{server.effective_port}"]

    if username:
        args.append(f"/u:{username}")
    if domain:
        args.append(f"/d:{domain}")
    if password:
        args.append(f"/p:{password}")

    if fullscreen:
        args.append("+f")
    elif parent_xid:
        args.append(f"/parent-window:{parent_xid}")

    args += [f"/w:{max(320, width)}", f"/h:{max(240, height)}"]

    if o.dynamic_resolution and not o.smart_sizing:
        args.append("+dynamic-resolution")
    if o.smart_sizing:
        args.append("/smart-sizing")
    if o.scale and o.scale != 100:
        args.append(f"/scale:{o.scale}")

    args.append(f"/bpp:{o.color_depth}")
    args.append(f"/network:{o.network}")
    if o.gfx:
        # AVC420/AVC444 solo existen si FreeRDP se compilo con H.264; RFX y
        # progressive están siempre disponibles.
        args.append("/gfx:RFX:on,progressive:on,small-cache:on")
    if o.security != "auto":
        args.append(f"/sec:{o.security}")
    if o.ignore_cert:
        args.append("/cert:ignore")
    args.append("+clipboard" if o.clipboard else "-clipboard")
    if o.sound == "local":
        args.append("/sound:sys:pulse")
    elif o.sound == "remote":
        args.append("/audio-mode:1")
    if o.microphone:
        args.append("/microphone:sys:pulse")
    if o.redirect_drives:
        args.append("+drives")
    if o.home_drive:
        args.append("+home-drive")
    if o.shared_folder:
        label = Path(o.shared_folder).name or "shared"
        args.append(f"/drive:{label},{o.shared_folder}")
    if o.printers:
        args.append("/printer")
    if o.smartcard:
        args.append("/smartcard")
    if o.multimon:
        args.append("/multimon")
    if o.console:
        args.append("+admin")
    if o.keyboard_layout:
        args.append(f"/kbd:layout:{o.keyboard_layout}")
    if o.gateway:
        args.append(f"/g:{o.gateway}")
        if o.gateway_username:
            args.append(f"/gu:{o.gateway_username}")
        if o.gateway_domain:
            args.append(f"/gd:{o.gateway_domain}")
        gw_pass = o.gateway_password()
        if gw_pass:
            args.append(f"/gp:{gw_pass}")

    args += ["+auto-reconnect", "/auto-reconnect-max-retries:3", "/log-level:INFO"]
    args += _split_extra(o.extra_args)

    # /args-from:stdin evita que la contraseña aparezca en la tabla de procesos.
    payload = ("\n".join(args) + "\n").encode()
    return Launch(argv=[binary, "/args-from:stdin"], stdin_data=payload)


# ---------------------------------------------------------------- VNC
def _vnc_password_file(password: str) -> Path | None:
    if not password:
        return None
    path = runtime_dir() / f"vnc-{os.getpid()}-{secrets.token_hex(4)}.pwd"
    try:
        result = subprocess.run(
            ["vncpasswd", "-f"],
            input=(password + "\n" + password + "\n").encode(),
            capture_output=True,
            timeout=10,
        )
        data = result.stdout
    except (OSError, subprocess.SubprocessError):
        data = b""
    if not data:
        data = _obfuscate_vnc_password(password)
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return path


def build_vnc(
    server: Server,
    username: str,
    password: str,
    width: int,
    height: int,
    fullscreen: bool = False,
    binary_override: str = "",
) -> Launch:
    binary = find_binary(VNC_BINARIES, binary_override)
    o = server.vnc
    port = server.effective_port
    # TigerVNC: host::port para puerto TCP absoluto, host:N para display.
    target = f"{server.host}::{port}"

    args = [binary, target]
    args += ["-Shared" if o.shared else "-Shared=0"]
    if o.view_only:
        args.append("-ViewOnly")
    args += [f"-QualityLevel={o.quality}", f"-CompressLevel={o.compression}"]
    args += [f"-PreferredEncoding={o.encoding}"]
    args.append("-FullColor" if o.full_color else "-FullColor=0")
    args.append("-RemoteResize=1" if o.remote_resize else "-RemoteResize=0")
    args.append("-AlertOnFatalError=0")
    args.append("-ReconnectOnError=0")
    if username or o.username:
        args.append(f"-User={username or o.username}")
    if fullscreen:
        args.append("-FullScreen")
    else:
        args.append(f"-geometry={max(320, width)}x{max(240, height)}+0+0")

    tempfiles: list[Path] = []
    pwfile = _vnc_password_file(password)
    if pwfile:
        args.append(f"-PasswordFile={pwfile}")
        tempfiles.append(pwfile)

    args += _split_extra(o.extra_args)
    return Launch(argv=args, tempfiles=tempfiles, reparent_needed=True)


def _split_extra(extra: str) -> list[str]:
    if not extra.strip():
        return []
    import shlex

    try:
        return shlex.split(extra)
    except ValueError:
        return extra.split()


def build(
    server: Server,
    username: str,
    domain: str,
    password: str,
    parent_xid: int | None,
    width: int,
    height: int,
    fullscreen: bool = False,
    settings=None,
) -> Launch:
    rdp_bin = settings["rdp_binary"] if settings else ""
    vnc_bin = settings["vnc_binary"] if settings else ""
    if server.protocol == VNC:
        return build_vnc(
            server, username, password, width, height, fullscreen, vnc_bin
        )
    if server.protocol != RDP:
        raise BackendMissing(f"Protocolo no soportado: {server.protocol}")
    return build_rdp(
        server,
        username,
        domain,
        password,
        parent_xid,
        width,
        height,
        fullscreen,
        rdp_bin,
    )


# --------------------------------------------------- d3des (respaldo)
_D3DES_KEY = b"\x17\x52\x6b\x06\x23\x4e\x58\x07"


def _obfuscate_vnc_password(password: str) -> bytes:
    """Fallback en Python puro si no hay vncpasswd: DES con la clave fija VNC.

    El formato del fichero es la contraseña (8 bytes, rellenada con ceros)
    cifrada con DES usando la clave fija de VNC con los bits de cada byte
    invertidos.
    """
    from .d3des import des_encrypt_block, reverse_bits

    data = password.encode("latin-1", "replace")[:8].ljust(8, b"\x00")
    return des_encrypt_block(reverse_bits(_D3DES_KEY), data)
