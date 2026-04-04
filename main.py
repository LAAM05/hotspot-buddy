"""
main.py - MyHotspot · Interfaz gráfica dark mode
Paleta: fondo negro profundo · azul oscuro · tipografía blanca
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable
import threading
import ctypes
import subprocess
import sys

import hotspot_powershell
import hotspot_python
import hotspot_mobile
import error_handler

# ─── Paleta de colores ────────────────────────────────────────────────────────
BG        = "#0B0B12"   # Fondo raíz
SURFACE   = "#101018"   # Superficie de tarjetas
SURFACE2  = "#16161F"   # Entradas, consola
BORDER    = "#1C1C2E"   # Bordes sutiles
BORDER2   = "#252535"   # Bordes en hover/focus

ACCENT    = "#1D4ED8"   # Azul principal
ACCENT_H  = "#2563EB"   # Azul hover
ACCENT_D  = "#1E3A8A"   # Azul oscuro (seleccionado)

TEXT      = "#E2E8F0"   # Texto principal
TEXT2     = "#64748B"   # Texto secundario
TEXT3     = "#94A3B8"   # Texto terciario

GREEN     = "#22C55E"   # Éxito
GREEN_D   = "#14532D"   # Fondo éxito
RED       = "#EF4444"   # Error
RED_D     = "#450A0A"   # Fondo error
YELLOW    = "#F59E0B"   # Advertencia
YELLOW_D  = "#451A03"   # Fondo advertencia

FONT      = "Segoe UI"
MONO      = "Cascadia Code" if True else "Consolas"  # Fuente consola


# ─── Helpers de widget ────────────────────────────────────────────────────────
def _flat_btn(parent: tk.Widget, text: str, command: Callable,
              bg=ACCENT, bg_h=ACCENT_H, fg=TEXT,
              font_size=9, padx=16, pady=7,
              **kwargs) -> tk.Button:
    """Botón plano con efecto hover."""
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg,
        activebackground=bg_h, activeforeground=TEXT,
        relief=tk.FLAT, bd=0, cursor="hand2",
        font=(FONT, font_size),
        padx=padx, pady=pady,
        **kwargs,
    )
    btn.bind("<Enter>", lambda _: btn.config(bg=bg_h))
    btn.bind("<Leave>", lambda _: btn.config(bg=bg))
    return btn


def _ghost_btn(parent: tk.Widget, text: str, command: Callable,
               font_size=8, **kwargs) -> tk.Button:
    """Botón fantasma (solo borde, sin fondo)."""
    return _flat_btn(
        parent, text, command,
        bg=SURFACE2, bg_h=BORDER2, fg=TEXT3,
        font_size=font_size, padx=12, pady=5,
        **kwargs,
    )


def _divider(parent: tk.Widget, side="top", pady=(0, 0)) -> tk.Frame:
    """Línea divisora de 1px."""
    d = tk.Frame(parent, bg=BORDER, height=1)
    d.pack(fill=tk.X, pady=pady)
    return d


def _label(parent: tk.Widget, text: str, size=9, color=TEXT,
           weight="normal", anchor="w", **kwargs) -> tk.Label:
    return tk.Label(
        parent, text=text, bg=parent.cget("bg"),
        fg=color, font=(FONT, size, weight),
        anchor=anchor, **kwargs,
    )


def _section_title(parent: tk.Widget, text: str) -> tk.Label:
    return _label(parent, text.upper(), size=7, color=TEXT2, weight="bold")


def _card(parent: tk.Widget, pady=(0, 8), padx=0) -> tk.Frame:
    """Tarjeta con borde sutil de 1px y fondo SURFACE."""
    wrap = tk.Frame(parent, bg=BORDER)
    wrap.pack(fill=tk.X, pady=pady, padx=padx)
    inner = tk.Frame(wrap, bg=SURFACE, padx=16, pady=12)
    inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    return inner


def _entry_field(parent: tk.Widget, variable: tk.StringVar,
                 show="", width=30) -> tuple[tk.Frame, tk.Entry]:
    """Entry con borde que cambia de color al enfocar."""
    border = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    entry = tk.Entry(
        border, textvariable=variable,
        show=show, width=width,
        bg=SURFACE2, fg=TEXT,
        insertbackground=TEXT,
        relief=tk.FLAT, bd=0,
        font=(FONT, 10),
        highlightthickness=0,
    )
    entry.pack(fill=tk.X, ipady=6, ipadx=6)
    entry.bind("<FocusIn>",  lambda _: border.config(bg=ACCENT))
    entry.bind("<FocusOut>", lambda _: border.config(bg=BORDER))
    return border, entry


class HotspotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MyHotspot")
        self.root.configure(bg=BG)
        self.root.geometry("700x740")
        self.root.resizable(True, True)
        self.root.minsize(600, 620)

        # Variables
        self.current_method = tk.StringVar(value="mobile")
        self.ssid_var       = tk.StringVar()
        self.password_var   = tk.StringVar()
        self.developer_mode = tk.BooleanVar(value=False)
        self.show_pwd_var   = tk.BooleanVar(value=False)

        self._method_btns: dict[str, tk.Button] = {}

        self._apply_ttk_style()
        self._setup_ui()
        self._check_support()

    # ─── TTK style para scrollbar ─────────────────────────────────────────────
    def _apply_ttk_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Dark.Vertical.TScrollbar",
            background=BORDER2,
            troughcolor=SURFACE2,
            arrowcolor=TEXT2,
            bordercolor=SURFACE2,
            lightcolor=SURFACE2,
            darkcolor=SURFACE2,
        )
        style.map(
            "Dark.Vertical.TScrollbar",
            background=[("active", ACCENT)],
        )

    # ─── UI principal ─────────────────────────────────────────────────────────
    def _setup_ui(self):
        # Contenedor principal con scroll horizontal
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=24, pady=18)

        self._build_header(main)
        _divider(main, pady=(10, 14))
        self._build_method_card(main)
        self._build_config_card(main)
        self._build_actions(main)
        _divider(main, pady=(12, 8))
        self._build_console(main)
        self._build_statusbar(main)

    # ─── Header ──────────────────────────────────────────────────────────────
    def _build_header(self, parent: tk.Frame):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill=tk.X)

        # Left: icono + título
        left = tk.Frame(row, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.Y)

        _label(left, "◈", size=18, color=ACCENT, weight="bold").pack(side=tk.LEFT, padx=(0, 10))

        titles = tk.Frame(left, bg=BG)
        titles.pack(side=tk.LEFT)
        _label(titles, "MyHotspot", size=17, color=TEXT, weight="bold").pack(anchor="w")
        _label(titles, "Gestor de Punto de Acceso Wi-Fi", size=9, color=TEXT2).pack(anchor="w")

        # Right: badges
        right = tk.Frame(row, bg=BG)
        right.pack(side=tk.RIGHT, anchor="center")

        self.admin_badge = tk.Label(
            right, text="", bg=GREEN_D, fg=GREEN,
            font=(FONT, 8, "bold"), padx=10, pady=3,
        )
        self.admin_badge.pack(side=tk.LEFT, padx=(0, 6))

        build = error_handler.get_windows_build()
        if build:
            if error_handler.is_affected_by_ics_bug():
                b_bg, b_fg, b_text = YELLOW_D, YELLOW, f"Build {build}  ⚠"
            else:
                b_bg, b_fg, b_text = SURFACE2, TEXT2, f"Build {build}"
            tk.Label(
                right, text=b_text, bg=b_bg, fg=b_fg,
                font=(FONT, 8), padx=10, pady=3,
            ).pack(side=tk.LEFT)

        self._check_admin_status()

    # ─── Selector de método ───────────────────────────────────────────────────
    def _build_method_card(self, parent: tk.Frame):
        _section_title(parent, "Método de conexión").pack(fill=tk.X, pady=(0, 6))
        card = _card(parent, pady=(0, 14))

        # Fila de pills (método)
        pills = tk.Frame(card, bg=SURFACE)
        pills.pack(fill=tk.X, pady=(0, 10))

        methods = [
            ("mobile",     "Mobile Hotspot",  True),
            ("python",     "Python  (netsh)", False),
            ("powershell", "PowerShell",       False),
        ]
        for value, label, recommended in methods:
            pill_text = f"  {label}  "
            if recommended:
                pill_text = f"  ★  {label}  "
            btn = tk.Button(
                pills, text=pill_text,
                command=lambda v=value: self._select_method(v),
                relief=tk.FLAT, bd=0, cursor="hand2",
                font=(FONT, 9),
                padx=6, pady=6,
            )
            btn.pack(side=tk.LEFT, padx=(0, 4))
            self._method_btns[value] = btn

        self._update_method_pills()
        self.current_method.trace_add("write", lambda *_: self._update_method_pills())

        _divider(card)

        # Fila utilitaria
        util = tk.Frame(card, bg=SURFACE)
        util.pack(fill=tk.X, pady=(10, 0))

        # Checkbox developer mode
        dev_frame = tk.Frame(util, bg=SURFACE)
        dev_frame.pack(side=tk.LEFT)
        self._dev_check = tk.Checkbutton(
            dev_frame, text="Modo Desarrollador",
            variable=self.developer_mode,
            command=self._toggle_developer_mode,
            bg=SURFACE, fg=TEXT2,
            activebackground=SURFACE, activeforeground=TEXT,
            selectcolor=BORDER2,
            font=(FONT, 8),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self._dev_check.pack(side=tk.LEFT)

        self.dev_badge = tk.Label(
            dev_frame, text="  DEV  ",
            bg=ACCENT_D, fg=ACCENT_H,
            font=(FONT, 7, "bold"),
            padx=4, pady=1,
        )
        # Se muestra solo cuando dev mode está activo

        # Botones utilitarios (derecha)
        _ghost_btn(util, "⚙  Windows Hotspot",
                   self._open_windows_hotspot_settings).pack(side=tk.RIGHT, padx=(4, 0))
        _ghost_btn(util, "Diagnosticar",
                   self._diagnose).pack(side=tk.RIGHT, padx=(4, 0))

    def _select_method(self, value: str):
        self.current_method.set(value)
        self._update_method_pills()

    def _update_method_pills(self):
        selected = self.current_method.get()
        for value, btn in self._method_btns.items():
            if value == selected:
                btn.config(bg=ACCENT, fg=TEXT, activebackground=ACCENT_H)
                btn.bind("<Enter>", lambda _, b=btn: b.config(bg=ACCENT_H))
                btn.bind("<Leave>", lambda _, b=btn: b.config(bg=ACCENT))
            else:
                btn.config(bg=SURFACE2, fg=TEXT2, activebackground=BORDER2)
                btn.bind("<Enter>", lambda _, b=btn: b.config(bg=BORDER2))
                btn.bind("<Leave>", lambda _, b=btn: b.config(bg=SURFACE2))

    # ─── Configuración ────────────────────────────────────────────────────────
    def _build_config_card(self, parent: tk.Frame):
        _section_title(parent, "Configuración").pack(fill=tk.X, pady=(0, 6))
        card = _card(parent, pady=(0, 14))

        # SSID
        ssid_row = tk.Frame(card, bg=SURFACE)
        ssid_row.pack(fill=tk.X, pady=(0, 10))

        lbl_w = 90
        _label(ssid_row, "Nombre (SSID)", size=9, color=TEXT2).pack(side=tk.LEFT, ipadx=lbl_w)

        ssid_border, _ = _entry_field(ssid_row, self.ssid_var, width=32)
        ssid_border.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Contraseña
        pwd_row = tk.Frame(card, bg=SURFACE)
        pwd_row.pack(fill=tk.X)

        _label(pwd_row, "Contraseña", size=9, color=TEXT2).pack(side=tk.LEFT, ipadx=lbl_w)

        pwd_border, self.pwd_entry = _entry_field(
            pwd_row, self.password_var, show="●", width=25
        )
        pwd_border.pack(side=tk.LEFT, fill=tk.X, expand=True)

        show_btn = _flat_btn(
            pwd_row, "Mostrar", self._toggle_password,
            bg=SURFACE2, bg_h=BORDER2, fg=TEXT2,
            font_size=8, padx=10, pady=5,
        )
        show_btn.pack(side=tk.LEFT, padx=(6, 0))

        _label(card, "Mínimo 8 caracteres  ·  caracteres especiales permitidos",
               size=7, color=TEXT2).pack(anchor="w", pady=(6, 0))

    # ─── Acciones ────────────────────────────────────────────────────────────
    def _build_actions(self, parent: tk.Frame):
        # Fila primaria
        row1 = tk.Frame(parent, bg=BG)
        row1.pack(fill=tk.X, pady=(0, 6))

        _flat_btn(row1, "Crear Hotspot",  self._create_hotspot,
                  padx=18, pady=9).pack(side=tk.LEFT, padx=(0, 6))
        _flat_btn(row1, "Detener",        self._stop_hotspot,
                  bg=SURFACE2, bg_h=BORDER2, fg=TEXT2,
                  padx=14, pady=9).pack(side=tk.LEFT, padx=(0, 6))
        _flat_btn(row1, "Eliminar",       self._delete_hotspot,
                  bg=RED_D, bg_h="#6B0606", fg=RED,
                  padx=14, pady=9).pack(side=tk.LEFT, padx=(0, 6))
        _flat_btn(row1, "Ver Estado",     self._show_status,
                  bg=SURFACE2, bg_h=BORDER2, fg=TEXT2,
                  padx=14, pady=9).pack(side=tk.LEFT)

        # Fila reparación
        row2 = tk.Frame(parent, bg=BG)
        row2.pack(fill=tk.X, pady=(0, 4))

        _flat_btn(row2, "⚡  Reparar conectividad", self._repair_connectivity,
                  bg=ACCENT_D, bg_h=ACCENT, fg=TEXT,
                  padx=16, pady=7).pack(side=tk.LEFT, padx=(0, 8))

        build = error_handler.get_windows_build()
        if error_handler.is_affected_by_ics_bug():
            tk.Label(
                row2,
                text=f"⚠  Build {build} — bug ICS/DHCP detectado.\n"
                     "Usa 'Crear Hotspot' y luego 'Reparar conectividad' si los dispositivos no tienen internet.",
                bg=BG, fg=YELLOW,
                font=(FONT, 8),
                justify=tk.LEFT,
                anchor="w",
            ).pack(side=tk.LEFT)

    # ─── Consola de salida ────────────────────────────────────────────────────
    def _build_console(self, parent: tk.Frame):
        _section_title(parent, "Consola").pack(fill=tk.X, pady=(0, 6))

        wrap = tk.Frame(parent, bg=BORDER)
        wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        inner = tk.Frame(wrap, bg=SURFACE2)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        scrollbar = ttk.Scrollbar(inner, orient=tk.VERTICAL, style="Dark.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.status_text = tk.Text(
            inner,
            bg=SURFACE2, fg=TEXT,
            insertbackground=TEXT,
            selectbackground=ACCENT_D, selectforeground=TEXT,
            relief=tk.FLAT, bd=0,
            font=(MONO, 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
            padx=12, pady=10,
            highlightthickness=0,
            cursor="arrow",
        )
        self.status_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.status_text.yview)

        # Tags de color para mensajes
        self.status_text.tag_configure("ok",      foreground=GREEN)
        self.status_text.tag_configure("error",   foreground=RED)
        self.status_text.tag_configure("warning", foreground=YELLOW)
        self.status_text.tag_configure("dim",     foreground=TEXT2)

    # ─── Barra de estado ──────────────────────────────────────────────────────
    def _build_statusbar(self, parent: tk.Frame):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill=tk.X, pady=(0, 4))

        self.dev_label = tk.Label(
            bar, text="",
            bg=ACCENT_D, fg=ACCENT_H,
            font=(FONT, 7, "bold"),
            padx=8, pady=2,
        )
        # Se muestra dinámicamente

        self.status_bar_label = tk.Label(
            bar, text="",
            bg=BG, fg=TEXT2,
            font=(FONT, 8),
            anchor="e",
        )
        self.status_bar_label.pack(side=tk.RIGHT)

    # ─── Lógica de UI ─────────────────────────────────────────────────────────
    def _toggle_password(self):
        if self.show_pwd_var.get():
            self.show_pwd_var.set(False)
            self.pwd_entry.config(show="●")
        else:
            self.show_pwd_var.set(True)
            self.pwd_entry.config(show="")

    def _toggle_developer_mode(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
            self.status_text.config(font=(MONO, 8))
            self.dev_label.config(text="  ◉  DEV MODE  ")
            self.dev_label.pack(side=tk.LEFT, padx=(0, 8))
            self.status_bar_label.config(
                text="Modo desarrollador activo — información técnica detallada habilitada"
            )
        else:
            error_handler.DebugLogger.disable()
            self.status_text.config(font=(MONO, 9))
            self.dev_label.pack_forget()
            self.status_bar_label.config(text="")

    def _check_admin_status(self):
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            if is_admin:
                self.admin_badge.config(
                    text="  ✓  Admin  ",
                    bg=GREEN_D, fg=GREEN,
                )
            else:
                self.admin_badge.config(
                    text="  ✗  Sin admin  ",
                    bg=RED_D, fg=RED,
                )
            self.admin_badge.pack(side=tk.LEFT, padx=(0, 6))
        except Exception:
            self.admin_badge.config(
                text="  ?  Admin  ",
                bg=SURFACE2, fg=TEXT2,
            )

    def _update_status(self, message: str):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        # Colorear líneas especiales
        for line in message.split("\n"):
            low = line.lower()
            if any(k in low for k in ("✓", "éxito", "iniciado", "correctamente", "compatible", "fixed", "success")):
                self.status_text.insert(tk.END, line + "\n", "ok")
            elif any(k in low for k in ("✗", "error", "fallo", "falló", "no se pudo", "crítico")):
                self.status_text.insert(tk.END, line + "\n", "error")
            elif any(k in low for k in ("⚠", "advertencia", "warning", "manual", "bug")):
                self.status_text.insert(tk.END, line + "\n", "warning")
            elif line.startswith("  ") or line.startswith("─") or line.startswith("="):
                self.status_text.insert(tk.END, line + "\n", "dim")
            else:
                self.status_text.insert(tk.END, line + "\n")
        self.status_text.config(state=tk.DISABLED)
        self.status_text.see(tk.END)

    def _open_windows_hotspot_settings(self):
        try:
            subprocess.run(
                ["start", "ms-settings:network-mobilehotspot"],
                shell=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._update_status(
                "Se abrió la configuración de Hotspot móvil de Windows.\n\n"
                "Activa 'Compartir mi conexión a Internet' para crear el hotspot."
            )
        except Exception:
            self._update_status(
                "No se pudo abrir la configuración.\n"
                "Abre manualmente: Configuración > Red e Internet > Zona de conexión móvil."
            )

    def _get_manager(self):
        method = self.current_method.get()
        if method == "powershell":
            return hotspot_powershell
        elif method == "python":
            return hotspot_python
        return hotspot_mobile

    def _get_method_description(self) -> str:
        method = self.current_method.get()
        if method == "powershell":
            return "PowerShell (netsh)"
        elif method == "python":
            return "Python (netsh)"
        return "Mobile Hotspot (Windows API)"

    def _run_async(self, func: Callable):
        def wrapper():
            try:
                success, message = func()
                self.root.after(0, lambda: self._update_status(message))
                if not success:
                    self.root.after(0, lambda: self._show_error_dialog(message))
            except Exception as exc:
                msg = f"Error inesperado: {exc}"
                self.root.after(0, lambda: self._update_status(msg))
                self.root.after(0, lambda: self._show_error_dialog(msg))
        threading.Thread(target=wrapper, daemon=True).start()

    def _show_error_dialog(self, message: str):
        win = tk.Toplevel(self.root)
        win.title("Error")
        win.configure(bg=BG)
        win.geometry("580x420")
        win.transient(self.root)
        win.grab_set()

        # Header
        h = tk.Frame(win, bg=RED_D, padx=20, pady=14)
        h.pack(fill=tk.X)
        tk.Label(h, text="✗  Ha ocurrido un error",
                 bg=RED_D, fg=RED, font=(FONT, 12, "bold")).pack(anchor="w")

        # Contenido
        c = tk.Frame(win, bg=BG, padx=16, pady=12)
        c.pack(fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(c, orient=tk.VERTICAL, style="Dark.Vertical.TScrollbar")
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        txt = tk.Text(
            c, bg=SURFACE2, fg=TEXT,
            relief=tk.FLAT, bd=0,
            font=(MONO, 9), wrap=tk.WORD,
            yscrollcommand=sb.set,
            padx=10, pady=8,
            highlightthickness=0,
        )
        txt.pack(fill=tk.BOTH, expand=True)
        sb.config(command=txt.yview)
        txt.insert(tk.END, message)
        txt.config(state=tk.DISABLED)

        # Botones
        btns = tk.Frame(win, bg=BG, pady=12)
        btns.pack(fill=tk.X, padx=16)
        _flat_btn(btns, "Copiar al portapapeles",
                  lambda: self._copy_to_clipboard(message),
                  bg=SURFACE2, bg_h=BORDER2, fg=TEXT2,
                  padx=14, pady=7).pack(side=tk.LEFT, padx=(0, 8))
        _flat_btn(btns, "Cerrar", win.destroy,
                  padx=14, pady=7).pack(side=tk.LEFT)

    def _copy_to_clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copiado", "Copiado al portapapeles.")

    # ─── Acciones del hotspot ─────────────────────────────────────────────────
    def _check_support(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        manager = self._get_manager()
        success, message = manager.check_support()
        method_desc = self._get_method_description()
        if success:
            build = error_handler.get_windows_build()
            bug_note = ""
            if error_handler.is_affected_by_ics_bug():
                bug_note = (
                    f"\n\n⚠  Windows Build {build} (25H2) — bug ICS/DHCP conocido.\n"
                    "El hotspot se activa pero los dispositivos pueden no recibir IP.\n"
                    "→  Usa 'Crear Hotspot' y luego 'Reparar conectividad' si no hay internet."
                )
            self._update_status(
                f"Verificación de compatibilidad  [{method_desc}]\n\n{message}{bug_note}"
            )
            return
        if self.current_method.get() == "mobile" and "ERROR_WINRT_BRIDGE" in message:
            results = [f"Verificación [{method_desc}]\n\n{message}"]
            for fb_val, fb_desc, fb_mgr in [
                ("python",     "Python (netsh)",     hotspot_python),
                ("powershell", "PowerShell (netsh)", hotspot_powershell),
            ]:
                ok, fb_msg = fb_mgr.check_support()
                results.append(f"\n\nVerificación [{fb_desc}]\n\n{fb_msg}")
                if ok:
                    self.current_method.set(fb_val)
                    self._update_method_pills()
                    results.append(f"\n\n→  Método cambiado a [{fb_desc}] automáticamente.")
                    break
            self._update_status("".join(results))
            return
        self._update_status(f"Verificación [{method_desc}]\n\n{message}")

    def _diagnose(self):
        manager = self._get_manager()
        diagnosis = manager.diagnose()
        if diagnosis:
            msg = f"Diagnóstico del sistema:\n\n{diagnosis}"
        else:
            msg = (
                "Diagnóstico del sistema:\n\n"
                "✓  No se detectaron problemas obvios.\n\n"
                "Si el hotspot no funciona:\n"
                "  1.  Ejecuta como Administrador\n"
                "  2.  Verifica que el WiFi esté encendido\n"
                "  3.  Cierra VPNs y firewalls temporalmente\n"
                "  4.  Usa 'Reparar conectividad' si el hotspot está activo pero sin internet"
            )
        if self.developer_mode.get():
            msg += f"\n\n{error_handler.DebugLogger.get_full_report()}"
        self._update_status(msg)

    def _create_hotspot(self):
        ssid     = self.ssid_var.get().strip()
        password = self.password_var.get().strip()
        if not ssid:
            messagebox.showerror("Campo requerido", "El nombre de red (SSID) es obligatorio.")
            return
        if not password:
            messagebox.showerror("Campo requerido", "La contraseña es obligatoria.")
            return
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()

        self._update_status(f"Creando hotspot '{ssid}'...")

        def create():
            methods_order = ["mobile", "python", "powershell"]
            sel = self.current_method.get()
            idx = methods_order.index(sel) if sel in methods_order else 0
            ordered = methods_order[idx:] + methods_order[:idx]

            log: list[str] = []
            for m in ordered:
                mgr   = {"mobile": hotspot_mobile, "python": hotspot_python,
                          "powershell": hotspot_powershell}[m]
                desc  = {"mobile": "Mobile Hotspot (API)",
                          "python": "Python (netsh)",
                          "powershell": "PowerShell (netsh)"}[m]
                log.append(f"[ {desc} ]")
                ok, msg = mgr.create_hotspot(ssid, password)
                log.append(msg)
                if ok:
                    return True, "\n\n".join(log)
                log.append("─── Probando siguiente método...\n")
            return False, "\n\n".join(log)

        self._run_async(create)

    def _stop_hotspot(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        self._update_status("Deteniendo hotspot...")
        self._run_async(self._get_manager().stop_hotspot)

    def _delete_hotspot(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        self._update_status("Eliminando hotspot...")
        self._run_async(self._get_manager().delete_hotspot)

    def _show_status(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        self._run_async(self._get_manager().get_status)

    def _repair_connectivity(self):
        if self.developer_mode.get():
            error_handler.DebugLogger.enable()
        if self.current_method.get() != "mobile":
            self._update_status(
                "⚠  Reparar conectividad requiere el método Mobile Hotspot.\n\n"
                "Selecciona 'Mobile Hotspot' en el selector de método e intenta de nuevo."
            )
            return
        build = error_handler.get_windows_build()
        self._update_status(
            f"Reparando conectividad  (Windows Build {build})...\n\n"
            "  ·  Forzando IP 192.168.137.1 en el adaptador virtual\n"
            "  ·  Habilitando IP Forwarding en registro\n"
            "  ·  Reiniciando icssvc → SharedAccess → DHCP\n\n"
            "Espera unos segundos..."
        )
        self._run_async(hotspot_mobile.fix_connectivity)


# ─── Arranque ──────────────────────────────────────────────────────────────────
def _elevate_if_needed() -> None:
    try:
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        is_admin = False
    if not is_admin:
        params = " ".join(f'"{a}"' for a in sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        if ret > 32:
            sys.exit(0)


def main():
    _elevate_if_needed()
    root = tk.Tk()
    HotspotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
