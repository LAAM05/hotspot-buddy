"""Contrato de la interfaz HotspotBase.

Regresión del bug más grave: las tres implementaciones dejaban métodos
abstractos sin implementar, así que instanciarlas (o simplemente importar
los módulos con singleton a nivel de módulo) lanzaba TypeError y la app
no arrancaba.
"""
import pytest

import hotspot_mobile
import hotspot_powershell
import hotspot_python
from hotspot_base import HotspotBase

CLASSES = [
    hotspot_mobile.WindowsMobileHotspot,
    hotspot_python.HotspotManager,
    hotspot_powershell.PowerShellHotspot,
]

MODULES = [hotspot_mobile, hotspot_python, hotspot_powershell]

INTERFACE_METHODS = [
    "create_hotspot",
    "stop_hotspot",
    "delete_hotspot",
    "get_status",
    "check_support",
    "diagnose",
]


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_class_is_instantiable(cls):
    instance = cls()  # TypeError si falta algún método abstracto
    assert isinstance(instance, HotspotBase)


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_class_implements_full_interface(cls):
    instance = cls()
    for name in INTERFACE_METHODS:
        assert callable(getattr(instance, name)), f"{cls.__name__} sin {name}"
    assert isinstance(instance.is_running, bool)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_module_level_api(module):
    """main.py usa los módulos de forma intercambiable (fallback en cadena):
    todos deben exponer las mismas funciones a nivel de módulo."""
    for name in INTERFACE_METHODS:
        assert callable(getattr(module, name, None)), f"{module.__name__} sin {name}()"


def test_mobile_exposes_fix_connectivity():
    assert callable(hotspot_mobile.fix_connectivity)
