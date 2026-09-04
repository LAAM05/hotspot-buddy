"""
hotspot_base.py - Clase base abstracta para todos los métodos de hotspot
"""
from abc import ABC, abstractmethod
from typing import Tuple, Optional

class HotspotBase(ABC):
    """Interfaz común para todos los métodos de implementación de hotspot"""
    
    @abstractmethod
    def create_hotspot(self, ssid: str, password: str) -> Tuple[bool, str]:
        """Crea un punto de acceso Wi-Fi
        
        Args:
            ssid: Nombre de la red
            password: Contraseña de la red (mínimo 8 caracteres)
            
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        pass
    
    @abstractmethod
    def stop_hotspot(self) -> Tuple[bool, str]:
        """Detiene el punto de acceso Wi-Fi activo
        
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        pass
    
    @abstractmethod
    def delete_hotspot(self) -> Tuple[bool, str]:
        """Elimina la configuración del punto de acceso Wi-Fi
        
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Tuple[bool, str]:
        """Obtiene el estado actual del punto de acceso Wi-Fi
        
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        pass
    
    @abstractmethod
    def check_support(self) -> Tuple[bool, str]:
        """Verifica si el adaptador Wi-Fi soporta este método de hotspot
        
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        pass
    
    @abstractmethod
    def diagnose(self) -> str:
        """Ejecuta diagnóstico de red y devuelve resultados
        
        Returns:
            str: Información de diagnóstico
        """
        pass
    
    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Indica si el hotspot está actualmente activo
        
        Returns:
            bool: True si está activo, False en caso contrario
        """
        pass