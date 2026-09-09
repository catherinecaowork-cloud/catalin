"""凭证加密。

规格要求：凭证落库为密文、接口不回显明文。这里用对称密钥做最小实现，
密钥单独落盘且在 .gitignore 内；换成 KMS 信封加密时只需替换本模块。
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from autotest_control.settings import settings

_fernet: Fernet | None = None


def _load_key() -> bytes:
    path = settings.secret_key_path
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    return key


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    return _cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")
