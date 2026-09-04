"""
fix_hotspot.py - Solucionador definitivo de hotspot para Windows 11
Estrategia dual: Mobile Hotspot WinRT API → netsh Hosted Network → Diagnóstico
REQUISITO: Ejecutar como Administrador (o se solicitará auto-elevación UAC)
"""
import subprocess
import sys
import time
import socket
import ctypes
import os
import argparse
import logging
from typing import Optional, Tuple

# ─── Logging ────────────────────────────────────────────────────────────────────
log_path = os.path.join(os.environ.get("TEMP", "."), "fix_hotspot.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ─── UAC Auto-elevación ──────────────────────────────────────────────────────────
def elevate_if_needed() -> None:
    """Re-lanza el proceso con privilegios de administrador vía UAC si es necesario."""
    try:
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        is_admin = False

    if not is_admin:
        print("Requiriendo permisos de administrador (UAC)...")
        params = " ".join(f'"{a}"' for a in sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        # ShellExecuteW returns > 32 on success
        if ret > 32:
            sys.exit(0)
        else:
            print(f"✗ No se pudo elevar permisos (código {ret}). Ejecuta manualmente como Administrador.")
            sys.exit(1)


# ─── Clase principal ─────────────────────────────────────────────────────────────
class HotspotFixer:
    # Flags de PowerShell para máxima compatibilidad y velocidad
    _PS_FLAGS = [
        "powershell",
        "-NonInteractive",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command",
    ]

    def __init__(self, ssid: str, password: str, host_ip: str = "192.168.137.1") -> None:
        self.ssid = ssid
        self.password = password
        self.host_ip = host_ip
        self.dns_primary = "8.8.8.8"
        self.dns_secondary = "8.8.4.4"
        self.virtual_adapter_name: Optional[str] = None
        self.virtual_adapter_guid: Optional[str] = None
        self.internet_adapter_name: Optional[str] = None
        self.internet_adapter_guid: Optional[str] = None

    # ─── Helpers de ejecución ───────────────────────────────────────────────────

    def _run(self, cmd: list, timeout: int = 30) -> Tuple[bool, str]:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            output = (r.stdout + r.stderr).strip()
            log.debug("CMD %s -> rc=%d out=%s", cmd[:3], r.returncode, output[:300])
            return r.returncode == 0, output
        except subprocess.TimeoutExpired:
            log.warning("CMD timeout: %s", cmd)
            return False, "Timeout"
        except Exception as exc:
            log.error("CMD error: %s -> %s", cmd, exc)
            return False, str(exc)

    def _ps(self, script: str, timeout: int = 60) -> Tuple[bool, str]:
        return self._run(self._PS_FLAGS + [script], timeout)

    def _sc_query(self, service: str) -> str:
        _, out = self._run(["sc", "query", service])
        return out.upper()

    # ─── Verificaciones básicas ─────────────────────────────────────────────────

    def check_internet(self) -> bool:
        """Verifica conectividad a internet con socket TCP y fallback HTTP."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except Exception:
            pass
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=5)
            return True
        except Exception:
            return False

    def check_wlan_service(self) -> bool:
        """Verifica y repara el servicio WlanSvc."""
        state = self._sc_query("WlanSvc")
        if "RUNNING" in state:
            log.info("WlanSvc activo")
            return True

        log.info("WlanSvc no está corriendo (estado: %s), intentando reparar...", state.strip())

        # Si está atascado en transición, intentar forzar parada
        if "PENDING" in state:
            self._run(["sc", "stop", "WlanSvc"])
            time.sleep(8)

        # Asegurar que el servicio esté configurado para arranque automático
        self._run(["sc", "config", "WlanSvc", "start=", "auto"])
        self._run(["sc", "start", "WlanSvc"])
        time.sleep(5)

        if "RUNNING" in self._sc_query("WlanSvc"):
            log.info("WlanSvc iniciado correctamente")
            return True

        log.error("No se pudo iniciar WlanSvc")
        return False

    def check_hosted_network_support(self) -> bool:
        """Detecta si el driver WiFi soporta Hosted Network (maneja español e inglés)."""
        _, output = self._run(["netsh", "wlan", "show", "drivers"])
        lower = output.lower()

        # Inglés: "Hosted network supported  : Yes"
        if "hosted network supported" in lower:
            idx = lower.index("hosted network supported")
            snippet = lower[idx : idx + 80]
            return ": yes" in snippet or ":yes" in snippet

        # Español: "Red hospedada admitida    : Sí"
        if "red hospedada admitida" in lower:
            idx = lower.index("red hospedada admitida")
            snippet = lower[idx : idx + 80]
            return ": s" in snippet  # "Sí" → ": sí"

        log.warning("No se encontró el campo de soporte de hosted network en la salida de drivers")
        return False

    # ─── Detección de adaptadores ───────────────────────────────────────────────

    def find_internet_adapter(self) -> bool:
        """Detecta el adaptador con acceso a internet usando dos métodos."""
        # Método 1: perfil de conexión con IPv4/IPv6 a internet
        script1 = """\
$profile = Get-NetConnectionProfile | Where-Object {
    $_.IPv4Connectivity -eq "Internet" -or $_.IPv6Connectivity -eq "Internet"
} | Select-Object -First 1
if ($profile) {
    $a = Get-NetAdapter | Where-Object {
        $_.InterfaceIndex -eq $profile.InterfaceIndex -and $_.Status -eq "Up"
    }
    if ($a) { Write-Output "$($a.Name)|$($a.InterfaceGuid)" }
}
"""
        ok, out = self._ps(script1)
        if ok and "|" in out:
            parts = out.strip().split("|")
            if len(parts) >= 2:
                self.internet_adapter_name = parts[0].strip()
                self.internet_adapter_guid = parts[1].strip()
                return True

        # Método 2: ruta por defecto (0.0.0.0/0) con menor métrica
        script2 = """\
$route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
    Sort-Object RouteMetric | Select-Object -First 1
if ($route) {
    $a = Get-NetAdapter | Where-Object {
        $_.InterfaceIndex -eq $route.InterfaceIndex -and $_.Status -eq "Up"
    }
    if ($a) { Write-Output "$($a.Name)|$($a.InterfaceGuid)" }
}
"""
        ok, out = self._ps(script2)
        if ok and "|" in out:
            parts = out.strip().split("|")
            if len(parts) >= 2:
                self.internet_adapter_name = parts[0].strip()
                self.internet_adapter_guid = parts[1].strip()
                return True

        log.warning("No se pudo detectar el adaptador con internet")
        return False

    def find_virtual_adapter(self) -> bool:
        """Detecta el adaptador virtual del hosted network."""
        script = """\
$patterns = @(
    "*Wi-Fi Direct*",
    "*Microsoft Wi-Fi Direct Virtual Adapter*",
    "*Microsoft Hosted Network Virtual Adapter*",
    "*Virtual WiFi*"
)
foreach ($p in $patterns) {
    $a = Get-NetAdapter | Where-Object {
        $_.InterfaceDescription -like $p
    } | Select-Object -First 1
    if ($a) {
        Write-Output "$($a.Name)|$($a.InterfaceGuid)"
        break
    }
}
"""
        ok, out = self._ps(script)
        if ok and "|" in out.strip():
            parts = out.strip().split("|")
            if len(parts) >= 2:
                self.virtual_adapter_name = parts[0].strip()
                self.virtual_adapter_guid = parts[1].strip()
                return True

        # Fallback: "Local Area Connection*" activos
        script2 = """\
$a = Get-NetAdapter | Where-Object {
    $_.Name -like "Local Area Connection*" -and $_.Status -eq "Up"
} | Select-Object -First 1
if ($a) { Write-Output "$($a.Name)|$($a.InterfaceGuid)" }
"""
        ok, out = self._ps(script2)
        if ok and "|" in out.strip():
            parts = out.strip().split("|")
            if len(parts) >= 2:
                self.virtual_adapter_name = parts[0].strip()
                self.virtual_adapter_guid = parts[1].strip()
                return True

        return False

    # ─── Método 1: Mobile Hotspot API (WinRT) ───────────────────────────────────

    def try_mobile_hotspot(self) -> bool:
        """
        Usa la API WinRT Windows.Networking.NetworkOperators.
        Funciona con drivers modernos (Realtek 8852BE, Intel AX, etc.)
        aunque netsh hostednetwork no esté soportado.

        CORRECCIÓN CRÍTICA: ConfigureAccessPointAsync devuelve IAsyncAction
        (no IAsyncOperation<T>), por eso se usa Await-Action separado.
        """
        print("\n[Método 1] Mobile Hotspot API (WinRT)")

        ssid_esc = self.ssid.replace('"', '`"')
        pwd_esc = self.password.replace('"', '`"')

        script = f"""\
Add-Type -AssemblyName System.Runtime.WindowsRuntime

[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null

# Helper para IAsyncOperation<T>
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
    $_.Name -eq "AsTask" -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation``1"
}})[0]

