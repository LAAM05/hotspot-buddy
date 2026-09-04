"""Tests de hotspot_mobile.py (WinRT Mobile Hotspot vía PowerShell)."""
import pytest

import error_handler
import hotspot_mobile
from hotspot_mobile import WindowsMobileHotspot, ps_quote


@pytest.fixture
def manager():
    return WindowsMobileHotspot()


@pytest.fixture
def no_admin_check(monkeypatch):
    monkeypatch.setattr(error_handler, "check_admin_error", lambda: "")


# ─── ps_quote ─────────────────────────────────────────────────────────────────

def test_ps_quote_simple():
    assert ps_quote("MiRed") == "'MiRed'"


def test_ps_quote_escapes_single_quotes():
    assert ps_quote("O'Brien") == "'O''Brien'"


def test_ps_quote_leaves_dollar_and_backtick_literal():
    # Entre comillas simples de PowerShell, $ y ` son literales: no se tocan
    assert ps_quote("pa$$`word") == "'pa$$`word'"


# ─── Validación de entrada ────────────────────────────────────────────────────

def test_create_rejects_short_password(manager, no_admin_check):
    ok, msg = manager.create_hotspot("MiRed", "corta")
    assert not ok
    assert "8" in msg


def test_create_rejects_long_password(manager, no_admin_check):
    ok, _ = manager.create_hotspot("MiRed", "x" * 64)
    assert not ok


def test_create_rejects_long_ssid(manager, no_admin_check):
    ok, _ = manager.create_hotspot("s" * 33, "password123")
    assert not ok


# ─── Generación del script PowerShell ────────────────────────────────────────

def _capture_create_script(manager, monkeypatch, fake_run, ssid, password):
    run = fake_run(returncode=0, stdout="SUCCESS: Hotspot iniciado")
    monkeypatch.setattr(hotspot_mobile.subprocess, "run", run)
    monkeypatch.setattr(
        WindowsMobileHotspot, "_fix_ics_routing_26200", lambda self: (True, "fix ok")
    )
    ok, msg = manager.create_hotspot(ssid, password)
    assert ok, msg
    return run.calls[0]["cmd"], run.calls[0]["kwargs"]


def test_create_embeds_credentials_as_ps_literals(manager, monkeypatch, fake_run, no_admin_check):
    """Regresión: antes se pasaban SSID/contraseña con -ArgumentList junto a
    -Command, que PowerShell no soporta — $args llegaba vacío y el hotspot se
    configuraba sin nombre ni clave."""
    cmd, _ = _capture_create_script(manager, monkeypatch, fake_run, "Mi'Red", "pass'word123")
    script = cmd[-1]
    assert "-ArgumentList" not in cmd
    assert "$args[" not in script
    assert "$config.Ssid = 'Mi''Red'" in script
    assert "$config.Passphrase = 'pass''word123'" in script


def test_create_script_braces_are_balanced(manager, monkeypatch, fake_run, no_admin_check):
    """Regresión: el script de create_hotspot tenía una llave } extra que
    rompía el parseo de PowerShell en todos los casos."""
    cmd, _ = _capture_create_script(manager, monkeypatch, fake_run, "MiRed", "password123")
    script = cmd[-1]
    assert script.count("{") == script.count("}")


def test_create_marks_running_and_uses_timeout(manager, monkeypatch, fake_run, no_admin_check):
    _, kwargs = _capture_create_script(manager, monkeypatch, fake_run, "MiRed", "password123")
    assert manager.is_running is True
    assert kwargs.get("timeout") is not None


def test_all_static_scripts_have_balanced_braces(manager, monkeypatch, fake_run):
    """check_support / stop / status / fix: todos los scripts generados deben
    estar balanceados en llaves."""
    for method in ("check_support", "stop_hotspot", "get_status", "_fix_ics_routing_26200"):
        run = fake_run(returncode=0, stdout="")
        monkeypatch.setattr(hotspot_mobile.subprocess, "run", run)
        getattr(WindowsMobileHotspot(), method)()
        script = run.calls[0]["cmd"][-1]
        assert script.count("{") == script.count("}"), f"desbalance en {method}"


# ─── stop / delete ────────────────────────────────────────────────────────────

def test_stop_hotspot_success(manager, monkeypatch, fake_run):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run",
        fake_run(returncode=0, stdout="SUCCESS: Hotspot detenido"),
    )
    manager._is_running = True
    ok, _ = manager.stop_hotspot()
    assert ok
    assert manager.is_running is False


