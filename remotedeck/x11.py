"""Envoltura minima de Xlib via ctypes para embeber ventanas externas.

Solo se usa lo imprescindible: buscar la ventana de un proceso hijo,
reparentarla dentro de un contenedor Qt y redimensionarla.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from typing import Optional

_lib_name = ctypes.util.find_library("X11") or "libX11.so.6"

try:
    _x11 = ctypes.cdll.LoadLibrary(_lib_name)
except OSError:  # pragma: no cover - sistema sin X11
    _x11 = None

Window = ctypes.c_ulong
Atom = ctypes.c_ulong


class XWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("border_width", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("visual", ctypes.c_void_p),
        ("root", Window),
        ("class_", ctypes.c_int),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("map_installed", ctypes.c_int),
        ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long),
        ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("screen", ctypes.c_void_p),
    ]


class _ClientMessageData(ctypes.Union):
    _fields_ = [
        ("b", ctypes.c_char * 20),
        ("s", ctypes.c_short * 10),
        ("l", ctypes.c_long * 5),
    ]


class XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", Window),
        ("message_type", Atom),
        ("format", ctypes.c_int),
        ("data", _ClientMessageData),
    ]


class XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xclient", XClientMessageEvent), ("pad", ctypes.c_long * 24)]


if _x11 is not None:
    _x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    _x11.XOpenDisplay.restype = ctypes.c_void_p
    _x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    _x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    _x11.XDefaultRootWindow.restype = Window
    _x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    _x11.XInternAtom.restype = Atom
    _x11.XQueryTree.argtypes = [
        ctypes.c_void_p,
        Window,
        ctypes.POINTER(Window),
        ctypes.POINTER(Window),
        ctypes.POINTER(ctypes.POINTER(Window)),
        ctypes.POINTER(ctypes.c_uint),
    ]
    _x11.XGetWindowProperty.argtypes = [
        ctypes.c_void_p,
        Window,
        Atom,
        ctypes.c_long,
        ctypes.c_long,
        ctypes.c_int,
        Atom,
        ctypes.POINTER(Atom),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    _x11.XFree.argtypes = [ctypes.c_void_p]
    _x11.XReparentWindow.argtypes = [ctypes.c_void_p, Window, Window, ctypes.c_int, ctypes.c_int]
    _x11.XMoveResizeWindow.argtypes = [
        ctypes.c_void_p,
        Window,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    _x11.XResizeWindow.argtypes = [ctypes.c_void_p, Window, ctypes.c_uint, ctypes.c_uint]
    _x11.XMapWindow.argtypes = [ctypes.c_void_p, Window]
    _x11.XUnmapWindow.argtypes = [ctypes.c_void_p, Window]
    _x11.XFlush.argtypes = [ctypes.c_void_p]
    _x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _x11.XGetWindowAttributes.argtypes = [
        ctypes.c_void_p,
        Window,
        ctypes.POINTER(XWindowAttributes),
    ]
    _x11.XSendEvent.argtypes = [
        ctypes.c_void_p,
        Window,
        ctypes.c_int,
        ctypes.c_long,
        ctypes.POINTER(XEvent),
    ]
    _x11.XSetInputFocus.argtypes = [ctypes.c_void_p, Window, ctypes.c_int, ctypes.c_ulong]
    _x11.XSetErrorHandler.argtypes = [ctypes.c_void_p]
    _x11.XSetErrorHandler.restype = ctypes.c_void_p

_ERROR_HANDLER_T = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


def _ignore_errors(display, event):  # pragma: no cover
    return 0


_error_handler = _ERROR_HANDLER_T(_ignore_errors)


class X11:
    """Conexion X11 propia (independiente de la de Qt)."""

    def __init__(self) -> None:
        self.display: Optional[int] = None
        if _x11 is None:
            return
        name = os.environ.get("DISPLAY")
        if not name:
            return
        self.display = _x11.XOpenDisplay(name.encode())
        if self.display:
            _x11.XSetErrorHandler(_error_handler)

    @property
    def available(self) -> bool:
        return bool(self.display)

    def close(self) -> None:
        if self.display:
            _x11.XCloseDisplay(self.display)
            self.display = None

    # -- consultas ------------------------------------------------------
    def root(self) -> int:
        return int(_x11.XDefaultRootWindow(self.display))

    def atom(self, name: str, only_if_exists: bool = True) -> int:
        return int(_x11.XInternAtom(self.display, name.encode(), 1 if only_if_exists else 0))

    def children(self, window: int) -> list[int]:
        root = Window()
        parent = Window()
        kids = ctypes.POINTER(Window)()
        count = ctypes.c_uint()
        ok = _x11.XQueryTree(
            self.display,
            Window(window),
            ctypes.byref(root),
            ctypes.byref(parent),
            ctypes.byref(kids),
            ctypes.byref(count),
        )
        if not ok:
            return []
        out = [int(kids[i]) for i in range(count.value)]
        if kids:
            _x11.XFree(kids)
        return out

    def _cardinal(self, window: int, atom_name: str) -> Optional[int]:
        prop = self.atom(atom_name)
        if not prop:
            return None
        actual_type = Atom()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        data = ctypes.POINTER(ctypes.c_ubyte)()
        status = _x11.XGetWindowProperty(
            self.display,
            Window(window),
            prop,
            0,
            1,
            0,
            0,  # AnyPropertyType
            ctypes.byref(actual_type),
            ctypes.byref(actual_format),
            ctypes.byref(nitems),
            ctypes.byref(bytes_after),
            ctypes.byref(data),
        )
        value = None
        if status == 0 and nitems.value > 0 and data:
            value = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[0]
        if data:
            _x11.XFree(data)
        return int(value) if value is not None else None

    def window_pid(self, window: int) -> Optional[int]:
        return self._cardinal(window, "_NET_WM_PID")

    def has_wm_state(self, window: int) -> bool:
        return self._cardinal(window, "WM_STATE") is not None

    def geometry(self, window: int) -> Optional[tuple[int, int, int, int]]:
        attrs = XWindowAttributes()
        if not _x11.XGetWindowAttributes(self.display, Window(window), ctypes.byref(attrs)):
            return None
        return attrs.x, attrs.y, attrs.width, attrs.height

    def exists(self, window: int) -> bool:
        return self.geometry(window) is not None

    # -- busqueda -------------------------------------------------------
    def find_by_pid(self, pids: set[int], skip: set[int] | None = None) -> Optional[int]:
        """Busca una ventana cliente (con WM_STATE o _NET_WM_PID) de esos PIDs."""
        skip = skip or set()
        root = self.root()
        stack = list(self.children(root))
        depth = 0
        while stack and depth < 4:
            next_level: list[int] = []
            for win in stack:
                if win in skip:
                    continue
                pid = self.window_pid(win)
                if pid in pids:
                    client = self._client_window(win) or win
                    return client
                next_level.extend(self.children(win))
            stack = next_level
            depth += 1
        return None

    def _client_window(self, window: int) -> Optional[int]:
        """Si la ventana es un frame del WM, baja al cliente real."""
        if self.has_wm_state(window):
            return window
        for child in self.children(window):
            if self.has_wm_state(child):
                return child
        return None

    # -- manipulacion ---------------------------------------------------
    def reparent(self, window: int, parent: int, x: int = 0, y: int = 0) -> None:
        _x11.XReparentWindow(self.display, Window(window), Window(parent), x, y)
        _x11.XFlush(self.display)

    def move_resize(self, window: int, x: int, y: int, width: int, height: int) -> None:
        _x11.XMoveResizeWindow(
            self.display, Window(window), x, y, max(1, width), max(1, height)
        )
        _x11.XFlush(self.display)

    def map(self, window: int) -> None:
        _x11.XMapWindow(self.display, Window(window))
        _x11.XFlush(self.display)

    def focus(self, window: int) -> None:
        # RevertToParent = 2, CurrentTime = 0
        _x11.XSetInputFocus(self.display, Window(window), 2, 0)
        _x11.XFlush(self.display)

    def close_window(self, window: int) -> bool:
        """Envia WM_DELETE_WINDOW (cierre limpio)."""
        wm_protocols = self.atom("WM_PROTOCOLS")
        wm_delete = self.atom("WM_DELETE_WINDOW")
        if not wm_protocols or not wm_delete:
            return False
        event = XEvent()
        event.xclient.type = 33  # ClientMessage
        event.xclient.serial = 0
        event.xclient.send_event = 1
        event.xclient.display = self.display
        event.xclient.window = window
        event.xclient.message_type = wm_protocols
        event.xclient.format = 32
        event.xclient.data.l[0] = wm_delete
        event.xclient.data.l[1] = 0
        _x11.XSendEvent(self.display, Window(window), 0, 0, ctypes.byref(event))
        _x11.XFlush(self.display)
        return True

    def sync(self) -> None:
        if self.display:
            _x11.XSync(self.display, 0)


_shared: Optional[X11] = None


def shared() -> X11:
    global _shared
    if _shared is None:
        _shared = X11()
    return _shared


def available() -> bool:
    return shared().available
