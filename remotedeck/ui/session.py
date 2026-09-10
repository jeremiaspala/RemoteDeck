"""Widget de sesión: lanza el visor externo y lo embebe en la pestaña."""

from __future__ import annotations

from ..i18n import tr

import time
from enum import Enum

from PyQt6.QtCore import (
    QPoint,
    QProcess,
    QProcessEnvironment,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QCursor, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import backends, net, x11
from ..model import RDP, VNC, Server
from . import icons
from .theme import palette


class State(Enum):
    IDLE = "idle"
    WAKING = "waking"
    STARTING = "starting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


def state_text(state: "State") -> str:
    return {
        State.IDLE: tr("En espera"),
        State.WAKING: tr("Despertando equipo (WoL)"),
        State.STARTING: tr("Conectando"),
        State.CONNECTED: tr("Conectado"),
        State.DISCONNECTED: tr("Desconectado"),
        State.FAILED: tr("Error"),
    }.get(state, "")


class WakeWorker(QThread):
    """Envía el magic packet y espera a que el puerto responda."""

    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(bool)

    def __init__(self, server: Server, parent=None) -> None:
        super().__init__(parent)
        self.server = server
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        wol = self.server.wol
        host, port = self.server.host, self.server.effective_port
        if net.port_open(host, port, timeout=1.5):
            self.finished_ok.emit(True)
            return
        try:
            net.wake(wol.mac, wol.broadcast, wol.port)
            self.progress.emit(f"{tr('Magic packet enviado a')} {wol.mac}")
        except ValueError as exc:
            self.progress.emit(str(exc))
            self.finished_ok.emit(False)
            return
        deadline = time.monotonic() + max(5, wol.wait_seconds)
        while time.monotonic() < deadline and not self._stop:
            if net.port_open(host, port, timeout=2.0):
                self.finished_ok.emit(True)
                return
            remaining = int(deadline - time.monotonic())
            self.progress.emit(f"{tr('Esperando a')} {host}:{port}... ({remaining}s)")
            self.msleep(1500)
        self.finished_ok.emit(False)




class FullscreenBar(QWidget):
    """Barra flotante para salir de pantalla completa.

    Es una ventana propia y no roba el foco: mientras la sesión tiene el
    teclado (y por tanto F11 o Esc no llegan a la aplicación), el raton sigue
    siendo una via segura para volver.
    """

    def __init__(self, session: "SessionView") -> None:
        super().__init__(None)
        self.session = session
        c = palette(session.settings["theme"], session.settings["accent"])
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("FullscreenBar")
        self.setStyleSheet(
            f"""
            #FullscreenBar {{
                background: {c['panel']};
                border: 1px solid {c['border']};
                border-top: none;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }}
            QLabel {{ color: {c['text']}; font-weight: 600; }}
            QPushButton {{
                background: transparent; border: 1px solid transparent;
                border-radius: 7px; padding: 6px 10px; color: {c['text_dim']};
            }}
            QPushButton:hover {{ background: {c['panel_alt']}; color: {c['text']}; }}
            QPushButton:checked {{ background: {c['accent_soft']}; color: {c['text']}; }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 7, 10, 8)
        layout.setSpacing(6)

        title = QLabel(f"{session.server.label} · {session.server.target}")
        layout.addWidget(title)
        layout.addSpacing(14)

        self.pin_btn = QPushButton(icons.icon("star", c["text_dim"]), "")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip(tr("Mantener esta barra visible"))
        layout.addWidget(self.pin_btn)

        reconnect = QPushButton(icons.icon("refresh", c["text_dim"]), "")
        reconnect.setToolTip(tr("Reconectar"))
        reconnect.clicked.connect(session.reconnect)
        layout.addWidget(reconnect)

        exit_btn = QPushButton(icons.icon("fullscreen", c["text_dim"]), tr("  Salir (Esc)"))
        exit_btn.setToolTip(tr("Salir de pantalla completa"))
        exit_btn.clicked.connect(session.exit_fullscreen)
        layout.addWidget(exit_btn)

        close_btn = QPushButton(icons.icon("close", c["text_dim"]), "")
        close_btn.setToolTip(tr("Cerrar la sesión"))
        close_btn.clicked.connect(lambda: session.requestClose.emit(session))
        layout.addWidget(close_btn)

        self.adjustSize()
        self._grace_until = 0.0
        self._watch = QTimer(self)
        self._watch.setInterval(180)
        self._watch.timeout.connect(self._follow_cursor)

    @property
    def pinned(self) -> bool:
        return self.pin_btn.isChecked()

    def _screen_geometry(self):
        screen = self.session.screen() or QGuiApplication.primaryScreen()
        return screen.geometry()

    def place(self) -> None:
        geometry = self._screen_geometry()
        self.adjustSize()
        self.move(
            geometry.x() + (geometry.width() - self.width()) // 2,
            geometry.y(),
        )

    def start(self) -> None:
        self.place()
        self.show()
        self.raise_()
        # unos segundos de cortesia para que se vea donde esta el boton de salir
        self._grace_until = time.monotonic() + 4.5
        self._watch.start()
        QTimer.singleShot(4500, self._auto_hide)

    def stop(self) -> None:
        self._watch.stop()
        self.hide()

    def _auto_hide(self) -> None:
        if not self.pinned and self.isVisible():
            self.hide()

    def _follow_cursor(self) -> None:
        if not self.session.is_fullscreen:
            self.stop()
            return
        geometry = self._screen_geometry()
        pos = QCursor.pos()
        near_top = pos.y() <= geometry.y() + 2 and geometry.contains(pos)
        if near_top and not self.isVisible():
            self.place()
            self.show()
            self.raise_()
        elif self.isVisible() and not self.pinned:
            if (
                time.monotonic() > self._grace_until
                and pos.y() > geometry.y() + self.height() + 30
            ):
                self.hide()

class SessionView(QWidget):
    stateChanged = pyqtSignal(object)
    requestClose = pyqtSignal(object)

    POLL_MS = 150
    FIND_TIMEOUT_S = 25

    def __init__(self, server: Server, username: str, domain: str, password: str,
                 settings, parent=None) -> None:
        super().__init__(parent)
        self.server = server
        self.username = username
        self.domain = domain
        self.password = password
        self.settings = settings
        self.state = State.IDLE
        self.child_window: int | None = None
        self.launch: backends.Launch | None = None
        self.process: QProcess | None = None
        self.wake_worker: WakeWorker | None = None
        self._log: list[str] = []
        self._started_at = 0.0
        self._fullscreen = False
        self._reparented = False
        self._bar: FullscreenBar | None = None
        self._closing = False
        self.restore_cb = None  # lo fija la ventana principal

        self.setObjectName("SessionView")
        self._build_ui()

        self._find_timer = QTimer(self)
        self._find_timer.timeout.connect(self._find_child_window)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(220)
        self._resize_timer.timeout.connect(self._apply_child_geometry)
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(1500)
        self._watch_timer.timeout.connect(self._watch_child)

    # ------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget(self)
        self.container.setObjectName("SessionContainer")
        self.container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.container.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.container.setStyleSheet(f"background: {c['bg']};")
        self.container.setMinimumSize(320, 240)
        layout.addWidget(self.container)

        self.overlay = QWidget(self)
        self.overlay.setObjectName("SessionOverlay")
        ov = QVBoxLayout(self.overlay)
        ov.setContentsMargins(40, 40, 40, 40)
        ov.addStretch(1)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(
            icons.icon("rdp" if self.server.protocol == RDP else "vnc",
                       c["accent"], 48).pixmap(QSize(48, 48))
        )
        ov.addWidget(self.icon_label)

        self.title = QLabel(self.server.label)
        self.title.setObjectName("SessionTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ov.addWidget(self.title)

        self.message = QLabel("")
        self.message.setObjectName("SessionMsg")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        ov.addWidget(self.message)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.retry_btn = QPushButton(icons.icon("refresh", c["text"]), tr("  Reintentar"))
        self.retry_btn.clicked.connect(self.reconnect)
        self.retry_btn.hide()
        buttons.addWidget(self.retry_btn)
        self.log_btn = QPushButton(icons.icon("terminal", c["text"]), tr("  Ver registro"))
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(self._toggle_log)
        buttons.addWidget(self.log_btn)
        self.close_btn = QPushButton(icons.icon("close", c["text"]), tr("  Cerrar"))
        self.close_btn.setProperty("danger", True)
        self.close_btn.clicked.connect(lambda: self.requestClose.emit(self))
        buttons.addWidget(self.close_btn)
        buttons.addStretch(1)
        ov.addLayout(buttons)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("SessionLog")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(220)
        self.log_view.hide()
        ov.addWidget(self.log_view)
        ov.addStretch(1)

        self.overlay.raise_()

        QShortcut(QKeySequence("Ctrl+Alt+Shift+F"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self.exit_fullscreen)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())
        if self.child_window:
            self._resize_timer.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.child_window:
            self._resize_timer.start()

    def _toggle_log(self, checked: bool) -> None:
        self.log_view.setVisible(checked)
        if checked:
            self.log_view.setPlainText("\n".join(self._log[-400:]))
            self.log_view.verticalScrollBar().setValue(
                self.log_view.verticalScrollBar().maximum()
            )

    # --------------------------------------------------------- estado
    def _set_state(self, state: State, message: str = "") -> None:
        self.state = state
        self.message.setText(message or state_text(state))
        show_overlay = state != State.CONNECTED
        self.overlay.setVisible(show_overlay)
        if show_overlay:
            self.overlay.raise_()
        self.retry_btn.setVisible(state in (State.DISCONNECTED, State.FAILED))
        self.stateChanged.emit(self)

    def log(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        self._log.append(line)
        del self._log[:-800]
        if self.log_view.isVisible():
            self.log_view.appendPlainText(line)

    @property
    def status_text(self) -> str:
        return state_text(self.state)

    # ------------------------------------------------------- conexión
    def start(self) -> None:
        if self.state in (State.STARTING, State.CONNECTED, State.WAKING):
            return
        self._closing = False
        self._log.clear()
        self.log_view.clear()
        if self.server.wol.auto and self.server.wol.enabled:
            self._start_wake()
        else:
            self._launch()

    def reconnect(self) -> None:
        self.stop(quiet=True)
        QTimer.singleShot(300, self.start)

    def _start_wake(self) -> None:
        self._set_state(State.WAKING, tr("Enviando Wake-on-LAN..."))
        self.wake_worker = WakeWorker(self.server, self)
        self.wake_worker.progress.connect(
            lambda text: (self.log(text), self.message.setText(text))
        )
        self.wake_worker.finished_ok.connect(self._wake_done)
        self.wake_worker.start()

    def _wake_done(self, ok: bool) -> None:
        self.wake_worker = None
        if ok:
            self._launch()
        else:
            self._set_state(
                State.FAILED,
                f"{tr('El equipo no respondió en')} {self.server.host}:"
                f"{self.server.effective_port} {tr('tras el Wake-on-LAN.')}",
            )

    def _launch(self) -> None:
        self._set_state(State.STARTING, f"{tr('Conectando a')} {self.server.target}...")
        embed = self.server.display.embed and x11.available()
        if not x11.available():
            self.log(tr("X11 no disponible: la sesión se abrirá en ventana externa."))

        size = self._target_size()
        parent_xid = int(self.container.winId()) if embed else None
        try:
            self.launch = backends.build(
                self.server,
                self.username,
                self.domain,
                self.password,
                parent_xid,
                size[0],
                size[1],
                fullscreen=(self.server.display.mode == "fullscreen" and not embed),
                settings=self.settings,
            )
        except backends.BackendMissing as exc:
            self._set_state(State.FAILED, str(exc))
            return

        if self.server.protocol == RDP:
            shares = backends.resolve_shares(self.server, self.settings)
            for label, path in shares:
                self.log(
                    tr("Carpeta compartida: {path} -> \\\\tsclient\\{label}").format(
                        path=path, label=label
                    )
                )
            missing = backends.unavailable_share(self.server)
            if missing:
                self.log(
                    tr("La carpeta {path} no existe: no se comparte.").format(
                        path=missing
                    )
                )

        self.log("$ " + " ".join(self.launch.argv))
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        env = QProcessEnvironment.systemEnvironment()
        for key, value in (self.launch.env or {}).items():
            env.insert(key, value)
        env.insert("QT_QPA_PLATFORM", "xcb")
        env.insert("GDK_BACKEND", "x11")
        self.process.setProcessEnvironment(env)

        self.process.start(self.launch.argv[0], self.launch.argv[1:])
        if self.launch.stdin_data:
            self.process.write(self.launch.stdin_data)
            self.process.closeWriteChannel()

        self._started_at = time.monotonic()
        self.child_window = None
        self._reparented = False
        if embed:
            self._find_timer.start(self.POLL_MS)
        else:
            self._set_state(State.CONNECTED, "")
            self.overlay.setVisible(True)
            self.message.setText(tr("Sesión abierta en una ventana externa."))

    def _target_size(self) -> tuple[int, int]:
        d = self.server.display
        if d.mode == "fixed":
            return d.width, d.height
        width = max(640, self.container.width() or self.width() or 1280)
        height = max(480, self.container.height() or self.height() or 800)
        return width, height

    # ------------------------------------------------- embebido X11
    def _find_child_window(self) -> None:
        if self.process is None:
            self._find_timer.stop()
            return
        if time.monotonic() - self._started_at > self.FIND_TIMEOUT_S:
            self._find_timer.stop()
            if self.state not in (State.FAILED, State.DISCONNECTED):
                self._set_state(
                    State.FAILED,
                    tr("No se pudo embeber la ventana del visor. Revisa el "
                       "registro o desactiva 'Embeber en pestaña' en las "
                       "opciones del servidor."),
                )
            return

        conn = x11.shared()
        parent_xid = int(self.container.winId())

        if self.server.protocol == RDP:
            kids = conn.children(parent_xid)
            if kids:
                def area(win: int) -> int:
                    geometry = conn.geometry(win)
                    return geometry[2] * geometry[3] if geometry else 0

                self._attach(max(kids, key=area))
            return

        # VNC y cualquier visor sin soporte de parent-window: reparentar.
        pid = self.process.processId()
        if not pid:
            return
        win = conn.find_by_pid({pid})
        if win:
            conn.reparent(win, parent_xid, 0, 0)
            conn.map(win)
            self._reparented = True
            self._attach(win)

    def _attach(self, window: int) -> None:
        self._find_timer.stop()
        self.child_window = window
        self._apply_child_geometry()
        x11.shared().map(window)
        self._set_state(State.CONNECTED, "")
        self._watch_timer.start()
        if self.server.display.mode == "fullscreen":
            QTimer.singleShot(600, self.enter_fullscreen)
        # algunos visores se recolocan solos al terminar de arrancar
        for delay in (250, 700, 1500):
            QTimer.singleShot(delay, self._apply_child_geometry)
        QTimer.singleShot(400, self.focus_session)

    def _desired_geometry(self) -> tuple[int, int]:
        """Tamaño que debe tener la ventana embebida."""
        d = self.server.display
        if d.mode == "fixed":
            return d.width, d.height
        return max(320, self.container.width()), max(240, self.container.height())

    def _apply_child_geometry(self) -> None:
        if not self.child_window:
            return
        width, height = self._desired_geometry()
        x11.shared().move_resize(self.child_window, 0, 0, width, height)

    def _watch_child(self) -> None:
        if not self.child_window:
            return
        # en una pestaña oculta no hay nada que recolocar: al volver a mostrarse
        # el showEvent dispara _apply_child_geometry.
        if not self.isVisible():
            return
        conn = x11.shared()
        geometry = conn.geometry(self.child_window)
        if geometry is None:
            self.child_window = None
            self._watch_timer.stop()
            return
        x, y, width, height = geometry
        wanted = self._desired_geometry()
        if (x, y) != (0, 0) or (width, height) != wanted:
            conn.move_resize(self.child_window, 0, 0, *wanted)

    def focus_session(self) -> None:
        if self.child_window and self.state == State.CONNECTED:
            conn = x11.shared()
            if conn.exists(self.child_window):
                conn.focus(self.child_window)

    # ------------------------------------------------------- proceso
    def _read_output(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        for line in data.splitlines():
            self.log(line)

    def _process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._set_state(State.FAILED, tr("No se pudo iniciar el visor."))

    def _process_finished(self, code: int, status) -> None:
        self._find_timer.stop()
        self._watch_timer.stop()
        self.child_window = None
        if self.launch:
            self.launch.cleanup()
        if self.state == State.IDLE or self._closing:
            return
        reason = self._diagnose(code)
        if code == 0:
            self._set_state(State.DISCONNECTED, tr("Sesión finalizada."))
        else:
            self._set_state(State.FAILED, reason)

    def _diagnose(self, code: int) -> str:
        text = "\n".join(self._log[-60:]).lower()
        if "logon failure" in text or "0x00020009" in text or "authentication" in text:
            return tr("Fallo de autenticación: revisa usuario, dominio y contraseña.")
        if "connection refused" in text or "errconnect_connect_failed" in text:
            return f"{tr('Conexión rechazada por')} {self.server.target}."
        if "no route to host" in text or "unreachable" in text:
            return f"{self.server.host} {tr('no es alcanzable.')}"
        if "certificate" in text:
            return tr("Problema con el certificado del servidor.")
        if "authentication failure" in text or "auth failed" in text:
            return tr("Autenticación VNC rechazada.")
        return f"{tr('El visor terminó con código')} {code}."

    def stop(self, quiet: bool = False) -> None:
        self._closing = True
        if self._bar is not None:
            self._bar.stop()
        self._find_timer.stop()
        self._watch_timer.stop()
        if self.wake_worker:
            self.wake_worker.stop()
            self.wake_worker.wait(2000)
            self.wake_worker = None
        if quiet:
            self.state = State.IDLE
        if self.child_window:
            x11.shared().close_window(self.child_window)
            self.child_window = None
        proc = self.process
        self.process = None
        if proc is not None and proc.state() != QProcess.ProcessState.NotRunning:
            proc.terminate()
            if not proc.waitForFinished(2500):
                proc.kill()
                proc.waitForFinished(1500)
        if self.launch:
            self.launch.cleanup()

    # --------------------------------------------------- pantalla completa
    @property
    def is_fullscreen(self) -> bool:
        return self._fullscreen

    def toggle_fullscreen(self) -> None:
        if self._fullscreen:
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    def enter_fullscreen(self) -> None:
        if self._fullscreen or self.state != State.CONNECTED:
            return
        self._fullscreen = True
        self.setParent(None)
        self.setWindowFlags(Qt.WindowType.Window)
        self.showFullScreen()
        if self._bar is None:
            self._bar = FullscreenBar(self)
        QTimer.singleShot(150, self._apply_child_geometry)
        QTimer.singleShot(250, self._bar.start)
        QTimer.singleShot(400, self.focus_session)

    def exit_fullscreen(self) -> None:
        if not self._fullscreen:
            return
        self._fullscreen = False
        if self._bar is not None:
            self._bar.stop()
        self.setWindowFlags(Qt.WindowType.Widget)
        self.showNormal()
        if self.restore_cb is not None:
            self.restore_cb(self)
        QTimer.singleShot(150, self._apply_child_geometry)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._fullscreen:
            self.exit_fullscreen()
            event.ignore()
            return
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._fullscreen and event.key() == Qt.Key.Key_Escape:
            self.exit_fullscreen()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.focus_session()
        super().mousePressEvent(event)
