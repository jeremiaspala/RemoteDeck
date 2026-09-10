"""Dialogos: alta/edicion de servidores y grupos, ajustes y credenciales."""

from __future__ import annotations

from ..i18n import LANGUAGES, tr

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QScrollArea,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import net
from ..model import RDP, VNC, Credentials, Group, Server
from . import icons
from .brand import FUNDAMENTA_URL, fundamenta_pixmap
from .theme import palette


def _group_path(group: Group) -> str:
    parts = [group.name]
    node = group.parent
    while node is not None and node.parent is not None:
        parts.append(node.name)
        node = node.parent
    return " / ".join(reversed(parts))


def _scrollable(page: QWidget) -> QScrollArea:
    """Evita que los formularios largos queden aplastados."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(page)
    return area


def _password_field(placeholder: str = "") -> tuple[QWidget, QLineEdit]:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setPlaceholderText(placeholder)
    toggle = QPushButton(tr("Ver"))
    toggle.setCheckable(True)
    toggle.setFixedWidth(52)
    toggle.setProperty("flat", True)
    toggle.toggled.connect(
        lambda on: edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )
    )
    layout.addWidget(edit, 1)
    layout.addWidget(toggle)
    return box, edit




class AboutDialog(QDialog):
    """Acerca de: créditos, visores detectados y atajos."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        from .. import APP_NAME, __version__

        c = palette(settings["theme"], settings["accent"])
        dark = settings["theme"] != "light"
        self.setWindowTitle(f"{tr('Acerca de')} {APP_NAME}")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(icons.app_icon(c["accent"]).pixmap(QSize(72, 72)))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        title = QLabel(APP_NAME)
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel(f"{tr('versión')} {__version__}")
        version.setObjectName("SessionMsg")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        tagline = QLabel(
            tr("Gestor de conexiones RDP y VNC con las sesiones embebidas en "
            "pestañas, al estilo del Remote Desktop Connection Manager.")
        )
        tagline.setObjectName("SessionMsg")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        layout.addWidget(tagline)
        layout.addSpacing(10)

        credits = QLabel(
            '<div align="center">Creado por <b>Jeremías Palazzesi</b><br>'
            '<a style="color:%s; text-decoration:none;" href="%s">%s</a></div>'
            % (c["accent"], "https://github.com/jeremiaspala/RemoteDeck",
               "github.com/jeremiaspala/RemoteDeck")
        )
        credits.setOpenExternalLinks(True)
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(credits)
        layout.addSpacing(14)

        brand = QLabel()
        brand.setPixmap(fundamenta_pixmap(34, dark))
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setCursor(Qt.CursorShape.PointingHandCursor)
        brand.setToolTip(FUNDAMENTA_URL)
        layout.addWidget(brand)

        link = QLabel(
            '<div align="center"><a style="color:%s; text-decoration:none;" '
            'href="%s">fundamenta.ar</a></div>' % (c["accent"], FUNDAMENTA_URL)
        )
        link.setOpenExternalLinks(True)
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(link)
        layout.addSpacing(14)

        backends_box = QGroupBox(tr("Visores detectados"))
        backends_layout = QVBoxLayout(backends_box)
        for label, text in _detected_backends():
            row = QLabel(f"<b>{label}</b> · {text}")
            row.setObjectName("SessionMsg")
            row.setWordWrap(True)
            backends_layout.addWidget(row)
        layout.addWidget(backends_box)

        shortcuts = QLabel(
            tr("<div align='center'>F11 pantalla completa · Esc salir · "
            "Ctrl+R reconectar · Ctrl+W cerrar sesión · F5 comprobar estado</div>")
        )
        shortcuts.setObjectName("SessionMsg")
        shortcuts.setWordWrap(True)
        layout.addWidget(shortcuts)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Cerrar"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def _detected_backends() -> list[tuple[str, str]]:
    import subprocess

    from .. import backends as be

    out = []
    for label, candidates, args in (
        ("RDP", be.RDP_BINARIES, ["--version"]),
        ("VNC", be.VNC_BINARIES, ["--version"]),
    ):
        try:
            path = be.find_binary(candidates)
        except be.BackendMissing:
            out.append((label, "no encontrado"))
            continue
        version = ""
        try:
            result = subprocess.run(
                [path, *args], capture_output=True, text=True, timeout=6
            )
            version = (result.stdout + result.stderr).strip().splitlines()
            version = next((v for v in version if v.strip()), "")
        except (OSError, subprocess.SubprocessError):
            pass
        out.append((label, f"{version or path}"))
    return out

