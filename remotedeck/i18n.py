"""Traducciones de la interfaz.

El idioma de referencia es el español: los textos del código son las claves y
cada idioma aporta un diccionario. Si falta una traducción se muestra el
español, así que nunca queda un hueco en pantalla.
"""

from __future__ import annotations

import locale
import os

LANGUAGES = {
    "es": "Español",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
}
DEFAULT = "es"

_current = DEFAULT
_table: dict[str, str] = {}


def _load(code: str) -> dict[str, str]:
    if code == "es":
        return {}
    try:
        module = __import__(f"remotedeck.locales.{code}", fromlist=["STRINGS"])
    except ImportError:
        return {}
    return dict(getattr(module, "STRINGS", {}))


def set_language(code: str) -> str:
    global _current, _table
    code = (code or DEFAULT).lower()[:2]
    if code not in LANGUAGES:
        code = DEFAULT
    _current = code
    _table = _load(code)
    return code


def language() -> str:
    return _current


def system_language() -> str:
    """Idioma del sistema, si es uno de los soportados."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(var)
        if value:
            code = value.split(".")[0].split("_")[0].lower()
            if code in LANGUAGES:
                return code
    try:
        code = (locale.getlocale()[0] or "").split("_")[0].lower()
    except ValueError:
        code = ""
    return code if code in LANGUAGES else DEFAULT


def tr(text: str) -> str:
    """Traduce un texto de la interfaz (la clave es el original en español)."""
    if not _table:
        return text
    return _table.get(text, text)
