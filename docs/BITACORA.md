# Bitácora de desarrollo

Registro de cómo se construyó RemoteDeck: qué se decidió y por qué, qué se
rompió por el camino y cómo se probó cada cosa. Sesión del **9 y 10 de
septiembre de 2026**, de la nada al AppImage publicado.

---

## 1. El punto de partida

La idea: un clon del *Remote Desktop Connection Manager* de Windows para Linux,
empaquetado como AppImage con todas las bibliotecas adentro, con estilo moderno
y soporte de RDP y VNC.

Lo que había en la máquina de desarrollo (Ubuntu 26.04, Plasma sobre Wayland):
FreeRDP 3.31 (`xfreerdp3`), TigerVNC 1.15 (`vncviewer`), PyQt6 6.10 y Python
3.14.

---

## 2. Decisiones de arquitectura

### PyQt6 en vez de GTK

El punto crítico de todo el proyecto es **embeber la ventana de un visor
externo dentro de una pestaña**. Eso exige control fino sobre ventanas X11 y
Qt lo da: un `QWidget` con `WA_NativeWindow` tiene un XID real al que se le
puede reparentar cualquier ventana.

### Cómo se embebe cada protocolo

Son dos caminos distintos porque los visores no ofrecen lo mismo:

- **RDP**: FreeRDP tiene `/parent-window:<xid>`. Se le pasa el XID del
  contenedor y él solo crea su ventana adentro. Después se sondean los hijos
  X11 del contenedor hasta que aparece.
- **VNC**: TigerVNC no tiene nada equivalente (se revisó toda su lista de
  parámetros). Así que se lanza normal, se busca su ventana recorriendo el
  árbol X11 y comparando `_NET_WM_PID` con el PID del proceso, y se la
  reparenta con `XReparentWindow`. Es lo mismo que hacen `xdotool
  windowreparent` o `tabbed`.

Como la ruta de VNC sirve para cualquier aplicación X11, se puede reutilizar
si alguna vez se agrega otro visor.

### ctypes sobre libX11, sin python-xlib

Hace falta muy poco de Xlib: `XQueryTree`, `XGetWindowProperty`,
`XReparentWindow`, `XMoveResizeWindow`, `XSetInputFocus` y un `ClientMessage`
para cerrar limpio. Con `ctypes` eso son 300 líneas y **cero dependencias**
que empaquetar: `libX11` ya está en cualquier sistema con X11. Se instala un
manejador de errores X que ignora los fallos, porque las ventanas ajenas
pueden desaparecer entre que se consultan y se tocan.

### Cifrado solo con la biblioteca estándar

Se evaluó usar `cryptography`, pero arrastra un `.so` compilado al AppImage.
La construcción final es `scrypt` para derivar la clave y un flujo
HMAC-SHA256 en modo contador para cifrar, con HMAC-SHA256 como MAC
(cifrar-luego-autenticar). Todo con `hashlib`/`hmac`. Dos modos: clave local
en un fichero 0600 o contraseña maestra que se pide al arrancar.

### DES en Python puro para VNC

El fichero de contraseñas de VNC es la contraseña cifrada con DES usando una
clave fija con **los bits de cada byte invertidos** (herencia de la
implementación d3des original). Se implementó DES completo en `d3des.py` y se
verificó de dos formas: contra el vector de prueba clásico
(`133457799BBCDFF1` / `0123456789ABCDEF` → `85E813540F0AB405`) y contra la
salida real de `vncpasswd -f`, que fue la que confirmó que la variante correcta
es invertir los bits de la clave y no los de los datos. En tiempo de ejecución
se usa `vncpasswd` si está, y esto queda como respaldo.

### Las contraseñas no pasan por `ps`

- **FreeRDP**: acepta `/args-from:stdin`, así que **toda** la línea de
  comandos (contraseña incluida) se le manda por la entrada estándar.
- **TigerVNC**: solo acepta `-PasswordFile`, así que se escribe un fichero
  0600 en `$XDG_RUNTIME_DIR` que se borra al terminar la sesión.

---

## 3. Cronología

