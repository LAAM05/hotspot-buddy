import subprocess
import ctypes
import re
from typing import Optional
import error_handler
from hotspot_base import HotspotBase

# subprocess.CREATE_NO_WINDOW solo existe en Windows; en otros SO vale 0
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_command(cmd: list, step: str = "") -> tuple[int, str, str, error_handler.DebugInfo]:
    """Ejecuta un comando como lista (sin shell=True para evitar inyección de comandos)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="ignore",
            timeout=60,
        )
        debug_info = error_handler.DebugLogger.log(
            step=step,
            command=" ".join(cmd),
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return result.returncode, result.stdout, result.stderr, debug_info
    except Exception as exc:
        debug_info = error_handler.DebugLogger.log(
            step=step,
            command=" ".join(cmd),
            return_code=-1,
            stdout="",
            stderr=str(exc),
        )
        return -1, "", str(exc), debug_info

class HotspotManager(HotspotBase):
    def __init__(self):
        self._ssid: Optional[str] = None
        self._password: Optional[str] = None
        self._is_running: bool = False
        self._internet_sharing_enabled: bool = False
    
    @property
    def ssid(self) -> Optional[str]:
        return self._ssid
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    def validate_password(self, password: str) -> tuple[bool, str]:
        if len(password) < 8:
            return False, "La contraseña debe tener al menos 8 caracteres"
        if len(password) > 63:
            return False, "La contraseña no puede exceder 63 caracteres"
        # WPA2 permite caracteres ASCII imprimibles (0x20-0x7E) excepto comillas dobles
        # que romperían el comando netsh. Se permiten especiales como * ! @ # $ etc.
        if not re.match(r'^[\x20-\x7E]+$', password):
            return False, "La contraseña contiene caracteres no válidos (solo ASCII imprimible)"
        if '"' in password:
            return False, "La contraseña no puede contener comillas dobles (\") con netsh"
        return True, "Contraseña válida"
    
    def validate_ssid(self, ssid: str) -> tuple[bool, str]:
        if len(ssid) < 1 or len(ssid) > 32:
            return False, "El SSID debe tener entre 1 y 32 caracteres"
        # Verificar caracteres especiales problematicos
        invalid_chars = ['"', "'", '\\', '/', ':', '*', '?', '<', '>', '|']
        for char in invalid_chars:
            if char in ssid:
                return False, f"El SSID no puede contener el caracter '{char}'"
        return True, "SSID valido"
    
    def _check_hosted_network_support(self) -> tuple[bool, str]:
        code, out, err, _ = run_command(
            ["netsh", "wlan", "show", "drivers"], "VERIFICAR SOPORTE"
        )
        if code != 0:
            return False, "No se pudo verificar compatibilidad"

        lower = out.lower()
        # Inglés e Español
        if "hosted network supported" in lower:
            snippet = lower.split("hosted network supported")[1][:60]
            if ": yes" in snippet or ":yes" in snippet:
                return True, "Compatible"
        elif "red hospedada admitida" in lower:
            snippet = lower.split("red hospedada admitida")[1][:60]
            if ": s" in snippet:
                return True, "Compatible"

        adapter_name = ""
        for line in out.split("\n"):
            if "Interface name" in line or "Nombre de interfaz" in line:
                adapter_name = line.split(":")[-1].strip() if ":" in line else ""
                break

        return False, f"""ADAPTADOR NO COMPATIBLE
========================
Adaptador: {adapter_name if adapter_name else 'Desconocido'}

Tu adaptador WiFi NO soporta Hosted Network.
El comando netsh wlan start hostednetwork NO funcionará.

