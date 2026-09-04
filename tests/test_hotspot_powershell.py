"""Tests de hotspot_powershell.py (netsh vía PowerShell)."""
import pytest

import hotspot_powershell
from hotspot_powershell import PowerShellHotspot


@pytest.fixture
def manager():
    return PowerShellHotspot()


def _patch_ps(monkeypatch, success=True, msg=""):
    def fake(self, command, step=""):
        return success, msg, None
    monkeypatch.setattr(PowerShellHotspot, "run_powershell", fake)


def test_check_support_yes(manager, monkeypatch):
    _patch_ps(monkeypatch, True, "Interface name: Wi-Fi\nHosted network supported  : Yes")
    ok, _ = manager.check_support()
    assert ok


def test_check_support_no_suggests_mobile(manager, monkeypatch):
    _patch_ps(monkeypatch, True, "Interface name: Wi-Fi\nHosted network supported  : No")
    ok, msg = manager.check_support()
    assert not ok
    assert "Mobile Hotspot" in msg


def test_check_support_spanish(manager, monkeypatch):
    _patch_ps(monkeypatch, True, "Nombre de interfaz: Wi-Fi\nRed hospedada admitida    : Sí")
    ok, _ = manager.check_support()
    assert ok


def test_module_wrappers_delegate_to_singleton(monkeypatch):
    """Regresión: main.py llama hotspot_powershell.create_hotspot(...) y
    check_support() a nivel de módulo; antes no existían (AttributeError) o
    usaban una función run_powershell inexistente (NameError)."""
    monkeypatch.setattr(
        hotspot_powershell._manager, "create_hotspot", lambda s, p: (True, f"{s}/{p}")
    )
    monkeypatch.setattr(
        hotspot_powershell._manager, "check_support", lambda: (True, "soportado")
    )
    assert hotspot_powershell.create_hotspot("red", "clave") == (True, "red/clave")
    assert hotspot_powershell.check_support() == (True, "soportado")


def test_stop_updates_state(manager, monkeypatch):
    _patch_ps(monkeypatch, True, "detenido")
    manager._is_running = True
    ok, _ = manager.stop_hotspot()
    assert ok
    assert manager.is_running is False


def test_run_powershell_has_timeout(manager, monkeypatch, fake_run):
    run = fake_run(returncode=0, stdout="ok")
    monkeypatch.setattr(hotspot_powershell.subprocess, "run", run)
    manager.run_powershell("Get-Date", "TEST")
    assert run.calls[0]["kwargs"].get("timeout") is not None
