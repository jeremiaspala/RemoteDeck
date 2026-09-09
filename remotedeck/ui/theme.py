"""Paleta y hoja de estilos."""

from __future__ import annotations

DARK = {
    "bg": "#0f121a",
    "bg_alt": "#151926",
    "panel": "#171c2b",
    "panel_alt": "#1d2436",
    "border": "#262d42",
    "text": "#dbe2f2",
    "text_dim": "#8b94ad",
    "text_faint": "#5d6680",
    "accent": "#4c8dff",
    "accent_soft": "#22314f",
    "ok": "#3ecf8e",
    "warn": "#f5b544",
    "error": "#ff5f6d",
    "shadow": "rgba(0,0,0,0.45)",
}

LIGHT = {
    "bg": "#f4f6fb",
    "bg_alt": "#eaeef7",
    "panel": "#ffffff",
    "panel_alt": "#f1f4fb",
    "border": "#d6dcea",
    "text": "#1a2033",
    "text_dim": "#5d6680",
    "text_faint": "#8b94ad",
    "accent": "#2f6fe4",
    "accent_soft": "#dde8ff",
    "ok": "#12a06a",
    "warn": "#c98708",
    "error": "#d93a4a",
    "shadow": "rgba(30,40,70,0.14)",
}


def palette(theme: str, accent: str | None = None) -> dict[str, str]:
    base = dict(LIGHT if theme == "light" else DARK)
    if accent:
        base["accent"] = accent
    return base


def stylesheet(theme: str = "dark", accent: str | None = None) -> str:
    c = palette(theme, accent)
    return f"""
* {{ outline: none; }}

QWidget {{
    background: {c['bg']};
    color: {c['text']};
    font-family: "Inter", "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}}

QMainWindow::separator {{ background: {c['border']}; width: 1px; height: 1px; }}

/* ---------- Barra lateral ---------- */
#Sidebar {{ background: {c['bg_alt']}; border-right: 1px solid {c['border']}; }}
#SidebarHeader {{ background: transparent; padding: 0; }}
#BrandLabel {{ font-size: 15px; font-weight: 700; letter-spacing: 0.3px; }}
#BrandSub {{ color: {c['text_faint']}; font-size: 11px; }}

QTreeWidget {{
    background: transparent;
    border: none;
    padding: 4px 6px;
    show-decoration-selected: 1;
}}
QTreeWidget::item {{
    height: 30px;
    border-radius: 7px;
    padding-left: 2px;
    color: {c['text']};
}}
QTreeWidget::item:hover {{ background: {c['panel_alt']}; }}
QTreeWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
QTreeWidget::branch {{ background: transparent; }}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {{
    image: none; border-image: none;
}}

/* ---------- Campos ---------- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {c['accent']};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {c['accent']};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {c['text_faint']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {c['accent_soft']};
}}
#SearchBox {{ background: {c['panel']}; border-radius: 9px; padding: 7px 10px; }}

/* ---------- Botones ---------- */
QPushButton {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 7px 14px;
    color: {c['text']};
}}
QPushButton:hover {{ background: {c['panel']}; border-color: {c['accent']}; }}
QPushButton:pressed {{ background: {c['accent_soft']}; }}
QPushButton:disabled {{ color: {c['text_faint']}; border-color: {c['border']}; }}
QPushButton[accent="true"] {{
    background: {c['accent']};
    border: 1px solid {c['accent']};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {c['accent']}; border-color: #ffffff33; }}
QPushButton[flat="true"] {{ background: transparent; border: none; padding: 6px; }}
QPushButton[flat="true"]:hover {{ background: {c['panel_alt']}; }}
QPushButton[danger="true"]:hover {{ border-color: {c['error']}; color: {c['error']}; }}

/* ---------- Pestanas ---------- */
QTabWidget::pane {{ border: none; background: {c['bg']}; }}
QTabBar {{ background: {c['bg_alt']}; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {c['text_dim']};
    padding: 9px 16px;
    margin: 5px 2px 5px 0;
    border-radius: 8px;
    max-width: 240px;
}}
QTabBar::tab:hover {{ background: {c['panel_alt']}; color: {c['text']}; }}
QTabBar::tab:selected {{ background: {c['panel']}; color: {c['text']}; }}
QTabBar::close-button {{ image: none; subcontrol-position: right; }}

/* ---------- Barra de herramientas y estado ---------- */
QToolBar {{
    background: {c['bg_alt']};
    border-bottom: 1px solid {c['border']};
    padding: 5px 8px;
    spacing: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 10px;
    color: {c['text_dim']};
}}
QToolBar QToolButton:hover {{ background: {c['panel_alt']}; color: {c['text']}; }}
QToolBar QToolButton:pressed {{ background: {c['accent_soft']}; }}
QToolBar QToolButton:disabled {{ color: {c['text_faint']}; }}
QStatusBar {{
    background: {c['bg_alt']};
    border-top: 1px solid {c['border']};
    color: {c['text_dim']};
}}
QStatusBar::item {{ border: none; }}

/* ---------- Menus ---------- */
QMenuBar {{ background: {c['bg_alt']}; border-bottom: 1px solid {c['border']}; }}
QMenuBar::item {{ padding: 6px 11px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {c['panel_alt']}; }}
QMenu {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['accent_soft']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

/* ---------- Varios ---------- */
QGroupBox {{
    border: 1px solid {c['border']};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px;
    font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; color: {c['text_dim']}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {c['border']};
    border-radius: 4px;
    background: {c['panel']};
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']};
}}
QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {c['accent']}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {c['border']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QToolTip {{
    background: {c['panel']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 5px 8px;
}}
QTabWidget#Editor::pane {{ border: 1px solid {c['border']}; border-radius: 10px; }}

/* ---------- Sesion ---------- */
#SessionOverlay {{ background: {c['bg']}; }}
#SessionTitle {{ font-size: 17px; font-weight: 600; }}
#SessionMsg {{ color: {c['text_dim']}; }}
#SessionLog {{
    background: {c['bg_alt']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 11px;
    color: {c['text_dim']};
}}
#Welcome {{ background: {c['bg']}; }}
#WelcomeTitle {{ font-size: 24px; font-weight: 700; }}
#WelcomeSub {{ color: {c['text_dim']}; font-size: 13px; }}
#Card {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}
#Pill {{
    background: {c['panel_alt']};
    border: 1px solid {c['border']};
    border-radius: 11px;
    padding: 2px 9px;
    color: {c['text_dim']};
    font-size: 11px;
}}
"""