def test_delete_hotspot_clears_credentials(manager, monkeypatch, fake_run):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run",
        fake_run(returncode=0, stdout="SUCCESS: Hotspot detenido"),
    )
    manager._ssid, manager._password = "red", "clave12345"
    ok, _ = manager.delete_hotspot()
    assert ok
    assert manager._ssid is None
    assert manager._password is None


# ─── Fix ICS Build 26200 ─────────────────────────────────────────────────────

def test_fix_ics_reports_adapter(manager, monkeypatch, fake_run):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run",
        fake_run(returncode=0, stdout="ADAPTER:Conexión de área local* 2\nFIXED"),
    )
    ok, msg = manager.fix_connectivity()
    assert ok
    assert "Conexión de área local* 2" in msg


def test_fix_ics_no_adapter(manager, monkeypatch, fake_run):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run", fake_run(returncode=0, stdout="NO_ADAPTER")
    )
    ok, msg = manager.fix_connectivity()
    assert not ok
    assert "adaptador" in msg.lower()


def test_fix_ics_uses_config_values(manager, monkeypatch, fake_run):
    run = fake_run(returncode=0, stdout="FIXED")
    monkeypatch.setattr(hotspot_mobile.subprocess, "run", run)
    manager.fix_connectivity()
    script = run.calls[0]["cmd"][-1]
    assert "192.168.137.1" in script
    assert "__IP__" not in script and "__PREFIX__" not in script and "__DNS__" not in script


# ─── Modo offline (estilo Connectify) ────────────────────────────────────────

def test_scripts_use_profile_fallback_without_internet(manager, monkeypatch, fake_run):
    """El script no debe depender solo de GetInternetConnectionProfile():
    sin internet debe caer a GetConnectionProfiles() (cualquier perfil)."""
    run = fake_run(returncode=0, stdout="")
    monkeypatch.setattr(hotspot_mobile.subprocess, "run", run)
    manager.check_support()
    script = run.calls[0]["cmd"][-1]
    assert "Get-SharableProfile" in script
    assert "GetConnectionProfiles()" in script


def test_create_offline_succeeds_with_local_mode_warning(manager, monkeypatch, fake_run, no_admin_check):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run",
        fake_run(returncode=0, stdout="OFFLINE_MODE\nSUCCESS: Hotspot iniciado"),
    )
    monkeypatch.setattr(
        WindowsMobileHotspot, "_fix_ics_routing_26200", lambda self: (True, "fix ok")
    )
    ok, msg = manager.create_hotspot("MiRed", "password123")
    assert ok
    assert "Modo local" in msg


def test_create_no_profile_suggests_netsh(manager, monkeypatch, fake_run, no_admin_check):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run", fake_run(returncode=0, stdout="NO_PROFILE")
    )
    ok, msg = manager.create_hotspot("MiRed", "password123")
    assert not ok
    assert "netsh" in msg.lower()


def test_check_support_offline_mentions_local_mode(manager, monkeypatch, fake_run):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run",
        fake_run(returncode=0, stdout="OFFLINE_MODE\nSUPPORTED\nState: Off\nMaxClients: 8\nCurrentSSID: Casa"),
    )
    ok, msg = manager.check_support()
    assert ok
    assert "modo local" in msg.lower()


def test_check_support_no_profile_fails_without_caching(manager, monkeypatch, fake_run):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run", fake_run(returncode=0, stdout="NO_PROFILE")
    )
    ok, msg = manager.check_support()
    assert not ok
    assert "perfil de red" in msg.lower()
    assert manager._support_checked is False  # transitorio: no cachear


# ─── check_support ────────────────────────────────────────────────────────────

def test_check_support_parses_supported(manager, monkeypatch, fake_run):
    monkeypatch.setattr(
        hotspot_mobile.subprocess, "run",
        fake_run(returncode=0, stdout="SUPPORTED\nState: Off\nMaxClients: 8\nCurrentSSID: Casa"),
    )
    ok, msg = manager.check_support()
    assert ok
    assert "COMPATIBLE" in msg
    assert "Casa" in msg


def test_check_support_caches_result(manager, monkeypatch, fake_run):
    run = fake_run(returncode=0, stdout="SUPPORTED\nState: Off")
    monkeypatch.setattr(hotspot_mobile.subprocess, "run", run)
    manager.check_support()
    manager.check_support()
    assert len(run.calls) == 1


