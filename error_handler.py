from dataclasses import dataclass
from typing import Optional, List
import subprocess
import ctypes
import datetime

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
            f"Comando ejecutado:",
            f"  {self.command}",
            f"Codigo de retorno: {self.return_code}",
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
    _instance = None
    _enabled = False
    _logs: List[DebugInfo] = []
    
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
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        success = return_code == 0
        info = DebugInfo(step, command, return_code, stdout, stderr, timestamp, success)
        
        if cls._enabled:
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
    def clear(cls):
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


def check_admin_error() -> str:
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            return "ADVERTENCIA: No estas ejecutando como Administrador.\nAlgunas funciones pueden fallar.\n\nClic derecho > Ejecutar como administrador"
    except:
        pass
    return ""


def diagnose_network() -> str:
    issues = []
    
    try:
        result = subprocess.run(
            "netsh wlan show drivers",
            shell=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = result.stdout.lower()
        
        if "hosted network supported" in output:
            if "yes" not in output.split("hosted network supported")[1][:30]:
                issues.append("- Tu adaptador NO soporta Hosted Network")
        
        if "not found" in output or "no wireless" in output:
            issues.append("- No se detecto adaptador WiFi")
    
    except:
        pass
    
    try:
        result = subprocess.run(
            "netsh wlan show interfaces",
            shell=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = result.stdout.lower()
        
        if "disconnected" in output or "sin conexion" in output:
            issues.append("- El WiFi esta desconectado")
        
        if "hardware off" in output or "apagado" in output:
            issues.append("- El WiFi esta apagado")
    
    except:
        pass
    
    if issues:
        return "Problemas detectados:\n" + "\n".join(issues)
    return ""
