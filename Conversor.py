"""Conversor YouTube — descarga videos y Shorts de YouTube en MP3 o MP4."""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading

# Solo en desarrollo: algunos venv de Python 3.13 en Windows no encuentran Tcl/Tk.
if not getattr(sys, "frozen", False) and "TCL_LIBRARY" not in os.environ:
    _tcl = os.path.join(sys.base_prefix, "tcl")
    if os.path.isdir(os.path.join(_tcl, "tcl8.6")):
        os.environ["TCL_LIBRARY"] = os.path.join(_tcl, "tcl8.6")
        os.environ["TK_LIBRARY"] = os.path.join(_tcl, "tk8.6")

import tkinter as tk
from tkinter import filedialog, ttk

import yt_dlp

APP_NOMBRE = "Conversor YouTube"
CALIDADES = ["Máxima", "1080p", "720p", "480p", "360p"]
PATRON_YT = re.compile(r"(youtube\.com|youtu\.be|music\.youtube\.com)/", re.I)

# Colores (modo oscuro minimalista)
FONDO = "#151517"        # fondo de la ventana
CAMPO = "#1f1f23"        # cajas de texto y listas
BOTON = "#26262b"        # botones secundarios
BOTON_HOVER = "#303036"
BORDE = "#34343a"
TEXTO = "#ececf0"
SUAVE = "#8b8b95"
APAGADO = "#4a4a52"
ACENTO = "#e5322d"
ACENTO_HOVER = "#f04a44"
ACENTO_APAGADO = "#5a2321"


# ───────────────────────── Rutas y configuración ─────────────────────────

