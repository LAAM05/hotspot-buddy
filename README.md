# MyHotspot — Gestor de Punto de Acceso Wi-Fi

Aplicacion con interfaz grafica dark mode para Windows 11 que permite crear, gestionar y reparar un punto de acceso Wi-Fi (hotspot). Incluye fix especifico para el bug de ICS/DHCP de Windows 11 25H2 (Build 26200+).

## Requisitos

- Windows 10 (1903+) o Windows 11
- Python >= 3.12
- Privilegios de administrador (la app solicita elevacion UAC automaticamente)

## Instalacion

```bash
pip install -r requirements.txt
python main.py
```

## Estructura del Proyecto

```
MyHotspot/
├── main.py                 # Interfaz grafica dark mode (Tkinter)
├── hotspot_mobile.py       # Mobile Hotspot via WinRT API — RECOMENDADO
├── hotspot_python.py       # netsh wlan via subprocess nativo
├── hotspot_powershell.py   # netsh wlan via PowerShell
├── error_handler.py        # Logging, diagnostico y deteccion de builds
├── fix_hotspot.py          # Script CLI standalone (pruebas / uso sin GUI)
├── requirements.txt        # Dependencias
├── MyHotspot.spec          # Configuracion PyInstaller
└── README.md
```

## Metodos de Implementacion

### 1. Mobile Hotspot — WinRT API (Recomendado)

| Aspecto | Descripcion |
|---------|-------------|
| **API** | `Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager` |
| **Compatibilidad** | Funciona con adaptadores que NO soportan `netsh wlan start hostednetwork` |
| **Caso de uso** | **RECOMENDADO** — unico metodo funcional en Realtek 8852BE-VT y similares |
| **Requiere** | Windows 10 1903+ |

### 2. Python / PowerShell — netsh (Fallback)

| Aspecto | Descripcion |
|---------|-------------|
| **API** | `netsh wlan set/start hostednetwork` |
| **Compatibilidad** | Solo funciona si `Hosted network supported: Yes` |
| **Caso de uso** | Adaptadores Intel o drivers antiguos con soporte Hosted Network |

> La mayoria de adaptadores Realtek modernos reportan `Hosted network supported: No`.
> En ese caso el unico metodo funcional es Mobile Hotspot.

## Bug de ICS/DHCP en Windows 11 25H2 (Build 26200+)

**Sintoma:** el hotspot se activa y los dispositivos ven la red, pero no reciben IP → sin internet.

**Causa:** bug en la pila ICS de Windows 11 25H2. No es un problema de driver ni de la app.
Confirmado en HP Victus con MediaTek MT7921 y Realtek 8852BE-VT con el mismo OS Build.
`sfc /scannow` y `DISM` no detectan corrupcion porque no la hay.

**Solucion integrada:**
Tras iniciar el hotspot la app aplica automaticamente el fix. Tambien esta disponible como boton **"Reparar conectividad"** para ejecutarlo manualmente cuando el hotspot ya esta activo:

1. Forzar IP estatica `192.168.137.1/24` en el adaptador virtual Wi-Fi Direct
2. Activar `IPEnableRouter=1` en registro (necesario para que ICS enrute paquetes)
3. Fijar `ScopeAddress` en los parametros del servicio SharedAccess
4. Reiniciar servicios en orden: `icssvc` → `SharedAccess` → `Dhcp`

## Funciones Exportadas

Todos los modulos implementan la misma interfaz:

```python
def create_hotspot(ssid: str, password: str) -> tuple[bool, str]
def stop_hotspot()    -> tuple[bool, str]
def delete_hotspot()  -> tuple[bool, str]
def get_status()      -> tuple[bool, str]
def check_support()   -> tuple[bool, str]
def diagnose()        -> str
def fix_connectivity() -> tuple[bool, str]   # hotspot_mobile unicamente
```

## Solucion de Problemas

| Error | Causa | Solucion |
|-------|-------|----------|
| `Hosted network supported: No` | Driver no soporta netsh | Usar metodo **Mobile Hotspot** |
| `Access is denied` | Sin privilegios | La app pide UAC automaticamente; si falla, ejecutar como admin |
| `No hay conexion a internet` | Sin acceso WAN | Conectarse a internet antes de crear el hotspot |
| Dispositivos se conectan pero sin internet | Bug ICS Build 26200 | Pulsar **"Reparar conectividad"** |
| `Element not found / MobileBroadbandAccount` | Error antiguo ya corregido | Actualizar a la version actual |

## Modo Desarrollador

Activa el checkbox **"Modo Desarrollador"** en la GUI para ver:

- Comando exacto ejecutado (PowerShell o netsh)
- Codigo de retorno
- Salida stdout / stderr completa
- Timestamp de cada operacion

Util para diagnosticar fallos o reportar bugs.

## Generar Ejecutable

```bash
pip install pyinstaller
pyinstaller MyHotspot.spec
```

El ejecutable estara en `dist/MyHotspot.exe`. No requiere Python instalado.
