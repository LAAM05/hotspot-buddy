from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict, List, Optional, Any
import subprocess
import ctypes
import datetime
import socket

# subprocess.CREATE_NO_WINDOW solo existe en Windows; en otros SO vale 0
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


@dataclass
class DebugInfo:
    step: str
    command: str
    return_code: int
    stdout: str
    stderr: str
    timestamp: str
    success: bool

    def to_string(self) -> str:
        status = "OK" if self.success else "FALLO"
        lines = [
            f"[{self.timestamp}] Paso: {self.step}",
            f"Estado: {status}",
            "Comando ejecutado:",
            f"  {self.command}",
            f"Código de retorno: {self.return_code}",
        ]
        if self.stdout.strip():
            lines.append("Salida (stdout):")
            for line in self.stdout.strip().split("\n"):
                lines.append(f"  {line}")
        if self.stderr.strip():
            lines.append("Error (stderr):")
            for line in self.stderr.strip().split("\n"):
                lines.append(f"  {line}")
        return "\n".join(lines)


class DebugLogger:
    # Thread-safe debug logger
    _enabled: ClassVar[bool] = False
    _logs: ClassVar[List[DebugInfo]] = []
    _lock: ClassVar[Any] = None  # Will be initialized in _init_lock
    
    @classmethod
    def _init_lock(cls):
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()
    
    @classmethod
    def enable(cls):
        cls._enabled = True
    
    @classmethod
    def disable(cls):
        cls._enabled = False
    
    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled
    
    @classmethod
    def log(cls, step: str, command: str, return_code: int, stdout: str, stderr: str) -> DebugInfo:
        cls._init_lock()
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        success = return_code == 0
        info = DebugInfo(step, command, return_code, stdout, stderr, timestamp, success)
        
        if cls._enabled:
            with cls._lock:
                cls._logs.append(info)
        
        return info
    
    @classmethod
    def get_full_report(cls) -> str:
        if not cls._logs:
            return "No hay logs disponibles."
        
        lines = ["=" * 60, "REPORTE DE DEBUG - MODO DESARROLLADOR", "=" * 60, ""]
        
        for i, log in enumerate(cls._logs, 1):
            lines.append(f"--- LOG #{i} ---")
            lines.append(log.to_string())
            lines.append("")
        
        failed_logs = [log for log in cls._logs if not log.success]
        if failed_logs:
            lines.append("=" * 60)
            lines.append("RESUMEN DE ERRORES:")
            lines.append("=" * 60)
            for log in failed_logs:
                lines.append(f"- Paso '{log.step}' fallo con codigo {log.return_code}")
                if log.stderr.strip():
                    lines.append(f"  Error: {log.stderr.strip()[:100]}")
        
        return "\n".join(lines)
    
    @classmethod
    def clear(cls) -> None:
        # Crear nueva lista para evitar que referencias externas vean cambios
        cls._logs = []


