# Compila Conversor.exe en tu PC para probarlo antes de subir nada a GitHub.
# Uso (desde la carpeta del proyecto, con el venv activado):  .\compilar.ps1

$ErrorActionPreference = "Stop"

pip install pyinstaller==6.22.3 | Out-Null

pyinstaller --noconfirm --onefile --windowed --name Conversor `
  --icon icono.ico --add-data "icono.ico;." Conversor.py

# Copia FFmpeg y Deno junto al .exe, igual que en el .zip que recibirá tu amigo
New-Item -ItemType Directory -Force -Path dist\ffmpeg, dist\deno | Out-Null
Copy-Item ffmpeg\*.exe dist\ffmpeg\ -ErrorAction SilentlyContinue
Copy-Item deno\*.exe   dist\deno\   -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Listo: dist\Conversor.exe" -ForegroundColor Green
if (-not (Test-Path dist\ffmpeg\ffmpeg.exe)) { Write-Host "Aviso: falta ffmpeg\ffmpeg.exe en el proyecto" -ForegroundColor Yellow }
if (-not (Test-Path dist\deno\deno.exe))     { Write-Host "Aviso: falta deno\deno.exe (se usará Deno del sistema si está instalado)" -ForegroundColor Yellow }
