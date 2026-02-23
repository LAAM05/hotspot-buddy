import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Callable
import threading
import ctypes
import subprocess

import hotspot_powershell
import hotspot_python
import hotspot_mobile
import error_handler


class HotspotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MyHotspot - Gestor de Punto de Acceso Wi-Fi")
        self.root.geometry("650x650")
        self.root.resizable(True, True)
        self.root.minsize(580, 550)
        
        self.current_method = tk.StringVar(value="mobile")
        self.ssid_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.developer_mode = tk.BooleanVar(value=False)
        
        self._setup_ui()
        self._check_support()
    
    def _setup_ui(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10))
        style.configure("Warning.TLabel", font=("Segoe UI", 9), foreground="#D32F2F")
        style.configure("Dev.TCheckbutton", font=("Segoe UI", 9))
        style.configure("Recommended.TRadiobutton", font=("Segoe UI", 9))
        
        title_frame = ttk.Frame(self.root, padding="10")
        title_frame.pack(fill=tk.X)
        
        ttk.Label(
            title_frame, 
            text="MyHotspot", 
            style="Title.TLabel"
        ).pack(side=tk.LEFT)
        
        ttk.Label(
            title_frame, 
            text="Gestor de Punto de Acceso Wi-Fi", 
            font=("Segoe UI", 10)
        ).pack(side=tk.LEFT, padx=10)
        
        method_frame = ttk.LabelFrame(self.root, text="Metodo de implementacion", padding="10")
        method_frame.pack(fill=tk.X, padx=10, pady=5)
        
        row1_frame = ttk.Frame(method_frame)
        row1_frame.pack(fill=tk.X, pady=2)
        
        ttk.Radiobutton(
            row1_frame, 
            text="Mobile Hotspot (Recomendado) - APIs de Windows 10/11", 
            variable=self.current_method, 
            value="mobile",
            style="Recommended.TRadiobutton"
        ).pack(side=tk.LEFT, padx=5)
        
        self.mobile_recommended_label = ttk.Label(
            row1_frame,
            text="[RECOMENDADO]",
            font=("Segoe UI", 8, "bold"),
            foreground="green"
        )
        self.mobile_recommended_label.pack(side=tk.LEFT, padx=5)
        
        row2_frame = ttk.Frame(method_frame)
        row2_frame.pack(fill=tk.X, pady=2)
        
        ttk.Radiobutton(
            row2_frame, 
            text="Python (Nativo) - netsh wlan", 
            variable=self.current_method, 
            value="python"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Radiobutton(
            row2_frame, 
            text="PowerShell - netsh wlan", 
            variable=self.current_method, 
            value="powershell"
        ).pack(side=tk.LEFT, padx=5)
        
        row3_frame = ttk.Frame(method_frame)
        row3_frame.pack(fill=tk.X, pady=5)
        
        ttk.Separator(row3_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        dev_check = ttk.Checkbutton(
            row3_frame,
            text="Modo Desarrollador",
            variable=self.developer_mode,
            command=self._toggle_developer_mode,
            style="Dev.TCheckbutton"
        )
        dev_check.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            row3_frame,
            text="Abrir Hotspot de Windows",
            command=self._open_windows_hotspot_settings,
            width=22
        ).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(
            row3_frame,
            text="Diagnosticar",
            command=self._diagnose,
            width=12
        ).pack(side=tk.RIGHT, padx=5)
        
        config_frame = ttk.LabelFrame(self.root, text="Configuracion del Hotspot", padding="10")
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(config_frame, text="SSID (Nombre de red):").grid(row=0, column=0, sticky=tk.W, pady=5)
        ssid_entry = ttk.Entry(config_frame, textvariable=self.ssid_var, width=30)
        ssid_entry.grid(row=0, column=1, pady=5, padx=5)
        
        ttk.Label(config_frame, text="Contrasena:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        pwd_frame = ttk.Frame(config_frame)
        pwd_frame.grid(row=1, column=1, pady=5, padx=5, sticky=tk.W)
        
        self.pwd_entry = ttk.Entry(pwd_frame, textvariable=self.password_var, width=22, show="*")
        self.pwd_entry.pack(side=tk.LEFT)
        
        self.show_pwd_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            pwd_frame, 
            text="Mostrar", 
            variable=self.show_pwd_var,
            command=self._toggle_password
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(
            config_frame, 
            text="Minimo 8 caracteres", 
            font=("Segoe UI", 8)
        ).grid(row=2, column=1, sticky=tk.W)
        
        buttons_frame = ttk.Frame(self.root, padding="10")
        buttons_frame.pack(fill=tk.X)
        
        ttk.Button(
            buttons_frame, 
            text="Crear Hotspot", 
            command=self._create_hotspot,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            buttons_frame, 
            text="Detener", 
            command=self._stop_hotspot,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            buttons_frame, 
            text="Eliminar", 
            command=self._delete_hotspot,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            buttons_frame, 
            text="Ver Estado", 
            command=self._show_status,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        status_frame = ttk.LabelFrame(self.root, text="Estado y Mensajes", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.status_text = scrolledtext.ScrolledText(
            status_frame, 
            height=12, 
            width=70, 
            state=tk.DISABLED,
            wrap=tk.WORD,
            font=("Consolas", 9)
        )
        self.status_text.pack(fill=tk.BOTH, expand=True)
        
        info_frame = ttk.Frame(self.root, padding="5")
        info_frame.pack(fill=tk.X)
        
        self.admin_label = ttk.Label(
            info_frame, 
            text="",
            font=("Segoe UI", 9),
            foreground="gray"
        )
        self.admin_label.pack()
        
        self.dev_label = ttk.Label(
            info_frame,
            text="",
            font=("Segoe UI", 8),
            foreground="#FF6600"
        )
        self.dev_label.pack()
        
        self._check_admin_status()
        self._update_dev_label()
    
    def _toggle_password(self):
        if self.show_pwd_var.get():
            self.pwd_entry.config(show="")
        else:
            self.pwd_entry.config(show="*")
    
    def _toggle_developer_mode(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
            self.status_text.config(font=("Consolas", 8))
        else:
            error_handler.DebugLogger.disable()
            self.status_text.config(font=("Consolas", 9))
        self._update_dev_label()
    
    def _update_dev_label(self):
        if self.developer_mode.get():
            self.dev_label.config(
                text="[MODO DESARROLLADOR ACTIVO] - Se mostrara informacion tecnica detallada",
                foreground="#FF6600"
            )
        else:
            self.dev_label.config(text="", foreground="gray")
    
    def _check_admin_status(self):
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if is_admin:
                self.admin_label.config(
                    text="Ejecutando como Administrador - OK",
                    foreground="green"
                )
            else:
                self.admin_label.config(
                    text="ADVERTENCIA: No estas como Administrador. Algunas funciones fallaran.",
                    foreground="#D32F2F"
                )
        except:
            self.admin_label.config(
                text="No se pudo verificar el estado de administrador",
                foreground="orange"
            )
    
    def _open_windows_hotspot_settings(self):
        try:
            # Intento principal: abrir directamente la pagina de Hotspot movil
            subprocess.run(
                ["start", "ms-settings:network-mobilehotspot"],
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._update_status(
                "Se ha abierto la configuracion de Hotspot movil de Windows.\n\n"
                "Activa el interruptor \"Compartir mi conexion a Internet\" para crear el hotspot."
            )
        except Exception:
            try:
                # Fallback: abrir la seccion general de red
                subprocess.run(
                    ["start", "ms-settings:network-status"],
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self._update_status(
                    "No se pudo abrir directamente el Hotspot movil.\n"
                    "Se ha abierto la configuracion de red de Windows.\n\n"
                    "Desde ahi, ve a \"Hotspot movil\" y activalo manualmente."
                )
            except Exception:
                self._update_status(
                    "No se pudo abrir la configuracion de Windows.\n\n"
                    "Abre manualmente: Configuracion > Red e Internet > Hotspot movil."
                )
    
    def _get_manager(self):
        method = self.current_method.get()
        if method == "powershell":
            return hotspot_powershell
        elif method == "python":
            return hotspot_python
        else:
            return hotspot_mobile
    
    def _get_method_description(self) -> str:
        method = self.current_method.get()
        if method == "powershell":
            return "PowerShell (netsh)"
        elif method == "python":
            return "Python (netsh)"
        else:
            return "Mobile Hotspot (Windows API)"
    
    def _run_async(self, func: Callable):
        def wrapper():
            try:
                success, message = func()
                self.root.after(0, lambda: self._update_status(message))
                if not success:
                    self.root.after(0, lambda: self._show_error_dialog(message))
            except Exception as e:
                error_msg = f"Error inesperado: {str(e)}"
                self.root.after(0, lambda: self._update_status(error_msg))
                self.root.after(0, lambda: self._show_error_dialog(error_msg))
        
        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
    
    def _show_error_dialog(self, message: str):
        if self.developer_mode.get():
            width, height = 700, 500
        else:
            width, height = 550, 400
        
        error_window = tk.Toplevel(self.root)
        error_window.title("Error - Detalles")
        error_window.geometry(f"{width}x{height}")
        error_window.transient(self.root)
        error_window.grab_set()
        
        ttk.Label(
            error_window, 
            text="Ha ocurrido un error", 
            font=("Segoe UI", 12, "bold"),
            foreground="#D32F2F"
        ).pack(pady=10)
        
        text_frame = ttk.Frame(error_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        error_text = scrolledtext.ScrolledText(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 9)
        )
        error_text.pack(fill=tk.BOTH, expand=True)
        error_text.insert(tk.END, message)
        error_text.config(state=tk.DISABLED)
        
        btn_frame = ttk.Frame(error_window)
        btn_frame.pack(pady=10)
        
        ttk.Button(
            btn_frame, 
            text="Copiar al portapapeles", 
            command=lambda: self._copy_to_clipboard(message),
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame, 
            text="Cerrar", 
            command=error_window.destroy,
            width=15
        ).pack(side=tk.LEFT, padx=5)
    
    def _copy_to_clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copiado", "El mensaje ha sido copiado al portapapeles.")
    
    def _update_status(self, message: str):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.insert(tk.END, message)
        self.status_text.config(state=tk.DISABLED)
    
    def _check_support(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        
        manager = self._get_manager()
        success, message = manager.check_support()
        method_desc = self._get_method_description()
        self._update_status(f"Verificacion de compatibilidad [{method_desc}]:\n\n{message}")
    
    def _diagnose(self):
        manager = self._get_manager()
        diagnosis = manager.diagnose()
        
        if diagnosis:
            msg = f"Diagnostico del sistema:\n\n{diagnosis}\n\nEjecuta como Administrador para usar el hotspot."
        else:
            msg = "Diagnostico del sistema:\n\nNo se detectaron problemas obvios.\n\nSi el hotspot no funciona:\n1. Ejecuta como Administrador\n2. Verifica que el WiFi este encendido\n3. Cierra VPNs y firewalls temporalmente"
        
        if self.developer_mode.get():
            report = error_handler.DebugLogger.get_full_report()
            msg += f"\n\n{report}"
        
        self._update_status(msg)
    
    def _create_hotspot(self):
        ssid = self.ssid_var.get().strip()
        password = self.password_var.get().strip()
        
        if not ssid:
            messagebox.showerror("Error", "El SSID es obligatorio")
            return
        if not password:
            messagebox.showerror("Error", "La contrasena es obligatoria")
            return
        
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        
        def create():
            métodos = ["mobile", "python", "powershell"]
            metodo_seleccionado = self.current_method.get()
            
            if metodo_seleccionado in métodos:
                start_index = métodos.index(metodo_seleccionado)
                orden = métodos[start_index:] + métodos[:start_index]
            else:
                orden = métodos
            
            mensajes: list[str] = []
            exito_general = False
            
            for metodo in orden:
                if metodo == "mobile":
                    manager = hotspot_mobile
                    descripcion = "Mobile Hotspot (Windows API)"
                elif metodo == "python":
                    manager = hotspot_python
                    descripcion = "Python (netsh)"
                else:
                    manager = hotspot_powershell
                    descripcion = "PowerShell (netsh)"
                
                encabezado = f"[METODO: {descripcion}]"
                mensajes.append(encabezado)
                
                ok, msg = manager.create_hotspot(ssid, password)
                mensajes.append(msg)
                
                if ok:
                    exito_general = True
                    break
                else:
                    mensajes.append("\n--- Intentando siguiente metodo...\n")
            
            mensaje_final = f"Creando hotspot '{ssid}' con multiples metodos...\n\n" + "\n\n".join(mensajes)
            return exito_general, mensaje_final
        
        self._run_async(create)
    
    def _stop_hotspot(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        
        manager = self._get_manager()
        self._update_status("Deteniendo hotspot...")
        
        self._run_async(manager.stop_hotspot)
    
    def _delete_hotspot(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        
        manager = self._get_manager()
        self._update_status("Eliminando hotspot...")
        
        self._run_async(manager.delete_hotspot)
    
    def _show_status(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        
        manager = self._get_manager()
        self._run_async(manager.get_status)


def main():
    root = tk.Tk()
    app = HotspotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
