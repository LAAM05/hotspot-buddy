import subprocess
import ctypes
import error_handler
from typing import Optional

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


class WindowsMobileHotspot:
    def __init__(self):
        self._ssid: Optional[str] = None
        self._password: Optional[str] = None
        self._is_running: bool = False
    
    def _run_winrt_ps(self, inner_script: str, step: str) -> tuple[bool, str, error_handler.DebugInfo]:
        full_script = f'''
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] > $null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] > $null
[Windows.Foundation.AsyncStatus,Windows,ContentType=WindowsRuntime] > $null

Function Await-AsyncOperation($asyncOp) {{
    $deadline = (Get-Date).AddSeconds(30)
    while ($true) {{
        $statusCode = [int]$asyncOp.Status
        switch ($statusCode) {{
            0 {{
                if ((Get-Date) -gt $deadline) {{
                    throw "Timeout esperando operacion WinRT."
                }}
                Start-Sleep -Milliseconds 120
                continue
            }}
            1 {{
                return $asyncOp.GetResults()
            }}
            2 {{
                throw "Operacion WinRT cancelada."
            }}
            3 {{
                $code = $asyncOp.ErrorCode
                throw "Operacion WinRT fallo. HRESULT: $code"
            }}
            default {{
                throw "Estado WinRT inesperado: $statusCode"
            }}
        }}
    }}
}}

try {{
    {inner_script}
}} catch {{
    Write-Output "ERROR: $($_.Exception.Message)"
}}
'''
        return run_powershell(full_script, step)
    
    def check_support(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        script = '''
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()

if ($profile -eq $null) {
    Write-Output "NO_INTERNET"
    return
}

$tethering = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
$config = $tethering.GetCurrentAccessPointConfiguration()

Write-Output "SUPPORTED"
Write-Output "State: $($tethering.TetheringOperationalState)"
Write-Output "MaxClients: $($tethering.MaxClientCount)"
Write-Output "CurrentSSID: $($config.Ssid)"
'''
        
        success, msg, debug_info = self._run_winrt_ps(script, "CHECK_SUPPORT")
        
        if error_handler.DebugLogger.is_enabled():
            full_report = error_handler.DebugLogger.get_full_report()
        else:
            full_report = ""
        
        if "SUPPORTED" in msg:
            state = "Unknown"
            max_clients = "?"
            ssid = ""
            
            for line in msg.split("\n"):
                if "State:" in line:
                    state = line.replace("State:", "").strip()
                if "MaxClients:" in line:
                    max_clients = line.replace("MaxClients:", "").strip()
                if "CurrentSSID:" in line:
                    ssid = line.replace("CurrentSSID:", "").strip()
            
            result_msg = f"Mobile Hotspot: COMPATIBLE\nEstado: {state}\nSSID actual: {ssid}\nClientes max: {max_clients}"
            if full_report:
                result_msg += f"\n\n{full_report}"
            return True, result_msg
        
        if "NO_INTERNET" in msg:
            result_msg = "No hay conexion a internet.\nConectate primero."
            if full_report:
                result_msg += f"\n\n{full_report}"
            return False, result_msg
        
        if "ERROR_WINRT_BRIDGE" in msg:
            result_msg = (
                "No fue posible usar la API Mobile Hotspot desde PowerShell en este entorno.\n\n"
                f"{msg}\n\n"
                "Puedes seguir usando los metodos netsh (Python/PowerShell) o abrir el Hotspot de Windows."
            )
            if full_report:
                result_msg += f"\n\n{full_report}"
            return False, result_msg
        
        if "ERROR" in msg:
            result_msg = f"Mobile Hotspot no disponible.\n\n{msg}\n\nIntenta usar Python o PowerShell."
            if full_report:
                result_msg += f"\n\n{full_report}"
            return False, result_msg
        
        result_msg = "No se pudo verificar soporte"
        if full_report:
            result_msg += f"\n\n{full_report}"
        return False, result_msg
    
    def create_hotspot(self, ssid: str, password: str) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        admin_warning = error_handler.check_admin_error()
        if admin_warning:
            return False, admin_warning
        
        if len(password) < 8:
            return False, "La contrasena debe tener al menos 8 caracteres"
        
        self._ssid = ssid
        self._password = password
        
        script = f'''
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()

if ($profile -eq $null) {{
    Write-Output "ERROR: No hay conexion a internet"
    return
}}

$tethering = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)

$config = $tethering.GetCurrentAccessPointConfiguration()
$config.Ssid = "{ssid}"
$config.Passphrase = "{password}"

try {{
    $configOp = $tethering.ConfigureAccessPointAsync($config)
    $null = Await-AsyncOperation $configOp
}} catch {{
    # Continuar aunque falle la configuracion
}}

$startOp = $tethering.StartTetheringAsync()
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {{
    $state = "$($tethering.TetheringOperationalState)"
    if ($state -eq "On") {{
        Write-Output "SUCCESS: Hotspot '{ssid}' iniciado correctamente"
        return
    }}
    Start-Sleep -Milliseconds 300
}}

try {{
    if ([int]$startOp.Status -eq 1) {{
        $result = $startOp.GetResults()
        if ($result.Status -eq [Windows.Networking.NetworkOperators.TetheringOperationStatus]::Success) {{
            Write-Output "SUCCESS: Hotspot '{ssid}' iniciado correctamente"
            return
        }}
        Write-Output "ERROR: $($result.Status) - $($result.AdditionalErrorMessage)"
        return
    }}
}} catch {{
    # Ignorar y devolver timeout controlado
}}

Write-Output "ERROR: Timeout esperando activacion del hotspot"
'''
        
        success, msg, debug_info = self._run_winrt_ps(script, "START_HOTSPOT")
        
        if error_handler.DebugLogger.is_enabled():
            full_report = error_handler.DebugLogger.get_full_report()
        else:
            full_report = ""
        
        if "SUCCESS" in msg:
            self._is_running = True
            result_msg = f"Mobile Hotspot '{ssid}' creado exitosamente!\n\nLa conexion a internet se compartira automaticamente."
            if full_report:
                result_msg += f"\n\n{full_report}"
            return True, result_msg
        
        if "ERROR_WINRT_BRIDGE" in msg:
            error_msg = (
                "No se pudo iniciar Mobile Hotspot con la capa WinRT de PowerShell.\n\n"
                f"{msg}\n\n"
                "Prueba con el metodo Python/PowerShell (netsh) o con el boton 'Abrir Hotspot de Windows'."
            )
            if full_report:
                error_msg += f"\n\n{full_report}"
            return False, error_msg
        
        error_msg = f"No se pudo iniciar Mobile Hotspot.\n\n{msg}"
        if full_report:
            error_msg += f"\n\n{full_report}"
        return False, error_msg
    
    def stop_hotspot(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        script = '''
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()

if ($profile -eq $null) {
    Write-Output "ERROR: No hay conexion a internet"
    return
}

$tethering = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)

$stopOp = $tethering.StopTetheringAsync()
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    $state = "$($tethering.TetheringOperationalState)"
    if ($state -eq "Off") {
        Write-Output "SUCCESS: Hotspot detenido"
        return
    }
    Start-Sleep -Milliseconds 300
}

try {
    if ([int]$stopOp.Status -eq 1) {
        $result = $stopOp.GetResults()
        if ($result.Status -eq [Windows.Networking.NetworkOperators.TetheringOperationStatus]::Success) {
            Write-Output "SUCCESS: Hotspot detenido"
            return
        }
        Write-Output "ERROR: $($result.Status)"
        return
    }
} catch {
    # Ignorar y devolver timeout controlado
}

Write-Output "ERROR: Timeout esperando apagado del hotspot"
'''
        
        success, msg, debug_info = self._run_winrt_ps(script, "STOP_HOTSPOT")
        
        if error_handler.DebugLogger.is_enabled():
            full_report = error_handler.DebugLogger.get_full_report()
        else:
            full_report = ""
        
        if "SUCCESS" in msg:
            self._is_running = False
            result_msg = "Mobile Hotspot detenido."
            if full_report:
                result_msg += f"\n\n{full_report}"
            return True, result_msg
        
        error_msg = f"No se pudo detener Mobile Hotspot.\n\n{msg}"
        if full_report:
            error_msg += f"\n\n{full_report}"
        return False, error_msg
    
    def get_status(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        script = '''
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()

if ($profile -eq $null) {
    Write-Output "ERROR: No hay conexion a internet"
    return
}

$tethering = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
$config = $tethering.GetCurrentAccessPointConfiguration()

Write-Output "Estado Mobile Hotspot:"
Write-Output "======================"
Write-Output "SSID: $($config.Ssid)"
Write-Output "Estado: $($tethering.TetheringOperationalState)"
Write-Output "Clientes: $($tethering.ClientCount) / $($tethering.MaxClientCount)"
'''
        
        success, msg, debug_info = self._run_winrt_ps(script, "GET_STATUS")
        
        if error_handler.DebugLogger.is_enabled():
            full_report = error_handler.DebugLogger.get_full_report()
        else:
            full_report = ""
        
        if "Estado Mobile Hotspot" in msg:
            if full_report:
                return True, f"{msg}\n\n{full_report}"
            return True, msg
        
        if full_report:
            return False, f"{msg}\n\n{full_report}"
        return False, msg
    
    def diagnose(self) -> str:
        return error_handler.diagnose_network()


_manager = WindowsMobileHotspot()

def create_hotspot(ssid: str, password: str) -> tuple[bool, str]:
    return _manager.create_hotspot(ssid, password)

def stop_hotspot() -> tuple[bool, str]:
    return _manager.stop_hotspot()

def delete_hotspot() -> tuple[bool, str]:
    return _manager.stop_hotspot()

def get_status() -> tuple[bool, str]:
    return _manager.get_status()

def check_support() -> tuple[bool, str]:
    return _manager.check_support()

def diagnose() -> str:
    return _manager.diagnose()