ERROR_SOLUTIONS = {
    "hosted network couldn't be started": {
        "error": "No se pudo iniciar el punto de acceso.",
        "solutions": [
            "1. Asegurate de ejecutar la aplicacion como Administrador",
            "2. Verifica que el WiFi este encendido",
            "3. Desactiva cualquier VPN o firewall temporalmente",
            "4. Reinicia el adaptador de red desde Administrador de dispositivos",
            "5. Cierra otras aplicaciones que puedan usar el WiFi (como Mobile Hotspot de Windows)"
        ]
    },
    "group or resource is not in the correct state": {
        "error": "El adaptador de red no esta en el estado correcto.",
        "solutions": [
            "1. Ve a Configuracion > Red e Internet > Configuracion avanzada de red",
            "2. Desactiva y reactiva el adaptador WiFi",
            "3. Ejecuta como Administrador: netsh wlan set hostednetwork mode=disallow",
            "4. Reinicia el comando netsh wlan set hostednetwork mode=allow",
            "5. Si persiste, reinicia la computadora"
        ]
    },
    "access is denied": {
        "error": "Acceso denegado.",
        "solutions": [
            "1. Ejecuta la aplicacion como Administrador",
            "2. Clic derecho en el .exe > Ejecutar como administrador"
        ]
    },
    "wireless local area network interface is powered down": {
        "error": "El adaptador WiFi esta apagado.",
        "solutions": [
            "1. Enciende el WiFi desde la barra de tareas o Configuracion",
            "2. Verifica que no este en modo avion",
            "3. Revisa el interruptor fisico de WiFi (si tu laptop tiene uno)"
        ]
    },
    "the device is not ready": {
        "error": "El dispositivo de red no esta listo.",
        "solutions": [
            "1. Espera unos segundos e intenta de nuevo",
            "2. Reinicia el adaptador WiFi desde Administrador de dispositivos",
            "3. Desconecta y reconecta el adaptador USB WiFi (si aplica)"
        ]
    },
    "element not found": {
        "error": "No se encontro el elemento de red.",
        "solutions": [
            "1. El hotspot puede no estar configurado. Crea uno nuevo.",
            "2. Ejecuta: netsh wlan set hostednetwork mode=allow primero"
        ]
    },
    "the parameter is incorrect": {
        "error": "Parametro incorrecto.",
        "solutions": [
            "1. Verifica que el SSID no tenga caracteres especiales",
            "2. Usa solo letras y numeros en la contrasena",
            "3. El SSID debe tener maximo 32 caracteres"
        ]
    },
    "the requested operation requires elevation": {
        "error": "Se requieren permisos de administrador.",
        "solutions": [
            "1. Ejecuta la aplicacion como Administrador",
            "2. Clic derecho > Ejecutar como administrador"
        ]
    },
    "the hosted network couldn't be started": {
        "error": "El hosted network no pudo iniciarse.",
        "solutions": [
            "1. Verifica que el adaptador WiFi no este en uso por otra aplicacion",
            "2. El 'Mobile Hotspot' de Windows puede estar ocupando el adaptador",
            "3. Desactiva el hotspot de Windows en Configuracion > Red e Internet > Hotspot movil",
            "4. Reinicia el servicio WLAN AutoConfig (services.msc)"
        ]
    },
    "internet connection sharing": {
        "error": "Error al compartir conexion a internet.",
        "solutions": [
            "1. Verifica que tengas una conexion activa a internet",
            "2. Asegurate de tener permisos de administrador",
            "3. Desactiva temporalmente el firewall",
            "4. Reinicia el servicio 'SharedAccess' (servicios.msc)"
        ]
    }
}

GENERIC_ERRORS = {
    "no_wifi_adapter": {
        "error": "No se detecto adaptador WiFi.",
        "solutions": [
            "1. Verifica que tengas un adaptador WiFi instalado",
            "2. Revisa en Administrador de dispositivos > Adaptadores de red",
            "3. Instala los drivers del adaptador WiFi"
        ]
    },
    "not_supported": {
        "error": "Tu adaptador WiFi no soporta Hosted Network.",
        "solutions": [
            "SOLUCIONES ALTERNATIVAS:",
            "",
            "1. Usar Mobile Hotspot de Windows:",
            "   - Ve a Configuracion > Red e Internet > Hotspot movil",
            "   - Este metodo puede funcionar aunque netsh no lo soporte",
            "",
            "2. Usar un adaptador USB WiFi compatible:",
            "   - TP-Link TL-WN722N (version 1)",
            "   - Alfa AWUS036NHA",
            "   - Panda PAU09",
            "",
            "3. Actualizar drivers del adaptador:",
            "   - Busca drivers actualizados del fabricante",
            "   - A veces versiones nuevas habilitan esta funcion"
        ]
    },
    "unknown": {
        "error": "Error desconocido.",
        "solutions": [
            "1. Ejecuta como Administrador",
            "2. Verifica que el WiFi este activo",
            "3. Reinicia la aplicacion",
            "4. Consulta el log de Windows para mas detalles"
        ]
    }
}


def format_error(raw_error: str, debug_info: Optional[DebugInfo] = None) -> str:
    if DebugLogger.is_enabled() and debug_info:
        return format_developer_error(raw_error, debug_info)
    
    return format_user_error(raw_error)