# Helper para IAsyncAction (ConfigureAccessPointAsync devuelve IAsyncAction, NO IAsyncOperation)
$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
    $_.Name -eq "AsTask" -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq "IAsyncAction"
}})[0]

function Await-Op($asyncOp, $resultType) {{
    $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($asyncOp))
    if (-not $task.Wait(30000)) {{ throw "Timeout esperando operación async" }}
    return $task.Result
}}

function Await-Action($asyncAction) {{
    $task = $asTaskAction.Invoke($null, @($asyncAction))
    if (-not $task.Wait(30000)) {{ throw "Timeout esperando acción async" }}
}}

try {{
    $profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    if ($null -eq $profile) {{ Write-Output "ERROR:NO_INTERNET"; exit }}

    # Verificar capacidad de tethering ANTES de intentar crear el manager
    $adapterId = $profile.NetworkAdapter.NetworkAdapterId
    $capability = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::GetTetheringCapability($adapterId)
    if ($capability -ne [Windows.Networking.NetworkOperators.TetheringCapability]::Enabled) {{
        Write-Output "ERROR:NOT_CAPABLE:$capability"
        exit
    }}

    $mgr = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
    if ($null -eq $mgr) {{ Write-Output "ERROR:NULL_MANAGER"; exit }}

    # Configurar SSID y contraseña
    $config = $mgr.GetCurrentAccessPointConfiguration()
    $config.Ssid = "{ssid_esc}"
    $config.Passphrase = "{pwd_esc}"

    # ConfigureAccessPointAsync → IAsyncAction → usar Await-Action
    Await-Action ($mgr.ConfigureAccessPointAsync($config))

    # Iniciar si no está ya activo
    $state = $mgr.TetheringOperationalState
    if ($state -eq [Windows.Networking.NetworkOperators.TetheringOperationalState]::On) {{
        Write-Output "SUCCESS:ALREADY_ON"
    }} else {{
        $result = Await-Op ($mgr.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        if ($result.Status -eq [Windows.Networking.NetworkOperators.TetheringOperationStatus]::Success) {{
            Write-Output "SUCCESS:STARTED"
        }} else {{
            Write-Output "ERROR:$($result.Status):$($result.AdditionalErrorMessage)"
        }}
    }}
}} catch {{
    Write-Output "ERROR:EXCEPTION:$($_.Exception.Message)"
}}
"""
        ok, out = self._ps(script, timeout=90)
        log.debug("Mobile Hotspot result: %s", out.strip())

        if "SUCCESS" in out:
            status = "ya activo" if "ALREADY_ON" in out else "iniciado"
            print(f"  ✓ Mobile Hotspot {status} (SSID: {self.ssid})")
            return True

        reason = out.strip().split("\n")[-1] if out.strip() else "desconocido"
        print(f"  ✗ Mobile Hotspot no disponible: {reason}")
        return False

    # ─── Método 2: netsh Hosted Network ─────────────────────────────────────────

    def _enable_hosted_network_adapter(self) -> bool:
        """Habilita el Microsoft Hosted Network Virtual Adapter oculto en el sistema."""
        script = r"""\
$devs = Get-PnpDevice | Where-Object {
    $_.FriendlyName -like "*Hosted Network*" -or
    $_.FriendlyName -like "*Wi-Fi Direct*"
}
$found = $false
foreach ($d in $devs) {
    $found = $true
    if ($d.Status -ne "OK") {
        Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
        Write-Output "ENABLED:$($d.FriendlyName)"
    } else {
        Write-Output "OK:$($d.FriendlyName)"
    }
}
if (-not $found) { Write-Output "NOT_FOUND" }
"""
        ok, out = self._ps(script)
        log.debug("Hosted network adapter state: %s", out.strip())
        if "NOT_FOUND" in out:
            return False
        if "ENABLED" in out:
            time.sleep(3)  # Dar tiempo al SO para registrar el adaptador
        return True

    def try_netsh_hosted_network(self) -> bool:
        """Crea el hotspot con netsh wlan (método clásico, requiere driver compatible)."""
        print("\n[Método 2] netsh Hosted Network")

        if not self.check_hosted_network_support():
            print("  ✗ Driver no soporta Hosted Network")
            return False
        print("  ✓ Driver compatible")

        # Detener red existente
        self._run(["netsh", "wlan", "stop", "hostednetwork"])
        time.sleep(1)

        # Configurar red
        ok, out = self._run([
            "netsh", "wlan", "set", "hostednetwork",
            "mode=allow",
            f"ssid={self.ssid}",
            f"key={self.password}",
            "keyUsage=persistent",
        ])
        if not ok and "successfully" not in out.lower():
            print(f"  ✗ Error configurando: {out.strip()}")
            return False
        print(f"  ✓ Configurado: SSID={self.ssid}")

        # Iniciar red
        ok, out = self._run(["netsh", "wlan", "start", "hostednetwork"])
        if ok or "already" in out.lower():
            print("  ✓ Hosted network iniciado")
            time.sleep(4)
            return True

        # Recuperación: error de estado incorrecto
        if "correct state" in out.lower() or "couldn't be started" in out.lower():
            print(f"  ⚠ Error de estado, intentando recuperación...")
            return self._recover_hosted_network()

        print(f"  ✗ No se pudo iniciar: {out.strip()}")
        return False

    def _recover_hosted_network(self) -> bool:
        """Recuperación cuando hosted network falla por estado incorrecto."""
        # Paso 1: habilitar adaptador virtual oculto
        self._enable_hosted_network_adapter()

        # Paso 2: reiniciar WlanSvc para limpiar estado corrupto
        print("  Reiniciando WlanSvc...")
        self._run(["sc", "stop", "WlanSvc"])
        time.sleep(7)
        self._run(["sc", "start", "WlanSvc"])
        time.sleep(5)

        if "RUNNING" not in self._sc_query("WlanSvc"):
            print("  ✗ WlanSvc no pudo reiniciarse")
            return False
        print("  ✓ WlanSvc reiniciado")

        # Paso 3: reconfigurar desde cero
        self._run(["netsh", "wlan", "set", "hostednetwork", "mode=disallow"])
        time.sleep(2)
        self._run([
            "netsh", "wlan", "set", "hostednetwork",
            "mode=allow",
            f"ssid={self.ssid}",
            f"key={self.password}",
            "keyUsage=persistent",
        ])
        time.sleep(2)

        # Paso 4: reintentar inicio
        ok, out = self._run(["netsh", "wlan", "start", "hostednetwork"])
        if ok or "already" in out.lower():
            print("  ✓ Hosted network recuperado")
            time.sleep(4)
            return True

        print(f"  ✗ Recuperación fallida: {out.strip()}")
        return False

    # ─── Configuración de IP e ICS ──────────────────────────────────────────────

    def configure_static_ip(self) -> bool:
        """Configura IP estática en el adaptador virtual (solo IPv4, preserva IPv6)."""
        if not self.virtual_adapter_name:
            return False

        script = f"""\
$a = Get-NetAdapter -Name "{self.virtual_adapter_name}" -ErrorAction SilentlyContinue
if ($null -eq $a) {{ Write-Output "NO_ADAPTER"; exit }}

# Verificar si ya tiene la IP correcta
$existing = Get-NetIPAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
if ($existing -and $existing.IPAddress -eq "{self.host_ip}") {{
    Write-Output "ALREADY_SET"
    exit
}}

# Remover solo IPv4 (preservar IPv6)
Remove-NetIPAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -Confirm:$false -ErrorAction SilentlyContinue
Remove-NetRoute -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -Confirm:$false -ErrorAction SilentlyContinue

New-NetIPAddress -InterfaceIndex $a.InterfaceIndex `
    -IPAddress "{self.host_ip}" -PrefixLength 24 -ErrorAction Stop | Out-Null
Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex `
    -ServerAddresses ("{self.dns_primary}", "{self.dns_secondary}") -ErrorAction SilentlyContinue
Write-Output "SUCCESS"
"""
        ok, out = self._ps(script)
        if "SUCCESS" in out or "ALREADY_SET" in out:
            status = "ya configurada" if "ALREADY_SET" in out else "configurada"
            print(f"  ✓ IP {status}: {self.host_ip} en {self.virtual_adapter_name}")
            return True

        print(f"  ⚠ IP no configurada: {out.strip()}")
        return False

    def enable_ics(self) -> bool:
        """Habilita Internet Connection Sharing (ICS) via COM (HNetCfg.HNetShare)."""
        if not self.internet_adapter_guid or not self.virtual_adapter_guid:
            log.warning("ICS: faltan GUIDs de adaptadores")
            return False

        script = f"""\
try {{
    $mgr = New-Object -ComObject HNetCfg.HNetShare
    $all = @($mgr.EnumEveryConnection)

    $internet = $null
    $virtual  = $null

    foreach ($c in $all) {{
        try {{
            $props = $mgr.NetConnectionProps($c)
            if ($props.Guid -eq "{self.internet_adapter_guid}") {{ $internet = $c }}
            if ($props.Guid -eq "{self.virtual_adapter_guid}")  {{ $virtual  = $c }}
        }} catch {{}}
    }}

    if ($null -ne $internet -and $null -ne $virtual) {{
        # Deshabilitar ICS en TODAS las conexiones primero para evitar conflictos
        foreach ($c in $all) {{
            try {{
                $cfg = $mgr.INetSharingConfigurationForINetConnection($c)
                if ($cfg.SharingEnabled) {{ $cfg.DisableSharing() }}
            }} catch {{}}
        }}
        # Habilitar: 0 = pública (origen internet), 1 = privada (destino hotspot)
        $mgr.INetSharingConfigurationForINetConnection($internet).EnableSharing(0)
        $mgr.INetSharingConfigurationForINetConnection($virtual).EnableSharing(1)
        Write-Output "ICS_ENABLED"
    }} else {{
        $foundNet = ($null -ne $internet)
        $foundVirt = ($null -ne $virtual)
        Write-Output "NOT_FOUND:internet=$foundNet,virtual=$foundVirt"
    }}
}} catch {{
    Write-Output "ERROR:$($_.Exception.Message)"
}}
"""
        ok, out = self._ps(script)
        if "ICS_ENABLED" in out:
            print("  ✓ ICS habilitado vía COM")
            return True

        print(f"  ⚠ ICS COM falló ({out.strip()}), intentando registro...")
        return self._enable_ics_via_service()

    def _enable_ics_via_service(self) -> bool:
        """Fallback: asegura que el servicio SharedAccess esté activo y configura ICS base."""
        # Asegurar que SharedAccess (servicio ICS) esté corriendo
        self._run(["sc", "config", "SharedAccess", "start=", "auto"])
        self._run(["sc", "start", "SharedAccess"])
        time.sleep(3)

        state = self._sc_query("SharedAccess")
        if "RUNNING" in state:
            print("  ✓ SharedAccess (ICS) activo vía servicio")
            return True

        print("  ✗ ICS no pudo configurarse automáticamente")
        print("  → Configura manualmente:")
        print("    Panel de control > Redes > Propiedades del adaptador con internet")
        print("    Pestaña 'Compartir' > Activar ICS > Seleccionar la red virtual")
        return False

    def restart_services(self) -> None:
        """Reinicia servicios de red para aplicar configuración."""
        self._ps("""\
Restart-Service -Name "Dhcp"          -Force -ErrorAction SilentlyContinue
Start-Service   -Name "SharedAccess"         -ErrorAction SilentlyContinue
Start-Service   -Name "DnsCache"             -ErrorAction SilentlyContinue
""")
        print("  ✓ Servicios de red reiniciados")

    # ─── Verificación final ─────────────────────────────────────────────────────

    def verify(self) -> None:
        print("\n--- Verificación final ---")

        if self.virtual_adapter_name:
            script = f"""\
$a = Get-NetAdapter -Name "{self.virtual_adapter_name}" -ErrorAction SilentlyContinue
if ($a) {{
    $ip = Get-NetIPAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
    Write-Output "STATUS:$($a.Status)"
    if ($ip) {{ Write-Output "IP:$($ip.IPAddress)" }}
}}
"""
            _, out = self._ps(script)
            if self.host_ip in out:
                print(f"  ✓ IP del hotspot: {self.host_ip}")
            else:
                print(f"  ⚠ IP pendiente: {out.strip()}")

        _, out = self._ps(
            '(Get-Service "SharedAccess" -ErrorAction SilentlyContinue).Status'
        )
        if "Running" in out:
            print("  ✓ SharedAccess (ICS): activo")

        if self.check_internet():
            print("  ✓ Conexión a internet: activa")
        else:
            print("  ⚠ Internet no detectado (puede tardar unos segundos)")

    # ─── Flujo principal ────────────────────────────────────────────────────────

    def run(self) -> None:
        print("=" * 62)
        print("  HOTSPOT-BUDDY — Solucionador Definitivo Windows 11")
        print("=" * 62)
        print(f"  SSID: {self.ssid}   |   Log: {log_path}\n")

        # Verificar internet
        if not self.check_internet():
            print("✗ ERROR: Sin conexión a internet. Conéctate primero.")
            sys.exit(1)
        print("✓ Conexión a internet verificada\n")

        # Verificar WlanSvc
        print("--- Verificando servicios de red ---")
        if not self.check_wlan_service():
            print("\n✗ SERVICIO WLAN NO DISPONIBLE")
            print("  Ejecuta desde PowerShell como Admin:")
            print("    sfc /scannow")
            print("    DISM /Online /Cleanup-Image /RestoreHealth")
            sys.exit(1)
        print("  ✓ WlanSvc activo\n")

        # Detectar adaptador con internet
        print("--- Detectando adaptadores ---")
        if self.find_internet_adapter():
            print(f"  ✓ Internet: {self.internet_adapter_name}")
        else:
            print("  ⚠ Adaptador con internet no identificado — ICS manual requerido")

        # ── Método 1: Mobile Hotspot API ──
        if self.try_mobile_hotspot():
            # En Mobile Hotspot el ICS es automático, solo verificar
            self.restart_services()
            self.verify()
            self._print_success()
            return

        # ── Método 2: netsh Hosted Network ──
        if not self.try_netsh_hosted_network():
            self._print_failure()
            sys.exit(1)

        # Configurar IP e ICS para el método netsh
        print("\n--- Buscando adaptador virtual ---")
        found = False
        for i in range(8):
            if self.find_virtual_adapter():
                print(f"  ✓ Adaptador virtual: {self.virtual_adapter_name}")
                found = True
                break
            print(f"  Esperando... ({i + 1}/8)")
            time.sleep(3)

        if found:
            print("\n--- Configurando IP estática ---")
            self.configure_static_ip()

            print("\n--- Habilitando ICS ---")
            if not self.enable_ics():
                print("  ⚠ ICS no configurado — compartir internet requerirá acción manual")

        print("\n--- Reiniciando servicios ---")
        self.restart_services()
        self.verify()
        self._print_success()

    def _print_success(self) -> None:
        print("\n" + "=" * 62)
        print("  ✓ HOTSPOT CONFIGURADO CORRECTAMENTE")
        print("=" * 62)
        print(f"  SSID:       {self.ssid}")
        print(f"  Contraseña: {self.password}")
        print(f"  Gateway:    {self.host_ip}")
        print(f"  Log:        {log_path}")
        print("=" * 62)

    def _print_failure(self) -> None:
        print("\n" + "=" * 62)
        print("  ✗ NO SE PUDO CREAR EL HOTSPOT")
        print("=" * 62)
        print("""
  Ambos métodos fallaron. Acciones recomendadas:

  1. Hotspot nativo de Windows:
     Configuración > Red e Internet > Zona de conexión móvil

  2. Actualizar driver WiFi desde el sitio del fabricante

  3. Verificar que WiFi esté encendido y no en modo avión

  4. Diagnóstico del sistema:
     sfc /scannow
     DISM /Online /Cleanup-Image /RestoreHealth
""")


# ─── CLI ─────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Solucionador definitivo de hotspot para Windows 11",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ssid",       default="LA-Victus",     help="Nombre de la red WiFi")
    parser.add_argument("--password",   default="12345678*",     help="Contraseña (mín. 8 caracteres)")
    parser.add_argument("--ip",         default="192.168.137.1", help="IP del gateway del hotspot")
    parser.add_argument("--no-elevate", action="store_true",     help="No solicitar elevación UAC")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.no_elevate:
        elevate_if_needed()

    HotspotFixer(
        ssid=args.ssid,
        password=args.password,
        host_ip=args.ip,
    ).run()
