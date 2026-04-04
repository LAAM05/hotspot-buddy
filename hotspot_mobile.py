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
            ["powershell", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
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
        """
        Ejecuta un script PowerShell con el boilerplate WinRT correcto.

        CORRECCIÓN CRÍTICA:
        - ConfigureAccessPointAsync → IAsyncAction → usar Await-Action
        - StartTetheringAsync / StopTetheringAsync → IAsyncOperation<T> → usar Await-Op
        Los dos tipos son distintos y requieren helpers distintos de AsTask.
        """
        full_script = f'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

# Helper para IAsyncOperation<T> (StartTetheringAsync, StopTetheringAsync)
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
    $_.Name -eq "AsTask" -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation``1"
}})[0]

# Helper para IAsyncAction (ConfigureAccessPointAsync)
# IAsyncAction NO tiene GetResults() — requiere su propio AsTask overload
$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
    $_.Name -eq "AsTask" -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq "IAsyncAction"
}})[0]

function Await-Op($asyncOp, $resultType) {{
    $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($asyncOp))
    if (-not $task.Wait(30000)) {{ throw "Timeout en IAsyncOperation" }}
    return $task.Result
}}

function Await-Action($asyncAction) {{
    $task = $asTaskAction.Invoke($null, @($asyncAction))
    if (-not $task.Wait(30000)) {{ throw "Timeout en IAsyncAction" }}
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

        script = '''\
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $profile) { Write-Output "NO_INTERNET"; return }

# NOTA: GetTetheringCapability(NetworkAdapterId) es para adaptadores celulares/LTE,
# NO para Wi-Fi. Lanza "MobileBroadbandAccount not found" en adaptadores Wi-Fi normales.
# El approach correcto es intentar CreateFromConnectionProfile directamente.
try {
    $tethering = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
    $config = $tethering.GetCurrentAccessPointConfiguration()
    Write-Output "SUPPORTED"
    Write-Output "State: $($tethering.TetheringOperationalState)"
    Write-Output "MaxClients: $($tethering.MaxClientCount)"
    Write-Output "CurrentSSID: $($config.Ssid)"
} catch {
    Write-Output "NOT_CAPABLE:$($_.Exception.Message)"
}
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
            result_msg = "No hay conexión a internet.\nConéctate primero."
            if full_report:
                result_msg += f"\n\n{full_report}"
            return False, result_msg

        if "NOT_CAPABLE" in msg:
            capability = msg.split("NOT_CAPABLE:")[-1].strip().split("\n")[0]
            result_msg = (
                f"Mobile Hotspot no disponible en este adaptador.\n"
                f"Capacidad: {capability}\n\n"
                "Prueba el método netsh (Python/PowerShell) o actualiza el driver WiFi."
            )
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
        
        ssid_esc = ssid.replace('"', '`"')
        pwd_esc = password.replace('"', '`"')

        script = f'''\
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $profile) {{ Write-Output "ERROR: No hay conexion a internet"; return }}

# GetTetheringCapability(NetworkAdapterId) es solo para SIM/LTE — no usar con Wi-Fi.
$tethering = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)

$config = $tethering.GetCurrentAccessPointConfiguration()
$config.Ssid = "{ssid_esc}"
$config.Passphrase = "{pwd_esc}"

# ConfigureAccessPointAsync devuelve IAsyncAction → usar Await-Action (no Await-Op)
try {{ Await-Action ($tethering.ConfigureAccessPointAsync($config)) }} catch {{}}

