"""Configuración común de los tests.

Los tests se ejecutan en cualquier SO: todas las llamadas a subprocess /
PowerShell / netsh se mockean. Nada toca la red ni el sistema real.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import error_handler  # noqa: E402


@pytest.fixture(autouse=True)
def clean_debug_logger():
    """Evita que el estado del DebugLogger se filtre entre tests."""
    error_handler.DebugLogger.disable()
    error_handler.DebugLogger.clear()
    yield
    error_handler.DebugLogger.disable()
    error_handler.DebugLogger.clear()


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def fake_run():
    """Fábrica de reemplazos de subprocess.run que registra las llamadas."""
    def factory(returncode=0, stdout="", stderr=""):
        calls = []

        def _run(cmd, **kwargs):
            calls.append({"cmd": cmd, "kwargs": kwargs})
            return FakeCompletedProcess(returncode, stdout, stderr)

        _run.calls = calls
        return _run

    return factory
