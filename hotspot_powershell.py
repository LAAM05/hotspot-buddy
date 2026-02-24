import subprocess
import ctypes
import error_handler

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_powershell(command: str, step: str = "") -> tuple[bool, str, error_handler.DebugInfo]:
    try:
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        debug_info = error_handler.DebugLogger.log(
            step=step,
            command=command,
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
        )
        
        if result.returncode == 0:
            return True, result.stdout.strip(), debug_info
        
        error_msg = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
        return False, error_msg, debug_info
    
    except Exception as e:
        debug_info = error_handler.DebugLogger.log(
            step=step,
            command=command,
            return_code=-1,
            stdout="",
            stderr=str(e)
        )
        return False, str(e), debug_info

def _check_hosted_network_support() -> tuple[bool, str]:
    success, msg, _ = run_powershell("netsh wlan show drivers", "VERIFICAR SOPORTE")
    
    if not success:
        return False, "No se pudo verificar compatibilidad"
    
    output_lower = msg.lower()
    if "hosted network supported" in output_lower:
        after_supported = output_lower.split("hosted network supported")[1][:30]
        if "yes" in after_supported:
            return True, "Compatible"
    
    adapter_name = ""
    for line in msg.split("\n"):
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

def create_hotspot(ssid: str, password: str) -> tuple[bool, str]:
    error_handler.DebugLogger.clear()
    
    admin_warning = error_handler.check_admin_error()
    if admin_warning:
        return False, admin_warning
    
    supported, support_msg = _check_hosted_network_support()
    if not supported:
        if error_handler.DebugLogger.is_enabled():
            return False, f"{support_msg}\n\n{error_handler.DebugLogger.get_full_report()}"
        return False, support_msg
    
    if len(password) < 8:
        return False, "La contrasena debe tener al menos 8 caracteres"
    
    set_cmd = f'netsh wlan set hostednetwork mode=allow ssid="{ssid}" key="{password}"'
    success, msg, debug_info = run_powershell(set_cmd, "CONFIGURAR HOTSPOT")
    
    if not success:
        return False, f"Error al configurar el hotspot.\n\n{error_handler.format_error(msg, debug_info)}"
    
    start_cmd = "netsh wlan start hostednetwork"
    success, msg, debug_info = run_powershell(start_cmd, "INICIAR HOTSPOT")
    
    if success:
        if error_handler.DebugLogger.is_enabled():
            return True, f"Hotspot '{ssid}' creado exitosamente.\n\n{error_handler.DebugLogger.get_full_report()}"
        return True, f"Hotspot '{ssid}' creado exitosamente.\n\nNOTA: Para compartir internet:\n1. Centro de redes > Cambiar configuracion del adaptador\n2. Propiedades del adaptador con internet > Comargar\n3. Selecciona 'Conexion de area local*'"
    
    return False, f"No se pudo iniciar el hotspot.\n\n{error_handler.format_error(msg, debug_info)}"

def stop_hotspot() -> tuple[bool, str]:
    error_handler.DebugLogger.clear()
    
    success, msg, debug_info = run_powershell("netsh wlan stop hostednetwork", "DETENER HOTSPOT")
    
    if success:
        if error_handler.DebugLogger.is_enabled():
            return True, f"Hotspot detenido.\n\n{error_handler.DebugLogger.get_full_report()}"
        return True, "Hotspot detenido exitosamente."
    
    return False, f"No se pudo detener el hotspot.\n\n{error_handler.format_error(msg, debug_info)}"

def delete_hotspot() -> tuple[bool, str]:
    error_handler.DebugLogger.clear()
    
    stop_success, stop_msg = stop_hotspot()
    error_handler.DebugLogger.clear()
    
    set_cmd = "netsh wlan set hostednetwork mode=disallow"
    success, msg, debug_info = run_powershell(set_cmd, "ELIMINAR HOTSPOT")
    
    if success:
        if error_handler.DebugLogger.is_enabled():
            return True, f"Hotspot eliminado.\n\n{error_handler.DebugLogger.get_full_report()}"
        return True, "Hotspot eliminado exitosamente."
    
    return False, f"No se pudo eliminar el hotspot.\n\n{error_handler.format_error(msg, debug_info)}"

def get_status() -> tuple[bool, str]:
    error_handler.DebugLogger.clear()
    
    success, msg, debug_info = run_powershell("netsh wlan show hostednetwork", "OBTENER ESTADO")
    
    if success:
        if error_handler.DebugLogger.is_enabled():
            return True, f"{msg}\n\n{error_handler.DebugLogger.get_full_report()}"
        return True, msg
    
    return False, error_handler.format_error(msg, debug_info)

def check_support() -> tuple[bool, str]:
    error_handler.DebugLogger.clear()
    
    success, msg, debug_info = run_powershell("netsh wlan show drivers", "VERIFICAR COMPATIBILIDAD")
    
    if success:
        if "hosted network supported" in msg.lower():
            after_supported = msg.lower().split("hosted network supported")[1][:30]
            if "yes" in after_supported:
                admin_note = ""
                if not is_admin():
                    admin_note = "\n\nADVERTENCIA: No estas ejecutando como Administrador."
                if error_handler.DebugLogger.is_enabled():
                    return True, f"Adaptador COMPATIBLE.{admin_note}\n\n{error_handler.DebugLogger.get_full_report()}"
                return True, f"Tu adaptador WiFi es COMPATIBLE con Hosted Network.{admin_note}"
            
            adapter_name = ""
            for line in msg.split("\n"):
                if "Interface name" in line:
                    adapter_name = line.split(":")[-1].strip() if ":" in line else ""
                    break
            
            error_msg = f"""ADAPTADOR NO COMPATIBLE DETECTADO
================================
Adaptador: {adapter_name if adapter_name else 'Desconocido'}
Hosted Network: NO SOPORTADO

Este adaptador NO puede crear un hotspot usando netsh.

SOLUCION ALTERNATIVA:
Usa Mobile Hotspot de Windows:
  1. Configuracion > Red e Internet > Hotspot movil
  2. Activa "Compartir mi conexion a Internet"
"""
            if error_handler.DebugLogger.is_enabled():
                error_msg += f"\n{error_handler.DebugLogger.get_full_report()}"
            return False, error_msg
    
    return False, f"No se pudo verificar compatibilidad.\n\n{error_handler.format_error(msg, debug_info)}"

def diagnose() -> str:
    return error_handler.diagnose_network()