# Iniciar si no está ya activo
if ($tethering.TetheringOperationalState -eq [Windows.Networking.NetworkOperators.TetheringOperationalState]::On) {{
    Write-Output "SUCCESS: Hotspot ya activo"
}} else {{
    # StartTetheringAsync devuelve IAsyncOperation<NetworkOperatorTetheringOperationResult> → Await-Op
    $result = Await-Op ($tethering.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
    if ($result.Status -eq [Windows.Networking.NetworkOperators.TetheringOperationStatus]::Success) {{
        Write-Output "SUCCESS: Hotspot iniciado"
    }} else {{
        Write-Output "ERROR: $($result.Status) - $($result.AdditionalErrorMessage)"
    }}
}}
'''
        
        success, msg, debug_info = self._run_winrt_ps(script, "START_HOTSPOT")
        
        if error_handler.DebugLogger.is_enabled():
            full_report = error_handler.DebugLogger.get_full_report()
        else:
            full_report = ""
        
        if "SUCCESS" in msg:
            self._is_running = True

            # Aplicar fix de ICS/DHCP para Windows 11 Build 26200 (25H2)
            # En este build el DHCP de ICS falla silenciosamente:
            # los dispositivos ven la red pero no reciben IP → sin internet.
            fix_ok, fix_msg = self._fix_ics_routing_26200()
            already = "ya activo" in msg

            if already:
                result_msg = f"Mobile Hotspot '{ssid}' ya estaba activo."
            else:
                result_msg = f"Mobile Hotspot '{ssid}' iniciado correctamente."

            result_msg += f"\n\n{fix_msg}"
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
    
    def _fix_ics_routing_26200(self) -> tuple[bool, str]:
        """
        Workaround para el bug de ICS/DHCP en Windows 11 25H2 (Build 26200+).

        PROBLEMA (confirmado en foros HP y Microsoft):
          El Mobile Hotspot se activa y los dispositivos ven la red, pero el
          servidor DHCP de ICS falla → los dispositivos no reciben IP → sin internet.
          El bug afecta la pila de red de Windows, no los drivers.
          sfc /scannow y DISM no detectan corrupción porque no la hay.

        SOLUCIÓN:
          1. Forzar IP estática 192.168.137.1/24 en el adaptador virtual Wi-Fi Direct.
          2. Habilitar IP Forwarding en registro (IPEnableRouter=1) — clave para
             que ICS enrute paquetes entre el adaptador de internet y el virtual.
          3. Fijar parámetros de scope del servicio SharedAccess.
          4. Reiniciar icssvc → SharedAccess → Dhcp en el orden correcto.

        Se aplica siempre (no solo en Build 26200) porque no tiene efectos adversos
        en builds anteriores y garantiza la conectividad en todos los casos.
        """
        build = error_handler.get_windows_build()
        build_note = f" (Windows Build {build})" if build else ""

        script = """\
# Esperar hasta 15 s a que aparezca el adaptador virtual del Mobile Hotspot
$va = $null
$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline -and $null -eq $va) {
    foreach ($p in @("*Wi-Fi Direct*", "*Microsoft Wi-Fi Direct Virtual Adapter*")) {
        $va = Get-NetAdapter | Where-Object {
            $_.InterfaceDescription -like $p -and $_.Status -eq "Up"
        } | Select-Object -First 1
        if ($va) { break }
    }
    if ($null -eq $va) {
        $va = Get-NetAdapter | Where-Object {
            $_.Name -like "Local Area Connection*" -and $_.Status -eq "Up"
        } | Select-Object -First 1
    }
    if ($null -eq $va) { Start-Sleep -Milliseconds 500 }
}

if ($null -eq $va) { Write-Output "NO_ADAPTER"; exit }
Write-Output "ADAPTER:$($va.Name)"

# 1. IP estática 192.168.137.1/24 en el adaptador virtual (fix DHCP Build 26200)
Remove-NetIPAddress -InterfaceIndex $va.InterfaceIndex -AddressFamily IPv4 `
    -Confirm:$false -ErrorAction SilentlyContinue
New-NetIPAddress -InterfaceIndex $va.InterfaceIndex `
    -IPAddress "192.168.137.1" -PrefixLength 24 -ErrorAction SilentlyContinue | Out-Null
Set-DnsClientServerAddress -InterfaceIndex $va.InterfaceIndex `
    -ServerAddresses ("8.8.8.8", "8.8.4.4") -ErrorAction SilentlyContinue

# 2. Habilitar IP Forwarding (crítico para el routing ICS en Build 26200)
$tcpPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters"
Set-ItemProperty -Path $tcpPath -Name "IPEnableRouter" -Value 1 -Type DWord `
    -ErrorAction SilentlyContinue

# 3. Fijar parámetros de scope del servicio ICS
$icsPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters"
Set-ItemProperty -Path $icsPath -Name "ScopeAddress"       -Value "192.168.137.1" -ErrorAction SilentlyContinue
Set-ItemProperty -Path $icsPath -Name "ScopeAddressBackup" -Value "192.168.137.1" -ErrorAction SilentlyContinue

# 4. Reiniciar servicios en el orden correcto
#    icssvc (Windows Mobile Hotspot Service) debe reiniciarse ANTES que SharedAccess
Stop-Service -Name "SharedAccess" -Force -ErrorAction SilentlyContinue
Stop-Service -Name "icssvc"       -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Service -Name "icssvc"       -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Service -Name "SharedAccess" -ErrorAction SilentlyContinue
Start-Service -Name "Dhcp"         -ErrorAction SilentlyContinue

Write-Output "FIXED"
"""
        ok, out, debug_info = self._run_winrt_ps(script, "FIX_ICS_26200")
        error_handler.DebugLogger.log(
            step="FIX_ICS_26200",
            command="ICS routing fix script",
            return_code=0 if "FIXED" in out else 1,
            stdout=out,
            stderr="",
        )

        if "NO_ADAPTER" in out:
            return False, (
                f"⚠ Fix de conectividad{build_note}: no se encontró el adaptador virtual.\n"
                "El hotspot puede funcionar, pero si los dispositivos no reciben IP,\n"
                "pulsa 'Reparar conectividad' una vez que el hotspot esté activo."
            )

        adapter = ""
        for line in out.split("\n"):
            if line.startswith("ADAPTER:"):
                adapter = line.split(":", 1)[1].strip()

        if "FIXED" in out:
            return True, (
                f"✓ Fix de conectividad aplicado{build_note}.\n"
                f"  Adaptador: {adapter}\n"
                "  IP: 192.168.137.1 | IP Routing: ON | icssvc + SharedAccess reiniciados.\n"
                "Los dispositivos deberían recibir IP y tener acceso a internet."
            )

        return False, f"⚠ Fix de conectividad incompleto{build_note}:\n{out.strip()}"

    def fix_connectivity(self) -> tuple[bool, str]:
        """
        Punto de entrada público para reparar la conectividad del hotspot.
        Útil como acción manual desde la GUI cuando el hotspot está activo
        pero los dispositivos no reciben IP (bug ICS Build 26200).
        """
        error_handler.DebugLogger.clear()
        return self._fix_ics_routing_26200()

    def stop_hotspot(self) -> tuple[bool, str]:
        error_handler.DebugLogger.clear()
        
        script = '''\
$profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $profile) { Write-Output "ERROR: Sin conexion"; return }

$tethering = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)

$result = Await-Op ($tethering.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
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

def fix_connectivity() -> tuple[bool, str]:
    """
    Repara la conectividad del hotspot activo.
    Diseñado para el bug de ICS/DHCP de Windows 11 25H2 (Build 26200+)
    donde los dispositivos conectados no reciben IP.
    """
    return _manager.fix_connectivity()
