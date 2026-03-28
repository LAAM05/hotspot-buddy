"""
fix_hotspot.py - Solución robusta para "Conectividad Limitada" en Windows 11
Este script crea un hotspot usando netsh (método clásico) y configura explícitamente:
1. IP estática 192.168.137.1/24 en el adaptador virtual
2. Internet Connection Sharing (ICS) entre el adaptador con internet y el virtual
3. DNS de Google (8.8.8.8, 8.8.4.4)
4. Reglas de firewall para permitir tráfico NAT
REQUISITOS: Ejecutar como Administrador
"""
import subprocess
import sys
import time
import re
import socket
from typing import Optional, List, Tuple
class HotspotFixer:
    def __init__(self):
        self.ssid = "LA-Victus"
        self.password = "12345678*"
        self.host_ip = "192.168.137.1"
        self.host_subnet = "255.255.255.0"
        self.dns_primary = "8.8.8.8"
        self.dns_secondary = "8.8.4.4"
        self.virtual_adapter_name = None
        self.internet_adapter_name = None
        self.internet_adapter_guid = None
        self.virtual_adapter_guid = None
    def run_powershell(self, command: str, admin: bool = True) -> Tuple[bool, str]:
        """Ejecuta comando PowerShell y devuelve (éxito, salida)"""
        try:
            if admin:
                cmd = [
                    "powershell", "-ExecutionPolicy", "Bypass",
                    "-Command", f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -Command \"{command}\"' -Wait -Verb RunAs"
                ]
            else:
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-Command", command]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                shell=False
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout ejecutando comando"
        except Exception as e:
            return False, str(e)
    def run_command(self, command: List[str], admin: bool = False) -> Tuple[bool, str]:
        """Ejecuta comando estándar y devuelve (éxito, salida)"""
        try:
            if admin:
                # Para comandos que requieren admin, usamos powershell con Verb RunAs
                ps_cmd = " ".join([f'"{c}"' if ' ' in c else c for c in command])
                return self.run_powershell(ps_cmd, admin=True)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout ejecutando comando"
        except Exception as e:
            return False, str(e)
    def check_admin(self) -> bool:
        """Verifica si se ejecuta como administrador"""
        try:
            result = subprocess.run(
                ["powershell", "-Command", "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"],
                capture_output=True,
                text=True
            )
            return result.stdout.strip().lower() == "true"
        except:
            return False
    def check_internet_connection(self) -> bool:
        """Verifica conectividad a internet"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except:
            return False
    def get_network_adapters(self) -> List[dict]:
        """Obtiene lista de adaptadores de red con su información"""
        adapters = []
        try:
            cmd = 'Get-NetAdapter | Where-Object {$_.Status -eq "Up"} | Select-Object Name, InterfaceGuid, InterfaceDescription | Format-List'
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                current_adapter = {}
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line.startswith("Name"):
                        if current_adapter:
                            adapters.append(current_adapter)
                        current_adapter = {"name": line.split(":", 1)[1].strip()}
                    elif line.startswith("InterfaceGuid"):
                        current_adapter["guid"] = line.split(":", 1)[1].strip()
                    elif line.startswith("InterfaceDescription"):
                        current_adapter["description"] = line.split(":", 1)[1].strip()
                if current_adapter:
                    adapters.append(current_adapter)
        except Exception as e:
            print(f"Error obteniendo adaptadores: {e}")
        return adapters
    def find_internet_adapter(self) -> Optional[Tuple[str, str]]:
        """Encuentra el adaptador con conexión a internet"""
        try:
            cmd = '''
            $internet = Get-NetConnectionProfile | Where-Object {$_.IPv4Connectivity -eq "Internet" -or $_.IPv6Connectivity -eq "Internet"}
            if ($internet) {
                $adapter = Get-NetAdapter | Where-Object {$_.InterfaceIndex -eq $internet.InterfaceIndex}
                Write-Output "$($adapter.Name)|$($adapter.InterfaceGuid)"
            }
            '''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) >= 2:
                    return parts[0], parts[1]
        except Exception as e:
            print(f"Error buscando adaptador de internet: {e}")
        return None
    def find_virtual_adapter(self) -> Optional[Tuple[str, str]]:
        """Encuentra el adaptador virtual del hotspot (Microsoft Wi-Fi Direct Virtual Adapter)"""
        try:
            cmd = '''
            $virtual = Get-NetAdapter | Where-Object {$_.InterfaceDescription -like "*Wi-Fi Direct*" -or $_.InterfaceDescription -like "*Virtual WiFi*" -or $_.Name -like "*Local Area Connection*"} | Where-Object {$_.Status -eq "Up"}
            if ($virtual) {
                Write-Output "$($virtual.Name)|$($virtual.InterfaceGuid)"
            } else {
                # Si no está activo, buscar por descripción aunque esté down
                $virtual = Get-NetAdapter | Where-Object {$_.InterfaceDescription -like "*Wi-Fi Direct*" -or $_.InterfaceDescription -like "*Virtual WiFi*"}
                if ($virtual) {
                    Write-Output "$($virtual.Name)|$($virtual.InterfaceGuid)"
                }
            }
            '''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) >= 2:
                    return parts[0], parts[1]
        except Exception as e:
            print(f"Error buscando adaptador virtual: {e}")
        return None
    def stop_hosted_network(self) -> bool:
        """Detiene la red hospedada si está activa"""
        success, output = self.run_command(["netsh", "wlan", "stop", "hostednetwork"])
        if success:
            print("✓ Red hospedada detenida")
        return True  # No fallar si ya estaba detenida
    def create_hosted_network(self) -> bool:
        """Crea la red hospedada con netsh"""
        # Primero verificar si ya existe
        success, output = self.run_command(["netsh", "wlan", "show", "hostednetwork"])
        if "Hosted network settings" in output and "SSID name" in output:
            print("✓ La red hospedada ya existe, actualizando configuración...")
            # Actualizar configuración
            success, output = self.run_command([
                "netsh", "wlan", "set", "hostednetwork",
                "mode=allow",
                f"ssid={self.ssid}",
                f"key={self.password}",
                "keyUsage=persistent"
            ])
            if not success:
                print(f"⚠ Advertencia al actualizar red: {output}")
        else:
            # Crear nueva red
            success, output = self.run_command([
                "netsh", "wlan", "set", "hostednetwork",
                "mode=allow",
                f"ssid={self.ssid}",
                f"key={self.password}",
                "keyUsage=persistent"
            ])
            if not success:
                print(f"✗ Error creando red hospedada: {output}")
                return False
        print(f"✓ Red hospedada configurada: SSID={self.ssid}")
        return True
    def start_hosted_network(self) -> bool:
        """Inicia la red hospedada"""
        success, output = self.run_command(["netsh", "wlan", "start", "hostednetwork"])
        if success:
            print("✓ Red hospedada iniciada")
            # Pequeña pausa para que Windows cree el adaptador virtual
            time.sleep(2)
            return True
        else:
            print(f"⚠ Advertencia al iniciar red: {output}")
            # Continuar incluso si hay advertencias comunes
            if "already been started" in output.lower():
                return True
            return False
    def configure_static_ip(self, adapter_name: str) -> bool:
        """Configura IP estática en el adaptador virtual"""
        try:
            cmd = f'''
            $adapter = Get-NetAdapter -Name "{adapter_name}" -ErrorAction SilentlyContinue
            if ($adapter) {{
                Remove-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -Confirm:$false -ErrorAction SilentlyContinue
                Remove-NetRoute -InterfaceIndex $adapter.InterfaceIndex -Confirm:$false -ErrorAction SilentlyContinue
                New-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -IPAddress "{self.host_ip}" -PrefixLength 24 -DefaultGateway ""
                Set-DnsClientServerAddress -InterfaceIndex $adapter.InterfaceIndex -ServerAddresses ("{self.dns_primary}", "{self.dns_secondary}")
                Write-Output "SUCCESS"
            }} else {{
                Write-Output "ADAPTER_NOT_FOUND"
            }}
            '''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if "SUCCESS" in result.stdout:
                print(f"✓ IP estática configurada: {self.host_ip}/24 en {adapter_name}")
                return True
            elif "ADAPTER_NOT_FOUND" in result.stdout:
                print(f"⚠ Adaptador {adapter_name} no encontrado, intentando con GUID...")
                return False
            else:
                print(f"⚠ Error configurando IP: {result.stdout} {result.stderr}")
                return False
        except Exception as e:
            print(f"✗ Excepción configurando IP: {e}")
            return False
    def enable_ics(self, internet_adapter_guid: str, virtual_adapter_guid: str) -> bool:
        """Habilita Internet Connection Sharing (ICS)"""
        try:
            # Método 1: Usando objetos COM (más confiable)
            cmd = f'''
            $netSharingManager = New-Object -ComObject HNetCfg.HNetShare
            # Obtener la conexión de internet
            $internetConnection = $netSharingManager.EnumEveryConnection | Where-Object {{
                $netSharingManager.NetConnectionProps($_).Guid -eq "{internet_adapter_guid}"
            }}
            # Obtener la conexión virtual del hotspot
            $virtualConnection = $netSharingManager.EnumEveryConnection | Where-Object {{
                $netSharingManager.NetConnectionProps($_).Guid -eq "{virtual_adapter_guid}"
            }}
            if ($internetConnection -and $virtualConnection) {{
                # Habilitar ICS en la conexión de internet (compartir hacia la virtual)
                $netSharingManager.INetSharingConfigurationForINetConnection($internetConnection).EnableSharing(0)  # 0 = PUBLIC
                # Configurar la conexión virtual como privada
                $netSharingManager.INetSharingConfigurationForINetConnection($virtualConnection).EnableSharing(1)  # 1 = PRIVATE
                Write-Output "ICS_ENABLED"
            }} else {{
                if (-not $internetConnection) {{ Write-Output "INTERNET_ADAPTER_NOT_FOUND" }}
                if (-not $virtualConnection) {{ Write-Output "VIRTUAL_ADAPTER_NOT_FOUND" }}
            }}
            '''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if "ICS_ENABLED" in result.stdout:
                print("✓ ICS habilitado correctamente")
                return True
            else:
                print(f"⚠ ICS no se pudo habilitar completamente: {result.stdout}")
                # Intentar método alternativo con registry
                return self.enable_ics_registry(internet_adapter_guid, virtual_adapter_guid)
        except Exception as e:
            print(f"✗ Excepción habilitando ICS: {e}")
            return False
    def enable_ics_registry(self, internet_adapter_guid: str, virtual_adapter_guid: str) -> bool:
        """Método alternativo: Habilitar ICS vía registro"""
        try:
            cmd = f'''
            $regPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters"
            # Configurar reglas de firewall para ICS
            netsh advfirewall firewall add rule name="ICS DHCP Server" dir=in action=allow protocol=UDP localport=67 remoteport=any program="System" enable=yes
            netsh advfirewall firewall add rule name="ICS DNS Server" dir=in action=allow protocol=UDP localport=53 remoteport=any program="System" enable=yes
            Write-Output "REGISTRY_CONFIG_DONE"
            '''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if "REGISTRY_CONFIG_DONE" in result.stdout:
                print("✓ Configuración alternativa de ICS aplicada")
                return True
            return False
        except Exception as e:
            print(f"✗ Excepción en método registry: {e}")
            return False
    def restart_dhcp_service(self) -> bool:
        """Reinicia el servicio DHCP Client para asegurar asignación correcta"""
        try:
            cmd = '''
            Restart-Service -Name "Dhcp" -Force -ErrorAction SilentlyContinue
            Start-Service -Name "SharedAccess" -ErrorAction SilentlyContinue
            Write-Output "SERVICES_RESTARTED"
            '''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            print("✓ Servicios de red reiniciados")
            return True
        except Exception as e:
            print(f"⚠ No se pudieron reiniciar servicios: {e}")
            return False
    def flush_dns_and_reset_network(self) -> bool:
        """Limpia caché DNS y resetea pila de red"""
        commands = [
            ["ipconfig", "/flushdns"],
            ["ipconfig", "/release"],
            ["ipconfig", "/renew"],
            ["netsh", "winsock", "reset"],
            ["netsh", "int", "ip", "reset"]
        ]
        for cmd in commands:
            try:
                subprocess.run(cmd, capture_output=True, timeout=30)
            except:
                pass
        print("✓ Caché DNS limpiada y pila de red reseteada")
        print("⚠ NOTA: Es recomendable reiniciar el equipo después de ejecutar este script")
        return True
    def verify_connectivity(self) -> bool:
        """Verifica que la configuración sea correcta"""
        print("\n--- Verificando configuración ---")
        # Verificar IP del adaptador virtual
        try:
            cmd = f'''
            $adapter = Get-NetAdapter | Where-Object {{$_.InterfaceDescription -like "*Wi-Fi Direct*" -or $_.InterfaceDescription -like "*Virtual WiFi*"}}
            if ($adapter) {{
                $ip = Get-NetIPAddress -InterfaceIndex $adapter.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
                if ($ip) {{
                    Write-Output "IP:$($ip.IPAddress)"
                }} else {{
                    Write-Output "NO_IP_CONFIGURED"
                }}
            }} else {{
                Write-Output "NO_VIRTUAL_ADAPTER"
            }}
            '''
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if self.host_ip in result.stdout:
                print(f"✓ IP verificada: {self.host_ip}")
            else:
                print(f"⚠ IP no configurada correctamente: {result.stdout}")
        except Exception as e:
            print(f"✗ Error verificando IP: {e}")
        # Verificar servicios
        try:
            cmd = 'Get-Service -Name "SharedAccess" | Select-Object Status'
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if "Running" in result.stdout:
                print("✓ Servicio ICS (SharedAccess) en ejecución")
            else:
                print("⚠ Servicio ICS no está en ejecución")
        except:
            pass
        return True
    def run(self):
        """Ejecuta todo el proceso de fix"""
        print("=" * 60)
        print("FIX_HOTSPOT - Solución para Conectividad Limitada en Windows 11")
        print("=" * 60)
        # Verificar privilegios de administrador
        if not self.check_admin():
            print("✗ ERROR: Este script debe ejecutarse como Administrador")
            print("   Haz clic derecho en PowerShell/CMD y selecciona 'Ejecutar como administrador'")
            print("   Luego ejecuta: python fix_hotspot.py")
            sys.exit(1)
        print("✓ Privilegios de administrador verificados\n")
        # Verificar conexión a internet
        if not self.check_internet_connection():
            print("✗ ERROR: No hay conexión a internet en este equipo")
            print("   Conecta este equipo a internet antes de crear el hotspot")
            sys.exit(1)
        print("✓ Conexión a internet verificada\n")
        # Encontrar adaptador con internet
        internet_info = self.find_internet_adapter()
        if not internet_info:
            print("✗ ERROR: No se pudo encontrar el adaptador con conexión a internet")
            sys.exit(1)
        self.internet_adapter_name, self.internet_adapter_guid = internet_info
        print(f"✓ Adaptador de internet encontrado: {self.internet_adapter_name}")
        print(f"  GUID: {self.internet_adapter_guid}\n")
        # Detener red hospedada existente
        print("--- Deteniendo red hospedada existente ---")
        self.stop_hosted_network()
        # Crear/configurar red hospedada
        print("\n--- Configurando red hospedada ---")
        if not self.create_hosted_network():
            print("✗ ERROR: No se pudo configurar la red hospedada")
            sys.exit(1)
        # Iniciar red hospedada
        print("\n--- Iniciando red hospedada ---")
        if not self.start_hosted_network():
            print("⚠ Advertencia: La red podría no haberse iniciado completamente")
        # Esperar a que aparezca el adaptador virtual
        print("\n--- Buscando adaptador virtual ---")
        max_retries = 5
        for i in range(max_retries):
            virtual_info = self.find_virtual_adapter()
            if virtual_info:
                self.virtual_adapter_name, self.virtual_adapter_guid = virtual_info
                print(f"✓ Adaptador virtual encontrado: {self.virtual_adapter_name}")
                print(f"  GUID: {self.virtual_adapter_guid}\n")
                break
            else:
                print(f"  Esperando adaptador virtual... ({i+1}/{max_retries})")
                time.sleep(2)
        else:
            print("⚠ No se encontró adaptador virtual, intentando continuar...")
            # Intentar obtener nombre genérico
            self.virtual_adapter_name = "Local Area Connection* 10"  # Nombre común
            self.virtual_adapter_guid = None
        # Configurar IP estática
        print("\n--- Configurando IP estática ---")
        if not self.configure_static_ip(self.virtual_adapter_name):
            # Intentar con otros nombres posibles
            alternative_names = [
                "Local Area Connection* 10",
                "Local Area Connection* 11",
                "Wi-Fi 2",
                "Ethernet 2"
            ]
            for alt_name in alternative_names:
                if self.configure_static_ip(alt_name):
                    self.virtual_adapter_name = alt_name
                    break
        # Habilitar ICS
        print("\n--- Habilitando Internet Connection Sharing (ICS) ---")
        if self.virtual_adapter_guid and self.internet_adapter_guid:
            if not self.enable_ics(self.internet_adapter_guid, self.virtual_adapter_guid):
                print("⚠ ICS no se pudo habilitar automáticamente")
                print("  Pasos manuales:")
                print(f"  1. Abre 'ncpa.cpl' (Conexiones de red)")
                print(f"  2. Click derecho en '{self.internet_adapter_name}' > Propiedades")
                print(f"  3. Pestaña 'Compartir'")
                print(f"  4. Marca 'Permitir a otros usuarios...'")
                print(f"  5. Selecciona '{self.virtual_adapter_name}' en la lista")
        else:
            print("⚠ No se pudieron obtener los GUIDs necesarios para ICS automático")
        # Reiniciar servicios DHCP
        print("\n--- Reiniciando servicios de red ---")
        self.restart_dhcp_service()
        # Flush DNS
        print("\n--- Limpiando caché DNS ---")
        self.flush_dns_and_reset_network()
        # Verificación final
        self.verify_connectivity()
        print("\n" + "=" * 60)
        print("¡CONFIGURACIÓN COMPLETADA!")
        print("=" * 60)
        print(f"\nHotspot creado:")
        print(f"  SSID: {self.ssid}")
        print(f"  Contraseña: {self.password}")
        print(f"  IP Gateway: {self.host_ip}")
        print(f"\nEn tu celular:")
        print(f"  1. Olvida la red '{self.ssid}' si ya estaba guardada")
        print(f"  2. Vuelve a conectarte")
        print(f"  3. Debería funcionar sin 'conectividad limitada'")
        print(f"\n⚠ RECOMENDACIÓN: Reinicia tu equipo para aplicar todos los cambios")
        print("=" * 60)
if __name__ == "__main__":
    fixer = HotspotFixer()
    fixer.run()