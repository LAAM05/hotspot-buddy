"""Tests de hotspot_python.py (netsh vía subprocess)."""
import pytest

import error_handler
import hotspot_python
from hotspot_python import HotspotManager


@pytest.fixture
def manager():
    return HotspotManager()


def _debug_info():
    return error_handler.DebugInfo("t", "cmd", 0, "", "", "00:00:00.000", True)


# ─── Validaciones ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pwd,ok", [
    ("password123", True),
    ("pa$$w0rd!@#", True),
    ("corta", False),            # < 8
    ("x" * 64, False),           # > 63
    ('con"comilla', False),      # rompe netsh
    ("conñ12345", False),        # no ASCII imprimible
])
def test_validate_password(manager, pwd, ok):
    valid, _ = manager.validate_password(pwd)
    assert valid is ok


@pytest.mark.parametrize("ssid,ok", [
    ("MiRed", True),
    ("Red 5G Casa", True),
    ("", False),
    ("s" * 33, False),
    ('red"x', False),
    ("red/x", False),
    ("red*", False),
])
def test_validate_ssid(manager, ssid, ok):
    valid, _ = manager.validate_ssid(ssid)
    assert valid is ok


# ─── check_support: parseo inglés/español ────────────────────────────────────

def _patch_netsh_drivers(monkeypatch, output):
    monkeypatch.setattr(
        hotspot_python, "run_command",
        lambda cmd, step="": (0, output, "", _debug_info()),
    )


def test_check_support_english_yes(manager, monkeypatch):
    _patch_netsh_drivers(monkeypatch, "Interface name: Wi-Fi\nHosted network supported  : Yes\n")
    ok, _ = manager.check_support()
    assert ok


def test_check_support_english_no(manager, monkeypatch):
    _patch_netsh_drivers(monkeypatch, "Interface name: Wi-Fi\nHosted network supported  : No\n")
    ok, msg = manager.check_support()
    assert not ok
    assert "Mobile Hotspot" in msg  # debe sugerir la alternativa soportada


def test_check_support_spanish_si(manager, monkeypatch):
    _patch_netsh_drivers(monkeypatch, "Nombre de interfaz: Wi-Fi\nRed hospedada admitida    : Sí\n")
    ok, _ = manager.check_support()
    assert ok


def test_check_support_spanish_no(manager, monkeypatch):
    _patch_netsh_drivers(monkeypatch, "Nombre de interfaz: Wi-Fi\nRed hospedada admitida    : No\n")
    ok, _ = manager.check_support()
    assert not ok


# ─── create_hotspot ───────────────────────────────────────────────────────────

def test_create_validates_before_running_netsh(manager, monkeypatch):
    monkeypatch.setattr(error_handler, "check_admin_error", lambda: "")
    monkeypatch.setattr(
        HotspotManager, "_check_hosted_network_support", lambda self: (True, "ok")
    )
    called = []
    monkeypatch.setattr(
        hotspot_python, "run_command",
        lambda cmd, step="": called.append(cmd) or (0, "", "", _debug_info()),
    )
    ok, _ = manager.create_hotspot("MiRed", "corta")
    assert not ok
    assert called == []  # netsh nunca debe ejecutarse con entrada inválida


def test_create_uses_list_args_no_shell(manager, monkeypatch, fake_run):
    """El comando se pasa como lista (sin shell=True): sin inyección de comandos."""
    monkeypatch.setattr(error_handler, "check_admin_error", lambda: "")
    monkeypatch.setattr(
        HotspotManager, "_check_hosted_network_support", lambda self: (True, "ok")
    )
    monkeypatch.setattr(error_handler, "has_internet_connection", lambda: True)
    monkeypatch.setattr(
        HotspotManager, "_enable_internet_sharing", lambda self: (True, "ICS ok")
    )
    run = fake_run(returncode=0, stdout="ok")
    monkeypatch.setattr(hotspot_python.subprocess, "run", run)

    ok, msg = manager.create_hotspot("MiRed", "password123")
    assert ok, msg
    for call in run.calls:
        assert isinstance(call["cmd"], list)
        assert call["kwargs"].get("shell") is not True
    assert manager.is_running is True


def test_create_offline_succeeds_in_local_mode(manager, monkeypatch, fake_run):
    """Modo Connectify: sin internet el hotspot debe crearse igualmente
    (red local), con advertencia y sin intentar configurar ICS."""
    monkeypatch.setattr(error_handler, "check_admin_error", lambda: "")
    monkeypatch.setattr(
        HotspotManager, "_check_hosted_network_support", lambda self: (True, "ok")
    )
    monkeypatch.setattr(error_handler, "has_internet_connection", lambda: False)

    ics_called = []
    monkeypatch.setattr(
        HotspotManager, "_enable_internet_sharing",
        lambda self: ics_called.append(True) or (True, "ICS"),
    )
    monkeypatch.setattr(hotspot_python.subprocess, "run", fake_run(returncode=0, stdout="ok"))

    ok, msg = manager.create_hotspot("MiRed", "password123")
    assert ok
    assert manager.is_running is True
    assert "sin internet" in msg.lower()
    assert ics_called == []  # sin WAN no debe tocarse ICS


def test_create_online_enables_ics(manager, monkeypatch, fake_run):
    monkeypatch.setattr(error_handler, "check_admin_error", lambda: "")
    monkeypatch.setattr(
        HotspotManager, "_check_hosted_network_support", lambda self: (True, "ok")
    )
    monkeypatch.setattr(error_handler, "has_internet_connection", lambda: True)
    monkeypatch.setattr(
        HotspotManager, "_enable_internet_sharing", lambda self: (True, "ICS habilitado")
    )
    monkeypatch.setattr(hotspot_python.subprocess, "run", fake_run(returncode=0, stdout="ok"))
    ok, msg = manager.create_hotspot("MiRed", "password123")
    assert ok
    assert "ICS habilitado" in msg


# ─── ICS ──────────────────────────────────────────────────────────────────────

def test_enable_ics_uses_hnetcfg_com(manager, monkeypatch, fake_run):
    """Regresión: el método anterior 'verificaba' con WMI sin habilitar nada.
    El ICS real requiere el objeto COM HNetCfg.HNetShare."""
    monkeypatch.setattr(HotspotManager, "_get_internet_adapter", lambda self: "Wi-Fi")
    monkeypatch.setattr(
        HotspotManager, "_get_hotspot_adapter_name", lambda self: "Local Area Connection* 2"
    )
    run = fake_run(returncode=0, stdout="SUCCESS: ICS configurado correctamente")
    monkeypatch.setattr(hotspot_python.subprocess, "run", run)

    ok, _ = manager._enable_internet_sharing()
    assert ok
    script = run.calls[0]["cmd"][-1]
    assert "HNetCfg.HNetShare" in script
    assert "EnableSharing(0)" in script and "EnableSharing(1)" in script
    assert "Win32_NetworkAdapter" not in script


def test_enable_ics_fails_without_adapters(manager, monkeypatch):
    monkeypatch.setattr(HotspotManager, "_get_internet_adapter", lambda self: None)
    ok, msg = manager._enable_internet_sharing()
    assert not ok