class ServerDialog(QDialog):
    def __init__(self, server: Server, store, settings, parent=None, is_new=False):
        super().__init__(parent)
        self.server = server
        self.store = store
        self.settings = settings
        self.setWindowTitle(
            tr("Nuevo servidor") if is_new else f"{tr('Editar')} · {server.label}"
        )
        self.setMinimumSize(700, 600)
        self.resize(760, 720)
        self._build()
        self._load()

    # ------------------------------------------------------------ UI
    def _build(self) -> None:
        c = palette(self.settings["theme"], self.settings["accent"])
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("Editor")
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(
            _scrollable(self._tab_general()), icons.icon("server", c["text_dim"]), tr("General")
        )
        self.tabs.addTab(
            _scrollable(self._tab_credentials()), icons.icon("lock", c["text_dim"]),
            tr("Credenciales"),
        )
        self.tabs.addTab(
            _scrollable(self._tab_display()), icons.icon("fullscreen", c["text_dim"]),
            tr("Pantalla"),
        )
        self.rdp_tab = _scrollable(self._tab_rdp())
        self.tabs.addTab(self.rdp_tab, icons.icon("rdp", c["text_dim"]), tr("RDP"))
        self.vnc_tab = _scrollable(self._tab_vnc())
        self.tabs.addTab(self.vnc_tab, icons.icon("vnc", c["text_dim"]), tr("VNC"))
        self.tabs.addTab(
            _scrollable(self._tab_wol()), icons.icon("power", c["text_dim"]), tr("Wake-on-LAN")
        )
        self.tabs.addTab(self._tab_notes(), icons.icon("info", c["text_dim"]), tr("Notas"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(tr("Guardar"))
        ok.setProperty("accent", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _tab_general(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(14, 16, 14, 16)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("Nombre visible"))
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText(tr("IP o nombre DNS"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(0, 65535)
        self.port_spin.setSpecialValueText(tr("por defecto"))
        self.proto_combo = QComboBox()
        self.proto_combo.addItem(tr("RDP · Escritorio remoto de Windows"), RDP)
        self.proto_combo.addItem(tr("VNC · Escritorio remoto multiplataforma"), VNC)
        self.proto_combo.currentIndexChanged.connect(self._proto_changed)
        self.group_combo = QComboBox()
        for group in self.store.groups():
            label = "Raíz" if group is self.store.root else _group_path(group)
            self.group_combo.addItem(label, group.id)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(tr("producción, sucursal-centro"))
        self.fav_check = QCheckBox(tr("Marcar como favorito"))
        self.startup_check = QCheckBox(tr("Conectar al iniciar la aplicación"))

        form.addRow(tr("Nombre"), self.name_edit)
        form.addRow(tr("Host"), self.host_edit)
        form.addRow(tr("Puerto"), self.port_spin)
        form.addRow(tr("Protocolo"), self.proto_combo)
        form.addRow(tr("Grupo"), self.group_combo)
        form.addRow(tr("Etiquetas"), self.tags_edit)
        form.addRow("", self.fav_check)
        form.addRow("", self.startup_check)
        return page

    def _tab_credentials(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(12)
        self.inherit_check = QCheckBox(tr("Heredar credenciales del grupo"))
        self.inherit_check.toggled.connect(self._inherit_changed)
        layout.addWidget(self.inherit_check)

        self.cred_box = QGroupBox(tr("Credenciales del servidor"))
        form = QFormLayout(self.cred_box)
        form.setSpacing(10)
        self.user_edit = QLineEdit()
        self.domain_edit = QLineEdit()
        self.domain_edit.setPlaceholderText(tr("Dominio (solo RDP)"))
        pw_widget, self.pass_edit = _password_field(tr("Se pedirá al conectar si se deja vacío"))
        form.addRow(tr("Usuario"), self.user_edit)
        form.addRow(tr("Dominio"), self.domain_edit)
        form.addRow(tr("Contraseña"), pw_widget)
        layout.addWidget(self.cred_box)

        self.inherited_label = QLabel()
        self.inherited_label.setObjectName("SessionMsg")
        self.inherited_label.setWordWrap(True)
        layout.addWidget(self.inherited_label)
        layout.addStretch(1)
        return page

    def _tab_display(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(14, 16, 14, 16)
        form.setSpacing(12)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("Ajustar al tamaño de la pestaña"), "fit")
        self.mode_combo.addItem(tr("Resolución fija"), "fixed")
        self.mode_combo.addItem(tr("Pantalla completa"), "fullscreen")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        size_box = QWidget()
        size_layout = QHBoxLayout(size_box)
        size_layout.setContentsMargins(0, 0, 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 7680)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 4320)
        size_layout.addWidget(self.width_spin)
        size_layout.addWidget(QLabel("x"))
        size_layout.addWidget(self.height_spin)
        size_layout.addStretch(1)
        self.embed_check = QCheckBox(tr("Embeber la sesión en una pestaña"))
        self.embed_check.setToolTip(
            tr("Si se desactiva, el visor se abre en su propia ventana del sistema.")
        )
        form.addRow(tr("Modo"), self.mode_combo)
        form.addRow(tr("Resolución"), size_box)
        form.addRow("", self.embed_check)
        return page

    def _tab_rdp(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(14)

        general = QGroupBox(tr("Sesión"))
        form = QFormLayout(general)
        form.setSpacing(11)
        form.setContentsMargins(14, 8, 14, 12)
        self.rdp_security = QComboBox()
        for label, value in (
            (tr("Automática"), "auto"), ("NLA", "nla"), ("TLS", "tls"),
            (tr("RDP clásico"), "rdp"),
        ):
            self.rdp_security.addItem(label, value)
        self.rdp_depth = QComboBox()
        for depth in (32, 24, 16, 15, 8):
            self.rdp_depth.addItem(f"{depth} {tr('bits')}", depth)
        self.rdp_network = QComboBox()
        for label, value in (
            (tr("Automática"), "auto"), ("LAN", "lan"), (tr("Banda ancha"), "broadband"),
            ("WAN", "wan"), (tr("Módem"), "modem"),
        ):
            self.rdp_network.addItem(label, value)
        self.rdp_scale = QSpinBox()
        self.rdp_scale.setRange(100, 180)
        self.rdp_scale.setSingleStep(40)
        self.rdp_scale.setSuffix(" %")
        self.rdp_kbd = QLineEdit()
        self.rdp_kbd.setPlaceholderText(tr("es, latam, 0x0000080A..."))
        form.addRow(tr("Seguridad"), self.rdp_security)
        form.addRow(tr("Profundidad de color"), self.rdp_depth)
        form.addRow(tr("Tipo de red"), self.rdp_network)
        form.addRow(tr("Escala"), self.rdp_scale)
        form.addRow(tr("Teclado"), self.rdp_kbd)
        layout.addWidget(general)

        options = QGroupBox(tr("Opciones"))
        grid = QGridLayout(options)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(9)
        grid.setContentsMargins(14, 8, 14, 12)
        self.rdp_console = QCheckBox(tr("Sesión de consola/admin"))
        self.rdp_clipboard = QCheckBox(tr("Portapapeles compartido"))
        self.rdp_gfx = QCheckBox(tr("Aceleración GFX (RemoteFX)"))
        self.rdp_dynres = QCheckBox(tr("Resolución dinámica"))
        self.rdp_smart = QCheckBox(tr("Escalar al tamaño de la ventana"))
        self.rdp_multimon = QCheckBox(tr("Multi-monitor"))
        self.rdp_drives = QCheckBox(tr("Redirigir unidades locales"))
        self.rdp_home = QCheckBox(tr("Redirigir carpeta personal"))
        self.rdp_printers = QCheckBox(tr("Redirigir impresoras"))
        self.rdp_smartcard = QCheckBox(tr("Redirigir lector de tarjetas"))
        self.rdp_mic = QCheckBox(tr("Micrófono"))
        self.rdp_cert = QCheckBox(tr("Ignorar errores de certificado"))
        widgets = [
            self.rdp_console, self.rdp_clipboard, self.rdp_gfx, self.rdp_dynres,
            self.rdp_smart, self.rdp_multimon, self.rdp_drives, self.rdp_home,
            self.rdp_printers, self.rdp_smartcard, self.rdp_mic, self.rdp_cert,
        ]
        for index, widget in enumerate(widgets):
            grid.addWidget(widget, index // 2, index % 2)
        layout.addWidget(options)

        extra = QGroupBox(tr("Audio, carpeta y pasarela"))
        form2 = QFormLayout(extra)
        form2.setSpacing(11)
        form2.setContentsMargins(14, 8, 14, 12)
        self.rdp_sound = QComboBox()
        for label, value in ((tr("Sin audio"), "off"), (tr("Reproducir aquí"), "local"),
                             (tr("Reproducir en el servidor"), "remote")):
            self.rdp_sound.addItem(label, value)
        share_box = QWidget()
        share_layout = QHBoxLayout(share_box)
        share_layout.setContentsMargins(0, 0, 0, 0)
        self.rdp_share = QLineEdit()
        self.rdp_share.setPlaceholderText(tr("Carpeta local a compartir"))
        browse = QPushButton("...")
        browse.setFixedWidth(40)
        browse.clicked.connect(self._pick_folder)
        share_layout.addWidget(self.rdp_share, 1)
        share_layout.addWidget(browse)
        self.rdp_gateway = QLineEdit()
        self.rdp_gateway.setPlaceholderText("gateway.dominio.com:443")
        self.rdp_gw_user = QLineEdit()
        self.rdp_gw_domain = QLineEdit()
        gw_pw, self.rdp_gw_pass = _password_field()
        self.rdp_extra = QLineEdit()
        self.rdp_extra.setPlaceholderText(tr("Argumentos adicionales de xfreerdp"))
        form2.addRow(tr("Audio"), self.rdp_sound)
        form2.addRow(tr("Carpeta"), share_box)
        form2.addRow(tr("Gateway"), self.rdp_gateway)
        form2.addRow(tr("Usuario gateway"), self.rdp_gw_user)
        form2.addRow(tr("Dominio gateway"), self.rdp_gw_domain)
        form2.addRow(tr("Contraseña gateway"), gw_pw)
        form2.addRow(tr("Extra"), self.rdp_extra)
        layout.addWidget(extra)
        layout.addStretch(1)
        return page

    def _tab_vnc(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setSpacing(11)
        self.vnc_encoding = QComboBox()
        for enc in ("Tight", "ZRLE", "Hextile", "Raw"):
            self.vnc_encoding.addItem(enc, enc)
        self.vnc_quality = QSpinBox()
        self.vnc_quality.setRange(0, 9)
        self.vnc_compress = QSpinBox()
        self.vnc_compress.setRange(0, 9)
        self.vnc_user = QLineEdit()
        self.vnc_user.setPlaceholderText(tr("Solo para VeNCrypt/Plain"))
        self.vnc_extra = QLineEdit()
        self.vnc_extra.setPlaceholderText(tr("Argumentos adicionales de vncviewer"))
        form.addRow(tr("Codificación"), self.vnc_encoding)
        form.addRow(tr("Calidad JPEG"), self.vnc_quality)
        form.addRow(tr("Compresión"), self.vnc_compress)
        form.addRow(tr("Usuario"), self.vnc_user)
        form.addRow(tr("Extra"), self.vnc_extra)
        layout.addLayout(form)

        options = QGroupBox(tr("Opciones"))
        grid = QGridLayout(options)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(9)
        grid.setContentsMargins(14, 8, 14, 12)
        self.vnc_viewonly = QCheckBox(tr("Solo lectura"))
        self.vnc_shared = QCheckBox(tr("Sesión compartida"))
        self.vnc_color = QCheckBox(tr("Color completo"))
        self.vnc_resize = QCheckBox(tr("Redimensionar el escritorio remoto"))
        for index, widget in enumerate(
            [self.vnc_viewonly, self.vnc_shared, self.vnc_color, self.vnc_resize]
        ):
            grid.addWidget(widget, index // 2, index % 2)
        layout.addWidget(options)
        layout.addStretch(1)
        return page

    def _tab_wol(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setSpacing(12)
        mac_box = QWidget()
        mac_layout = QHBoxLayout(mac_box)
        mac_layout.setContentsMargins(0, 0, 0, 0)
        self.wol_mac = QLineEdit()
        self.wol_mac.setPlaceholderText(tr("AA:BB:CC:DD:EE:FF"))
        detect = QPushButton(tr("Detectar"))
        detect.setToolTip(tr("Buscar la MAC en la tabla ARP local"))
        detect.clicked.connect(self._detect_mac)
        mac_layout.addWidget(self.wol_mac, 1)
        mac_layout.addWidget(detect)
        self.wol_broadcast = QLineEdit()
        self.wol_broadcast.setPlaceholderText("255.255.255.255")
        self.wol_port = QSpinBox()
        self.wol_port.setRange(1, 65535)
        self.wol_wait = QSpinBox()
        self.wol_wait.setRange(5, 600)
        self.wol_wait.setSuffix(" s")
        self.wol_auto = QCheckBox(tr("Despertar automáticamente antes de conectar"))
        form.addRow(tr("MAC"), mac_box)
        form.addRow(tr("Broadcast"), self.wol_broadcast)
        form.addRow(tr("Puerto"), self.wol_port)
        form.addRow(tr("Espera máxima"), self.wol_wait)
        form.addRow("", self.wol_auto)
        layout.addLayout(form)
        hint = QLabel(
            tr("El paquete mágico se envía por difusión UDP a los puertos 7 y 9. "
            "Para despertar equipos en otra subred, indica la dirección de "
            "difusión de esa red y permite el reenvío en el router.")
        )
        hint.setObjectName("SessionMsg")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _tab_notes(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 16)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(tr("Notas, inventario, contactos..."))
        layout.addWidget(self.notes_edit)
        return page

    # -------------------------------------------------------- carga
    def _load(self) -> None:
        s = self.server
        self.name_edit.setText(s.name)
        self.host_edit.setText(s.host)
        self.port_spin.setValue(s.port)
        self.proto_combo.setCurrentIndex(0 if s.protocol == RDP else 1)
        parent_id = s.parent.id if s.parent else self.store.root.id
        index = self.group_combo.findData(parent_id)
        self.group_combo.setCurrentIndex(max(0, index))
        self.tags_edit.setText(", ".join(s.tags))
        self.fav_check.setChecked(s.favorite)
        self.startup_check.setChecked(s.connect_on_startup)

        self.inherit_check.setChecked(s.credentials.inherit)
        self.user_edit.setText(s.credentials.username)
        self.domain_edit.setText(s.credentials.domain)
        self.pass_edit.setText(s.credentials.password())
        self._inherit_changed(s.credentials.inherit)

        self.mode_combo.setCurrentIndex(
            {"fit": 0, "fixed": 1, "fullscreen": 2}.get(s.display.mode, 0)
        )
        self.width_spin.setValue(s.display.width)
        self.height_spin.setValue(s.display.height)
        self.embed_check.setChecked(s.display.embed)
        self._mode_changed()

        o = s.rdp
        self.rdp_security.setCurrentIndex(max(0, self.rdp_security.findData(o.security)))
        self.rdp_depth.setCurrentIndex(max(0, self.rdp_depth.findData(o.color_depth)))
        self.rdp_network.setCurrentIndex(max(0, self.rdp_network.findData(o.network)))
        self.rdp_scale.setValue(o.scale if o.scale in (100, 140, 180) else 100)
        self.rdp_kbd.setText(o.keyboard_layout)
        self.rdp_console.setChecked(o.console)
        self.rdp_clipboard.setChecked(o.clipboard)
        self.rdp_gfx.setChecked(o.gfx)
        self.rdp_dynres.setChecked(o.dynamic_resolution)
        self.rdp_smart.setChecked(o.smart_sizing)
        self.rdp_multimon.setChecked(o.multimon)
        self.rdp_drives.setChecked(o.redirect_drives)
        self.rdp_home.setChecked(o.home_drive)
        self.rdp_printers.setChecked(o.printers)
        self.rdp_smartcard.setChecked(o.smartcard)
        self.rdp_mic.setChecked(o.microphone)
        self.rdp_cert.setChecked(o.ignore_cert)
        self.rdp_sound.setCurrentIndex(max(0, self.rdp_sound.findData(o.sound)))
        self.rdp_share.setText(o.shared_folder)
        self.rdp_gateway.setText(o.gateway)
        self.rdp_gw_user.setText(o.gateway_username)
        self.rdp_gw_domain.setText(o.gateway_domain)
        self.rdp_gw_pass.setText(o.gateway_password())
        self.rdp_extra.setText(o.extra_args)

        v = s.vnc
        self.vnc_encoding.setCurrentIndex(max(0, self.vnc_encoding.findData(v.encoding)))
        self.vnc_quality.setValue(v.quality)
        self.vnc_compress.setValue(v.compression)
        self.vnc_user.setText(v.username)
        self.vnc_extra.setText(v.extra_args)
        self.vnc_viewonly.setChecked(v.view_only)
        self.vnc_shared.setChecked(v.shared)
        self.vnc_color.setChecked(v.full_color)
        self.vnc_resize.setChecked(v.remote_resize)

        w = s.wol
        self.wol_mac.setText(w.mac)
        self.wol_broadcast.setText(w.broadcast)
        self.wol_port.setValue(w.port)
        self.wol_wait.setValue(w.wait_seconds)
        self.wol_auto.setChecked(w.auto)

        self.notes_edit.setPlainText(s.notes)
        self._proto_changed()

    # ------------------------------------------------------ reacciones
    def _proto_changed(self) -> None:
        is_rdp = self.proto_combo.currentData() == RDP
        self.tabs.setTabVisible(self.tabs.indexOf(self.rdp_tab), is_rdp)
        self.tabs.setTabVisible(self.tabs.indexOf(self.vnc_tab), not is_rdp)
        self.domain_edit.setEnabled(is_rdp)

    def _mode_changed(self) -> None:
        fixed = self.mode_combo.currentData() == "fixed"
        self.width_spin.setEnabled(fixed)
        self.height_spin.setEnabled(fixed)

    def _inherit_changed(self, checked: bool) -> None:
        self.cred_box.setEnabled(not checked)
        if checked:
            parent = self.server.parent
            inherited = None
            while parent is not None:
                if not parent.credentials.is_empty():
                    inherited = parent.credentials
                    break
                parent = parent.parent
            if inherited:
                who = inherited.username
                if inherited.domain:
                    who = f"{inherited.domain}\\{who}"
                self.inherited_label.setText(f"Se usaran las credenciales del grupo: {who}")
            else:
                self.inherited_label.setText(
                    tr("Ningún grupo padre tiene credenciales: se pedirán al conectar.")
                )
        else:
            self.inherited_label.setText("")

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Carpeta a compartir"))
        if folder:
            self.rdp_share.setText(folder)

    def _detect_mac(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.information(self, tr("Wake-on-LAN"), tr("Indica primero el host."))
            return
        mac = net.lookup_mac(host)
        if mac:
            self.wol_mac.setText(mac)
        else:
            QMessageBox.information(
                self,
                tr("Wake-on-LAN"),
                tr("No se encontró la MAC en la tabla ARP. Haz primero un ping al "
                "equipo estando encendido, o escríbela a mano."),
            )

    # -------------------------------------------------------- guardar
    def _accept(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, tr("Falta el host"), tr("Indica la IP o el nombre del equipo."))
            self.tabs.setCurrentIndex(0)
            self.host_edit.setFocus()
            return
        mac = self.wol_mac.text().strip()
        if mac and not net.is_valid_mac(mac):
            QMessageBox.warning(self, tr("MAC inválida"), tr("El formato debe ser AA:BB:CC:DD:EE:FF."))
            return
        self._save()
        self.accept()

    def _save(self) -> None:
        s = self.server
        s.name = self.name_edit.text().strip()
        s.host = self.host_edit.text().strip()
        s.port = self.port_spin.value()
        s.protocol = self.proto_combo.currentData()
        s.tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        s.favorite = self.fav_check.isChecked()
        s.connect_on_startup = self.startup_check.isChecked()

        s.credentials.inherit = self.inherit_check.isChecked()
        s.credentials.username = self.user_edit.text().strip()
        s.credentials.domain = self.domain_edit.text().strip()
        s.credentials.set_password(self.pass_edit.text())

        s.display.mode = self.mode_combo.currentData()
        s.display.width = self.width_spin.value()
        s.display.height = self.height_spin.value()
        s.display.embed = self.embed_check.isChecked()

        o = s.rdp
        o.security = self.rdp_security.currentData()
        o.color_depth = self.rdp_depth.currentData()
        o.network = self.rdp_network.currentData()
        o.scale = self.rdp_scale.value()
        o.keyboard_layout = self.rdp_kbd.text().strip()
        o.console = self.rdp_console.isChecked()
        o.clipboard = self.rdp_clipboard.isChecked()
        o.gfx = self.rdp_gfx.isChecked()
        o.dynamic_resolution = self.rdp_dynres.isChecked()
        o.smart_sizing = self.rdp_smart.isChecked()
        o.multimon = self.rdp_multimon.isChecked()
        o.redirect_drives = self.rdp_drives.isChecked()
        o.home_drive = self.rdp_home.isChecked()
        o.printers = self.rdp_printers.isChecked()
        o.smartcard = self.rdp_smartcard.isChecked()
        o.microphone = self.rdp_mic.isChecked()
        o.ignore_cert = self.rdp_cert.isChecked()
        o.sound = self.rdp_sound.currentData()
        o.shared_folder = self.rdp_share.text().strip()
        o.gateway = self.rdp_gateway.text().strip()
        o.gateway_username = self.rdp_gw_user.text().strip()
        o.gateway_domain = self.rdp_gw_domain.text().strip()
        from ..vault import vault

        o.gateway_secret = vault.encrypt(self.rdp_gw_pass.text())
        o.extra_args = self.rdp_extra.text().strip()

        v = s.vnc
        v.encoding = self.vnc_encoding.currentData()
        v.quality = self.vnc_quality.value()
        v.compression = self.vnc_compress.value()
        v.username = self.vnc_user.text().strip()
        v.extra_args = self.vnc_extra.text().strip()
        v.view_only = self.vnc_viewonly.isChecked()
        v.shared = self.vnc_shared.isChecked()
        v.full_color = self.vnc_color.isChecked()
        v.remote_resize = self.vnc_resize.isChecked()

        w = s.wol
        w.mac = net.normalize_mac(self.wol_mac.text()) if self.wol_mac.text().strip() else ""
        w.broadcast = self.wol_broadcast.text().strip() or "255.255.255.255"
        w.port = self.wol_port.value()
        w.wait_seconds = self.wol_wait.value()
        w.auto = self.wol_auto.isChecked()

        s.notes = self.notes_edit.toPlainText()

    @property
    def selected_group_id(self) -> str:
        return self.group_combo.currentData()


class GroupDialog(QDialog):
    def __init__(self, group: Group, settings, parent=None, is_new=False,
                 store=None, parent_group=None):
        super().__init__(parent)
        self.group = group
        self.store = store
        self.setWindowTitle(
            tr("Nuevo grupo") if is_new else f"{tr('Editar grupo')} · {group.label}"
        )
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(11)
        self.name_edit = QLineEdit(group.name)
        self.name_edit.setPlaceholderText(tr("Nombre del grupo"))
        form.addRow(tr("Nombre"), self.name_edit)

        self.parent_combo = QComboBox()
        if store is not None:
            forbidden = {group.id} | {n.id for n in group.walk()}
            for candidate in store.groups():
                if candidate.id in forbidden:
                    continue
                label = "Raíz" if candidate is store.root else _group_path(candidate)
                self.parent_combo.addItem(label, candidate.id)
            target = parent_group or group.parent or store.root
            index = self.parent_combo.findData(target.id)
            self.parent_combo.setCurrentIndex(max(0, index))
            form.addRow(tr("Dentro de"), self.parent_combo)
        layout.addLayout(form)

        box = QGroupBox(tr("Credenciales heredadas por los servidores del grupo"))
        gform = QFormLayout(box)
        self.user_edit = QLineEdit(group.credentials.username)
        self.domain_edit = QLineEdit(group.credentials.domain)
        pw_widget, self.pass_edit = _password_field()
        self.pass_edit.setText(group.credentials.password())
        gform.addRow(tr("Usuario"), self.user_edit)
        gform.addRow(tr("Dominio"), self.domain_edit)
        gform.addRow(tr("Contraseña"), pw_widget)
        layout.addWidget(box)

        self.notes_edit = QPlainTextEdit(group.notes)
        self.notes_edit.setPlaceholderText(tr("Notas del grupo"))
        self.notes_edit.setMaximumHeight(90)
        layout.addWidget(self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(tr("Guardar"))
        ok.setProperty("accent", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_parent_id(self) -> str | None:
        return self.parent_combo.currentData() if self.store is not None else None

    def _accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("Falta el nombre"), tr("El grupo necesita un nombre."))
            return
        self.group.name = name
        self.group.credentials.username = self.user_edit.text().strip()
        self.group.credentials.domain = self.domain_edit.text().strip()
        self.group.credentials.set_password(self.pass_edit.text())
        self.group.notes = self.notes_edit.toPlainText()
        self.accept()


class CredentialsPrompt(QDialog):
    """Pide credenciales al conectar cuando no hay ninguna guardada."""

    def __init__(self, server: Server, creds: Credentials, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('Credenciales')} · {server.label}")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        info = QLabel(f"{server.protocol.upper()} · {server.target}")
        info.setObjectName("SessionMsg")
        layout.addWidget(info)

        form = QFormLayout()
        self.user_edit = QLineEdit(creds.username)
        self.domain_edit = QLineEdit(creds.domain)
        pw_widget, self.pass_edit = _password_field()
        self.pass_edit.setText(creds.password())
        if server.protocol == RDP:
            form.addRow(tr("Usuario"), self.user_edit)
            form.addRow(tr("Dominio"), self.domain_edit)
        form.addRow(tr("Contraseña"), pw_widget)
        layout.addLayout(form)

        self.save_check = QCheckBox(tr("Guardar en este servidor"))
        self.save_check.setChecked(True)
        layout.addWidget(self.save_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(tr("Conectar"))
        ok.setProperty("accent", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        (self.pass_edit if creds.username else self.user_edit).setFocus()

    def values(self) -> tuple[str, str, str, bool]:
        return (
            self.user_edit.text().strip(),
            self.domain_edit.text().strip(),
            self.pass_edit.text(),
            self.save_check.isChecked(),
        )


class MasterPasswordDialog(QDialog):
    def __init__(self, mode: str = "ask", parent=None):
        """mode: ask | set"""
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle(tr("Contraseña maestra"))
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        text = (
            tr("Introduce la contraseña maestra para descifrar las credenciales.")
            if mode == "ask"
            else tr("Define una contraseña maestra. Sin ella no se podrán recuperar "
                    "las credenciales guardadas.")
        )
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("SessionMsg")
        layout.addWidget(label)

        form = QFormLayout()
        pw1, self.pass_edit = _password_field()
        form.addRow(tr("Contraseña"), pw1)
        if mode == "set":
            pw2, self.confirm_edit = _password_field()
            form.addRow(tr("Repetir"), pw2)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff5f6d;")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("accent", True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.pass_edit.setFocus()

    def _accept(self) -> None:
        if self.mode == "set":
            if len(self.pass_edit.text()) < 6:
                self.error_label.setText(tr("Usa al menos 6 caracteres."))
                return
            if self.pass_edit.text() != self.confirm_edit.text():
                self.error_label.setText(tr("Las contraseñas no coinciden."))
                return
        elif not self.pass_edit.text():
            self.error_label.setText(tr("Introduce la contraseña."))
            return
        self.accept()

    def password(self) -> str:
        return self.pass_edit.text()


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._old_language = settings["language"]
        self.setWindowTitle(tr("Preferencias"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        appearance = QGroupBox(tr("Apariencia"))
        form = QFormLayout(appearance)
        form.setSpacing(11)
        self.lang_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        index = self.lang_combo.findData(settings["language"])
        self.lang_combo.setCurrentIndex(max(0, index))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("Oscuro"), "dark")
        self.theme_combo.addItem(tr("Claro"), "light")
        self.theme_combo.setCurrentIndex(0 if settings["theme"] != "light" else 1)
        self.accent_edit = QLineEdit(settings["accent"])
        self.tabpos_combo = QComboBox()
        self.tabpos_combo.addItem(tr("Arriba"), "top")
        self.tabpos_combo.addItem(tr("Abajo"), "bottom")
        self.tabpos_combo.setCurrentIndex(0 if settings["tab_position"] == "top" else 1)
        form.addRow(tr("Idioma"), self.lang_combo)
        form.addRow(tr("Tema"), self.theme_combo)
        form.addRow(tr("Color de acento"), self.accent_edit)
        form.addRow(tr("Pestañas"), self.tabpos_combo)
        layout.addWidget(appearance)

        behaviour = QGroupBox(tr("Comportamiento"))
        form2 = QFormLayout(behaviour)
        self.dbl_check = QCheckBox(tr("Conectar al hacer doble clic"))
        self.dbl_check.setChecked(bool(settings["connect_on_double_click"]))
        self.confirm_check = QCheckBox(tr("Confirmar antes de cerrar una sesión activa"))
        self.confirm_check.setChecked(bool(settings["confirm_close_session"]))
        self.status_check = QCheckBox(tr("Comprobar el estado de los equipos"))
        self.status_check.setChecked(bool(settings["status_check"]))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(15, 3600)
        self.interval_spin.setSuffix(" s")
        self.interval_spin.setValue(int(settings["status_interval"]))
        form2.addRow("", self.dbl_check)
        form2.addRow("", self.confirm_check)
        form2.addRow("", self.status_check)
        form2.addRow(tr("Intervalo"), self.interval_spin)
        layout.addWidget(behaviour)

        binaries = QGroupBox(tr("Visores"))
        form3 = QFormLayout(binaries)
        self.rdp_bin = QLineEdit(settings["rdp_binary"])
        self.rdp_bin.setPlaceholderText(tr("xfreerdp3 (automático)"))
        self.vnc_bin = QLineEdit(settings["vnc_binary"])
        self.vnc_bin.setPlaceholderText(tr("vncviewer (automático)"))
        form3.addRow(tr("RDP"), self.rdp_bin)
        form3.addRow(tr("VNC"), self.vnc_bin)
        layout.addWidget(binaries)

        security = QGroupBox(tr("Seguridad"))
        vbox = QVBoxLayout(security)
        from ..vault import vault

        state = (
            tr("Las credenciales se cifran con una contraseña maestra.")
            if vault.mode == "master"
            else tr("Las credenciales se cifran con una clave local (fichero 0600).")
        )
        label = QLabel(state)
        label.setWordWrap(True)
        label.setObjectName("SessionMsg")
        vbox.addWidget(label)
        row = QHBoxLayout()
        self.master_btn = QPushButton(
            "Quitar contraseña maestra" if vault.mode == "master"
            else "Definir contraseña maestra"
        )
        row.addWidget(self.master_btn)
        row.addStretch(1)
        vbox.addLayout(row)
        layout.addWidget(security)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Guardar"))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("accent", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def language_changed(self) -> bool:
        return self._old_language != self.lang_combo.currentData()

    def _accept(self) -> None:
        self.settings["language"] = self.lang_combo.currentData()
        self.settings["theme"] = self.theme_combo.currentData()
        accent = self.accent_edit.text().strip()
        self.settings["accent"] = accent if accent.startswith("#") else "#4c8dff"
        self.settings["tab_position"] = self.tabpos_combo.currentData()
        self.settings["connect_on_double_click"] = self.dbl_check.isChecked()
        self.settings["confirm_close_session"] = self.confirm_check.isChecked()
        self.settings["status_check"] = self.status_check.isChecked()
        self.settings["status_interval"] = self.interval_spin.value()
        self.settings["rdp_binary"] = self.rdp_bin.text().strip()
        self.settings["vnc_binary"] = self.vnc_bin.text().strip()
        self.settings.save()
        self.accept()