| Hito | Qué se hizo |
|---|---|
| Núcleo | Modelo de datos (grupos/servidores con herencia estilo RDCMan), almacenamiento JSON, cifrado, utilidades de red y Wake-on-LAN, envoltura de X11, constructores de línea de comandos |
| Interfaz | Tema oscuro/claro en QSS, iconos SVG generados en memoria, árbol lateral con arrastrar y soltar, pestañas de sesión, diálogos de servidor/grupo/preferencias |
| Importadores | Remmina (con contraseñas del llavero), `.rdg` de RDCMan, `.rdp`, JSON propio |
| Empaquetado | Script que arma el AppDir con CPython portable + PyQt6 + los visores y sus bibliotecas |
| Pulido | Barra flotante en pantalla completa, formularios con scroll, tildes y eñes, Acerca de con créditos |
| Multiidioma | Módulo `i18n` propio y diccionarios en español, inglés, francés y alemán |
| Bandeja | Icono en la bandeja del sistema, arranque con el sistema, arranque minimizado |

Versiones publicadas: **1.0.0** (primera), **1.1.0** (idiomas y barra
flotante), **1.2.0** (bandeja y arranque automático), **1.2.1** (casillas de
los árboles).

---

## 4. Los problemas que aparecieron

Esta es la parte que vale la pena guardar.

### `Can't open display` al lanzar el visor

`QProcess.processEnvironment()` devuelve un entorno **vacío** si nadie lo fijó
antes. Al agregarle un par de variables y llamar a `setProcessEnvironment()`,
el proceso hijo se quedaba sin `DISPLAY` ni nada. Se arregló partiendo de
`QProcessEnvironment.systemEnvironment()`.

### La ventana embebida quedaba en un rincón

Tras reparentar, el visor se redimensionaba pero no se movía a (0,0): FLTK (y
otros toolkits) se recolocan solos al terminar de arrancar, pisando el
`XMoveResizeWindow` inicial. La solución fue reaplicar la geometría a los
250 ms, 700 ms y 1,5 s, y además vigilarla cada 1,5 s comparándola con la
deseada. De paso eso cubre el modo de resolución fija, donde el tamaño que
manda es el del servidor y no el del contenedor.

### En pantalla completa no había forma de salir

`F11` y `Esc` no llegaban nunca: apenas hacés clic dentro del escritorio
remoto, el visor se queda con el foco del teclado (FreeRDP incluso hace grab).
No hay atajo de Qt que sobreviva a eso. La solución es la que usa Remmina: una
**barra flotante** que es una ventana propia (`X11BypassWindowManagerHint` +
`WA_ShowWithoutActivating`, para no robar el foco) y que aparece cuando el
puntero toca el borde superior. El ratón siempre funciona, el teclado no.

Efecto colateral: al pasar a pantalla completa la sesión sale del
`QTabWidget`, así que `current_session()` devolvía `None` y la barra de
herramientas dejaba de actuar sobre ella. Ahora primero busca una sesión en
pantalla completa.

### FreeRDP rechazaba la línea de comandos entera

`/gfx:AVC444` fallaba con *Command line parsing failed at 'gfx'*: el FreeRDP de
Ubuntu viene compilado **sin H.264**, así que ni siquiera acepta el valor. Se
cambió por `/gfx:RFX:on,progressive:on,small-cache:on`, que existe siempre.

A partir de ahí se agregó un paso de validación: generar los argumentos para
todas las combinaciones de opciones y ejecutarlos de verdad contra
`xfreerdp3` y `vncviewer` apuntando a un puerto cerrado, comprobando que
ninguno produce error de parseo. Encontró este bug y evita los próximos.

### El AppImage no arrancaba en sistemas ajenos

El plugin `xcb` de Qt necesita `libxcb-cursor0`, `libxcb-icccm4`,
`libxcb-image0`, `libxcb-keysyms1`, `libxcb-render-util0`, `libxcb-util1` y
`libxkbcommon-x11-0`, que en muchas distros no vienen instaladas: es el clásico
*could not load the Qt platform plugin "xcb"*. Se detectó comparando las
dependencias `NEEDED` de todo el AppDir contra lo empaquetado. Ahora esas
bibliotecas van adentro, en `usr/lib/qtdeps`, y `AppRun` las agrega al
`LD_LIBRARY_PATH`.

En la misma revisión se eliminaron 14 plugins de Qt huérfanos: al recortar
módulos que no se usan (Quick, WebEngine, Multimedia…) quedaban plugins
apuntando a bibliotecas borradas. El script ahora los detecta solo con
`objdump -p`.

### El script de compilación se cortaba sin decir nada

Terminaba con código 141 (SIGPIPE) en medio del empaquetado. La causa:
`printf '%s\n' "$LDCONFIG_OUT" | awk '... {print; exit}'` — `awk` cerraba la
tubería al encontrar la primera coincidencia, `printf` moría de SIGPIPE y
`set -e` abortaba el script. Se reemplazó la tubería por un *here-string*.
Antes de eso, otro corte silencioso: `ldconfig` vive en `/usr/sbin` y no está
en el PATH de un usuario normal.

