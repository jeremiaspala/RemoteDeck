"""Cifrado de credenciales.

Construccion: scrypt(KDF) + keystream HMAC-SHA256 en modo contador + HMAC-SHA256
como MAC (encrypt-then-MAC). Solo stdlib, para que el AppImage no arrastre
dependencias binarias de criptografia.

Dos modos:
  * ``local``  : la clave vive en un fichero 0600 dentro de ~/.config. Protege
                 frente a lectura casual del JSON, no frente a alguien con
                 acceso a la cuenta.
  * ``master`` : la clave se deriva de una contraseña maestra que se pide al
                 abrir la aplicación. Nada utilizable queda en disco.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass

from .paths import CONFIG_DIR, VAULT_FILE, ensure_dirs

SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
PREFIX = "enc:v1:"
KEY_FILE = CONFIG_DIR / "vault.key"


class VaultLocked(Exception):
    pass


class BadPassword(Exception):
    pass


def _derive(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password, salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )


def _subkeys(key: bytes) -> tuple[bytes, bytes]:
    enc = hmac.new(key, b"remotedeck-enc", hashlib.sha256).digest()
    mac = hmac.new(key, b"remotedeck-mac", hashlib.sha256).digest()
    return enc, mac


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


@dataclass
class VaultMeta:
    mode: str = "local"
    salt: str = ""
    check: str = ""

    @classmethod
    def load(cls) -> "VaultMeta":
        if VAULT_FILE.exists():
            try:
                return cls(**json.loads(VAULT_FILE.read_text()))
            except (ValueError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        ensure_dirs()
        VAULT_FILE.write_text(json.dumps(self.__dict__, indent=2))
        os.chmod(VAULT_FILE, 0o600)


class Vault:
    def __init__(self) -> None:
        self.meta = VaultMeta.load()
        self._key: bytes | None = None

    # -- estado ---------------------------------------------------------
    @property
    def mode(self) -> str:
        return self.meta.mode

    @property
    def locked(self) -> bool:
        return self._key is None

    def needs_password(self) -> bool:
        return self.meta.mode == "master"

    # -- apertura -------------------------------------------------------
    def unlock(self, password: str | None = None) -> None:
        if self.meta.mode == "master":
            if not password:
                raise VaultLocked("se requiere contraseña maestra")
            salt = base64.b64decode(self.meta.salt)
            key = _derive(password.encode(), salt)
            if not self._check_ok(key):
                raise BadPassword("contraseña maestra incorrecta")
            self._key = key
        else:
            self._key = self._local_key()

    def lock(self) -> None:
        self._key = None

    def _local_key(self) -> bytes:
        ensure_dirs()
        if KEY_FILE.exists():
            raw = base64.b64decode(KEY_FILE.read_bytes())
            if len(raw) == 32:
                return raw
        raw = secrets.token_bytes(32)
        KEY_FILE.write_bytes(base64.b64encode(raw))
        os.chmod(KEY_FILE, 0o600)
        return raw

    def _check_ok(self, key: bytes) -> bool:
        if not self.meta.check:
            return True
        try:
            return self._decrypt_with(key, self.meta.check) == "remotedeck"
        except Exception:
            return False

    # -- cambio de modo -------------------------------------------------
    def set_master_password(self, password: str) -> None:
        """Pasa a modo master. El llamante debe re-cifrar los secretos."""
        salt = secrets.token_bytes(16)
        key = _derive(password.encode(), salt)
        self.meta.mode = "master"
        self.meta.salt = base64.b64encode(salt).decode()
        self._key = key
        self.meta.check = self.encrypt("remotedeck")
        self.meta.save()

    def clear_master_password(self) -> None:
        self.meta.mode = "local"
        self.meta.salt = ""
        self.meta.check = ""
        self._key = self._local_key()
        self.meta.check = self.encrypt("remotedeck")
        self.meta.save()

    def initialize(self) -> None:
        """Crea el fichero de metadatos la primera vez."""
        if not VAULT_FILE.exists():
            self._key = self._local_key()
            self.meta.check = self.encrypt("remotedeck")
            self.meta.save()

    # -- API ------------------------------------------------------------
    def encrypt(self, plaintext: str) -> str:
        if plaintext == "":
            return ""
        if self._key is None:
            raise VaultLocked("vault cerrado")
        k_enc, k_mac = _subkeys(self._key)
        nonce = secrets.token_bytes(16)
        data = plaintext.encode()
        ct = bytes(a ^ b for a, b in zip(data, _keystream(k_enc, nonce, len(data))))
        tag = hmac.new(k_mac, nonce + ct, hashlib.sha256).digest()[:16]
        return PREFIX + base64.b64encode(nonce + ct + tag).decode()

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        if not token.startswith(PREFIX):
            return token  # texto plano heredado de una importación
        if self._key is None:
            raise VaultLocked("vault cerrado")
        return self._decrypt_with(self._key, token)

    @staticmethod
    def _decrypt_with(key: bytes, token: str) -> str:
        k_enc, k_mac = _subkeys(key)
        raw = base64.b64decode(token[len(PREFIX) :])
        nonce, ct, tag = raw[:16], raw[16:-16], raw[-16:]
        expected = hmac.new(k_mac, nonce + ct, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expected):
            raise BadPassword("MAC invalido")
        return bytes(
            a ^ b for a, b in zip(ct, _keystream(k_enc, nonce, len(ct)))
        ).decode()


vault = Vault()
