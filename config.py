"""
config.py - Gestión de configuración externa
"""
import json
import os
from typing import Any, Dict, List, Optional

class Config:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        """Load configuration from JSON file."""
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        except FileNotFoundError:
            # Default configuration if file not found
            self._config = {
                "hotspot": {
                    "ip_address": "192.168.137.1",
                    "prefix_length": 24,
                    "dns_servers": ["8.8.8.8", "8.8.4.4"],
                    "timeout_seconds": 30
                },
                "validation": {
                    "ssid_min_length": 1,
                    "ssid_max_length": 32,
                    "password_min_length": 8,
                    "password_max_length": 63
                },
                "debug": {
                    "enabled_by_default": False
                }
            }
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Error parsing config.json: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        Example: config.get('hotspot.ip_address')
        """
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def get_hotspot_ip(self) -> str:
        return self.get('hotspot.ip_address', '192.168.137.1')

    def get_hotspot_prefix(self) -> int:
        return self.get('hotspot.prefix_length', 24)

    def get_dns_servers(self) -> List[str]:
        return self.get('hotspot.dns_servers', ["8.8.8.8", "8.8.4.4"])

    def get_timeout_seconds(self) -> int:
        return self.get('hotspot.timeout_seconds', 30)

    def get_ssid_min_length(self) -> int:
        return self.get('validation.ssid_min_length', 1)

    def get_ssid_max_length(self) -> int:
        return self.get('validation.ssid_max_length', 32)

    def get_password_min_length(self) -> int:
        return self.get('validation.password_min_length', 8)

    def get_password_max_length(self) -> int:
        return self.get('validation.password_max_length', 63)

    def is_debug_enabled_by_default(self) -> bool:
        return self.get('debug.enabled_by_default', False)

# Singleton instance
config = Config()