### Los menús iban lentos y la ventana parecía trabada

En Plasma sobre Wayland, Qt intentaba registrarse contra el portal xdg (fallaba
con *Could not register app ID*) y usaba los diálogos nativos de KDE, con la
latencia que eso implica. Se midió la construcción de los diálogos: 60 ms, o
sea que el problema no era el código. Ahora la aplicación arranca con
`QT_NO_XDG_DESKTOP_PORTAL=1`, diálogos no nativos y las animaciones de menú,
combo y tooltip apagadas.

### Cuadrados blancos en el diálogo de importar

Qt **no** aplica el estilo de `QCheckBox` a los indicadores de un `QTreeView`:
los dibujaba con el estilo nativo, un cuadro claro casi vacío sobre el tema
oscuro. Se estilaron explícitamente `QTreeView::indicator` y compañía.

De la misma familia: los combos no mostraban flecha, las casillas marcadas no
tenían tilde y los grupos del árbol no tenían chevron, porque la hoja de
estilos anulaba los adornos nativos sin poner otros. Se resolvió generando los
SVG de tilde, punto y flechas en `~/.cache/remotedeck/assets` y
referenciándolos desde el QSS.

### Formularios aplastados

La pestaña de RDP tiene tres bloques de opciones y no entraban en el diálogo:
los `QFormLayout` comprimen los widgets por debajo de su tamaño natural, así
que los combos cortaban el texto. Cada pestaña pasó a vivir dentro de un
`QScrollArea` y los campos tienen altura mínima.

### Los grupos nuevos quedaban anidados

Con un grupo seleccionado, el grupo nuevo caía adentro. Ahora se crea como
hermano, el menú contextual ofrece explícitamente *Nuevo grupo dentro* y el
diálogo tiene un selector **Dentro de** que además sirve para mover un grupo
existente.

### Herencia de credenciales

`effective_credentials()` heredaba del grupo aunque el servidor tuviera
marcado *no heredar*, si sus credenciales estaban vacías. Ahora *no heredar*
significa exactamente eso.

### Desplazamientos rotos al internacionalizar

Para envolver 200 y pico de textos con `tr()` se escribió un transformador
basado en `ast` que reescribe el código fuente. La primera pasada dejó el
fichero hecho un desastre porque **`ast` da los offsets en bytes UTF-8**, no en
caracteres, y el código está lleno de tildes. Se rehizo trabajando sobre
`bytes` y editando de atrás para adelante.

---

## 5. Cómo se probó

Sin servidores RDP o VNC de prueba a mano (`x11vnc` no funciona bajo Wayland),
se armaron pruebas que igual cubren el camino crítico:

- **Humo sin pantalla**: `QT_QPA_PLATFORM=offscreen` y configuración en un
  directorio temporal para construir la ventana principal y todos los
  diálogos, guardar, recargar y verificar que la contraseña se descifra.
- **Embebido de verdad**: se sustituyó el visor por `xclock` y se comprobó que
  la ventana se localiza por PID, se reparenta, queda en (0,0) con el tamaño
  del contenedor y sobrevive al cambio a pantalla completa. Es exactamente el
  mismo camino de código que usa VNC.
- **Capturas**: bajo Wayland no se puede capturar la raíz de X, pero sí una
  ventana concreta con `import -window <xid>`, y el XID se obtiene con el
  mismo módulo X11 de la aplicación. Así se revisaron los diálogos y el árbol,
  incluso con escalado HiDPI.
- **Argumentos**: se ejecutan los visores reales con las líneas generadas para
  detectar errores de parseo.
- **Bandeja**: se verificó por D-Bus que el proceso registra su ítem en el
  `StatusNotifierWatcher` de Plasma, y que con `--minimized` no crea ventana.
- **AppImage**: se prueba como lo haría cualquiera — copiar el fichero a una
  carpeta limpia, `chmod +x` y ejecutarlo con una configuración vacía.

---

## 6. Cosas que quedaron en el tintero

- Scroll dentro de la sesión cuando se usa resolución fija más grande que la
  pestaña (hoy se recorta).
- Miniaturas de las sesiones en el árbol.
- Túnel SSH para llegar a equipos detrás de un salto.
- Importar desde mRemoteNG.
- Descifrar contraseñas de `.rdg` (van con DPAPI de Windows; solo se pueden
  leer las que estén en texto plano).
