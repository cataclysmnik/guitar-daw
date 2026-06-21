import platform
import ctypes
import os
import sys
from ctypes import wintypes
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QMouseEvent

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Win32 Constants for native resizing and dragging
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]

class FramelessWindowMixin:
    """
    Mixin class that handles native Windows border resizing, shadows, system menus,
    and dragging by extending the client area and intercepting DWM hit tests.
    """
    def init_frameless(self, title_bar_widget, border_width=6):
        self.title_bar = title_bar_widget
        self.border_width = border_width
        
        if platform.system() == "Windows":
            # Force Windows to recalculate the frame size and trigger WM_NCCALCSIZE immediately
            try:
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_FRAMECHANGED = 0x0020
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
            except Exception as e:
                pass
        else:
            # On non-Windows platforms, we fall back to standard frameless window mode
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)

    def nativeEvent(self, eventType, message):
        if platform.system() != "Windows":
            return super().nativeEvent(eventType, message)
            
        try:
            # Cast void_p from Qt to MSG struct
            msg = MSG.from_address(int(message))
            
            # Extend client area to window size (hides native titlebar, keeps shadows & resizing)
            if msg.message == WM_NCCALCSIZE:
                return True, 0
                
            if msg.message == WM_NCHITTEST:
                # Call standard Win32 DefWindowProcW to let OS calculate resize borders
                user32 = ctypes.windll.user32
                user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
                user32.DefWindowProcW.restype = ctypes.c_void_p
                
                hit_test = user32.DefWindowProcW(
                    ctypes.c_void_p(msg.hwnd),
                    ctypes.c_uint(msg.message),
                    ctypes.c_void_p(msg.wParam),
                    ctypes.c_void_p(msg.lParam)
                )
                
                # If cursor is over standard resize borders, return native hit tests
                if hit_test in (HTLEFT, HTRIGHT, HTTOP, HTBOTTOM, HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT):
                    return True, hit_test
                    
                # Otherwise, check if cursor is over our CustomTitleBar
                x = msg.pt.x
                y = msg.pt.y
                if hasattr(self, 'title_bar') and self.title_bar:
                    dpi = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0
                    local_pos = self.title_bar.mapFromGlobal(QPoint(int(x / dpi), int(y / dpi)))
                    if self.title_bar.rect().contains(local_pos):
                        # Keep control buttons active under Qt
                        over_button = False
                        if hasattr(self.title_bar, 'btn_close') and self.title_bar.btn_close.geometry().contains(local_pos):
                            over_button = True
                        elif hasattr(self.title_bar, 'btn_min') and self.title_bar.btn_min.geometry().contains(local_pos):
                            over_button = True
                        elif hasattr(self.title_bar, 'btn_max') and self.title_bar.btn_max.geometry().contains(local_pos):
                            over_button = True
                            
                        if not over_button:
                            return True, HTCAPTION
                            
        except Exception as e:
            pass
            
        return super().nativeEvent(eventType, message)


class CustomTitleBar(QWidget):
    """
    A custom-painted window titlebar widget following Nothing's design aesthetic.
    Features monospaced Consolas typography, flat styling, and mouse dragging/max/min hooks.
    """
    def __init__(self, parent_window, title_text="GRAPHITE", can_maximize=False, can_minimize=True):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.can_maximize = can_maximize
        self.can_minimize = can_minimize
        
        self.drag_position = QPoint()
        
        self.setFixedHeight(30)
        self.setObjectName("CustomTitleBar")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 0, 0)
        layout.setSpacing(0)
        
        # Window Title label
        self.title_label = QLabel(title_text.upper())
        self.title_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 1.0px;")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Minimize button
        if self.can_minimize:
            self.btn_min = QPushButton("—")
            self.btn_min.setObjectName("TitleMinBtn")
            self.btn_min.setFixedSize(30, 30)
            self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_min.clicked.connect(self.parent_window.showMinimized)
            layout.addWidget(self.btn_min)
            
        # Maximize button
        if self.can_maximize:
            self.btn_max = QPushButton("☐")
            self.btn_max.setObjectName("TitleMaxBtn")
            self.btn_max.setFixedSize(30, 30)
            self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_max.clicked.connect(self.toggle_maximize)
            layout.addWidget(self.btn_max)
            
        # Close button
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("TitleCloseBtn")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.parent_window.close)
        layout.addWidget(self.btn_close)
        
        # Apply Nothing design QSS styling
        self.setStyleSheet("""
            QWidget#CustomTitleBar {
                background-color: #000000;
                border-bottom: 1px solid #222225;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #88888c;
                font-family: "Consolas", monospace;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ffffff;
                color: #000000;
            }
            QPushButton#TitleCloseBtn:hover {
                background-color: #ff0033;
                color: #ffffff;
            }
        """)

    def toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.btn_max.setText("☐")
        else:
            self.parent_window.showMaximized()
            self.btn_max.setText("⧉")

    # Drag window methods (only used on macOS/Linux as fallback; Windows uses nativeEvent)
    def mousePressEvent(self, event: QMouseEvent):
        if platform.system() == "Windows":
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if platform.system() == "Windows":
            event.ignore()
            return
        if event.buttons() == Qt.MouseButton.LeftButton:
            if not self.parent_window.isMaximized():
                self.parent_window.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()

def apply_dark_titlebar(window):
    """
    Forces the native Windows titlebar to use Dark Mode, matching the Graphite dark theme.
    (Retained as legacy fallback for standard window instances).
    """
    if platform.system() != "Windows":
        return

    try:
        hwnd = int(window.winId())
        set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        set_window_attribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        set_window_attribute.restype = ctypes.c_int
        
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
        
        rendering_policy = ctypes.c_int(1)
        res = set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))
        if res != 0:
            set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))
            
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
            
    except Exception as e:
        print(f"Warning: Could not apply dark titlebar theme: {e}")
