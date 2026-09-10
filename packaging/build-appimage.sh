#!/usr/bin/env bash
# Construye RemoteDeck-x86_64.AppImage con Python, PyQt6, FreeRDP y TigerVNC dentro.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
BUILD="$ROOT/build"
APPDIR="$BUILD/AppDir"
CACHE="$BUILD/cache"
PY_VERSION="3.12"
APP="RemoteDeck"

mkdir -p "$CACHE"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- descargas
fetch() {  # fetch <url> <destino>
    local url="$1" dest="$2"
    [ -s "$dest" ] && { log "cache: $(basename "$dest")"; return; }
    log "descargando $(basename "$dest")"
    curl -fL --retry 3 --progress-bar -o "$dest.part" "$url"
    mv "$dest.part" "$dest"
}

PY_URL=$(curl -fsSL "https://api.github.com/repos/niess/python-appimage/releases/tags/python${PY_VERSION}" \
    | grep -o "https://[^\"]*cp${PY_VERSION/./}-cp${PY_VERSION/./}-manylinux2014_x86_64.AppImage" | head -1)
[ -n "$PY_URL" ] || die "no se pudo resolver la URL de python-appimage"
fetch "$PY_URL" "$CACHE/python.AppImage"
fetch "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" \
      "$CACHE/appimagetool.AppImage"
chmod +x "$CACHE/python.AppImage" "$CACHE/appimagetool.AppImage"

