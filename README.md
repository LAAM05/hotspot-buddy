# MyHotspot - Gestor de Punto de Acceso Wi-Fi

Aplicacion con interfaz grafica para Windows 11 que permite crear, gestionar y eliminar un punto de acceso Wi-Fi (hotspot).

## Requisitos

- Windows 10 (1903+) o Windows 11
- Python >= 3.12
- Privilegios de administrador (recomendado)

## Instalacion

```bash
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

**Nota:** Ejecutar como administrador para permitir la gestion del hotspot.

## Estructura del Proyecto

```
MyHotspot/
├── main.py                 # Interfaz grafica (Tkinter)
├── hotspot_mobile.py       # Mobile Hotspot (Windows API) - RECOMENDADO
├── hotspot_python.py       # Implementacion nativa Python (netsh)
├── hotspot_powershell.py   # Implementacion con PowerShell (netsh)
├── error_handler.py        # Manejo de errores y modo desarrollador
├── requirements.txt        # Dependencias
├── MyHotspot.spec          # Configuracion PyInstaller
└── README.md               # Documentacion
```

## Metodos de Implementacion

### 1. Mobile Hotspot (Recomendado)

| Aspecto | Descripcion |
|---------|-------------|
| **Implementacion** | Usa `Windows.Networking.NetworkOperators` API de Windows 10/11 |
| **Compatibilidad** | Funciona con adaptadores que NO soportan `netsh wlan start hostednetwork` |
| **Ventajas** | Mas compatible, usa las mismas APIs que el Mobile Hotspot de Windows |
| **Desventajas** | Requiere Windows 10+ |
| **Caso de uso** | **RECOMENDADO** - Funciona con adaptadores Realtek modernos |

### 2. Python (Nativo)

| Aspecto | Descripcion |
|---------|-------------|
| **Implementacion** | Ejecuta `netsh wlan` directamente con `subprocess` |
| **Compatibilidad** | Solo funciona si `Hosted network supported: Yes` |
| **Ventajas** | Mas rapido, control granular |
| **Desventajas** | No funciona con muchos adaptadores Realtek modernos |
| **Caso de uso** | Adaptadores Intel, antiguos que soporten Hosted Network |

### 3. PowerShell

| Aspecto | Descripcion |
|---------|-------------|
| **Implementacion** | Ejecuta `netsh wlan` mediante `powershell.exe` |
| **Compatibilidad** | Solo funciona si `Hosted network supported: Yes` |
| **Ventajas** | Simple, sin dependencias |
| **Desventajas** | Overhead de PowerShell, misma limitacion de compatibilidad |
| **Caso de uso** | Debugging, comparacion de metodos |

## Por que mi adaptador no funciona con netsh?

```
Hosted network supported: No
```

Muchos adaptadores **Realtek** modernos (como el 8852BE-VT) NO soportan el comando `netsh wlan start hostednetwork`. Esto es una limitacion del driver, no de Windows.

**Solucion:** Usa el metodo **Mobile Hotspot** que usa APIs modernas de Windows que pueden funcionar aunque netsh no lo haga.

## Como crear el ejecutable

```bash
pip install pyinstaller
pyinstaller MyHotspot.spec
```

El ejecutable estara en `dist/MyHotspot.exe`

## Funciones Comunes

Todos los modulos implementan la misma interfaz:

```python
def create_hotspot(ssid: str, password: str) -> tuple[bool, str]
def stop_hotspot() -> tuple[bool, str]
def delete_hotspot() -> tuple[bool, str]
def get_status() -> tuple[bool, str]
def check_support() -> tuple[bool, str]
def diagnose() -> str
```

## Solucion de Problemas

| Error | Solucion |
|-------|----------|
| "Hosted network supported: No" | Usar metodo Mobile Hotspot |
| "Access is denied" | Ejecutar como administrador |
| "No hay conexion a internet" | Conectarse a internet primero |
| "The group or resource is not in the correct state" | Reiniciar adaptador WiFi o PC |

## Modo Desarrollador

Activa el checkbox "Modo Desarrollador" para ver:
- Comando exacto ejecutado
- Codigo de retorno
- Salida stdout/stderr
- Timestamp de cada operacion
- Reporte completo de la sesion

Esto ayuda a diagnosticar problemas tecnicos.
