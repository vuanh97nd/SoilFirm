"""Lưu tùy chọn ghi nhớ đăng nhập trong hồ sơ người dùng Windows.

Khóa được mã hóa bằng DPAPI của chính tài khoản Windows hiện tại.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time


SESSION_SECONDS = 24 * 60 * 60


def credentials_path() -> Path:
    base = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
    if not base:
        base = str(Path.home() / 'AppData' / 'Roaming') if sys.platform == 'win32' else str(Path.home() / '.config')
    return Path(base) / 'SoilFirm' / 'login.json'


def session_path() -> Path:
    return credentials_path().with_name('session.json')


def _crypt(data: bytes, decrypt: bool = False) -> bytes:
    if sys.platform != 'win32':
        raise RuntimeError('Ghi nhớ mật khẩu chỉ hỗ trợ Windows.')

    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

    raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(result.pbData)


def save_credentials(username: str, key: str) -> None:
    destination = credentials_path()
    secret = base64.b64encode(_crypt(key.encode('utf-8'))).decode('ascii')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix='login-', suffix='.tmp', dir=destination.parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'version': 1, 'username': username, 'secret': secret}, stream,
                      ensure_ascii=False)
        os.replace(temp_name, destination)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.remove(temp_name)


def clear_credentials() -> None:
    credentials_path().unlink(missing_ok=True)


def save_session(username: str, key: str) -> None:
    """Lưu phiên 24 giờ; khóa vẫn được DPAPI bảo vệ như tùy chọn ghi nhớ."""
    destination = session_path()
    secret = base64.b64encode(_crypt(key.encode('utf-8'))).decode('ascii')
    destination.parent.mkdir(parents=True, exist_ok=True)
    issued = time.time()
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix='session-', suffix='.tmp', dir=destination.parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'version': 1, 'username': username, 'secret': secret,
                       'issued_at': issued, 'expires_at': issued + SESSION_SECONDS}, stream,
                      ensure_ascii=False)
        os.replace(temp_name, destination)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.remove(temp_name)


def clear_session() -> None:
    session_path().unlink(missing_ok=True)


def load_session() -> tuple[str, str] | None:
    destination = session_path()
    if not destination.is_file():
        return None
    try:
        data = json.loads(destination.read_text(encoding='utf-8'))
        issued = float(data['issued_at'])
        expiry = float(data['expires_at'])
        now = time.time()
        if (data.get('version') != 1 or not data.get('username') or not data.get('secret')
                or not (issued - 300 <= now < expiry <= issued + SESSION_SECONDS + 1)):
            clear_session()
            return None
        key = _crypt(base64.b64decode(data['secret'], validate=True), decrypt=True).decode('utf-8')
        return str(data['username']), key
    except (KeyError, TypeError, ValueError, OSError):
        clear_session()
        return None


def load_credentials(legacy_path: str | None = None) -> tuple[str, str] | None:
    destination = credentials_path()
    if destination.is_file():
        data = json.loads(destination.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not data.get('secret'):
            raise ValueError('Dữ liệu ghi nhớ đăng nhập không hợp lệ.')
        key = _crypt(base64.b64decode(data['secret'], validate=True), decrypt=True).decode('utf-8')
        return str(data.get('username', '')), key

    # Chỉ nhập lại tệp cũ khi chạy từ mã nguồn; tệp cạnh .exe một file có thể
    # nằm trong thư mục giải nén tạm của PyInstaller và sẽ mất khi thoát.
    if legacy_path and Path(legacy_path).is_file():
        legacy = Path(legacy_path)
        old = json.loads(legacy.read_text(encoding='utf-8'))
        if old.get('remember') and old.get('username') and old.get('key'):
            save_credentials(old['username'], old['key'])
            legacy.unlink()
            return old['username'], old['key']
    return None
