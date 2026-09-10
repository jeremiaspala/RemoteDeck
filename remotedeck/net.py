"""Utilidades de red: Wake-on-LAN, chequeo de puerto y resolución de MAC."""

from __future__ import annotations

import re
import socket
import subprocess
import time

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