def carpeta_de_la_app():
    """Carpeta del .exe (empaquetado) o del .py (desarrollo), sin depender del cwd."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ruta_recurso(nombre):
    """Archivos metidos DENTRO del .exe (como el icono) se extraen en sys._MEIPASS."""
    base = getattr(sys, "_MEIPASS", carpeta_de_la_app())
    return os.path.join(base, nombre)


def buscar_ffmpeg():
    """Devuelve la carpeta de FFmpeg junto a la app, o None si está en el PATH / no existe."""
    local = os.path.join(carpeta_de_la_app(), "ffmpeg")
    if os.path.isfile(os.path.join(local, "ffmpeg.exe")) or os.path.isfile(os.path.join(local, "ffmpeg")):
        return local
    return None


def ffmpeg_disponible():
    return buscar_ffmpeg() is not None or shutil.which("ffmpeg") is not None


def buscar_deno():
    for nombre in ("deno.exe", "deno"):
        ruta = os.path.join(carpeta_de_la_app(), "deno", nombre)
        if os.path.isfile(ruta):
            return ruta
    return None


def ruta_config():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ConversorYoutube", "config.json")


def cargar_config():
    try:
        with open(ruta_config(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_config(datos):
    try:
        os.makedirs(os.path.dirname(ruta_config()), exist_ok=True)
        with open(ruta_config(), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # no es crítico


def carpeta_descargas():
    ruta = os.path.join(os.path.expanduser("~"), "Downloads")
    return ruta if os.path.isdir(ruta) else os.path.expanduser("~")


# ───────────────────────── Lógica de descarga ─────────────────────────

class Cancelado(Exception):
    pass


def opciones_descarga(formato, calidad, destino, hook_progreso, hook_post):
    opts = {
        # Nombre de archivo limitado para evitar rutas demasiado largas en Windows
        "outtmpl": os.path.join(destino, "%(title).150B.%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,              # un enlace con &list= descarga solo ese video
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "progress_hooks": [hook_progreso],
        "postprocessor_hooks": [hook_post],
    }

    ffmpeg = buscar_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg

    deno = buscar_deno()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}

    if formato == "mp3":
        opts.update({
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"},
            ],
        })
    else:
        # 'res' usa el lado más corto del video, así 1080p funciona igual
        # para videos horizontales y para Shorts verticales.
        # Se prefiere H.264 + AAC para que el MP4 se reproduzca en cualquier lado.
        orden = ["vcodec:h264", "acodec:aac"]
        if calidad != "Máxima":
            orden.insert(0, "res:" + calidad.rstrip("p"))
        else:
            orden.insert(0, "res")
        opts.update({
            "format": "bv*+ba/b",
            "format_sort": orden,
            "merge_output_format": "mp4",
        })
    return opts


def mensaje_de_error(exc):
    texto = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).replace("ERROR: ", "").strip()
    bajo = texto.lower()
    if "unsupported url" in bajo or "is not a valid url" in bajo:
        return "El enlace no es válido."
    if "private video" in bajo:
        return "El video es privado."
    if "video unavailable" in bajo:
        return "El video no está disponible."
    if "sign in to confirm your age" in bajo:
        return "El video tiene restricción de edad."
    if "ffmpeg" in bajo and "not found" in bajo:
        return "No se encontró FFmpeg."
    if "getaddrinfo" in bajo or "timed out" in bajo or "connection" in bajo:
        return "Sin conexión a Internet."
    primera = texto.splitlines()[0] if texto else "Error desconocido."
    return primera[:160]


# ───────────────────────── Interfaz ─────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NOMBRE)
        self.configure(bg=FONDO, padx=22, pady=18)
        self.resizable(False, False)
        try:
            self.iconbitmap(default=ruta_recurso("icono.ico"))  # icono de la ventana y la barra de tareas
        except tk.TclError:
            pass  # en Linux/macOS los .ico no siempre son compatibles

        self.config_app = cargar_config()
        self.cola = queue.Queue()
        self.cancelar = threading.Event()
        self.descargando = False
        self.ultimo_url = ""   # para no volver a autopegar el enlace ya descargado

        self.url = tk.StringVar()
        self.formato = tk.StringVar(value=self.config_app.get("formato", "mp4"))
        self.calidad = tk.StringVar(value=self.config_app.get("calidad", "1080p"))
        destino = self.config_app.get("destino")
        self.destino = tk.StringVar(value=destino if destino and os.path.isdir(destino) else carpeta_descargas())
        self.estado = tk.StringVar(value="Pega un enlace de YouTube o de un Short.")

        self._estilos()
        self._construir()
        self._titulo_oscuro()
        self._centrar()

        self.bind("<Return>", lambda e: self.accion_principal())
        self.bind("<FocusIn>", self._autopegar)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.after(100, self._leer_cola)

    # ── estilos ──
    def _estilos(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        fuente = ("Segoe UI", 10)
        st.configure(".", background=FONDO, foreground=TEXTO, font=fuente,
                     selectbackground=ACENTO, selectforeground="#ffffff",
                     insertcolor=TEXTO, troughcolor=CAMPO)
        st.configure("TFrame", background=FONDO)
        st.configure("TLabel", background=FONDO, foreground=TEXTO)
        st.configure("Titulo.TLabel", font=("Segoe UI Semibold", 15))
        st.configure("Suave.TLabel", foreground=SUAVE, font=("Segoe UI", 9))

        st.configure("TEntry", fieldbackground=CAMPO, foreground=TEXTO, insertcolor=TEXTO,
                     bordercolor=BORDE, lightcolor=CAMPO, darkcolor=CAMPO, padding=7)
        st.map("TEntry", bordercolor=[("focus", ACENTO)], lightcolor=[("focus", ACENTO)])

        st.configure("TButton", background=BOTON, foreground=TEXTO, bordercolor=BORDE,
                     lightcolor=BOTON, darkcolor=BOTON, focuscolor=BOTON,
                     padding=(10, 6), relief="flat")
        st.map("TButton", background=[("pressed", BORDE), ("active", BOTON_HOVER)],
               lightcolor=[("active", BOTON_HOVER)], darkcolor=[("active", BOTON_HOVER)])

        st.configure("Acento.TButton", background=ACENTO, foreground="#ffffff",
                     bordercolor=ACENTO, lightcolor=ACENTO, darkcolor=ACENTO, focuscolor=ACENTO,
                     font=("Segoe UI Semibold", 10), padding=(10, 9))
        st.map("Acento.TButton",
               background=[("disabled", ACENTO_APAGADO), ("active", ACENTO_HOVER)],
               lightcolor=[("disabled", ACENTO_APAGADO), ("active", ACENTO_HOVER)],
               darkcolor=[("disabled", ACENTO_APAGADO), ("active", ACENTO_HOVER)],
               bordercolor=[("disabled", ACENTO_APAGADO), ("active", ACENTO_HOVER)],
               foreground=[("disabled", SUAVE)])

        st.configure("Seg.Toolbutton", background=BOTON, foreground=SUAVE, bordercolor=BORDE,
                     lightcolor=BOTON, darkcolor=BOTON, focuscolor=BOTON,
                     padding=(18, 6), anchor="center")
        st.map("Seg.Toolbutton",
               background=[("selected", TEXTO), ("active", BOTON_HOVER)],
               foreground=[("selected", FONDO), ("active", TEXTO)],
               lightcolor=[("selected", TEXTO)], darkcolor=[("selected", TEXTO)],
               focuscolor=[("selected", TEXTO)])

        st.configure("TCombobox", fieldbackground=CAMPO, background=BOTON, foreground=TEXTO,
                     bordercolor=BORDE, lightcolor=CAMPO, darkcolor=CAMPO, arrowcolor=SUAVE,
                     selectbackground=CAMPO, selectforeground=TEXTO, padding=5)
        st.map("TCombobox",
               fieldbackground=[("disabled", FONDO), ("readonly", CAMPO)],
               foreground=[("disabled", APAGADO)],
               arrowcolor=[("disabled", APAGADO)],
               background=[("disabled", FONDO), ("active", BOTON_HOVER)],
               selectbackground=[("readonly", CAMPO)], selectforeground=[("readonly", TEXTO)])
        # Lista desplegable del combobox (es un widget clásico de Tk)
        self.option_add("*TCombobox*Listbox.background", CAMPO)
        self.option_add("*TCombobox*Listbox.foreground", TEXTO)
        self.option_add("*TCombobox*Listbox.selectBackground", ACENTO)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.font", fuente)

        st.configure("Horizontal.TProgressbar", troughcolor=CAMPO, background=ACENTO,
                     bordercolor=CAMPO, lightcolor=ACENTO, darkcolor=ACENTO, thickness=6)

    # ── widgets ──
    def _construir(self):
        ancho = 400

        ttk.Label(self, text=APP_NOMBRE, style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, text="MP3 y MP4 · videos y Shorts", style="Suave.TLabel").pack(anchor="w", pady=(0, 14))

        # Enlace
        fila = ttk.Frame(self)
        fila.pack(fill="x")
        self.entrada = ttk.Entry(fila, textvariable=self.url, width=38)
        self.entrada.pack(side="left", fill="x", expand=True)
        ttk.Button(fila, text="Pegar", command=self.pegar).pack(side="left", padx=(8, 0))

        # Formato + calidad
        fila = ttk.Frame(self)
        fila.pack(fill="x", pady=(12, 0))
        for valor, texto in (("mp3", "MP3"), ("mp4", "MP4")):
            ttk.Radiobutton(fila, text=texto, value=valor, variable=self.formato,
                            style="Seg.Toolbutton", command=self._actualizar_calidad).pack(side="left")
        self.combo = ttk.Combobox(fila, textvariable=self.calidad, values=CALIDADES,
                                  state="readonly", width=9)
        self.combo.pack(side="right")
        self.lbl_calidad = ttk.Label(fila, text="Calidad", style="Suave.TLabel")
        self.lbl_calidad.pack(side="right", padx=(0, 8))

        # Carpeta de destino
        fila = ttk.Frame(self)
        fila.pack(fill="x", pady=(12, 0))
        self.lbl_destino = ttk.Label(fila, style="Suave.TLabel", width=44, anchor="w")
        self.lbl_destino.pack(side="left", fill="x", expand=True)
        ttk.Button(fila, text="Carpeta…", command=self.elegir_carpeta).pack(side="right")
        self._mostrar_destino()

        # Botón principal
        self.boton = ttk.Button(self, text="Descargar", style="Acento.TButton", command=self.accion_principal)
        self.boton.pack(fill="x", pady=(16, 10))

        # Progreso y estado
        self.barra = ttk.Progressbar(self, length=ancho, mode="determinate", maximum=100)
        self.barra.pack(fill="x")
        fila = ttk.Frame(self)
        fila.pack(fill="x", pady=(6, 0))
        ttk.Label(fila, textvariable=self.estado, style="Suave.TLabel",
                  wraplength=310, justify="left").pack(side="left", fill="x", expand=True)
        self.btn_abrir = ttk.Button(fila, text="Abrir carpeta", command=self.abrir_carpeta)

        self._actualizar_calidad()
        self.entrada.focus_set()

    def _titulo_oscuro(self):
        # Barra de título oscura en Windows 10 (20H1+) y Windows 11
        if sys.platform != "win32":
            return
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            valor = ctypes.c_int(1)
            for atributo in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (nuevo y antiguo)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor)) == 0:
                    break
        except Exception:  # noqa: BLE001
            pass

    def _centrar(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"+{x}+{y}")

    # ── acciones ──
    def _actualizar_calidad(self):
        es_mp4 = self.formato.get() == "mp4"
        self.combo.configure(state="readonly" if es_mp4 else "disabled")
        self.lbl_calidad.configure(foreground=SUAVE if es_mp4 else APAGADO)

    def _mostrar_destino(self):
        ruta = self.destino.get()
        corta = ruta if len(ruta) <= 48 else "…" + ruta[-47:]
        self.lbl_destino.configure(text="Guardar en: " + corta)

    def pegar(self):
        try:
            self.url.set(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def _autopegar(self, _evento=None):
        # Si el campo está vacío y hay un enlace de YouTube copiado, lo pega solo.
        if self.descargando or self.url.get().strip():
            return
        try:
            texto = self.clipboard_get().strip()
        except tk.TclError:
            return
        if PATRON_YT.search(texto) and "\n" not in texto and texto != self.ultimo_url:
            self.url.set(texto)

    def elegir_carpeta(self):
        ruta = filedialog.askdirectory(title="Elige dónde guardar", initialdir=self.destino.get())
        if ruta:
            self.destino.set(ruta)
            self._mostrar_destino()

    def abrir_carpeta(self):
        ruta = self.destino.get()
        if sys.platform == "win32":
            os.startfile(ruta)
        else:
            subprocess.Popen(["xdg-open", ruta])

    def accion_principal(self):
        if self.descargando:
            self.cancelar.set()
            self.estado.set("Cancelando…")
            self.boton.state(["disabled"])
        else:
            self.iniciar()

    def iniciar(self):
        url = self.url.get().strip()
        if not PATRON_YT.search(url):
            self.estado.set("Ese no parece un enlace de YouTube.")
            return
        if not ffmpeg_disponible():
            self.estado.set("Falta FFmpeg: debe estar en la carpeta 'ffmpeg' junto a la app.")
            return
        if not os.path.isdir(self.destino.get()):
            self.estado.set("La carpeta de destino no existe.")
            return

        self.config_app.update(formato=self.formato.get(), calidad=self.calidad.get(),
                               destino=self.destino.get())
        guardar_config(self.config_app)

        self.descargando = True
        self.ultimo_url = url
        self.cancelar.clear()
        self.btn_abrir.pack_forget()
        self.boton.configure(text="Cancelar")
        self.barra.configure(mode="determinate", value=0)
        self.estado.set("Preparando…")

        hilo = threading.Thread(
            target=self._trabajar,
            args=(url, self.formato.get(), self.calidad.get(), self.destino.get()),
            daemon=True,
        )
        hilo.start()

    # ── hilo de descarga (no toca widgets; se comunica por la cola) ──
    def _trabajar(self, url, formato, calidad, destino):
        def hook_progreso(d):
            if self.cancelar.is_set():
                raise Cancelado()
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                hecho = d.get("downloaded_bytes") or 0
                pct = hecho * 100 / total if total else 0
                titulo = (d.get("info_dict") or {}).get("title", "")
                self.cola.put(("progreso", pct, titulo, d.get("speed"), d.get("eta")))

        def hook_post(d):
            if self.cancelar.is_set():
                raise Cancelado()  # evita empezar la conversión si se pulsó Cancelar
            if d["status"] == "started":
                self.cola.put(("procesando",))

        try:
            opts = opciones_descarga(formato, calidad, destino, hook_progreso, hook_post)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            if self.cancelar.is_set():
                self.cola.put(("cancelado",))
            else:
                self.cola.put(("listo", (info or {}).get("title", "")))
        except Exception as exc:  # noqa: BLE001 — cualquier fallo se muestra al usuario
            if self.cancelar.is_set() or isinstance(exc, Cancelado):
                self.cola.put(("cancelado",))
            else:
                self.cola.put(("error", mensaje_de_error(exc)))

    # ── actualización de la interfaz desde la cola ──
    def _leer_cola(self):
        try:
            while True:
                msg = self.cola.get_nowait()
                tipo = msg[0]
                if tipo == "progreso":
                    _, pct, titulo, vel, eta = msg
                    if str(self.barra.cget("mode")) != "determinate":
                        self.barra.stop()
                        self.barra.configure(mode="determinate")
                    self.barra.configure(value=pct)
                    partes = [f"{pct:.0f}%"]
                    if vel:
                        partes.append(f"{vel / 1_048_576:.1f} MB/s")
                    if eta:
                        partes.append(f"{int(eta) // 60}:{int(eta) % 60:02d} restante")
                    nombre = (titulo[:42] + "…") if len(titulo) > 43 else titulo
                    self.estado.set((nombre + "\n" if nombre else "") + "  ·  ".join(partes))
                elif tipo == "procesando":
                    self.barra.configure(mode="indeterminate")
                    self.barra.start(12)
                    self.estado.set("Convirtiendo…")
                elif tipo == "listo":
                    self._terminar()
                    self.barra.configure(value=100)
                    self.estado.set("Listo ✓  " + (msg[1][:45] if msg[1] else ""))
                    self.btn_abrir.pack(side="right")
                    self.url.set("")
                elif tipo == "cancelado":
                    self._terminar()
                    self.barra.configure(value=0)
                    self.estado.set("Descarga cancelada.")
                elif tipo == "error":
                    self._terminar()
                    self.barra.configure(value=0)
                    self.estado.set("Error: " + msg[1])
        except queue.Empty:
            pass
        self.after(100, self._leer_cola)

    def _terminar(self):
        self.descargando = False
        self.barra.stop()
        self.barra.configure(mode="determinate")
        self.boton.configure(text="Descargar")
        self.boton.state(["!disabled"])

    def _cerrar(self):
        self.cancelar.set()
        self.destroy()


def activar_dpi():
    # Texto nítido en pantallas con escalado de Windows
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    activar_dpi()
    App().mainloop()