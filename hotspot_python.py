import subprocess
import ctypes
import re
from typing import Optional
import error_handler

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_command(cmd: str, step: str = "") -> tuple[int, str, str, error_handler.DebugInfo]:
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        debug_info = error_handler.DebugLogger.log(
            step=step,
            command=cmd,
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
        )
        return result.returncode, result.stdout, result.stderr, debug_info
    except Exception as e:
        debug_info = error_handler.DebugLogger.log(
            step=step,
            command=cmd,
            return_code=-1,
            stdout="",
            stderr=str(e)
        )
        return -1, "", str(e), debug_info

class HotspotManager:
    def __init__(self):
        self._ssid: Optional[str] = None
        self._password: Optional[str] = None
        self._is_running: bool = False
    
    @property
    def ssid(self) -> Optional[str]:
        return self._ssid
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    def validate_password(self, password: str) -> tuple[bool, str]:
        if len(password) < 8:
            return False, "La contrasena debe tener al menos 8 caracteres"
        if len(password) > 63:
            return False, "La contrasena no puede exceder 63 caracteres"
        if not re.match(r'^[a-zA-Z0-9]+$', password):
            return False, "La contrasena solo puede contener letras y numeros"
        return True, "Contrasena valida"
    
    def validate_ssid(self, ssid: str) -> tuple[bool, str]:
        if len(ssid) < 1 or len(ssid) > 32:
            return False, "El SSID debe tener entre 1 y 32 caracteres"
        return True, "SSID valido"
    
    def _check_hosted_network_support(self) -> tuple[bool, str]:
        code, out, err, _ = run_command("netsh wlan show drivers", "VERIFICAR SOPORTE")
        if code != 0:
            return False, "No se pudo verificar compatibilidad"
        
        output_lower = out.lower()
        if "hosted network supported" in output_lower:
            after_supported = output_lower.split("hosted network supported")[1][:30]
            if "yes" in after_supported:
                return True, "Compatible"
        
        adapter_name = ""
        for line in out.split("\n"):
            if "Interface name" in line:
                adapter_name = line.split(":")[-1].strip() if ":" in line else ""
                break
        
        return False, f"""ADAPTADOR NO COMPATIBLE
========================
Adaptador: {adapter_name if adapter_name else 'Desconocido'}

Tu adaptador WiFi NO soporta Hosted Network.
El comando netsh wlan start hostednetwork NO funcionara.

SOLUCION ALTERNATIVA:
Usa el Mobile Hotspot de Windows:
  1. Configuracion > Red e Internet > Hotspot movil
  2. Activa "Compartir mi conexion a Internet"
"""
    
    def create_hotspot(self, ssid: str, password: str) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        admin_warning = error_handler.check_admin_error()
        if admin_warning:
            return False, admin_warning
        
        supported, support_msg = self._check_hosted_network_support()
        if not supported:
            if error_handler.DebugLogger.is_enabled():
                return False, f"{support_msg}\n\n{error_handler.DebugLogger.get_full_report()}"
            return False, support_msg
        
        valid_ssid, ssid_msg = self.validate_ssid(ssid)
        if not valid_ssid:
            return False, ssid_msg
        
        valid_pwd, pwd_msg = self.validate_password(password)
        if not valid_pwd:
            return False, pwd_msg
        
        self._ssid = ssid
        self._password = password
        
        set_cmd = f'netsh wlan set hostednetwork mode=allow ssid="{ssid}" key="{password}"'
        code, out, err, debug_info = run_command(set_cmd, "CONFIGURAR HOTSPOT")
        
        if code != 0:
            error_msg = err if err else out
            return False, f"Error al configurar el hotspot.\n\n{error_handler.format_error(error_msg, debug_info)}"
        
        start_cmd = "netsh wlan start hostednetwork"
        code, out, err, debug_info = run_command(start_cmd, "INICIAR HOTSPOT")
        
        if code == 0:
            self._is_running = True
            if error_handler.DebugLogger.is_enabled():
                return True, f"Hotspot '{ssid}' creado exitosamente.\n\n{error_handler.DebugLogger.get_full_report()}"
            return True, f"Hotspot '{ssid}' creado exitosamente.\n\nNOTA: Para compartir internet:\n1. Centro de redes > Cambiar configuracion del adaptador\n2. Propiedades del adaptador con internet > Comargar\n3. Selecciona 'Conexion de area local*'"
        
        error_msg = err if err else out
        return False, f"No se pudo iniciar el hotspot.\n\n{error_handler.format_error(error_msg, debug_info)}"
    
    def stop_hotspot(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        code, out, err, debug_info = run_command("netsh wlan stop hostednetwork", "DETENER HOTSPOT")
        
        if code == 0:
            self._is_running = False
            if error_handler.DebugLogger.is_enabled():
                return True, f"Hotspot detenido.\n\n{error_handler.DebugLogger.get_full_report()}"
            return True, "Hotspot detenido exitosamente."
        
        error_msg = err if err else out
        return False, f"No se pudo detener el hotspot.\n\n{error_handler.format_error(error_msg, debug_info)}"
    
    def delete_hotspot(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        if self._is_running:
            self.stop_hotspot()
            error_handler.DebugLogger.clear()
        
        code, out, err, debug_info = run_command("netsh wlan set hostednetwork mode=disallow", "ELIMINAR HOTSPOT")
        
        if code == 0:
            self._ssid = None
            self._password = None
            if error_handler.DebugLogger.is_enabled():
                return True, f"Hotspot eliminado.\n\n{error_handler.DebugLogger.get_full_report()}"
            return True, "Hotspot eliminado exitosamente."
        
        error_msg = err if err else out
        return False, f"No se pudo eliminar el hotspot.\n\n{error_handler.format_error(error_msg, debug_info)}"
    
    def get_status(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        code, out, err, debug_info = run_command("netsh wlan show hostednetwork", "OBTENER ESTADO")
        
        if code != 0:
            error_msg = err if err else out
            return False, error_handler.format_error(error_msg, debug_info)
        
        if error_handler.DebugLogger.is_enabled():
            return True, f"{out}\n\n{error_handler.DebugLogger.get_full_report()}"
        return True, out
    
    def check_support(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        code, out, err, debug_info = run_command("netsh wlan show drivers", "VERIFICAR COMPATIBILIDAD")
        
        if code != 0:
            return False, f"No se pudo verificar la compatibilidad.\n\n{error_handler.format_error(err if err else out, debug_info)}"
        
        output_lower = out.lower()
        
        adapter_name = ""
        for line in out.split("\n"):
            if "Interface name" in line or "Nombre de interfaz" in line:
                adapter_name = line.split(":")[-1].strip() if ":" in line else ""
                break
        
        if "hosted network supported" in output_lower:
            after_supported = output_lower.split("hosted network supported")[1][:30]
            if "yes" in after_supported:
                admin_note = ""
                if not is_admin():
                    admin_note = "\n\nADVERTENCIA: No estas ejecutando como Administrador."
                if error_handler.DebugLogger.is_enabled():
                    return True, f"Adaptador COMPATIBLE.{admin_note}\n\n{error_handler.DebugLogger.get_full_report()}"
                return True, f"Tu adaptador WiFi ({adapter_name}) es COMPATIBLE con Hosted Network.{admin_note}"
            
            error_msg = f"""ADAPTADOR NO COMPATIBLE DETECTADO
================================
Adaptador: {adapter_name if adapter_name else 'Desconocido'}
Hosted Network: NO SOPORTADO

Este adaptador NO puede crear un hotspot usando netsh.

SOLUCIONES ALTERNATIVAS:

1. Usar Mobile Hotspot de Windows:
   - Ve a Configuracion > Red e Internet > Hotspot movil
   - Activa "Comartir mi conexion a Internet"
   - Este metodo puede funcionar aunque netsh no lo soporte

2. Usar un adaptador USB WiFi compatible:
   - TP-Link TL-WN722N (version 1)
   - Alfa AWUS036NHA / AWUS036ACH
   - Panda PAU09 / PAU05
   - Netgear A6210

3. Intentar actualizar drivers:
   - Visita la web del fabricante (Realtek, Intel, etc.)
   - Busca drivers especificos para tu modelo
"""
            if error_handler.DebugLogger.is_enabled():
                error_msg += f"\n{error_handler.DebugLogger.get_full_report()}"
            return False, error_msg
        
        return False, "No se pudo determinar la compatibilidad."

_manager = HotspotManager()

def create_hotspot(ssid: str, password: str) -> tuple[bool, str]:
    return _manager.create_hotspot(ssid, password)

def stop_hotspot() -> tuple[bool, str]:
    return _manager.stop_hotspot()

def delete_hotspot() -> tuple[bool, str]:
    return _manager.delete_hotspot()

def get_status() -> tuple[bool, str]:
    return _manager.get_status()

def check_support() -> tuple[bool, str]:
    return _manager.check_support()

def diagnose() -> str:
    return error_handler.diagnose_network()
