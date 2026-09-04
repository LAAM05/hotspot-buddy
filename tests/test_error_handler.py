"""Tests de error_handler.py."""
import socket

import pytest

import error_handler
from error_handler import DebugInfo, DebugLogger


# ─── DebugLogger ─────────────────────────────────────────────────────────────

def test_log_returns_debug_info_always():
    info = DebugLogger.log("PASO", "cmd", 0, "out", "")
    assert isinstance(info, DebugInfo)
    assert info.success is True


def test_log_only_stored_when_enabled():
    DebugLogger.log("PASO", "cmd", 0, "", "")
    assert "No hay logs" in DebugLogger.get_full_report()

    DebugLogger.enable()
    DebugLogger.log("PASO2", "cmd2", 1, "", "boom")
    report = DebugLogger.get_full_report()
    assert "PASO2" in report
    assert "RESUMEN DE ERRORES" in report  # return_code 1 → aparece como fallo


def test_clear_resets_logs():
    DebugLogger.enable()
    DebugLogger.log("PASO", "cmd", 0, "", "")
    DebugLogger.clear()
    assert "No hay logs" in DebugLogger.get_full_report()


# ─── format_error ─────────────────────────────────────────────────────────────

def test_format_user_error_known_message():
    msg = error_handler.format_user_error("Access is denied.")
    assert "Administrador" in msg


def test_format_user_error_unknown_message():
    msg = error_handler.format_user_error("algo raro paso")
    assert "algo raro paso" in msg
    assert "soluciones" in msg.lower()


def test_format_error_uses_developer_mode():
    DebugLogger.enable()
    info = DebugLogger.log("PASO_X", "comando-x", 1, "", "stderr-x")
    msg = error_handler.format_error("fallo", info)
    assert "MODO DESARROLLADOR" in msg
    assert "comando-x" in msg


# ─── Detección de build / bug ICS ────────────────────────────────────────────

def test_get_windows_build_returns_zero_off_windows():
    # En Linux no hay winreg: debe degradar a 0, no lanzar
    assert isinstance(error_handler.get_windows_build(), int)


@pytest.mark.parametrize("build,affected", [(22631, False), (26100, False), (26200, True), (26300, True)])
def test_is_affected_by_ics_bug_threshold(monkeypatch, build, affected):
    monkeypatch.setattr(error_handler, "get_windows_build", lambda: build)
    assert error_handler.is_affected_by_ics_bug() is affected


# ─── has_internet_connection ─────────────────────────────────────────────────

def test_has_internet_true(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: object())
    assert error_handler.has_internet_connection() is True


def test_has_internet_false(monkeypatch):
    def fail(*a, **k):
        raise OSError("sin red")
    monkeypatch.setattr(socket, "create_connection", fail)
    assert error_handler.has_internet_connection() is False


# ─── enable_ics ──────────────────────────────────────────────────────────────

def test_enable_ics_requires_admin(monkeypatch):
    monkeypatch.setattr(error_handler, "_is_admin", lambda: False)
    ok, msg = error_handler.enable_ics("Wi-Fi", "Local Area Connection* 2")
    assert not ok
    assert "administrador" in msg.lower()


def test_enable_ics_uses_hnetcfg_com(monkeypatch):
    monkeypatch.setattr(error_handler, "_is_admin", lambda: True)
    captured = {}

    class Fake:
        returncode = 0
        stdout = "SUCCESS: ICS habilitado correctamente"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["script"] = cmd[-1]
        return Fake()

    monkeypatch.setattr(error_handler.subprocess, "run", fake_run)
    ok, _ = error_handler.enable_ics("Wi-Fi", "Local Area Connection* 2")
    assert ok
    assert "HNetCfg.HNetShare" in captured["script"]
    assert "Win32_NetworkAdapter" not in captured["script"]