def format_user_error(raw_error: str) -> str:
    raw_lower = raw_error.lower()
    
    for key, info in ERROR_SOLUTIONS.items():
        if key in raw_lower:
            solutions_text = "\n".join(info["solutions"])
            return f"{info['error']}\n\nPosibles soluciones:\n{solutions_text}"
    
    for key, info in GENERIC_ERRORS.items():
        if key in raw_lower:
            solutions_text = "\n".join(info["solutions"])
            return f"{info['error']}\n\nPosibles soluciones:\n{solutions_text}"
    
    if raw_error.strip():
        solutions_text = "\n".join(GENERIC_ERRORS["unknown"]["solutions"])
        return f"Error: {raw_error}\n\nPosibles soluciones:\n{solutions_text}"
    
    solutions_text = "\n".join(GENERIC_ERRORS["unknown"]["solutions"])
    return f"Error inesperado.\n\nPosibles soluciones:\n{solutions_text}"


def format_developer_error(raw_error: str, debug_info: DebugInfo) -> str:
    lines = [
        "=" * 60,
        "MODO DESARROLLADOR - INFORMACION TECNICA",
        "=" * 60,
        "",
        f"PASO DONDE FALLO: {debug_info.step}",
        f"TIMESTAMP: {debug_info.timestamp}",
        "",
        "COMANDO EJECUTADO:",
        f"  {debug_info.command}",
        "",
        f"CODIGO DE RETORNO: {debug_info.return_code}",
    ]
    
    if debug_info.stdout.strip():
        lines.append("")
        lines.append("SALIDA STDOUT:")
        for line in debug_info.stdout.strip().split("\n"):
            lines.append(f"  {line}")
    
    if debug_info.stderr.strip():
        lines.append("")
        lines.append("SALIDA STDERR:")
        for line in debug_info.stderr.strip().split("\n"):
            lines.append(f"  {line}")
    
    if raw_error.strip():
        lines.append("")
        lines.append("MENSAJE DE ERROR ORIGINAL:")
        lines.append(f"  {raw_error}")
    
    lines.append("")
    lines.append("=" * 60)
    lines.append("REPORTE COMPLETO DE LA SESION:")
    lines.append("=" * 60)
    lines.append(DebugLogger.get_full_report())
    
    return "\n".join(lines)


