"""Just enough of the Windows-only modules for Gem's code to import elsewhere. Nothing here does anything."""
import ctypes
import subprocess
import sys
import types
from unittest import mock


class _Function:
    def __init__(self):
        self.restype = None
        self.argtypes = None
        self.errcheck = None

    def __call__(self, *args, **kwargs):
        return 0


class _Library:
    def __init__(self, *args, **kwargs):
        self._functions = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._functions.setdefault(name, _Function())


def install():
    ctypes.WinDLL = _Library
    ctypes.OleDLL = _Library
    ctypes.windll = types.SimpleNamespace()
    ctypes.oledll = types.SimpleNamespace()
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE
    ctypes.HRESULT = getattr(ctypes, "HRESULT", ctypes.c_long)
    subprocess.CREATE_NO_WINDOW = 0x08000000
    subprocess.STARTUPINFO = mock.MagicMock
    subprocess.STARTF_USESHOWWINDOW = 1
    sys.modules.setdefault("winreg", mock.MagicMock())
