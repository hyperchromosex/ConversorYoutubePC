# ConversorYoutubePC

Aplicación sencilla para Windows que descarga videos y Shorts de YouTube en MP3 o MP4.

- Pega el enlace (si ya lo tienes copiado, se pega solo al abrir la ventana).
- Elige MP3 o MP4 y, para MP4, la calidad (1080p por defecto).
- Pulsa **Descargar** o Enter. Se puede cancelar en cualquier momento.
- Recuerda la última carpeta, formato y calidad usados.

## Para usarla (sin instalar nada)

1. Ve a la pestaña **Releases** del repositorio y descarga `Conversor-vX.Y.Z.zip`.
2. Descomprime el `.zip` donde quieras (por ejemplo, en el Escritorio).
3. Abre `Conversor.exe` con doble clic.

No muevas `Conversor.exe` fuera de su carpeta: necesita tener al lado las carpetas
`ffmpeg\` y `quickjs\`. Si quieres tenerlo en el Escritorio, crea un acceso directo.

```
Conversor\
├── Conversor.exe
├── ffmpeg\
│   └── ffmpeg.exe
└── quickjs\
    └── qjs.exe      (motor JavaScript que yt-dlp necesita para YouTube)
```

> Windows SmartScreen puede avisar porque el `.exe` no está firmado:
> pulsa **Más información → Ejecutar de todas formas**.

## Desarrollo

### Preparar el entorno (una sola vez)

```powershell
cd C:\Users\centu\Desktop\Watashi\Python\ConversorYoutubePC
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copia los ejecutables externos dentro del proyecto (no se suben a GitHub):

- `ffmpeg\ffmpeg.exe`: desde la carpeta `bin` de tu descarga de FFmpeg (ffprobe no hace falta).
- `deno\deno.exe`: desde https://github.com/denoland/deno/releases
  (archivo `deno-x86_64-pc-windows-msvc.zip`). Si ya tienes Deno instalado en
  el sistema, puedes saltarte este paso.

### Ejecutar en desarrollo

```powershell
python Conversor.py
```

### Compilar el .exe localmente (opcional)

```powershell
pip install pyinstaller==6.22.3
pyinstaller --noconfirm --onefile --windowed --name Conversor `
  --icon icono.ico --add-data "icono.ico;." Conversor.py
```

El resultado queda en `dist\Conversor.exe`. Para probarlo, copia `ffmpeg\` y
`deno\` junto a él dentro de `dist\`.

## Publicar una nueva versión

```powershell
git add .
git commit -m "Descripción del cambio"
git push
git tag v1.0.1
git push origin v1.0.1
```

Al subir la etiqueta, GitHub Actions compila la app, le añade FFmpeg y QuickJS, y
publica el `.zip` en **Releases** automáticamente.

Versionado (SemVer):
- `v1.0.0 → v1.0.1`: corrección de errores
- `v1.0.0 → v1.1.0`: función nueva compatible
- `v1.0.0 → v2.0.0`: cambio grande o incompatible

### Si YouTube deja de funcionar

Suele arreglarse actualizando yt-dlp. Cambia la versión en `requirements.txt`
(la última está en https://pypi.org/project/yt-dlp/), pruébalo con
`pip install -r requirements.txt` y `python Conversor.py`, y saca una versión nueva.

## Licencias

- FFmpeg: GPL — https://ffmpeg.org/legal.html
- QuickJS-NG: MIT (o Deno: MIT, si se compila con JS_RUNTIME: "deno")
- yt-dlp: Unlicense
