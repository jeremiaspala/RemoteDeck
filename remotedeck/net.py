"""Utilidades de red: Wake-on-LAN, chequeo de puerto y resolución de MAC."""

from __future__ import annotations

import errno
import re
import selectors
import socket
import subprocess
import time
from typing import Callable, Sequence

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-]?){5}[0-9A-Fa-f]{2}$")


def normalize_mac(mac: str) -> str:
    raw = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(raw) != 12:
        raise ValueError(f"MAC invalida: {mac!r}")
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2)).upper()


def is_valid_mac(mac: str) -> bool:
    try:
        normalize_mac(mac)
        return True
    except ValueError:
        return False


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(normalize_mac(mac).replace(":", ""))
    return b"\xff" * 6 + raw * 16


def wake(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Envía el magic packet. Repite en los puertos habituales 9 y 7."""
    packet = magic_packet(mac)
    ports = {port, 9, 7}
    targets = {broadcast or "255.255.255.255", "255.255.255.255"}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for addr in targets:
            for p in ports:
                try:
                    sock.sendto(packet, (addr, p))
                except OSError:
                    continue


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan_ports(
    targets: Sequence[tuple[str, str, int]],
    on_result: Callable[[str, bool], None],
    timeout: float = 1.5,
    batch: int = 128,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    """Comprueba muchos puertos a la vez con conexiones no bloqueantes.

    Un `connect` por socket y un solo `select` para todos: comprobar cien
    equipos cuesta lo mismo que comprobar uno, y sin un hilo por equipo.
    `targets` son tuplas (clave, host, puerto) y el resultado se entrega por
    `on_result(clave, abierto)`.
    """
    for start in range(0, len(targets), max(1, batch)):
        if should_stop is not None and should_stop():
            return
        chunk = targets[start : start + max(1, batch)]
        pending: dict[socket.socket, str] = {}
        selector = selectors.DefaultSelector()
        try:
            for key, host, port in chunk:
                if not host:
                    continue
                try:
                    family, _type, proto, _canon, addr = socket.getaddrinfo(
                        host, port, type=socket.SOCK_STREAM
                    )[0]
                    sock = socket.socket(family, socket.SOCK_STREAM, proto)
                except (OSError, IndexError):
                    on_result(key, False)
                    continue
                sock.setblocking(False)
                try:
                    err = sock.connect_ex(addr)
                except OSError:
                    err = errno.EHOSTUNREACH
                if err in (0, errno.EISCONN):
                    on_result(key, True)
                    sock.close()
                    continue
                if err not in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK):
                    on_result(key, False)
                    sock.close()
                    continue
                pending[sock] = key
                selector.register(sock, selectors.EVENT_WRITE)

            deadline = time.monotonic() + max(0.2, timeout)
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if should_stop is not None and should_stop():
                    return
                for event, _mask in selector.select(min(remaining, 0.25)):
                    sock = event.fileobj
                    key = pending.pop(sock, None)
                    selector.unregister(sock)
                    code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    sock.close()
                    if key is not None:
                        on_result(key, code == 0)
            timed_out, pending = pending, {}
            for sock, key in timed_out.items():
                selector.unregister(sock)
                sock.close()
                on_result(key, False)
        finally:
            selector.close()
            for sock in pending:
                try:
                    sock.close()
                except OSError:
                    pass


def wait_for_port(host: str, port: int, seconds: int, should_stop=None) -> bool:
    deadline = time.monotonic() + max(1, seconds)
    while time.monotonic() < deadline:
        if should_stop is not None and should_stop():
            return False
        if port_open(host, port, timeout=2.0):
            return True
        time.sleep(2.0)
    return False


def lookup_mac(host: str) -> str:
    """Intenta obtener la MAC del host desde la tabla ARP local."""
    try:
        ip = socket.gethostbyname(host)
    except OSError:
        return ""
    try:
        out = subprocess.run(
            ["ip", "neigh", "show", ip],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    match = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", out)
    if match:
        return normalize_mac(match.group(1))
    try:
        with open("/proc/net/arp") as fh:
            for line in fh.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip and parts[3] != "00:00:00:00:00:00":
                    return normalize_mac(parts[3])
    except OSError:
        pass
    return ""