# ------------------------------------------------------------ base Python
log "preparando AppDir"
rm -rf "$APPDIR" "$BUILD/squashfs-root"
( cd "$BUILD" && "$CACHE/python.AppImage" --appimage-extract >/dev/null )
mv "$BUILD/squashfs-root" "$APPDIR"
rm -f "$APPDIR"/*.desktop "$APPDIR"/*.png "$APPDIR"/AppRun "$APPDIR"/.DirIcon

PYBIN=$(find "$APPDIR" -type f -name "python${PY_VERSION}" -perm -u+x | head -1)
[ -n "$PYBIN" ] || die "no se encontro el interprete dentro del AppDir"
SITE=$("$PYBIN" -c 'import site; print(site.getsitepackages()[0])')
log "python: $PYBIN"
log "site-packages: $SITE"

# ---------------------------------------------------------------- PyQt6
log "instalando PyQt6"
"$PYBIN" -m pip install --upgrade pip >/dev/null
"$PYBIN" -m pip install "PyQt6>=6.6" >/dev/null

# adelgaza Qt: fuera lo que no usamos
QT_LIB="$SITE/PyQt6/Qt6/lib"
if [ -d "$QT_LIB" ]; then
    log "recortando Qt"
    for mod in Qt6WebEngineCore Qt6WebEngineWidgets Qt6Quick3D Qt6Designer Qt6Bluetooth \
               Qt6Nfc Qt6Sensors Qt6SerialPort Qt6Multimedia Qt6Charts Qt6DataVisualization \
               Qt6Sql Qt6Test Qt6Help Qt6Pdf Qt6Quick Qt6Qml Qt6QmlModels Qt6Positioning; do
        rm -f "$QT_LIB/lib${mod}"*.so.* 2>/dev/null || true
        rm -f "$SITE/PyQt6/${mod#Qt6}"*.abi3.so 2>/dev/null || true
    done
    rm -rf "$SITE/PyQt6/Qt6/qml" "$SITE/PyQt6/Qt6/translations" \
           "$SITE/PyQt6/Qt6/plugins/sqldrivers" "$SITE/PyQt6/Qt6/plugins/multimedia" \
           "$SITE/PyQt6/Qt6/plugins/geometryloaders" \
           "$SITE/PyQt6/Qt6/plugins/sceneparsers" "$SITE/PyQt6/Qt6/plugins/renderers" \
           "$SITE/PyQt6/Qt6/plugins/assetimporters" "$SITE/PyQt6/Qt6/plugins/texttospeech" \
           "$SITE/PyQt6/Qt6/plugins/webview" 2>/dev/null || true
    # el tema GTK arrastra todo GTK3 y ademas lo desactivamos en tiempo de ejecucion
    rm -f "$SITE/PyQt6/Qt6/plugins/platformthemes/libqgtk3.so" 2>/dev/null || true

    log "eliminando plugins huerfanos"
    "$PYBIN" - "$SITE/PyQt6/Qt6" <<'PYORPHAN'
import pathlib, re, subprocess, sys

root = pathlib.Path(sys.argv[1])
present = {p.name for p in (root / "lib").glob("*.so*")}
removed = 0
for plugin in (root / "plugins").rglob("*.so"):
    try:
        dump = subprocess.run(
            ["objdump", "-p", str(plugin)], capture_output=True, text=True, timeout=20
        ).stdout
    except Exception:
        continue
    needed = set(re.findall(r"NEEDED\s+(\S+)", dump))
    if any(n.startswith("libQt6") and n not in present for n in needed):
        plugin.unlink()
        removed += 1
print(f"    plugins eliminados: {removed}")
PYORPHAN
fi

# ------------------------------------------------------------ aplicacion
log "copiando RemoteDeck"
rm -rf "$SITE/remotedeck"
cp -r "$ROOT/remotedeck" "$SITE/remotedeck"
find "$SITE/remotedeck" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# -------------------------------------------------- visores RDP y VNC
VIEWER_DIR="$APPDIR/usr/lib/viewers"
mkdir -p "$VIEWER_DIR/bin" "$VIEWER_DIR/lib" "$APPDIR/usr/bin"

# Bibliotecas que SIEMPRE deben venir del sistema anfitrion.
is_excluded() {
    case "$1" in
        ld-linux*|libc.so*|libm.so*|libdl.so*|libpthread.so*|librt.so*|libutil.so*|\
        libresolv.so*|libnsl.so*|libgcc_s.so*|libstdc++.so*|\
        libGL.so*|libGLX.so*|libGLdispatch.so*|libEGL.so*|libOpenGL.so*|libGLU.so*|\
        libdrm.so*|libgbm.so*|libglapi.so*|\
        libX11.so*|libX11-xcb.so*|libxcb.so*|libxcb-*|libXext.so*|libXrender.so*|\
        libXi.so*|libXfixes.so*|libXdamage.so*|libXrandr.so*|libXcursor.so*|\
        libXinerama.so*|libXtst.so*|libXau.so*|libXdmcp.so*|libwayland-*|\
        libselinux.so*|libudev.so*|libdbus-1.so*|libsystemd.so*)
            return 0 ;;
    esac
    return 1
}

bundle_binary() {  # bundle_binary <ruta> [nombre destino]
    local src="$1" name="${2:-$(basename "$1")}"
    [ -x "$src" ] || { log "aviso: no existe $src, se omite"; return; }
    cp -L "$src" "$VIEWER_DIR/bin/$name"
    ldd "$src" 2>/dev/null | awk '/=> \//{print $3}' | sort -u | while read -r lib; do
        local base; base=$(basename "$lib")
        is_excluded "$base" && continue
        [ -e "$VIEWER_DIR/lib/$base" ] && continue
        cp -L "$lib" "$VIEWER_DIR/lib/$base"
    done
    cat > "$APPDIR/usr/bin/$name" <<WRAP
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\$0")")"
VIEWERS="\$HERE/../lib/viewers"
export LD_LIBRARY_PATH="\$VIEWERS/lib:\$LD_LIBRARY_PATH"
exec "\$VIEWERS/bin/$name" "\$@"
WRAP
    chmod +x "$APPDIR/usr/bin/$name"
    log "empaquetado: $name"
}

# Bibliotecas auxiliares que exige el plugin xcb de Qt y que muchas distros no
# traen instaladas (libxcb-cursor0 es el caso tipico).
QTDEPS="$APPDIR/usr/lib/qtdeps"
mkdir -p "$QTDEPS"
log "empaquetando dependencias del plugin xcb"
LDCONFIG_OUT="$(/usr/sbin/ldconfig -p 2>/dev/null || ldconfig -p 2>/dev/null || true)"
for soname in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 \
              libxcb-keysyms.so.1 libxcb-render-util.so.0 libxcb-util.so.1 \
              libxcb-xkb.so.1 libxkbcommon.so.0 libxkbcommon-x11.so.0; do
    # here-string en vez de tuberia: awk termina antes y provocaria SIGPIPE
    src=$(awk -v s="$soname" '$1 == s && /x86-64/ {print $NF; exit}' <<< "$LDCONFIG_OUT")
    if [ -n "$src" ] && [ -e "$src" ]; then
        cp -L "$src" "$QTDEPS/$soname"
    else
        log "aviso: no se encontro $soname en el sistema"
    fi
done

log "empaquetando visores"
bundle_binary "$(command -v xfreerdp3 || command -v xfreerdp || true)" xfreerdp3
bundle_binary "$(readlink -f "$(command -v vncviewer || true)")" vncviewer
bundle_binary "$(command -v vncpasswd || true)" vncpasswd

# segunda pasada: dependencias de las propias bibliotecas copiadas
for _ in 1 2 3; do
    for lib in "$VIEWER_DIR"/lib/*.so*; do
        [ -e "$lib" ] || continue
        ldd "$lib" 2>/dev/null | awk '/=> \//{print $3}' | sort -u | while read -r dep; do
            base=$(basename "$dep")
            is_excluded "$base" && continue
            [ -e "$VIEWER_DIR/lib/$base" ] && continue
            cp -L "$dep" "$VIEWER_DIR/lib/$base"
        done
    done
done

# ------------------------------------------------------- icono y desktop
log "generando icono"
"$PYBIN" - "$APPDIR" "$SITE" <<'PYICON'
import sys, os

appdir, site_dir = sys.argv[1], sys.argv[2]
sys.path.insert(0, site_dir)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

app = QGuiApplication([])
from remotedeck.ui.icons import app_icon_svg

renderer = QSvgRenderer(QByteArray(app_icon_svg()))
for size in (256, 128, 64, 48, 32):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    target = os.path.join(
        appdir, "usr/share/icons/hicolor", f"{size}x{size}", "apps"
    )
    os.makedirs(target, exist_ok=True)
    image.save(os.path.join(target, "remotedeck.png"))
    if size == 256:
        image.save(os.path.join(appdir, "remotedeck.png"))
PYICON
cp "$APPDIR/remotedeck.png" "$APPDIR/.DirIcon"

cat > "$APPDIR/remotedeck.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=RemoteDeck
GenericName=Gestor de escritorios remotos
Comment=Conexiones RDP y VNC organizadas en pestanas
Exec=remotedeck %U
Icon=remotedeck
Categories=Network;RemoteAccess;Utility;
Terminal=false
StartupNotify=true
Keywords=rdp;vnc;remoto;escritorio;remote;desktop;
DESKTOP
mkdir -p "$APPDIR/usr/share/applications"
cp "$APPDIR/remotedeck.desktop" "$APPDIR/usr/share/applications/"

# ------------------------------------------------------------- AppRun
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export APPDIR="$HERE"
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib/qtdeps${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# El embebido de ventanas exige XCB (bajo Wayland se usa XWayland).
if [ -n "$DISPLAY" ] && [ -z "$REMOTEDECK_PLATFORM" ]; then
    export QT_QPA_PLATFORM=xcb
fi
PYBIN=$(ls "$HERE"/opt/python*/bin/python3.* 2>/dev/null | head -1)
[ -x "$PYBIN" ] || PYBIN=$(ls "$HERE"/usr/bin/python3.* 2>/dev/null | head -1)
exec "$PYBIN" -c "from remotedeck.app import main; raise SystemExit(main())" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# ------------------------------------------------------------- empaquetar
log "generando AppImage"
OUT="$ROOT/${APP}-x86_64.AppImage"
rm -f "$OUT"
export ARCH=x86_64
if ! "$CACHE/appimagetool.AppImage" "$APPDIR" "$OUT" 2>"$BUILD/appimagetool.log"; then
    log "appimagetool con FUSE fallo, extrayendo"
    ( cd "$CACHE" && ./appimagetool.AppImage --appimage-extract >/dev/null )
    "$CACHE/squashfs-root/AppRun" "$APPDIR" "$OUT"
fi

chmod +x "$OUT"
log "listo: $OUT ($(du -h "$OUT" | cut -f1))"
