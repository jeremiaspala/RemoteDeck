# RemoteDeck

Gestor de conexiones remotas para Linux al estilo del *Remote Desktop Connection
Manager* de Windows: arbol de grupos a la izquierda, sesiones **RDP** y **VNC**
embebidas en pestanas a la derecha, y todo empaquetado en un unico AppImage.

![RemoteDeck](docs/screenshot.png)

## Que hace

- **Grupos anidados** con herencia de credenciales (un grupo guarda usuario /
  dominio / contrasena y sus equipos los heredan), arrastrar y soltar para
  reorganizar.
- **Sesiones embebidas en pestanas**: FreeRDP se lanza con `/parent-window` y el
  visor de TigerVNC se reparenta dentro de la pestana, asi que las sesiones no
  se dispersan en ventanas sueltas. Pantalla completa con `F11`.
- **RDP completo**: NLA/TLS/RDP, profundidad de color, GFX (H.264), resolucion
  dinamica, portapapeles, audio, microfono, unidades, impresoras, tarjeta
  inteligente, multi-monitor, RD Gateway, distribucion de teclado y argumentos
  extra.
- **VNC**: codificacion, calidad, compresion, solo lectura, sesion compartida,
  redimensionado remoto.
- **Wake-on-LAN** por equipo: MAC (con deteccion desde la tabla ARP), direccion
  de difusion, puerto y espera; opcion de despertar automaticamente antes de
  conectar y esperar a que el puerto responda.
- **Estado en vivo**: comprueba periodicamente el puerto de cada equipo y pinta
  el indicador en verde o rojo.
- **Importadores**: perfiles de **Remmina** (incluidas las contrasenas del
  llavero), ficheros **.rdg** de RDCMan, ficheros **.rdp** y export/import en
  JSON propio.
- **Credenciales cifradas** en disco, con contrasena maestra opcional.
- Busqueda incremental, favoritos, notas y etiquetas por equipo, tema oscuro o
  claro con color de acento configurable.

## Uso rapido

```bash
./RemoteDeck-x86_64.AppImage
```

El AppImage trae dentro Python, PyQt6, FreeRDP 3 (`xfreerdp3`) y TigerVNC
(`vncviewer`), asi que no hace falta instalar nada. Si el sistema ya tiene esos
visores y prefieres usarlos, se indican en *Preferencias > Visores*.

Atajos:

| Atajo | Accion |
|---|---|
| `Doble clic` / `Enter` | Conectar |
| `F11` | Pantalla completa (salir con `Esc`) |
| `Ctrl+R` | Reconectar |
| `Ctrl+W` | Cerrar la sesion activa |
| `Ctrl+N` / `Ctrl+Shift+N` | Nuevo servidor / grupo |
| `F2`, `Ctrl+D`, `Supr` | Editar, duplicar, eliminar |
| `Ctrl+Shift+W` | Enviar Wake-on-LAN |
| `F5` | Comprobar el estado de los equipos |

## Ejecutar desde el codigo

```bash
sudo apt install python3-pyqt6 python3-pyqt6.qtsvg freerdp3-x11 tigervnc-viewer
python3 run.py
```

## Construir el AppImage

```bash
bash packaging/build-appimage.sh
```

Descarga una base de CPython portable, instala PyQt6, copia la aplicacion y
empaqueta `xfreerdp3`, `vncviewer` y `vncpasswd` con sus bibliotecas en
`usr/lib/viewers`. Resultado: `RemoteDeck-x86_64.AppImage` (~140 MB).

Las bibliotecas del nucleo (glibc, libstdc++, X11, OpenGL) se toman del sistema
anfitrion, como es habitual en los AppImage: el binario resultante funciona en
distribuciones con una glibc igual o mas nueva que la de la maquina donde se
construyo.

## Donde se guardan las cosas

| Ruta | Contenido |
|---|---|
| `~/.config/remotedeck/connections.json` | Arbol de grupos y equipos (0600) |
| `~/.config/remotedeck/settings.json` | Preferencias de la interfaz |
| `~/.config/remotedeck/vault.json` | Modo de cifrado y comprobacion de clave |
| `~/.config/remotedeck/vault.key` | Clave local cuando no hay contrasena maestra (0600) |

### Cifrado de credenciales

Las contrasenas se guardan cifradas con `scrypt` + flujo de clave HMAC-SHA256 en
modo contador y HMAC-SHA256 como MAC (cifrar-luego-autenticar), solo con la
biblioteca estandar de Python.

- **Modo local** (por defecto): la clave vive en `vault.key` con permisos 0600.
  Protege frente a la lectura casual del JSON o de una copia de seguridad, no
  frente a alguien que ya tiene acceso a tu sesion de usuario.
- **Modo maestro**: la clave se deriva de una contrasena que se pide al arrancar
  y no queda nada utilizable en disco. Se activa en *Preferencias > Seguridad*.

Las contrasenas nunca aparecen en la tabla de procesos: a FreeRDP se le pasan
por `stdin` con `/args-from:stdin` y a TigerVNC mediante un fichero temporal
0600 en `$XDG_RUNTIME_DIR` que se borra al terminar la sesion.

## Notas tecnicas

- El embebido de ventanas necesita X11. En sesiones Wayland la aplicacion se
  fuerza a XCB (XWayland) automaticamente; los visores tambien.
- RDP usa `/parent-window` de FreeRDP. VNC no tiene equivalente, asi que se
  localiza la ventana del visor por su PID y se reparenta con `XReparentWindow`.
- Si el embebido falla en algun equipo concreto, en *Pantalla* de ese servidor
  se puede desmarcar «Embeber la sesion en una pestana» y el visor se abrira en
  su propia ventana.
- Con «Resolucion fija» la sesion mantiene su tamano y se recorta si la pestana
  es mas pequena; para que se adapte, usa «Ajustar al tamano de la pestana».

## Licencia

MIT.