SOLUCIÓN ALTERNATIVA:
Usa el método Mobile Hotspot (WinRT) de esta aplicación,
o manualmente: Configuración > Red > Zona de conexión móvil
"""
    
    def _get_hotspot_adapter_name(self) -> Optional[str]:
        """Obtiene el nombre del adaptador virtual del hotspot."""
        code, out, err, _ = run_command(["netsh", "interface", "show", "interface"], "LIST_ADAPTERS")
        if code != 0:
            return None
        
        for line in out.split("\n"):
            # Buscar adaptadores tipo "Local Area Connection*" o "Conexión de área local*"
            if "Local Area Connection*" in line or "Conexión de área local*" in line:
                parts = line.split()
                if len(parts) >= 4:
                    return ' '.join(parts[3:])
        return None
    
    def _get_internet_adapter(self) -> Optional[str]:
        """Obtiene el nombre del adaptador con conexion a internet."""
        adapters = error_handler.get_network_adapters()
        return adapters.get('internet_adapter') or adapters.get('wifi_adapter')
    
    def _enable_internet_sharing(self) -> tuple[bool, str]:
        """Habilita el compartimiento de internet (ICS)."""
        internet_adapter = self._get_internet_adapter()
        hotspot_adapter = self._get_hotspot_adapter_name()
        
        if not internet_adapter:
            return False, "No se encontro adaptador con internet"
        
        if not hotspot_adapter:
            return False, "No se encontro adaptador del hotspot. Inicia el hotspot primero."
        
        # ICS real se habilita con el objeto COM HNetCfg.HNetShare
        # (INetSharingConfiguration.EnableSharing). Win32_NetworkAdapter NO
        # tiene ningún método EnableSharing — el enfoque WMI anterior nunca
        # compartía nada y reportaba éxito falso.
        ps_script = f'''
$ErrorActionPreference = "Continue"

try {{
    $regPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters"
    Set-ItemProperty -Path $regPath -Name "ScopeAddress"       -Value "192.168.137.1" -Force
    Set-ItemProperty -Path $regPath -Name "ScopeAddressBackup" -Value "192.168.137.1" -Force

    $hotspotAdapter = Get-NetAdapter -Name "{hotspot_adapter}" -ErrorAction SilentlyContinue
    if ($hotspotAdapter) {{
        New-NetIPAddress -InterfaceIndex $hotspotAdapter.ifIndex -IPAddress "192.168.137.1" -PrefixLength 24 -ErrorAction SilentlyContinue | Out-Null
        Set-DnsClientServerAddress -InterfaceIndex $hotspotAdapter.ifIndex -ServerAddresses ("8.8.8.8", "8.8.4.4") -ErrorAction SilentlyContinue
    }}

    $netShare = New-Object -ComObject HNetCfg.HNetShare
    $connections = @($netShare.EnumEveryConnection)

    $publicCfg = $null
    $privateCfg = $null
    foreach ($conn in $connections) {{
        $props = $netShare.NetConnectionProps.Invoke($conn)
        $cfg = $netShare.INetSharingConfigurationForINetConnection.Invoke($conn)
        if ($props.Name -eq "{internet_adapter}") {{ $publicCfg = $cfg }}
        if ($props.Name -eq "{hotspot_adapter}") {{ $privateCfg = $cfg }}
        # Deshabilitar sharing previo para evitar conflictos
        if ($cfg.SharingEnabled) {{ $cfg.DisableSharing() }}
    }}

    if ($null -eq $publicCfg)  {{ Write-Output "ERROR: No se encontro el adaptador de internet: {internet_adapter}"; return }}
    if ($null -eq $privateCfg) {{ Write-Output "ERROR: No se encontro el adaptador del hotspot: {hotspot_adapter}"; return }}

    $publicCfg.EnableSharing(0)   # ICSSHARINGTYPE_PUBLIC
    $privateCfg.EnableSharing(1)  # ICSSHARINGTYPE_PRIVATE

    Write-Output "SUCCESS: ICS configurado correctamente"
    Write-Output "InternetAdapter: {internet_adapter}"
    Write-Output "HotspotAdapter: {hotspot_adapter}"
    Write-Output "Gateway: 192.168.137.1"
}} catch {{
    Write-Output "ERROR: $($_.Exception.Message)"
    Write-Output "Configura manualmente: Panel de Control > Redes > Propiedades > Compartir"
}}
'''

        try:
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=60,
                encoding='utf-8',
                errors='ignore'
            )
            
            debug_info = error_handler.DebugLogger.log(
                step="ENABLE_ICS",
                command="PowerShell ICS script",
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr
            )
            
            if "SUCCESS" in result.stdout:
                self._internet_sharing_enabled = True
                return True, "Internet compartido exitosamente. Los dispositivos conectados tendran acceso a internet."
            
            error_msg = result.stderr if result.stderr else result.stdout
            return False, f"No se pudo compartir internet: {error_msg}\n\nLos dispositivos podran conectarse pero no tendran internet. Configura manualmente el compartimiento en las propiedades del adaptador."
        
        except subprocess.TimeoutExpired:
            return False, "Timeout al configurar compartimiento de internet"
        except Exception as e:
            return False, f"Error al configurar compartimiento: {str(e)}"
    
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
        
        # Sin internet NO se bloquea la creación (modo Connectify): el hotspot
        # se crea en modo local y los dispositivos se ven entre sí sin WAN.
        offline = not error_handler.has_internet_connection()

        self._ssid = ssid
        self._password = password
        
        code, out, err, debug_info = run_command(
            ["netsh", "wlan", "set", "hostednetwork",
             "mode=allow", f"ssid={ssid}", f"key={password}"],
            "CONFIGURAR HOTSPOT",
        )

        if code != 0:
            error_msg = err if err else out
            return False, f"Error al configurar el hotspot.\n\n{error_handler.format_error(error_msg, debug_info)}"

        code, out, err, debug_info = run_command(
            ["netsh", "wlan", "start", "hostednetwork"], "INICIAR HOTSPOT"
        )
        
        if code == 0:
            self._is_running = True

            base_msg = f"Hotspot '{ssid}' creado exitosamente."
            if offline:
                # Sin WAN no tiene sentido configurar ICS: red local solamente
                base_msg += (
                    "\n\n⚠ Modo local (sin internet): la PC no tiene conexión a internet, "
                    "así que los dispositivos podrán conectarse a la red y verse entre sí, "
                    "pero sin acceso a internet.\n"
                    "Cuando la PC recupere internet, recrea el hotspot para compartirla."
                )
            else:
                # Intentar habilitar internet sharing automaticamente
                _, sharing_msg = self._enable_internet_sharing()
                base_msg += f"\n\n{sharing_msg}"

            if error_handler.DebugLogger.is_enabled():
                return True, f"{base_msg}\n\n{error_handler.DebugLogger.get_full_report()}"
            return True, base_msg
        
        error_msg = err if err else out
        return False, f"No se pudo iniciar el hotspot.\n\n{error_handler.format_error(error_msg, debug_info)}"
    
    def stop_hotspot(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        code, out, err, debug_info = run_command(["netsh", "wlan", "stop", "hostednetwork"], "DETENER HOTSPOT")
        
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
        
        code, out, err, debug_info = run_command(
            ["netsh", "wlan", "set", "hostednetwork", "mode=disallow"], "ELIMINAR HOTSPOT"
        )
        
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
        
        code, out, err, debug_info = run_command(["netsh", "wlan", "show", "hostednetwork"], "OBTENER ESTADO")
        
        if code != 0:
            error_msg = err if err else out
            return False, error_handler.format_error(error_msg, debug_info)
        
        if error_handler.DebugLogger.is_enabled():
            return True, f"{out}\n\n{error_handler.DebugLogger.get_full_report()}"
        return True, out
    
    def check_support(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        code, out, err, debug_info = run_command(
            ["netsh", "wlan", "show", "drivers"], "VERIFICAR COMPATIBILIDAD"
        )

        if code != 0:
            return False, f"No se pudo verificar la compatibilidad.\n\n{error_handler.format_error(err if err else out, debug_info)}"

        lower = out.lower()

        adapter_name = ""
        for line in out.split("\n"):
            if "Interface name" in line or "Nombre de interfaz" in line:
                adapter_name = line.split(":")[-1].strip() if ":" in line else ""
                break

        # Inglés e Español
        is_supported = False
        if "hosted network supported" in lower:
            snippet = lower.split("hosted network supported")[1][:60]
            is_supported = ": yes" in snippet or ":yes" in snippet
        elif "red hospedada admitida" in lower:
            snippet = lower.split("red hospedada admitida")[1][:60]
            is_supported = ": s" in snippet

        if is_supported:
            admin_note = ""
            if not is_admin():
                admin_note = "\n\nADVERTENCIA: No estás ejecutando como Administrador."
            if error_handler.DebugLogger.is_enabled():
                return True, f"Adaptador COMPATIBLE.{admin_note}\n\n{error_handler.DebugLogger.get_full_report()}"
            return True, f"Tu adaptador WiFi ({adapter_name}) es COMPATIBLE con Hosted Network.{admin_note}"

        error_msg = f"""ADAPTADOR NO COMPATIBLE
================================
Adaptador: {adapter_name if adapter_name else 'Desconocido'}
Hosted Network: NO SOPORTADO

Este adaptador NO puede crear un hotspot con netsh.

SOLUCIONES ALTERNATIVAS:
1. Usa el método Mobile Hotspot (WinRT) de esta aplicación
2. Actualiza el driver WiFi desde el sitio del fabricante
3. Configuración > Red > Zona de conexión móvil (nativo Windows)
"""
        if error_handler.DebugLogger.is_enabled():
            error_msg += f"\n{error_handler.DebugLogger.get_full_report()}"
        return False, error_msg

    def diagnose(self) -> str:
        return error_handler.diagnose_network()

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
