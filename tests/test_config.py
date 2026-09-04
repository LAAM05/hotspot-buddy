"""Tests de config.py — regresión de los métodos que no recibían self."""
import config as config_module
from config import Config, config


def test_singleton():
    assert Config() is config


def test_get_dot_notation():
    assert config.get("hotspot.ip_address") == "192.168.137.1"
    assert config.get("validation.password_min_length") == 8


def test_get_missing_key_returns_default():
    assert config.get("no.existe", "fallback") == "fallback"
    assert config.get("hotspot.no_existe") is None


def test_all_getters_are_callable_on_instance():
    """Regresión: varios métodos estaban definidos sin `self` y explotaban
    con TypeError/NameError al llamarlos sobre la instancia."""
    assert config.get_hotspot_ip() == "192.168.137.1"
    assert config.get_hotspot_prefix() == 24
    assert config.get_dns_servers() == ["8.8.8.8", "8.8.4.4"]
    assert config.get_timeout_seconds() == 30
    assert config.get_ssid_min_length() == 1
    assert config.get_ssid_max_length() == 32
    assert config.get_password_min_length() == 8
    assert config.get_password_max_length() == 63
    assert config.is_debug_enabled_by_default() is False


def test_defaults_when_config_file_missing(monkeypatch):
    instance = object.__new__(Config)
    monkeypatch.setattr(
        config_module.os.path, "join", lambda *a: "/ruta/inexistente/config.json"
    )
    instance._load_config()
    assert instance.get("hotspot.ip_address") == "192.168.137.1"
    assert instance.get("validation.password_max_length") == 63
