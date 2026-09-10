# Manual de RemoteDeck

Guía rápida de todo lo que hace la aplicación. Si venís de Remmina o del
Remote Desktop Connection Manager de Windows, la idea te va a resultar familiar:
a la izquierda el árbol de equipos, a la derecha las sesiones en pestañas.

---

## 1. Instalación

### AppImage (recomendado)

```bash
chmod +x RemoteDeck-x86_64.AppImage
./RemoteDeck-x86_64.AppImage
```

No instala nada ni pide permisos de administrador. Trae adentro Python, PyQt6,
FreeRDP 3 y TigerVNC, así que funciona aunque no tengas ningún cliente remoto
instalado.

Para que aparezca en el menú de aplicaciones, podés usar
[Gear Lever](https://github.com/mijorus/gearlever) o AppImageLauncher, o crear
el `.desktop` a mano:

```bash
mkdir -p ~/.local/bin ~/.local/share/applications
mv RemoteDeck-x86_64.AppImage ~/.local/bin/
cat > ~/.local/share/applications/remotedeck.desktop <<EOF
[Desktop Entry]
Type=Application
Name=RemoteDeck
Comment=Conexiones RDP y VNC en pestañas
Exec=$HOME/.local/bin/RemoteDeck-x86_64.AppImage
Icon=remotedeck
Categories=Network;RemoteAccess;
Terminal=false
EOF
```

### Desde el código

```bash
git clone https://github.com/jeremiaspala/RemoteDeck.git
cd RemoteDeck
python3 run.py
```

---

## 2. Dependencias

### Qué necesita el AppImage del sistema

Casi nada: el paquete trae Python 3.12, PyQt6 (con su propio Qt), FreeRDP 3,
TigerVNC y las bibliotecas de esos visores. Del sistema solo usa el stack
gráfico y el núcleo de la distro:

| Componente | Paquete en Debian/Ubuntu | Para qué |
|---|---|---|
| glibc, libstdc++, libgcc | `libc6`, `libstdc++6` | base del sistema |
| X11 / XWayland | `libx11-6`, `libxcb1`, `libxext6`, `libxi6`, `libxrandr2`, `libxfixes3`, `libxcursor1` | ventanas y entrada |
| OpenGL | `libgl1`, `libegl1` | render de Qt |
| D-Bus, udev, systemd | `libdbus-1-3`, `libudev1`, `libsystemd0` | integración con el escritorio |
| PulseAudio (opcional) | `libpulse0` | audio de las sesiones RDP |

Las bibliotecas auxiliares que el plugin `xcb` de Qt suele echar en falta
(`libxcb-cursor0`, `libxcb-icccm4`, `libxcb-image0`, `libxcb-keysyms1`,
`libxcb-render-util0`, `libxcb-util1`, `libxkbcommon-x11-0`) **van dentro del
AppImage**, así que no hace falta instalarlas.

También necesita **X11 o XWayland**. En una sesión Wayland pura (sin XWayland)
no hay forma de embeber las ventanas de los visores; la aplicación se fuerza
sola a XCB cuando detecta `DISPLAY`.

### Qué necesita si lo ejecutás desde el código

```bash
sudo apt install python3 python3-pyqt6 python3-pyqt6.qtsvg \
                 freerdp3-x11 tigervnc-viewer tigervnc-common
```

| Dependencia | Obligatoria | Para qué |
|---|---|---|
| Python ≥ 3.10 | sí | la aplicación |
| PyQt6 + PyQt6-QtSvg | sí | interfaz e iconos |
| `libX11` | sí | se usa por ctypes para embeber ventanas |
| `xfreerdp3` (FreeRDP 3) | para RDP | visor RDP |
| `vncviewer` (TigerVNC) | para VNC | visor VNC |
| `vncpasswd` (`tigervnc-common`) | no | genera el fichero de contraseña de VNC; si falta, RemoteDeck lo genera solo |
| `python3-gi` + `gir1.2-secret-1` | no | leer las contraseñas de Remmina del llavero |
| `iproute2` (`ip neigh`) | no | detectar la MAC para Wake-on-LAN |

No hay dependencias de PyPI: el cifrado, el DES de VNC y el acceso a X11 están
resueltos con la biblioteca estándar y ctypes.

---

## 3. Primeros pasos

1. **Crear un grupo**: `Ctrl+Shift+N`. Los grupos se anidan y sirven para
   ordenar por sucursal, cliente o rol. El grupo nuevo queda al mismo nivel que
   lo que tengas seleccionado; con el menú contextual sobre un grupo podés
   crearlo adentro, y en el diálogo hay un selector **Dentro de** para
   moverlo.
2. **Cargar las credenciales en el grupo** (pestaña del diálogo de grupo). Todos
   los equipos que cuelguen de ahí las heredan: si tenés un dominio con 40
   servidores, cargás el usuario una sola vez.
3. **Crear un servidor**: `Ctrl+N`. Como mínimo, nombre y host. Si dejás la
   contraseña vacía, se pide al conectar.
4. **Conectar**: doble clic o `Enter`.

Podés arrastrar equipos y grupos dentro del árbol para reordenarlos.

---

## 4. La ventana de un servidor

| Pestaña | Qué hay |
|---|---|
| **General** | Nombre, host, puerto, protocolo, grupo, etiquetas, favorito y conexión automática al arrancar |
| **Credenciales** | Heredar del grupo o usar propias (usuario, dominio, contraseña) |
| **Pantalla** | Ajustar a la pestaña / resolución fija / pantalla completa, y si la sesión va embebida o en ventana aparte |
| **RDP** | Seguridad, color, red, escala, teclado, portapapeles, audio, micrófono, carpeta de intercambio, unidades, impresoras, tarjetas, multi-monitor, RD Gateway y argumentos extra |
| **VNC** | Codificación, calidad, compresión, solo lectura, sesión compartida, redimensionado remoto |
| **Wake-on-LAN** | MAC, difusión, puerto, espera y encendido automático |
| **Notas** | Texto libre: inventario, contactos, qué hace ese equipo |

### Modos de pantalla

- **Ajustar al tamaño de la pestaña**: la sesión sigue el tamaño de la ventana.
  Con RDP se usa resolución dinámica (el escritorio remoto se reajusta solo) y
  con VNC, `RemoteResize`. Es lo que querés el 90 % de las veces.
- **Resolución fija**: la sesión mantiene el tamaño que indiques. Si la pestaña
  es más chica, se recorta.
- **Pantalla completa**: al conectar salta directo a pantalla completa.

---

## 5. Trabajar con las sesiones

- Cada conexión abre una pestaña. El punto de color del ícono indica el estado:
  gris conectando, verde conectado, rojo error.
- **Pantalla completa**: `F11`. Para volver, `Esc` o `F11`… **pero ojo**: si
  hiciste clic dentro del escritorio remoto, el teclado se lo queda el visor y
  esas teclas no llegan a RemoteDeck. Para eso está la **barra flotante**:
  llevá el mouse al borde superior de la pantalla y aparece con los botones de
  salir, reconectar y cerrar. Con el botón de la estrella la dejás fija.
- **Reconectar**: `Ctrl+R`. Sirve cuando se cae la conexión o cambiaste
  opciones del servidor.
- **Cerrar la sesión**: `Ctrl+W` o la cruz de la pestaña.
- **Ver el registro**: en el panel de error, el botón *Ver registro* muestra la
  salida completa del visor. Es lo primero que hay que mirar cuando algo falla.
- Si un equipo no se deja embeber, desmarcá *Embeber la sesión en una pestaña*
  en la pestaña **Pantalla** y el visor se abre en su propia ventana.

---

## 6. Carpeta de intercambio

Al conectarte por RDP, RemoteDeck publica una carpeta local en el equipo remoto
como una unidad de red. Es la forma más directa de mover ficheros en las dos
direcciones sin montar SMB ni levantar un FTP.

Por omisión comparte `~/RemoteDeck` (se crea sola la primera vez) con el nombre
`RemoteDeck`. En el servidor la ves como:

- **Windows**: en *Este equipo*, junto a los discos, y también en
  `\\tsclient\RemoteDeck`.
- **Windows Server con Escritorio remoto**: igual, siempre que la directiva de
  grupo no tenga bloqueada la redirección de unidades.

`Sesión` → `Abrir carpeta de intercambio` (`Ctrl+Shift+O`) abre esa carpeta en
tu gestor de ficheros; también está en el menú del icono de la bandeja. Si hay
una sesión activa, abre la carpeta que ve esa sesión.

### Configurarla

En **Preferencias** → *Carpeta de intercambio*:

| Opción | Qué hace |
|---|---|
| **Compartir una carpeta local en las sesiones RDP** | Activa o desactiva la carpeta global para todas las conexiones |
| **Carpeta** | Ruta local. Vacío significa `~/RemoteDeck` |
| **Nombre de la unidad** | Cómo se llama la unidad en el servidor |

Y por equipo, en su pestaña **RDP** → *Carpeta de intercambio*:

| Opción | Qué hace |
|---|---|
| **Publicar la carpeta de intercambio de RemoteDeck** | Desmarcalo en los equipos donde no quieras compartir nada |
| **Carpeta extra** | Una segunda carpeta, solo para ese equipo (por ejemplo, la de instaladores) |
| **Nombre** | Nombre de esa unidad en el servidor |

Las carpetas que se publican quedan anotadas en el registro de la sesión
(*Ver registro*), con la ruta local y el nombre remoto.

### Un par de detalles

- La redirección va por el canal `rdpdr` de RDP: no abre ningún puerto ni
  necesita nada instalado en el servidor.
- Si la carpeta no existe, RemoteDeck la crea. Si la ruta configurada no se
  puede crear, la sesión arranca igual, sin unidad.
- Con *Redirigir unidades locales* (en las opciones de RDP) se comparten además
  todos los puntos de montaje del sistema. La carpeta de intercambio es lo
  contrario: una sola carpeta, controlada.
- **VNC no tiene transferencia de ficheros**: el visor de TigerVNC no
  implementa el canal, así que esta opción solo aplica a RDP.

---

## 7. Wake-on-LAN

En la pestaña **Wake-on-LAN** de cada servidor:

- **MAC**: escribila o tocá *Detectar* (la busca en la tabla ARP local, así que
  el equipo tiene que haber estado encendido y visible hace poco).
- **Broadcast**: `255.255.255.255` sirve para la red local. Para despertar
  equipos de otra subred, poné la dirección de difusión de esa red
  (`192.168.20.255`, por ejemplo) y habilitá el reenvío de esos paquetes en el
  router.
- **Puerto**: 9 por defecto. El paquete se manda igual al 7 y al 9.
- **Despertar automáticamente antes de conectar**: si el puerto RDP/VNC no
  responde, RemoteDeck manda el paquete mágico y espera hasta el tiempo que
  indiques antes de lanzar el visor.

Para dispararlo a mano: `Ctrl+Shift+W` o el menú contextual. Podés seleccionar
varios equipos (o un grupo entero) y despertarlos todos juntos.

---

## 8. Importar conexiones

**Archivo > Importar de Remmina** lee los perfiles de `~/.local/share/remmina`,
respeta los grupos y recupera las contraseñas guardadas en el llavero
(libsecret) o cifradas con la clave de `remmina.pref`.

**Archivo > Importar fichero** acepta:

- `.rdg` de Remote Desktop Connection Manager (grupos, credenciales y
  resoluciones; las contraseñas de RDCMan van cifradas con DPAPI de Windows y
  no se pueden descifrar en Linux, salvo que estén guardadas en texto plano).
- `.rdp` sueltos.
- `.remmina` sueltos.
- `.json` exportado por RemoteDeck.

En todos los casos aparece una vista previa donde podés destildar lo que no
quieras importar y decidir si se fusiona con los grupos existentes.

**Archivo > Exportar conexiones** genera un JSON con todo el árbol. Las
contraseñas van cifradas con la clave de ese equipo: si te llevás el fichero a
otra máquina, vas a tener que volver a cargarlas.

---

## 9. Seguridad de las credenciales

Las contraseñas nunca se guardan en texto plano ni aparecen en la lista de
procesos (a FreeRDP se le pasan por `stdin` y a TigerVNC por un fichero
temporal con permisos 0600 que se borra al cerrar la sesión).

En **Preferencias > Seguridad** elegís cómo se cifran:

- **Clave local** (por defecto): la clave vive en `~/.config/remotedeck/vault.key`
  con permisos 0600. Te protege de que alguien lea el JSON o un backup, no de
  alguien que ya tiene tu sesión de usuario abierta.
- **Contraseña maestra**: la clave se deriva de una contraseña que se pide al
  abrir la aplicación (scrypt) y no queda nada utilizable en disco. Al
  activarla o desactivarla, todas las credenciales se vuelven a cifrar solas.

---

## 10. Bandeja del sistema y arranque automático

RemoteDeck deja un icono en la bandeja del sistema. Con un clic mostrás u
ocultás la ventana, y con el botón derecho tenés un menú para conectarte a
cualquier equipo sin abrirla: primero los favoritos y después el árbol
completo, respetando los grupos.

En **Preferencias > Sistema**:

| Opción | Qué hace |
|---|---|
| **Mostrar icono en la bandeja del sistema** | Activa o desactiva el icono. Si lo desactivás, cerrar la ventana cierra la aplicación. |
| **Al cerrar la ventana, minimizar a la bandeja** | La cruz de la ventana esconde la aplicación en vez de cerrarla. Para salir de verdad: `Ctrl+Q`, *Archivo > Salir* o *Salir* en el menú de la bandeja. |
| **Iniciar con el sistema** | Escribe `~/.config/autostart/remotedeck.desktop` apuntando al ejecutable actual (el propio AppImage si lo estás usando). |
| **Iniciar minimizado en la bandeja** | Al arrancar no se abre la ventana: solo queda el icono. Se aplica también al arranque automático. |

También podés forzarlo desde la línea de comandos:

```bash
./RemoteDeck-x86_64.AppImage --minimized
```

Si tu escritorio no expone una bandeja del sistema, RemoteDeck lo detecta y
desactiva la opción (en GNOME hace falta la extensión *AppIndicator Support*).

---

## 11. Idioma

En **Preferencias > Apariencia > Idioma** podés elegir entre **español**
(el idioma principal), **inglés**, **francés** y **alemán**. El cambio se
aplica al instante: la ventana se reconstruye sola con los textos nuevos. Si
hay sesiones abiertas, RemoteDeck avisa y el idioma se aplica en el próximo
arranque para no cortarte una conexión.

Si falta alguna traducción, se muestra el texto en español en vez de dejar el
hueco vacío. Los diccionarios están en `remotedeck/locales/` (un fichero
Python por idioma, con el texto en español como clave), así que agregar un
idioma nuevo es copiar uno de esos ficheros y traducirlo.

---

## 12. Atajos

| Atajo | Acción |
|---|---|
| Doble clic / `Enter` | Conectar |
| `F11` | Pantalla completa |
| `Esc` | Salir de pantalla completa |
| `Ctrl+R` | Reconectar |
| `Ctrl+W` | Cerrar la sesión activa |
| `Ctrl+N` | Nuevo servidor |
| `Ctrl+Shift+N` | Nuevo grupo |
| `F2` | Editar |
| `Ctrl+D` | Duplicar servidor |
| `Supr` | Eliminar |
| `Ctrl+Shift+W` | Enviar Wake-on-LAN |
| `Ctrl+Shift+O` | Abrir la carpeta de intercambio |
| `F5` | Comprobar el estado de los equipos |
| `Ctrl+,` | Preferencias |
| `Ctrl+Q` | Salir (cierra de verdad, aunque esté la bandeja) |

---

## 13. Problemas frecuentes

**"No se pudo embeber la ventana del visor"**
El visor tardó más de 25 segundos en abrir su ventana o el servidor rechazó la
conexión antes de mostrarla. Mirá el registro. Si pasa siempre con ese equipo,
usá el modo de ventana externa.

**Fallo de autenticación en RDP**
Casi siempre es el dominio. Probá con `DOMINIO\usuario` en el campo de usuario o
cargá el dominio en su campo. Si el servidor es viejo, probá *Seguridad: RDP
clásico* o *TLS* en vez de NLA.

**La sesión RDP se ve borrosa o va lenta**
Bajá la profundidad de color a 16 bits y poné *Tipo de red: WAN* o *Modem*. Si
tu FreeRDP tiene H.264 compilado, agregá `/gfx:AVC444:on` en *Argumentos
adicionales*.

**El audio no suena**
*Audio: Reproducir aquí* necesita PulseAudio o PipeWire con el shim de Pulse
(`libpulse0`) en el sistema anfitrión.

**VNC pide contraseña igual**
Las contraseñas de VNC clásico (VncAuth) están limitadas a 8 caracteres: si la
tuya es más larga, el servidor solo mira los primeros 8. Para autenticación con
usuario (VeNCrypt/Plain) cargá el usuario en la pestaña VNC.

**El Wake-on-LAN no despierta nada**
Verificá que la placa tenga WoL habilitado (`ethtool eth0 | grep Wake-on`) y en
la BIOS/UEFI. Por Wi-Fi rara vez funciona. Entre subredes hace falta que el
router reenvíe el broadcast dirigido.

**No arranca y dice algo de `xcb`**
Estás en una sesión sin X11 ni XWayland. Instalá XWayland o iniciá sesión en X11.

---

## 14. Dónde se guarda todo

| Ruta | Contenido |
|---|---|
| `~/.config/remotedeck/connections.json` | Grupos y equipos (permisos 0600) |
| `~/.config/remotedeck/connections.json.bak` | Copia de la versión anterior |
| `~/.config/remotedeck/settings.json` | Preferencias de la interfaz |
| `~/.config/remotedeck/vault.json` | Modo de cifrado |
| `~/.config/remotedeck/vault.key` | Clave local (si no usás contraseña maestra) |
| `~/.config/autostart/remotedeck.desktop` | Arranque automático (si lo activaste) |
| `~/RemoteDeck/` | Carpeta de intercambio por omisión (se comparte en las sesiones RDP) |
| `~/.cache/remotedeck/` | Iconos generados y registros |
| `$XDG_RUNTIME_DIR/remotedeck/` | Ficheros temporales de contraseñas de VNC |

Para empezar de cero, borrá `~/.config/remotedeck`.