def get_windows_build() -> int:
    """
    Devuelve el número de build de Windows (ej: 26200 para 25H2).
    Útil para detectar el bug de ICS DHCP presente en Build 26200+.
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        )
        build_str, _ = winreg.QueryValueEx(key, "CurrentBuildNumber")
        winreg.CloseKey(key)
        return int(build_str)
    except Exception:
        return 0


def is_affected_by_ics_bug() -> bool:
    """
    Detecta si el sistema está afectado por el bug de ICS/DHCP de
    Windows 11 25H2 (Build 26200+).

    En este build el servidor DHCP de ICS falla: el hotspot se activa
    pero los dispositivos no reciben IP y no tienen internet.
    Referencia: HP Community forums, Build 26200 (25H2) con MediaTek/Realtek.
    """
    return get_windows_build() >= 26200


def check_admin_error() -> str:
    if not _is_admin():
        return (
            "ADVERTENCIA: No estás ejecutando como Administrador.\n"
            "Algunas funciones pueden fallar.\n\n"
            "Clic derecho > Ejecutar como administrador"
        )
    return ""


def has_internet_connection() -> bool:
    """Verifica si hay conexión activa a internet."""
    for host in (("8.8.8.8", 53), ("1.1.1.1", 53)):
        try:
            socket.create_connection(host, timeout=3)
            return True
        except Exception:
            pass
    return False


def diagnose_network() -> str:
    issues = []
    recommendations = []
    
    # Verificar conexion a internet
    if not has_internet_connection():
        issues.append("- NO hay conexion a internet en la computadora")
        recommendations.append("CONSEJO CRITICO: Conecta la computadora a internet antes de crear el hotspot")
    
    def _run_diag(cmd: list) -> str:
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8", errors="ignore",
                timeout=30,
            )
            return r.stdout.lower()
        except Exception:
            return ""

    # Verificar soporte de Hosted Network (inglés y español)
    out = _run_diag(["netsh", "wlan", "show", "drivers"])
    if "hosted network supported" in out:
        if "yes" not in out.split("hosted network supported")[1][:30]:
            issues.append("- Tu adaptador NO soporta Hosted Network (netsh)")
            recommendations.append("Usa el método Mobile Hotspot de Windows en lugar de netsh")
    elif "red hospedada admitida" in out:
        if ": s" not in out.split("red hospedada admitida")[1][:30]:
            issues.append("- Tu adaptador NO soporta Hosted Network (netsh)")
            recommendations.append("Usa el método Mobile Hotspot de Windows en lugar de netsh")
    if "not found" in out or "no wireless" in out:
        issues.append("- No se detectó adaptador WiFi")

    # Verificar estado del adaptador WiFi
    out2 = _run_diag(["netsh", "wlan", "show", "interfaces"])
    if "disconnected" in out2 or "sin conexion" in out2 or "desconectado" in out2:
        issues.append("- El WiFi está desconectado")
    if "hardware off" in out2 or "apagado" in out2:
        issues.append("- El WiFi está apagado por hardware")

    # Verificar servicio ICS
    out3 = _run_diag(["sc", "query", "SharedAccess"])
    if "stopped" in out3:
        recommendations.append("El servicio ICS (SharedAccess) está detenido — el hotspot puede no compartir internet")
    
    # Construir mensaje
    output_lines = []
    if issues:
        output_lines.append("Problemas detectados:")
        output_lines.extend(issues)
    
    if recommendations:
        if issues:
            output_lines.append("")
        output_lines.append("Recomendaciones:")
        output_lines.extend(recommendations)
    
    if not issues and not recommendations:
        return ""
    
    return "\n".join(output_lines)


def get_network_adapters() -> Dict[str, Any]:
    """Obtiene informacion detallada de los adaptadores de red."""
    adapters = {
        'internet_adapter': None,
        'wifi_adapter': None,
        'hotspot_adapters': [],
        'all_adapters': []
    }
    
    try:
        result = subprocess.run(
            "netsh interface show interface",
            shell=True,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW
        )
        
        for line in result.stdout.split('\n')[3:]:  # Saltar cabecera
            parts = line.split()
            if len(parts) >= 4:
                state = parts[0]
                name = ' '.join(parts[3:])
                adapters['all_adapters'].append({
                    'state': state,
                    'name': name
                })
                
                # Detectar adaptador de internet (Ethernet o WiFi conectado)
                if state == 'Connected':
                    if 'Ethernet' in name or 'Local Area Connection' in name:
                        adapters['internet_adapter'] = name
                    elif 'Wi-Fi' in name or 'Wireless' in name or 'WiFi' in name:
                        adapters['wifi_adapter'] = name
                
                # Detectar adaptadores de hotspot existentes
                if 'Local Area Connection*' in name or 'Conexión de área local*' in name:
                    adapters['hotspot_adapters'].append(name)
    except Exception as e:
        adapters['error'] = str(e)
    
    return adapters


def enable_ics(internet_adapter: str, hotspot_adapter: str) -> tuple[bool, str]:
    """
    Habilita Internet Connection Sharing (ICS) entre dos adaptadores.
    
    Args:
        internet_adapter: Nombre del adaptador con internet
        hotspot_adapter: Nombre del adaptador del hotspot
    
    Returns:
        Tuple[bool, str]: (exito, mensaje)
    """
    DebugLogger.clear()
    
    if not _is_admin():
        return False, "Se requieren permisos de administrador para habilitar ICS"
    
    # ICS se habilita con el objeto COM HNetCfg.HNetShare
    # (INetSharingConfiguration.EnableSharing). Win32_NetworkAdapter no tiene
    # ningún método EnableSharing — el enfoque WMI anterior fallaba siempre.
    ps_script = f'''
$ErrorActionPreference = "Stop"

try {{
    $regPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters"
    Set-ItemProperty -Path $regPath -Name "ScopeAddress" -Value "192.168.137.1" -Force
    Set-ItemProperty -Path $regPath -Name "ScopeAddressBackup" -Value "192.168.137.1" -Force

    $netShare = New-Object -ComObject HNetCfg.HNetShare
    $publicCfg = $null
    $privateCfg = $null
    foreach ($conn in @($netShare.EnumEveryConnection)) {{
        $props = $netShare.NetConnectionProps.Invoke($conn)
        $cfg = $netShare.INetSharingConfigurationForINetConnection.Invoke($conn)
        if ($props.Name -eq "{internet_adapter}") {{ $publicCfg = $cfg }}
        if ($props.Name -eq "{hotspot_adapter}") {{ $privateCfg = $cfg }}
        if ($cfg.SharingEnabled) {{ $cfg.DisableSharing() }}
    }}

    if ($publicCfg -and $privateCfg) {{
        $publicCfg.EnableSharing(0)   # ICSSHARINGTYPE_PUBLIC
        $privateCfg.EnableSharing(1)  # ICSSHARINGTYPE_PRIVATE
        Write-Output "SUCCESS: ICS habilitado correctamente"
        return
    }}

    Write-Output "WARNING: No se pudo configurar ICS automaticamente"
    Write-Output "Configura manualmente: Panel de Control > Redes > Propiedades del adaptador > Compartir"

}} catch {{
    Write-Output "ERROR: $($_.Exception.Message)"
}}
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=30
        )
        
        debug_info = DebugLogger.log(
            step="ENABLE_ICS",
            command=ps_script[:100] + "...",
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
        )
        
        if "SUCCESS" in result.stdout:
            return True, "ICS habilitado correctamente. Los dispositivos conectados tendran internet."
        
        error_msg = result.stderr if result.stderr else result.stdout
        return False, f"No se pudo habilitar ICS: {error_msg}"
    
    except subprocess.TimeoutExpired:
        return False, "Timeout al configurar ICS"
    except Exception as e:
        return False, f"Error al configurar ICS: {str(e)}"


def configure_hotspot_dns(adapter_name: str, dns_servers: list = None) -> tuple[bool, str]:
    """
    Configura DNS manual para el adaptador del hotspot.
    
    Args:
        adapter_name: Nombre del adaptador
        dns_servers: Lista de servidores DNS (default: ["8.8.8.8", "8.8.4.4"])
    
    Returns:
        Tuple[bool, str]: (exito, mensaje)
    """
    if dns_servers is None:
        dns_servers = ["8.8.8.8", "8.8.4.4"]  # Google DNS
    
    DebugLogger.clear()
    
    if not _is_admin():
        return False, "Se requieren permisos de administrador"
    
    ps_script = f'''
$ErrorActionPreference = "Stop"

try {{
    $adapter = Get-NetAdapter -Name "{adapter_name}" -ErrorAction Stop
    $ifIndex = $adapter.ifIndex
    
    # Configurar DNS estaticos
    Set-DnsClientServerAddress -InterfaceIndex $ifIndex -ServerAddresses {",".join(dns_servers)}
    
    Write-Output "SUCCESS: DNS configurado a {", ".join(dns_servers)}"
}} catch {{
    Write-Output "ERROR: $($_.Exception.Message)"
}}
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=15
        )
        
        debug_info = DebugLogger.log(
            step="CONFIGURE_DNS",
            command=ps_script[:100] + "...",
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
        )
        
        if "SUCCESS" in result.stdout:
            return True, f"DNS configurado correctamente: {', '.join(dns_servers)}"
        
        error_msg = result.stderr if result.stderr else result.stdout
        return False, f"No se pudo configurar DNS: {error_msg}"
    
    except subprocess.TimeoutExpired:
        return False, "Timeout al configurar DNS"
    except Exception as e:
        return False, f"Error al configurar DNS: {str(e)}"


def reset_network_stack() -> tuple[bool, str]:
    """Reinicia la pila de red de Windows."""
    DebugLogger.clear()
    
    if not _is_admin():
        return False, "Se requieren permisos de administrador"
    
    commands: List[List[str]] = [
        ["netsh", "winsock", "reset"],
        ["netsh", "int", "ip", "reset"],
        ["ipconfig", "/release"],
        ["ipconfig", "/renew"],
        ["ipconfig", "/flushdns"],
    ]

    results = []
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=30,
            )
            DebugLogger.log(
                step=f"RESET_{cmd[0]}",
                command=" ".join(cmd),
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            results.append({
                "command": " ".join(cmd),
                "success": result.returncode == 0,
                "output": result.stdout or result.stderr,
            })
        except Exception as exc:
            results.append({"command": " ".join(cmd), "success": False, "output": str(exc)})
    
    failed = [r for r in results if not r["success"]]
    if failed:
        detail = "\n".join(f"- {r['command']}: {r['output']}" for r in failed)
        return False, f"Algunos comandos fallaron:\n{detail}"
    return True, "Pila de red reiniciada. Se recomienda reiniciar el equipo."
