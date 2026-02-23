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

$asTaskGeneric = (
    [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ 
        $_.Name -eq 'AsTask' -and 
        $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
    }}
)[0]

Function Await-Task($asyncOp, $resultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($resultType)
    $netTask = $asTask.Invoke($null, @($asyncOp))
    $netTask.Wait(-1) > $null
    return $netTask.Result
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
    $null = Await-Task $configOp ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringAccessPointConfiguration])
}} catch {{
    # Continuar aunque falle la configuracion
}}

$startOp = $tethering.StartTetheringAsync()
$result = Await-Task $startOp ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])

if ($result.Status -eq [Windows.Networking.NetworkOperators.TetheringOperationStatus]::Success) {{
    Write-Output "SUCCESS: Hotspot '{ssid}' iniciado correctamente"
}} else {{
    Write-Output "ERROR: $($result.Status) - $($result.AdditionalErrorMessage)"
}}
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
$result = Await-Task $stopOp ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])

if ($result.Status -eq [Windows.Networking.NetworkOperators.TetheringOperationStatus]::Success) {
    Write-Output "SUCCESS: Hotspot detenido"
} else {
    Write-Output "ERROR: $($result.Status)"
}
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
