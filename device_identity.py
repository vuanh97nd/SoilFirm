"""Định danh máy cho giới hạn đăng nhập một thiết bị."""
import hashlib
import platform
import uuid
from pathlib import Path


def device_id():
    identity = ''
    if platform.system() == 'Windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                identity = str(winreg.QueryValueEx(key, 'MachineGuid')[0])
        except OSError:
            pass
    else:
        try:
            identity = Path('/etc/machine-id').read_text().strip()
        except OSError:
            pass
    if not identity:
        identity = platform.node() + ':' + str(uuid.getnode())
    return hashlib.sha256(('SoilFirm-device:' + identity).encode('utf-8')).hexdigest()
