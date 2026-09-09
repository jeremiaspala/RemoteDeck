"""Widget de sesion: lanza el visor externo y lo embebe en la pestana."""

from __future__ import annotations

import time
from enum import Enum

from PyQt6.QtCore import QProcess, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
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


STATE_TEXT = {
    State.IDLE: "En espera",
    State.WAKING: "Despertando equipo (WoL)",
    State.STARTING: "Conectando",
    State.CONNECTED: "Conectado",
    State.DISCONNECTED: "Desconectado",
    State.FAILED: "Error",
}


class WakeWorker(QThread):
    """Envia el magic packet y espera a que el puerto responda."""

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
            self.progress.emit(f"Magic packet enviado a {wol.mac}")
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
            self.progress.emit(f"Esperando a {host}:{port}... ({remaining}s)")
            self.msleep(1500)
        self.finished_ok.emit(False)


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
        self.retry_btn = QPushButton(icons.icon("refresh", c["text"]), "  Reintentar")
        self.retry_btn.clicked.connect(self.reconnect)
        self.retry_btn.hide()
        buttons.addWidget(self.retry_btn)
        self.log_btn = QPushButton(icons.icon("terminal", c["text"]), "  Ver registro")
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(self._toggle_log)
        buttons.addWidget(self.log_btn)
        self.close_btn = QPushButton(icons.icon("close", c["text"]), "  Cerrar")
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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())
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
        self.message.setText(message or STATE_TEXT.get(state, ""))
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
        return STATE_TEXT.get(self.state, "")

    # ------------------------------------------------------- conexion
    def start(self) -> None:
        if self.state in (State.STARTING, State.CONNECTED, State.WAKING):
            return
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
        self._set_state(State.WAKING, "Enviando Wake-on-LAN...")
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
                f"El equipo no respondio en {self.server.host}:"
                f"{self.server.effective_port} tras el Wake-on-LAN.",
            )

    def _launch(self) -> None:
        self._set_state(State.STARTING, f"Conectando a {self.server.target}...")
        embed = self.server.display.embed and x11.available()
        if not x11.available():
            self.log("X11 no disponible: la sesion se abrira en ventana externa.")

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

        self.log("$ " + " ".join(self.launch.argv))
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        env = self.process.processEnvironment()
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
            self.message.setText("Sesion abierta en una ventana externa.")

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
                    "No se pudo embeber la ventana del visor. Revisa el registro "
                    "o desactiva 'Embeber en pestana' en las opciones del servidor.",
                )
            return

        conn = x11.shared()
        parent_xid = int(self.container.winId())

        if self.server.protocol == RDP:
            kids = conn.children(parent_xid)
            if kids:
                self._attach(kids[-1])
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
        QTimer.singleShot(400, self.focus_session)

    def _apply_child_geometry(self) -> None:
        if not self.child_window:
            return
        conn = x11.shared()
        width = max(320, self.container.width())
        height = max(240, self.container.height())
        conn.move_resize(self.child_window, 0, 0, width, height)

    def _watch_child(self) -> None:
        if self.child_window and not x11.shared().exists(self.child_window):
            self.child_window = None
            self._watch_timer.stop()

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
            self._set_state(State.FAILED, "No se pudo iniciar el visor.")

    def _process_finished(self, code: int, status) -> None:
        self._find_timer.stop()
        self._watch_timer.stop()
        self.child_window = None
        if self.launch:
            self.launch.cleanup()
        if self.state == State.IDLE:
            return
        reason = self._diagnose(code)
        if code == 0:
            self._set_state(State.DISCONNECTED, "Sesion finalizada.")
        else:
            self._set_state(State.FAILED, reason)

    def _diagnose(self, code: int) -> str:
        text = "\n".join(self._log[-60:]).lower()
        if "logon failure" in text or "0x00020009" in text or "authentication" in text:
            return "Fallo de autenticacion: revisa usuario, dominio y contrasena."
        if "connection refused" in text or "errconnect_connect_failed" in text:
            return f"Conexion rechazada por {self.server.target}."
        if "no route to host" in text or "unreachable" in text:
            return f"{self.server.host} no es alcanzable."
        if "certificate" in text:
            return "Problema con el certificado del servidor."
        if "authentication failure" in text or "auth failed" in text:
            return "Autenticacion VNC rechazada."
        return f"El visor termino con codigo {code}."

    def stop(self, quiet: bool = False) -> None:
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
        QTimer.singleShot(150, self._apply_child_geometry)
        QTimer.singleShot(300, self.focus_session)

    def exit_fullscreen(self) -> None:
        if not self._fullscreen:
            return
        self._fullscreen = False
        self.setWindowFlags(Qt.WindowType.Widget)
        self.showNormal()
        if self.restore_cb is not None:
            self.restore_cb(self)
        QTimer.singleShot(150, self._apply_child_geometry)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._fullscreen and event.key() == Qt.Key.Key_Escape:
            self.exit_fullscreen()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.focus_session()
        super().mousePressEvent(event)
