from __future__ import annotations

import os
from pathlib import Path

from . import APP_ID


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    base = Path(value) if value else Path.home() / default
    return base / APP_ID


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config")
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share")
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache")

CONNECTIONS_FILE = CONFIG_DIR / "connections.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
VAULT_FILE = CONFIG_DIR / "vault.json"
LOG_DIR = CACHE_DIR / "logs"

DEFAULT_SHARE_DIR = Path.home() / "RemoteDeck"


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass


def share_dir(configured: str = "") -> Path:
    """Carpeta local que se publica como unidad en las sesiones RDP."""
    raw = (configured or "").strip()
    return Path(os.path.expanduser(raw)) if raw else DEFAULT_SHARE_DIR


def ensure_share_dir(configured: str = "") -> Path | None:
    """Crea la carpeta de intercambio si hace falta. None si no se puede."""
    path = share_dir(configured)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path if path.is_dir() else None


def runtime_dir() -> Path:
    """Directorio efímero para ficheros temporales (passwords de VNC, etc.)."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    d = Path(base) / APP_ID if base else CACHE_DIR / "run"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d
