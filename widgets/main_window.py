import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFileDialog, QSplitter, QSlider,
    QMessageBox, QTabWidget, QFrame, QMenuBar, QSizeGrip, QStackedWidget,
    QApplication, QButtonGroup
)
from PySide6.QtCore import Qt, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QFont, QIcon, QAction, QKeySequence
from audio_engine import AudioEngine
from widgets.track_card import TrackCard
from widgets.effects_rack import EffectsRack
from widgets.level_meter import LevelMeter
from widgets.audio_settings import AudioSettingsDialog
from widgets.timeline import TimelineScrollContainer
from widgets.tuner import GuitarTunerWidget
from widgets.metronome import GuitarMetronomeWidget
from widgets.mixer import MixerWidget
from widgets.signal_flow import SignalFlowWidget
import project_manager

class TracksContainer(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setAcceptDrops(True)
        self.drop_indicator_y = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            drop_pos = event.position().toPoint()
            self.drop_indicator_y = self.main_window.calculate_drop_line_y(drop_pos.y())
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_indicator_y = None
        self.update()
        event.accept()

    def dropEvent(self, event):
        track_id_str = event.mimeData().text()
        try:
            track_id = int(track_id_str)
        except ValueError:
            event.ignore()
            return
            
        drop_pos = event.position().toPoint()
        self.drop_indicator_y = None
        self.update()
        self.main_window.reorder_tracks(track_id, drop_pos.y())
        event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drop_indicator_y is not None:
            from PySide6.QtGui import QPainter, QPen, QColor
            painter = QPainter(self)
            try:
                painter.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine))
                painter.drawLine(0, self.drop_indicator_y, self.width(), self.drop_indicator_y)
            finally:
                painter.end()

from theme_utils import FramelessWindowMixin

def apply_dark_theme_to_hwnd(hwnd):
    try:
        import ctypes
        dwmapi = ctypes.windll.dwmapi
        user32 = ctypes.windll.user32
        
        # 1. Enable Immersive Dark Mode
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
        use_dark = ctypes.c_int(1)
        res = dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(use_dark), ctypes.sizeof(use_dark)
        )
        if res != 0:
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                ctypes.byref(use_dark), ctypes.sizeof(use_dark)
            )
            
        # 2. Customize border and caption colors (Windows 11)
        DWMWA_CAPTION_COLOR = 35
        black_color = ctypes.c_int(0x00000000)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR,
            ctypes.byref(black_color), ctypes.sizeof(black_color)
        )
        
        DWMWA_TEXT_COLOR = 36
        white_color = ctypes.c_int(0x00FFFFFF)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_TEXT_COLOR,
            ctypes.byref(white_color), ctypes.sizeof(white_color)
        )
        
        DWMWA_BORDER_COLOR = 34
        border_color = ctypes.c_int(0x00252222)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_BORDER_COLOR,
            ctypes.byref(border_color), ctypes.sizeof(border_color)
        )
        
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception as e:
        print(f"Failed to apply dark theme to hwnd: {e}")

def run_in_dpi_context(hwnd, func):
    if not hwnd:
        return func()
    try:
        import ctypes
        user32 = ctypes.windll.user32
        if hasattr(user32, "GetWindowDpiAwarenessContext") and hasattr(user32, "SetThreadDpiAwarenessContext"):
            user32.GetWindowDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            user32.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
            user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            
            ctx = user32.GetWindowDpiAwarenessContext(hwnd)
            if ctx:
                old_ctx = user32.SetThreadDpiAwarenessContext(ctx)
                try:
                    return func()
                finally:
                    if old_ctx:
                        user32.SetThreadDpiAwarenessContext(old_ctx)
    except Exception as e:
        print(f"DPI context wrapper warning: {e}")
    return func()

class MainWindow(FramelessWindowMixin, QMainWindow):
    """Core Main Window for the Guitar DAW application."""
    def __init__(self, splash=None):
        super().__init__()
        self.setWindowTitle("Graphite")
        self.setMinimumSize(950, 600)
        self.setObjectName("MainWindow")
        
        if splash:
            splash.set_status("Initializing Audio Engine...", 30)
        # Initialize Audio Engine
        self.audio_engine = AudioEngine()
        
        if splash:
            splash.set_status("Creating default tracks...", 50)
        # Add default track
        self.audio_engine.add_track("Lead Guitar")
        self.audio_engine.add_track("Rhythm Guitar")
        
        self.track_cards = []
        self.selected_track = None
        self.current_project_path = None
        self.project_dirty = False
        
        # VST Embedded Settings state attributes
        self._vst_hwnd = None
        self._original_style = None
        self._last_vst_size = None
        self._vst_borders = (0, 0)
        self.active_vst_card = None
        self.pending_vst_to_open = None
        self.vst_loop_running = False
        self._vst_hook_cb = None
        self._enforce_timer = QTimer(self)
        self._enforce_timer.setInterval(50)
        self._enforce_timer.timeout.connect(self._enforce_vst_window)
        
        if splash:
            splash.set_status("Building GUI widgets...", 70)
        self.setup_ui()
        self.init_frameless(self.title_bar)
        
        # Load startup project if set
        startup_path = getattr(self.audio_engine, "startup_project_path", "")
        if startup_path and os.path.exists(startup_path):
            try:
                import project_manager
                success = project_manager.load_project(startup_path, self.audio_engine)
                if success:
                    print(f"Loaded startup project: {startup_path}")
                    self.refresh_track_cards()
                    if hasattr(self, 'mixer_widget'):
                        self.mixer_widget.rebuild()
            except Exception as e:
                print(f"Failed to load startup project: {e}")
        
        # Select first track by default
        if self.track_cards:
            self.track_cards[0].set_selected(True)
            
        # Start master meter polling timer
        self.master_timer = QTimer(self)
        self.master_timer.timeout.connect(self.update_master_levels)
        self.master_timer.start(33)
        
        if splash:
            splash.set_status("Starting Audio Stream...", 90)
        # Start the audio stream at startup automatically
        self.audio_engine.start_stream()
        self.update_stream_btn_style()
        
        if splash:
            splash.set_status("Graphite ready!", 100)
        self.update_title_bar()
        
    def update_title_bar(self, status=None):
        if not hasattr(self, 'title_bar') or not self.title_bar:
            return
        title = "GRAPHITE"
        if hasattr(self, 'current_project_path') and self.current_project_path:
            project_name = os.path.basename(self.current_project_path)
            project_name = os.path.splitext(project_name)[0]
            title += f" — {project_name}"
        else:
            title += " — [UNTITLED]"
        if hasattr(self, 'project_dirty') and self.project_dirty:
            title += " *"
        if status:
            title += f" [{status}]"
        self.title_bar.title_label.setText(title.upper())

    def mark_project_dirty(self):
        if not hasattr(self, 'project_dirty') or not self.project_dirty:
            self.project_dirty = True
            self.update_title_bar()
        
    def setup_ui(self):
        # Main central widget
        central_widget = QWidget(self)
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Custom Title Bar
        from theme_utils import CustomTitleBar
        self.title_bar = CustomTitleBar(self, title_text="GRAPHITE", can_maximize=True, can_minimize=True)
        main_layout.addWidget(self.title_bar)
        
        # --- 1. GLOBAL TOP MENU BAR ---
        menu_bar = QMenuBar(self)
        main_layout.addWidget(menu_bar)
        
        # Main workspace content container
        content_widget = QWidget(self)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)
        
        # File Menu
        file_menu = menu_bar.addMenu("File")
        
        self.action_new = QAction("New Project", self)
        self.action_new.setShortcut(QKeySequence("Ctrl+N"))
        self.action_new.triggered.connect(self.on_new_project)
        file_menu.addAction(self.action_new)
        
        self.action_load = QAction("Open Project...", self)
        self.action_load.setShortcut(QKeySequence("Ctrl+O"))
        self.action_load.triggered.connect(self.on_load_project)
        file_menu.addAction(self.action_load)
        
        self.action_save = QAction("Save Project", self)
        self.action_save.setShortcut(QKeySequence("Ctrl+S"))
        self.action_save.triggered.connect(self.on_save_project)
        file_menu.addAction(self.action_save)
        
        self.action_export = QAction("Export Audio...", self)
        self.action_export.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export.triggered.connect(self.on_export_audio)
        file_menu.addAction(self.action_export)
        
        file_menu.addSeparator()
        
        self.action_exit = QAction("Exit", self)
        self.action_exit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_exit.triggered.connect(self.close)
        file_menu.addAction(self.action_exit)
        
        # Track Menu
        track_menu = menu_bar.addMenu("Track")
        
        self.action_add_track = QAction("Add Track", self)
        self.action_add_track.setShortcut(QKeySequence("Ctrl+T"))
        self.action_add_track.triggered.connect(self.on_add_track)
        track_menu.addAction(self.action_add_track)
        
        self.action_add_backing_track = QAction("Add Backing Track...", self)
        self.action_add_backing_track.setShortcut(QKeySequence("Ctrl+B"))
        self.action_add_backing_track.triggered.connect(self.on_add_backing_track)
        track_menu.addAction(self.action_add_backing_track)
        
        # Audio Menu
        audio_menu = menu_bar.addMenu("Audio")
        
        self.action_stream = QAction("Toggle Play / Stop", self)
        self.action_stream.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self.action_stream.triggered.connect(self.toggle_play_stop)
        audio_menu.addAction(self.action_stream)
        
        self.action_pause = QAction("Pause Audio", self)
        self.action_pause.setShortcut(QKeySequence("Ctrl+Space"))
        self.action_pause.triggered.connect(self.on_transport_pause)
        audio_menu.addAction(self.action_pause)
        
        self.action_record = QAction("Record Track", self)
        self.action_record.setShortcut(QKeySequence("R"))
        self.action_record.triggered.connect(self.toggle_record)
        audio_menu.addAction(self.action_record)
        
        self.action_home = QAction("Go to Start", self)
        self.action_home.setShortcut(QKeySequence("Home"))
        self.action_home.triggered.connect(self.on_transport_stop)
        audio_menu.addAction(self.action_home)
        
        self.action_demo = QAction("Guitar Demo Loop", self)
        self.action_demo.setShortcut(QKeySequence("Ctrl+D"))
        self.action_demo.setCheckable(True)
        self.action_demo.setChecked(self.audio_engine.demo_loop_active)
        self.action_demo.triggered.connect(self.toggle_demo_loop)
        audio_menu.addAction(self.action_demo)
        
        audio_menu.addSeparator()
        
        self.action_settings = QAction("Audio Device Settings...", self)
        self.action_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.action_settings.triggered.connect(self.open_settings)
        audio_menu.addAction(self.action_settings)
        
        self.update_demo_btn_style()
        
        self.track_height = 150
        self.installEventFilter(self)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        
        # --- 2. MULTI-SPLIT WORKSPACE LAYOUT (Reaper-Style) ---
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setObjectName("MainVerticalSplitter")
        
        top_workspace = QSplitter(Qt.Orientation.Horizontal)
        top_workspace.setObjectName("TopWorkspaceSplitter")
        
        # Left Panel: Container for Toolbar and Scrollable Track Headers (TCP)
        self.tcp_panel = QWidget()
        self.tcp_panel.setObjectName("TcpPanel")
        tcp_layout = QVBoxLayout(self.tcp_panel)
        tcp_layout.setContentsMargins(0, 0, 0, 0)
        tcp_layout.setSpacing(0)
        
        # New TCP settings/arming mode toolbar
        self.tcp_toolbar = QWidget()
        self.tcp_toolbar.setObjectName("TcpToolbar")
        self.tcp_toolbar.setFixedHeight(31)  # Aligned to timeline toolbar height
        self.tcp_toolbar.setStyleSheet("""
            QWidget#TcpToolbar {
                background-color: #000000;
                border-bottom: 1px solid #222225;
            }
            QPushButton {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
                color: #88888c;
                font-family: "Consolas", monospace;
                font-size: 10px;
                font-weight: bold;
                padding: 4px 6px;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: #1a1a1c;
                border-color: #444448;
                color: #ffffff;
            }
            QPushButton:checked {
                background-color: #ff0033;
                border-color: #ff0033;
                color: #ffffff;
            }
        """)
        
        tcp_tb_layout = QHBoxLayout(self.tcp_toolbar)
        tcp_tb_layout.setContentsMargins(10, 4, 10, 4)
        tcp_tb_layout.setSpacing(6)
        
        self.arm_mode_group = QButtonGroup(self)
        self.arm_mode_group.setExclusive(True)
        
        self.btn_arm_standard = QPushButton("STANDARD")
        self.btn_arm_standard.setCheckable(True)
        self.btn_arm_standard.setChecked(True)
        self.arm_mode_group.addButton(self.btn_arm_standard)
        tcp_tb_layout.addWidget(self.btn_arm_standard)
        
        self.btn_arm_union = QPushButton("UNION")
        self.btn_arm_union.setCheckable(True)
        self.arm_mode_group.addButton(self.btn_arm_union)
        tcp_tb_layout.addWidget(self.btn_arm_union)
        
        self.btn_arm_exclusive = QPushButton("EXCLUSIVE")
        self.btn_arm_exclusive.setCheckable(True)
        self.arm_mode_group.addButton(self.btn_arm_exclusive)
        tcp_tb_layout.addWidget(self.btn_arm_exclusive)
        
        tcp_tb_layout.addStretch()
        tcp_layout.addWidget(self.tcp_toolbar)
        
        # Spacer widget of 30px to align tracklist cards horizontally with timeline track lanes
        self.tcp_spacer = QWidget()
        self.tcp_spacer.setObjectName("TcpSpacer")
        self.tcp_spacer.setFixedHeight(30)
        self.tcp_spacer.setStyleSheet("""
            QWidget#TcpSpacer {
                background-color: #000000;
                border-bottom: 1px solid #222225;
            }
        """)
        tcp_layout.addWidget(self.tcp_spacer)
        
        self.tracks_scroll = QScrollArea()
        self.tracks_scroll.setObjectName("TracksScrollArea")
        self.tracks_scroll.setWidgetResizable(True)
        self.tracks_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tracks_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.tracks_container = TracksContainer(self)
        self.tracks_container.setObjectName("TracksContainer")
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 0, 0, 0)
        self.tracks_layout.setSpacing(10)
        self.tracks_layout.addStretch()
        
        self.tracks_scroll.setWidget(self.tracks_container)
        tcp_layout.addWidget(self.tracks_scroll)
        top_workspace.addWidget(self.tcp_panel)
        
        # Right Panel: Waveform Timeline
        self.timeline = TimelineScrollContainer(self.audio_engine, self)
        top_workspace.addWidget(self.timeline)
        
        top_workspace.setSizes([320, 680])
        self.main_splitter.addWidget(top_workspace)
        
        # Bottom Dock: Tabbed Mixer, Tuner & Metronome Panel
        self.bottom_dock = QTabWidget()
        self.bottom_dock.setObjectName("BottomDockTabs")
        self.bottom_dock.currentChanged.connect(self.on_tab_changed)
        
        # ── Corner widget container ──────────
        self.corner_widget = QWidget()
        self.corner_layout = QHBoxLayout(self.corner_widget)
        self.corner_layout.setContentsMargins(0, 0, 4, 0)
        self.corner_layout.setSpacing(6)
        
        self._dock_pinned = True
        
        from theme_utils import get_resource_path
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        self.icon_pin = QIcon(get_resource_path("public/icons/pin.svg"))
        self.icon_unpin = QIcon(get_resource_path("public/icons/unpin.svg"))
        
        self.btn_dock_pin = QPushButton()
        self.btn_dock_pin.setIcon(self.icon_pin)
        self.btn_dock_pin.setIconSize(QSize(14, 14))
        self.btn_dock_pin.setObjectName("DockPinBtn")
        self.btn_dock_pin.setFixedHeight(24)
        self.btn_dock_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dock_pin.setToolTip("Toggle auto-hide behavior")
        self.btn_dock_pin.clicked.connect(self.toggle_dock_pin)
        self.corner_layout.addWidget(self.btn_dock_pin)

        self._dock_collapsed = False
        self._dock_saved_height = 250
        
        self._dock_anim = QVariantAnimation(self)
        self._dock_anim.setDuration(220)
        self._dock_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._dock_anim.valueChanged.connect(self._on_dock_anim_value)
        
        self.btn_dock_toggle = QPushButton("▼")
        self.btn_dock_toggle.setObjectName("DockToggleBtn")
        self.btn_dock_toggle.setFixedHeight(24)
        self.btn_dock_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dock_toggle.setToolTip("Collapse / expand panel")
        self.btn_dock_toggle.clicked.connect(self.toggle_bottom_dock)
        self.corner_layout.addWidget(self.btn_dock_toggle)

        self.bottom_dock.setCornerWidget(self.corner_widget, Qt.Corner.TopRightCorner)
        self._floating_dock_window = None
        
        # Instantiate effects rack and signal flow
        self.effects_rack = EffectsRack(self.audio_engine)
        self.signal_flow_widget = SignalFlowWidget(self.audio_engine, self.effects_rack)
        self.effects_rack.set_signal_flow_widget(self.signal_flow_widget)
        
        # Effects Tab — first in bottom dock
        self.vst_settings_tab = QWidget()
        vst_settings_layout = QHBoxLayout(self.vst_settings_tab)
        vst_settings_layout.setContentsMargins(5, 5, 5, 5)
        vst_settings_layout.setSpacing(5)
        vst_settings_layout.addWidget(self.effects_rack)
        vst_settings_layout.addWidget(self.signal_flow_widget)
        self.bottom_dock.addTab(self.vst_settings_tab, "Effects")
        
        # Utilities Tab (Tuner and Metronome side-by-side)
        utility_widget = QWidget()
        utility_widget.setObjectName("UtilitiesWidget")
        utility_layout = QHBoxLayout(utility_widget)
        utility_layout.setContentsMargins(5, 5, 5, 5)
        utility_layout.setSpacing(10)
        
        self.tuner_widget = GuitarTunerWidget(self.audio_engine)
        utility_layout.addWidget(self.tuner_widget, 1)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("color: #333333; margin: 10px 0;")
        utility_layout.addWidget(separator)
        
        self.metronome_widget = GuitarMetronomeWidget(self.audio_engine)
        utility_layout.addWidget(self.metronome_widget, 1)
        self.bottom_dock.addTab(utility_widget, "Utilities")
        
        # Mixer Tab — last in bottom dock
        self.mixer_widget = MixerWidget(self.audio_engine)
        self.bottom_dock.addTab(self.mixer_widget, "Mixer")
        self.mixer_widget.rebuild()
        
        self.main_splitter.addWidget(self.bottom_dock)
        
        self.main_splitter.setSizes([450, 250])
        
        # main_splitter will be added inside the WORKSPACE tab page below
        
        # Synchronize vertical scrolls
        self.tracks_scroll.verticalScrollBar().valueChanged.connect(self.timeline.scroll_area.verticalScrollBar().setValue)
        self.timeline.scroll_area.verticalScrollBar().valueChanged.connect(self.tracks_scroll.verticalScrollBar().setValue)
        
        # Build initial track widgets
        self.refresh_track_cards()
        
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.timeout.connect(self.check_auto_hide)
        self.auto_hide_timer.start(100)
        

        # Lay content out directly — no footer bar
        content_layout.addWidget(self.main_splitter)
        main_layout.addWidget(content_widget)
        
        # --- FLAT GRAPHITE QSS STYLESHEET ---
        self.setStyleSheet("""
            QMainWindow#MainWindow {
                background-color: #0b0b0c;
            }
            QTabWidget::pane {
                border: 1px solid #222225;
                background-color: #0b0b0c;
            }
            QTabBar::tab {
                background-color: #000000;
                color: #88888c;
                border: 1px solid #222225;
                border-bottom-color: transparent;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 15px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #0b0b0c;
                color: #ffffff;
                border-bottom-color: #0b0b0c;
            }
            QTabBar::tab:hover {
                background-color: #1a1a1c;
                color: #ffffff;
            }
            QPushButton#DockToggleBtn, QPushButton#DockPinBtn {
                background: transparent;
                border: 1px solid #333336;
                color: #888888;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                font-weight: bold;
                padding: 0px 10px;
                border-radius: 2px;
                margin: 2px 0px;
            }
            QPushButton#DockToggleBtn:hover, QPushButton#DockPinBtn:hover {
                border-color: #888888;
                color: #ffffff;
            }
            #CentralWidget {
                background-color: #0b0b0c;
                border: 1px solid #222225;
            }
            QLabel {
                color: #e2e2e5;
                font-family: "Consolas", "Courier New", monospace;
            }
            #BottomBar {
                background-color: #000000;
                border: 1px solid #222225;
                border-radius: 4px;
            }
            QPushButton#SettingsButton:hover {
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
                border-color: #444448;
            }
            QPushButton#TransportButton {
                background-color: #0b0b0c;
                color: #88888c;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 4px 12px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#TransportButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
                border-color: #444448;
            }
            #TracksScrollArea {
                background: transparent;
            }
            QMenuBar {
                background-color: #000000;
                color: #88888c;
                border-bottom: 1px solid #222225;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                padding-left: 10px;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 4px 10px;
                color: #88888c;
            }
            QMenuBar::item:selected {
                background-color: #ffffff;
                color: #000000;
            }
            QMenu {
                background-color: #000000;
                color: #88888c;
                border: 1px solid #222225;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 25px 6px 20px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #ffffff;
                color: #000000;
            }
            QMenu::separator {
                height: 1px;
                background-color: #222225;
                margin: 4px 0px;
            }
            #TracksScrollArea {
                background: transparent;
            }
            #TracksContainer {
                background: transparent;
            }
            #WorkspaceSplitter::handle {
                background-color: #222225;
                width: 2px;
            }
            #VstSplitter::handle {
                background-color: #222225;
                width: 2px;
            }
            QLabel#StatusLabel {
                color: #555558;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QLabel#MasterVolLabel {
                color: #88888c;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }
            QLabel#MasterDbLabel {
                color: #555558;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 10px;
            }
            QSlider#MasterSlider::groove:horizontal {
                background: #000000;
                height: 4px;
                border-radius: 0px;
            }
            QSlider#MasterSlider::sub-page:horizontal {
                background: #ffffff;
                height: 4px;
                border-radius: 0px;
            }
            QSlider#MasterSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #000000;
                width: 12px;
                margin-top: -3px;
                margin-bottom: -3px;
                border-radius: 0px;
            }
            QSlider#MasterSlider::handle:horizontal:hover {
                background: #ffffff;
                border-color: #ff0033;
            }
            QDialog {
                background-color: #0b0b0c;
                border: 1px solid #222225;
            }
            QMessageBox {
                background-color: #0b0b0c;
                color: #e2e2e5;
            }
            QMessageBox QLabel {
                color: #e2e2e5;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QMessageBox QPushButton {
                background-color: #0b0b0c;
                color: #88888c;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 5px 15px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                font-weight: bold;
            }
            QMessageBox QPushButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
                border-color: #444448;
            }
            QFileDialog {
                background-color: #0b0b0c;
            }
            QFileDialog QPushButton {
                background-color: #0b0b0c;
                color: #88888c;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 5px 15px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                font-weight: bold;
            }
            QFileDialog QPushButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
                border-color: #444448;
            }
            QFileDialog QLineEdit {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 4px;
                font-family: "Consolas", "Courier New", monospace;
            }
            QFileDialog QTreeView, QFileDialog QListView {
                background-color: #000000;
                color: #88888c;
                border: 1px solid #222225;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QFileDialog QTreeView::item:hover, QFileDialog QListView::item:hover {
                background-color: #1a1a1c;
                color: #ffffff;
            }
            QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected {
                background-color: #ffffff;
                color: #000000;
            }
            QFileDialog QHeaderView::section {
                background-color: #0b0b0c;
                color: #ffffff;
                border: 1px solid #222225;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                font-weight: bold;
                padding: 4px;
            }
            QFileDialog QComboBox {
                background-color: #000000;
                color: #88888c;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 4px;
                font-family: "Consolas", "Courier New", monospace;
            }
            QFileDialog QToolButton {
                background-color: #0b0b0c;
                color: #88888c;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 4px;
            }
            QFileDialog QToolButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
            }
        """)

    def refresh_track_cards(self):
        """Clears and rebuilds the vertical track listing UI."""
        # Clean up existing widgets
        for card in self.track_cards:
            self.tracks_layout.removeWidget(card)
            card.deleteLater()
        self.track_cards.clear()
        
        if hasattr(self, 'btn_add_track') and self.btn_add_track:
            self.tracks_layout.removeWidget(self.btn_add_track)
            self.btn_add_track.deleteLater()
            self.btn_add_track = None
        
        # Build cards for each track in audio engine
        for track in self.audio_engine.tracks:
            card = TrackCard(track, self.audio_engine)
            card.trackSelected.connect(self.on_track_selected)
            card.trackRemoved.connect(self.on_track_removed)
            card.trackDuplicated.connect(self.on_track_duplicated)
            
            self.tracks_layout.insertWidget(self.tracks_layout.count() - 1, card)
            card.setFixedHeight(self.track_height)
            self.track_cards.append(card)
            
        # Add the "+" button at the end
        self.btn_add_track = QPushButton("+ ADD TRACK")
        self.btn_add_track.setObjectName("AddTrackButton")
        self.btn_add_track.setFixedHeight(30)
        self.btn_add_track.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_track.clicked.connect(self.on_add_track_clicked)
        self.btn_add_track.setStyleSheet("""
            QPushButton#AddTrackButton {
                background-color: #0b0b0c;
                color: #88888c;
                border: 1px dashed #333333;
                border-radius: 4px;
                font-family: "Consolas", monospace;
                font-weight: bold;
                font-size: 10px;
                letter-spacing: 0.5px;
                margin: 5px 10px;
            }
            QPushButton#AddTrackButton:hover {
                background-color: #151518;
                color: #ffffff;
                border: 1px solid #ff0033;
            }
        """)
        self.tracks_layout.insertWidget(self.tracks_layout.count() - 1, self.btn_add_track)
            
        # Select first track if available
        if self.track_cards:
            self.track_cards[0].set_selected(True)
        else:
            self.effects_rack.set_track(None)
            self.selected_track = None
            
        if hasattr(self, 'timeline'):
            self.timeline.update_track_layout()

        if hasattr(self, 'mixer_widget'):
            self.mixer_widget.rebuild()

    def on_add_track_clicked(self):
        new_track_idx = len(self.audio_engine.tracks) + 1
        self.audio_engine.add_track(f"Track {new_track_idx}")
        self.refresh_track_cards()
        self.mark_project_dirty()

    def calculate_drop_line_y(self, drop_y):
        if not self.track_cards:
            return 30
            
        for card in self.track_cards:
            card_geom = card.geometry()
            card_y_center = card_geom.y() + card_geom.height() / 2
            if drop_y < card_y_center:
                return card_geom.y() - 5
                
        last_card_geom = self.track_cards[-1].geometry()
        return last_card_geom.y() + last_card_geom.height() + 5

    def reorder_tracks(self, dragged_track_id, drop_y):
        # Find the card being dragged
        dragged_card = None
        for card in self.track_cards:
            if card.track.track_id == dragged_track_id:
                dragged_card = card
                break
                
        if not dragged_card:
            return
            
        # Determine the new index in self.track_cards list based on drop_y
        new_index = 0
        inserted = False
        for i, card in enumerate(self.track_cards):
            if card == dragged_card:
                continue
            card_y_center = card.geometry().y() + card.geometry().height() / 2
            if drop_y < card_y_center:
                new_index = i
                inserted = True
                break
                
        if not inserted:
            new_index = len(self.track_cards) - 1
            if new_index < 0:
                new_index = 0
                
        old_index = self.track_cards.index(dragged_card)
        if old_index == new_index:
            return
            
        # Reorder with smooth height transition animations
        # 1. Collapse height at old position
        self.reorder_anim = QVariantAnimation(self)
        self.reorder_anim.setDuration(120)
        self.reorder_anim.setStartValue(self.track_height)
        self.reorder_anim.setEndValue(0)
        
        def on_collapse_val(val):
            dragged_card.setFixedHeight(val)
            
        self.reorder_anim.valueChanged.connect(on_collapse_val)
        
        def on_collapse_finished():
            self.reorder_anim.valueChanged.disconnect()
            try:
                self.reorder_anim.finished.disconnect()
            except RuntimeError:
                pass
                
            # Perform list reorder
            self.track_cards.remove(dragged_card)
            self.track_cards.insert(new_index, dragged_card)
            
            dragged_track = dragged_card.track
            self.audio_engine.tracks.remove(dragged_track)
            self.audio_engine.tracks.insert(new_index, dragged_track)
            
            # Rebuild layout
            for card in self.track_cards:
                self.tracks_layout.removeWidget(card)
            for i, card in enumerate(self.track_cards):
                self.tracks_layout.insertWidget(i, card)
                
            # 2. Expand height at new position
            self.reorder_anim_expand = QVariantAnimation(self)
            self.reorder_anim_expand.setDuration(120)
            self.reorder_anim_expand.setStartValue(0)
            self.reorder_anim_expand.setEndValue(self.track_height)
            
            def on_expand_val(val):
                dragged_card.setFixedHeight(val)
                
            self.reorder_anim_expand.valueChanged.connect(on_expand_val)
            
            def on_expand_finished():
                dragged_card.setFixedHeight(self.track_height)
                # Final update
                if hasattr(self, 'timeline'):
                    self.timeline.update_track_layout()
                    self.timeline.lanes.update()
                    
            self.reorder_anim_expand.finished.connect(on_expand_finished)
            self.reorder_anim_expand.start()
            
            if hasattr(self, 'timeline'):
                self.timeline.update_track_layout()
                self.timeline.lanes.update()
                
        self.reorder_anim.finished.connect(on_collapse_finished)
        self.reorder_anim.start()

    def on_track_selected(self, track):
        """Deselects other cards and selects this track."""
        self.close_active_vst(switch_tab=False)
        self.selected_track = track
        self.audio_engine.selected_track_id = track.track_id if track else None
        
        # Check current arming mode
        if hasattr(self, 'btn_arm_union') and self.btn_arm_union.isChecked():
            if track:
                track.armed = not track.armed
                self.mark_project_dirty()
        elif hasattr(self, 'btn_arm_exclusive') and self.btn_arm_exclusive.isChecked():
            for t in self.audio_engine.tracks:
                was_armed = t.armed
                if track and t == track:
                    t.armed = True
                else:
                    t.armed = False
                if t.armed != was_armed:
                    self.mark_project_dirty()
                    
        for card in self.track_cards:
            if card.track == track:
                card.set_selected(True)
            else:
                card.set_selected(False)
            if hasattr(card, 'btn_arm'):
                card.btn_arm.setChecked(card.track.armed)
                
        # Link to effects rack
        self.effects_rack.set_track(track)
        
    def focus_fx_rack(self, track):
        """Forces selecting the track and highlighting the effects rack."""
        self.on_track_selected(track)
        self.bottom_dock.setCurrentIndex(0)  # Effects tab is index 0
        
    def on_add_track(self):
        """Adds a track to audio engine and UI."""
        new_track = self.audio_engine.add_track()
        card = TrackCard(new_track, self.audio_engine)
        card.trackSelected.connect(self.on_track_selected)
        card.trackRemoved.connect(self.on_track_removed)
        card.trackDuplicated.connect(self.on_track_duplicated)
        
        self.tracks_layout.insertWidget(self.tracks_layout.count() - 1, card)
        self.track_cards.append(card)
        
        # Select it immediately
        card.set_selected(True)
        
        if hasattr(self, 'timeline'):
            self.timeline.update_track_layout()
        if hasattr(self, 'mixer_widget'):
            self.mixer_widget.rebuild()

    def on_add_backing_track(self):
        """Prompts the user to select an audio file, creates a dedicated 'Backing Track' track,
        loads the audio file, and inserts it at the beginning of the track."""
        dlg = QFileDialog(self)
        dlg.setWindowTitle("Import Backing Track")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setNameFilter("Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a *.wma *.aiff *.aif);;All Files (*)")
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        apply_dark_theme_to_hwnd(int(dlg.winId()))
        
        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            file_path = dlg.selectedFiles()[0]
            QApplication.processEvents()
            from widgets.loading_popup import LoadingPopup
            popup = LoadingPopup("LOADING BACKING TRACK...", self)
            popup.show()
            QApplication.processEvents()
            
            try:
                # Add a new track called "Backing Track"
                new_track = self.audio_engine.add_track("Backing Track")
                sample_rate = self.audio_engine.sample_rate
                
                # Load the audio file into an AudioItem at sample 0
                from audio_engine import AudioItem
                item = AudioItem(start_sample=0, sample_rate=sample_rate, file_path=file_path)
                if item.audio_data is not None:
                    with new_track.lock:
                        new_track.items.append(item)
                    new_track.update_pedalboard(self.audio_engine.sample_rate)
                    
                    self.refresh_track_cards()
                    self.mark_project_dirty()
                    if hasattr(self, 'timeline'):
                        self.timeline.update_track_layout()
                else:
                    self.show_themed_message_box(
                        "Error",
                        "Failed to load backing track audio data.",
                        QMessageBox.Icon.Critical
                    )
            finally:
                popup.hide()
                popup.close()
                QApplication.processEvents()
            self.mixer_widget.rebuild()
        
    def on_track_duplicated(self, track):
        new_name = f"{track.name} (Copy)"
        new_track = self.audio_engine.add_track(name=new_name)
        
        # Move new_track in audio_engine.tracks right after track
        self.audio_engine.tracks.remove(new_track)
        target_idx = -1
        for i, t in enumerate(self.audio_engine.tracks):
            if t == track:
                target_idx = i
                break
        if target_idx != -1:
            self.audio_engine.tracks.insert(target_idx + 1, new_track)
        else:
            self.audio_engine.tracks.append(new_track)
            
        # Duplicate basic properties
        new_track.volume = track.volume
        new_track.pan = track.pan
        new_track.mute = track.mute
        new_track.solo = track.solo
        new_track.armed = track.armed
        new_track.input_channel = track.input_channel
        
        # Duplicate items (clips)
        from audio_engine import AudioItem
        with track.lock:
            for item in track.items:
                audio_data_copy = item.audio_data.copy() if item.audio_data is not None else None
                duplicated_item = AudioItem(
                    start_sample=item.start_sample,
                    sample_rate=item.sample_rate,
                    file_path=item.file_path,
                    audio_data=audio_data_copy
                )
                duplicated_item.offset_samples = item.offset_samples
                duplicated_item.length_samples = item.length_samples
                new_track.items.append(duplicated_item)
                
        # Duplicate effects
        import project_manager
        for fx in track.effects:
            try:
                serialized = project_manager.serialize_effect(fx)
                duplicated_fx = project_manager.deserialize_effect(serialized)
                if duplicated_fx:
                    new_track.effects.append(duplicated_fx)
            except Exception as e:
                print(f"Error duplicating effect: {e}")
                
        # Re-build pedalboard
        new_track.update_pedalboard(self.audio_engine.sample_rate)
        
        # Rebuild GUI track cards list
        self.refresh_track_cards()
        self.mark_project_dirty()
        
        # Select the newly duplicated track card
        for card in self.track_cards:
            if card.track == new_track:
                card.set_selected(True)
                break
                
        if hasattr(self, 'mixer_widget'):
            self.mixer_widget.rebuild()

    def on_track_removed(self, track):
        """Deletes a track from engine and UI."""
        # Find card
        target_card = None
        for card in self.track_cards:
            if card.track == track:
                target_card = card
                break
                
        if target_card:
            self.tracks_layout.removeWidget(target_card)
            self.track_cards.remove(target_card)
            target_card.deleteLater()
            
            # Remove from engine
            self.audio_engine.remove_track(track.track_id)
            self.mark_project_dirty()
            
            # Reset selection if deleted track was active
            if self.selected_track == track:
                if self.track_cards:
                    self.track_cards[0].set_selected(True)
                else:
                    self.effects_rack.set_track(None)
                    self.selected_track = None
                    self.audio_engine.selected_track_id = None
                    
            if hasattr(self, 'timeline'):
                self.timeline.update_track_layout()
            if hasattr(self, 'mixer_widget'):
                self.mixer_widget.rebuild()

    def toggle_audio_stream(self):
        """Toggles the global sounddevice stream running state."""
        if self.audio_engine.is_running:
            self.audio_engine.stop_stream()
        else:
            self.audio_engine.start_stream()
        self.update_stream_btn_style()

    def update_stream_btn_style(self):
        """Changes stream menu action visual text based on stream state."""
        if hasattr(self, 'action_stream'):
            if self.audio_engine.is_running:
                self.action_stream.setText("Stop Audio")
            else:
                self.action_stream.setText("Start Audio")
        
        if self.audio_engine.is_running:
            if hasattr(self, 'lbl_status'):
                self.lbl_status.setText("Audio Engine: RUNNING | Low Latency")
        else:
            if hasattr(self, 'lbl_status'):
                self.lbl_status.setText("Audio Engine: STOPPED")
            
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'btn_play_pause'):
            self.update_transport_ui()

    def toggle_demo_loop(self):
        """Toggles real-time pre-computed chord arpeggio demo feedback."""
        active = self.action_demo.isChecked()
        self.audio_engine.demo_loop_active = active
        self.update_demo_btn_style()
        
    def update_demo_btn_style(self):
        """Changes style of demo loop button based on active state."""
        if hasattr(self, 'action_demo'):
            self.action_demo.setChecked(self.audio_engine.demo_loop_active)

    def open_settings(self):
        """Opens audio settings dialog panel."""
        dlg = AudioSettingsDialog(self.audio_engine, self)
        if dlg.exec() == AudioSettingsDialog.DialogCode.Accepted:
            # Refresh inputs in track cards in case device channels changed
            for card in self.track_cards:
                card.populate_inputs()
            self.update_stream_btn_style()

    def on_master_volume_changed(self):
        if not hasattr(self, 'slider_master'):
            return
        val_db = self.slider_master.value() / 10.0
        self.audio_engine.main_volume = val_db
        self.update_master_volume_label(val_db)
        
    def update_master_volume_label(self, val_db):
        if not hasattr(self, 'lbl_master_db'):
            return
        if val_db <= -60.0:
            self.lbl_master_db.setText("-inf dB")
        else:
            self.lbl_master_db.setText(f"{val_db:+.1f} dB")

    # ── Bottom dock collapse / expand ─────────────────────────────────────────

    def toggle_bottom_dock(self):
        """Slide the bottom dock closed or open with a smooth animation."""
        if self._dock_anim.state() == QVariantAnimation.State.Running:
            self._dock_anim.stop()

        sizes = self.main_splitter.sizes()
        total = sum(sizes)
        current_bottom = sizes[1] if len(sizes) > 1 else self.bottom_dock.height()

        tab_h = self.bottom_dock.tabBar().sizeHint().height()
        if tab_h < 15:
            tab_h = 28

        if self._dock_collapsed:
            # Expand: restore saved height
            target = max(self._dock_saved_height, 180)
            self.bottom_dock.setMaximumHeight(16777215)  # remove cap
            self._dock_anim.setStartValue(current_bottom)
            self._dock_anim.setEndValue(target)
            self._dock_collapsed = False
            self.btn_dock_toggle.setText("▼")
        else:
            # Collapse: save current height
            if current_bottom > tab_h + 10:
                self._dock_saved_height = current_bottom
            self._dock_anim.setStartValue(current_bottom)
            self._dock_anim.setEndValue(tab_h)
            self._dock_collapsed = True
            self.btn_dock_toggle.setText("▲")

        self._dock_anim.start()

    def _on_dock_anim_value(self, bottom_h):
        # We cap the dock height so it can squash past its minimum size
        self.bottom_dock.setMaximumHeight(bottom_h)
        # And we force the splitter to give space to the top workspace
        sizes = self.main_splitter.sizes()
        total = sum(sizes)
        top_h = max(0, total - bottom_h)
        self.main_splitter.setSizes([top_h, bottom_h])

    def toggle_dock_pin(self):
        self._dock_pinned = not self._dock_pinned
        if self._dock_pinned:
            self.btn_dock_pin.setIcon(self.icon_pin)
            self.expand_dock()
        else:
            self.btn_dock_pin.setIcon(self.icon_unpin)

    def check_auto_hide(self):
        if self._dock_pinned:
            return
            
        from PySide6.QtGui import QCursor
        global_pos = QCursor.pos()
        
        dock_rect = self.bottom_dock.rect()
        local_pos = self.bottom_dock.mapFromGlobal(global_pos)
        
        main_local = self.mapFromGlobal(global_pos)
        near_bottom = (main_local.y() > self.height() - 40) and (0 <= main_local.x() <= self.width())
        
        is_hovering = dock_rect.contains(local_pos) or near_bottom
        
        if is_hovering:
            self.expand_dock()
        else:
            self.collapse_dock()

    def expand_dock(self):
        if not self._dock_collapsed: return
        self.toggle_bottom_dock()
        
    def collapse_dock(self):
        if self._dock_collapsed: return
        self.toggle_bottom_dock()

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent, Qt
        if event.type() == QEvent.Type.Wheel:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                step = 10 if delta > 0 else -10
                self.adjust_track_height(step)
                return True
        return super().eventFilter(obj, event)

    def adjust_track_height(self, step):
        self.track_height = max(60, min(300, self.track_height + step))
        for card in self.track_cards:
            card.setFixedHeight(self.track_height)
        if hasattr(self, 'timeline'):
            self.timeline.lanes.lane_height = self.track_height
            self.timeline.lanes.update_geometry()
            self.timeline.lanes.update()
            self.timeline.update_track_layout()

    def update_master_levels(self):
        """Polls main engine peak VU dB and updates GUI meter."""
        if hasattr(self, 'master_level_meter'):
            self.master_level_meter.set_level(self.audio_engine.main_level_history)
        if hasattr(self, 'timeline'):
            self.timeline.update_widgets()

    def on_new_project(self):
        """Clears all tracks and creates a blank project."""
        reply = self.show_themed_message_box(
            "New Project",
            "Are you sure you want to clear current session and create a new project?",
            QMessageBox.Icon.Question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.audio_engine.stop_stream()
            with self.audio_engine.lock:
                self.audio_engine.tracks.clear()
                self.audio_engine.main_volume = 0.0
                self.audio_engine.demo_loop_active = False
            self.current_project_path = None
            self.audio_engine.current_project_directory = None
            self.project_dirty = False
            self.update_title_bar()
            if hasattr(self, 'mixer_widget') and hasattr(self.mixer_widget, 'master'):
                self.mixer_widget.master.update_volume_ui()
            self.action_demo.setChecked(False)
            self.update_demo_btn_style()
            self.audio_engine.add_track("Guitar 1")
            self.refresh_track_cards()
            self.audio_engine.start_stream()
            self.update_stream_btn_style()
            if hasattr(self, 'timeline'):
                self.timeline.update_track_layout()

    def on_save_project(self):
        """Saves current state to JSON file dialog."""
        dlg = QFileDialog(self)
        dlg.setWindowTitle("Save Graphite Session")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setNameFilter("Graphite DAW Project (*.graphite)")
        dlg.setDefaultSuffix("graphite")
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        apply_dark_theme_to_hwnd(int(dlg.winId()))
        
        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            file_path = dlg.selectedFiles()[0]
            if not file_path.endswith(".graphite"):
                file_path += ".graphite"
                
            QApplication.processEvents()
            
            from widgets.loading_popup import LoadingPopup
            popup = LoadingPopup("SAVING GRAPHITE PROJECT...", self)
            popup.show()
            QApplication.processEvents()
            
            try:
                success = project_manager.save_project(file_path, self.audio_engine)
            finally:
                popup.hide()
                popup.close()
                QApplication.processEvents()
                
            if success:
                self.current_project_path = file_path
                self.project_dirty = False
                self.update_title_bar()
                self.show_themed_message_box(
                    "Project Saved",
                    f"Successfully saved session to:\n{os.path.basename(file_path)}",
                    QMessageBox.Icon.Information
                )
                return True
            else:
                self.show_themed_message_box(
                    "Save Error",
                    "Failed to save project file.",
                    QMessageBox.Icon.Critical
                )
                return False
        return False
 
    def on_export_audio(self):
        """Opens the export settings dialog to render timeline mixdown to file."""
        from widgets.export_dialog import ExportDialog
        dlg = ExportDialog(self.audio_engine, self)
        dlg.exec()
 
    def on_load_project(self):
        """Loads session file and rebuilds cards UI."""
        dlg = QFileDialog(self)
        dlg.setWindowTitle("Open Graphite Session")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setNameFilter("Graphite DAW Project (*.graphite *.gtrp);;Graphite Project (*.graphite);;Legacy Cyberamp Project (*.gtrp)")
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        apply_dark_theme_to_hwnd(int(dlg.winId()))
        
        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            file_path = dlg.selectedFiles()[0]
            
            QApplication.processEvents()
            
            from widgets.loading_popup import LoadingPopup
            popup = LoadingPopup("LOADING GRAPHITE PROJECT...", self)
            popup.show()
            QApplication.processEvents()
            
            try:
                success = project_manager.load_project(file_path, self.audio_engine)
            finally:
                popup.hide()
                popup.close()
                QApplication.processEvents()
                
            if success:
                self.current_project_path = file_path
                self.project_dirty = False
                self.update_title_bar()
                # Rebuild cards and GUI state
                self.refresh_track_cards()
                if hasattr(self, 'mixer_widget') and hasattr(self.mixer_widget, 'master'):
                    self.mixer_widget.master.update_volume_ui()
                self.action_demo.setChecked(self.audio_engine.demo_loop_active)
                self.update_demo_btn_style()
                self.update_stream_btn_style()
                
                # Check dropdowns inputs in track cards
                for card in self.track_cards:
                    card.populate_inputs()
                    
                if hasattr(self, 'timeline'):
                    self.timeline.update_track_layout()
                    
                self.show_themed_message_box(
                    "Project Loaded",
                    f"Successfully loaded session:\n{os.path.basename(file_path)}",
                    QMessageBox.Icon.Information
                )
            else:
                self.show_themed_message_box(
                    "Load Error",
                    "Failed to parse or restore project file. Some VST3s may have failed loading.",
                    QMessageBox.Icon.Critical
                )

    def open_vst_in_tab(self, card, wrapper):
        try:
            if not hasattr(wrapper.effect, "show_editor"):
                self.show_themed_message_box("VST3 Editor", "This plugin does not support a custom editor interface.", QMessageBox.Icon.Warning)
                return
            
            import platform
            if platform.system() != "Windows":
                # Non-Windows: just open directly
                wrapper.effect.show_editor()
                return
            
            import ctypes
            import ctypes.wintypes
            
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            current_pid = kernel32.GetCurrentProcessId()
            
            # Check serialization lock
            if self.vst_loop_running:
                if self.active_vst_card is card:
                    return
                else:
                    self.pending_vst_to_open = (card, wrapper)
                    if self._vst_hwnd and user32.IsWindow(self._vst_hwnd):
                        self._enforce_timer.stop()
                        WM_CLOSE = 0x0010
                        user32.PostMessageW(self._vst_hwnd, WM_CLOSE, 0, 0)
                    else:
                        self.close_active_vst(switch_tab=False)
                return
            
            # If a VST is already active
            if self.active_vst_card is not None:
                if self.active_vst_card is card:
                    return
                else:
                    # Clicked a different card -> Set pending and trigger close
                    self.pending_vst_to_open = (card, wrapper)
                    if self._vst_hwnd and user32.IsWindow(self._vst_hwnd):
                        self._enforce_timer.stop()
                        WM_CLOSE = 0x0010
                        user32.PostMessageW(self._vst_hwnd, WM_CLOSE, 0, 0)
                    else:
                        self.close_active_vst(switch_tab=False)
                    return
            
            # Use pointer-safe window style functions to prevent OverflowError
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongPtrW.restype = ctypes.c_void_p
            
            self.active_vst_card = card
            
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()
            
            self._enforce_timer.start()
            
            vst_hwnd_ref = [None]
            
            EVENT_OBJECT_CREATE = 0x8000
            EVENT_OBJECT_SHOW = 0x8002
            WINEVENT_OUTOFCONTEXT = 0x0000
            GA_ROOT = 2
            
            WINEVENTPROC = ctypes.WINFUNCTYPE(
                None, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.c_void_p,
                ctypes.wintypes.LONG, ctypes.wintypes.LONG,
                ctypes.wintypes.DWORD, ctypes.wintypes.DWORD
            )
            
            hook_ref = [None]
            
            def _win_event_callback(hHook, event, hwnd, idObject, idChild, tid, time):
                if not hwnd or idObject != 0:
                    return
                
                # If we already have a valid VST window captured, ignore all other window events
                if self._vst_hwnd and user32.IsWindow(self._vst_hwnd):
                    return
                
                try:
                    live_dialog_hwnd = int(self.winId())
                except (RuntimeError, AttributeError):
                    return
                
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value != current_pid:
                    return
                
                root = user32.GetAncestor(hwnd, GA_ROOT)
                if not root:
                    root = hwnd
                    
                if root == live_dialog_hwnd:
                    return
                
                if not user32.IsWindow(root):
                    return
                
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(root, class_buf, 256)
                class_name = class_buf.value
                if class_name.startswith("Qt"):
                    return
                
                if class_name in ("#32768", "tooltips_class32", "ComboLBox"):
                    return
                
                length = user32.GetWindowTextLengthW(root)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(root, buf, length + 1)
                title = buf.value
                if title == "Graphite":
                    return
                
                # Check client size to ignore zero-size or collapsed helper windows
                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                client_rect = RECT()
                user32.GetClientRect(root, ctypes.byref(client_rect))
                cw = client_rect.right - client_rect.left
                ch = client_rect.bottom - client_rect.top
                if cw <= 100 or ch <= 100:
                    return
                
                GWL_STYLE = -16
                style_ptr = user32.GetWindowLongPtrW(root, GWL_STYLE)
                style = ctypes.cast(style_ptr, ctypes.c_void_p).value or 0
                
                print(f"[VST Debug] Callback Match: hwnd={root}, class={class_name}, title='{title}', size={cw}x{ch}, style={hex(style)}")
                
                vst_hwnd_ref[0] = root
                self._vst_hwnd = root
                
                # Force Windows title bar styles and standard controls
                WS_POPUP = 0x80000000
                WS_CAPTION = 0x00C00000
                WS_SYSMENU = 0x00080000
                WS_THICKFRAME = 0x00040000
                WS_MINIMIZEBOX = 0x00020000
                
                GWL_STYLE = -16
                new_style = (style | WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX)
                # Remove WS_CHILD (0x40000000) if set
                new_style = new_style & ~0x40000000
                user32.SetWindowLongPtrW(root, GWL_STYLE, ctypes.c_void_p(new_style))
                
                # Set main window as owner (keeps VST on top, gives it real title bar)
                GWLP_HWNDPARENT = -8
                main_hwnd = int(self.winId())
                user32.SetWindowLongPtrW(root, GWLP_HWNDPARENT, ctypes.c_void_p(main_hwnd))
                
                # Snap position: just below signal_flow_widget
                try:
                    snap_pos = self._get_vst_snap_position(cw, ch)
                    snap_x, snap_y = snap_pos
                except Exception:
                    snap_x, snap_y = 100, 200
                
                # Apply dark DWM styling
                try:
                    apply_dark_theme_to_hwnd(root)
                except Exception:
                    pass
                
                # Apply frame change and move to snap position
                SWP_NOZORDER = 0x0004
                SWP_FRAMECHANGED = 0x0020
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(root, 0, snap_x, snap_y, cw, ch,
                                    SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW)
                
                # Stop scanner timer
                self._enforce_timer.stop()
                
            self._vst_hook_cb = WINEVENTPROC(_win_event_callback)
            hook_ref[0] = user32.SetWinEventHook(
                EVENT_OBJECT_CREATE, EVENT_OBJECT_SHOW,
                None, self._vst_hook_cb, current_pid, 0, WINEVENT_OUTOFCONTEXT
            )
            
            # Start the loop!
            self.vst_loop_running = True
            try:
                wrapper.effect.show_editor()
            finally:
                self.vst_loop_running = False
            
            if hook_ref[0]:
                user32.UnhookWinEvent(hook_ref[0])
                hook_ref[0] = None
            self._vst_hook_cb = None
            
            if self.active_vst_card is card:
                self._vst_hwnd = None
                self._original_style = None
                self._last_vst_size = None
                self.active_vst_card = None
                
                if self.pending_vst_to_open:
                    next_card, next_wrapper = self.pending_vst_to_open
                    self.pending_vst_to_open = None
                    QTimer.singleShot(50, lambda: self.open_vst_in_tab(next_card, next_wrapper))
                else:
                    self.close_active_vst()
            
        except Exception as e:
            self.vst_loop_running = False
            self.show_themed_message_box("VST3 Editor Error", f"Failed to open editor: {e}", QMessageBox.Icon.Critical)

    def close_active_vst(self, switch_tab=True):
        self._enforce_timer.stop()
        self.pending_vst_to_open = None
        if self._vst_hwnd:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                if user32.IsWindow(self._vst_hwnd):
                    WM_CLOSE = 0x0010
                    user32.PostMessageW(self._vst_hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
            self._vst_hwnd = None
            self._original_style = None
            self._last_vst_size = None

        self.active_vst_card = None

    def show_builtin_placeholder(self, wrapper):
        self.close_active_vst(switch_tab=False)

    def show_no_vst_placeholder(self):
        self.close_active_vst(switch_tab=False)

    def on_tab_changed(self, index):
        # Called when the bottom dock tabs switch.
        # Close any open VST editor when leaving the Effects tab (index 1)
        if index != 1:  # Not on Effects tab
            if self.active_vst_card:
                self.close_active_vst(switch_tab=False)
    def on_fast_forward(self):
        """Moves playhead to the end of the longest recorded clip."""
        longest_sample = 0
        for track in self.audio_engine.tracks:
            for item in track.items:
                end_sample = item.start_sample + item.length_samples
                if end_sample > longest_sample:
                    longest_sample = end_sample
        self.audio_engine.playhead_samples = longest_sample
        if hasattr(self, 'timeline'):
            self.timeline.update_widgets()

    # --- THEMED MESSAGE BOX ---
    def show_themed_message_box(self, title, text, icon=QMessageBox.Icon.Information, buttons=QMessageBox.StandardButton.Ok):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(icon)
        msg.setStandardButtons(buttons)
        apply_dark_theme_to_hwnd(int(msg.winId()))
        return msg.exec()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _enforce_vst_window(self):
        if self._vst_hwnd:
            self._enforce_timer.stop()
            return
            
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        current_pid = kernel32.GetCurrentProcessId()
        
        if self.active_vst_card:
            try:
                found_hwnds = []
                GA_ROOT = 2
                main_hwnd = int(self.winId())
                
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                
                def enum_windows_cb(hwnd, lParam):
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == current_pid:
                        root = user32.GetAncestor(hwnd, GA_ROOT)
                        if root and user32.IsWindow(root) and root != main_hwnd:
                            class_buf = ctypes.create_unicode_buffer(256)
                            user32.GetClassNameW(root, class_buf, 256)
                            class_name = class_buf.value
                            if not class_name.startswith("Qt") and class_name not in ("#32768", "tooltips_class32", "ComboLBox"):
                                # Check client size to ignore zero-size or collapsed helper windows
                                class RECT(ctypes.Structure):
                                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                                client_rect = RECT()
                                user32.GetClientRect(root, ctypes.byref(client_rect))
                                cw = client_rect.right - client_rect.left
                                ch = client_rect.bottom - client_rect.top
                                
                                if cw > 100 and ch > 100:
                                    found_hwnds.append(root)
                    return True
                    
                cb = WNDENUMPROC(enum_windows_cb)
                user32.EnumWindows(cb, 0)
                
                if found_hwnds:
                    root = found_hwnds[0]
                    self._vst_hwnd = root
                    
                    GWL_STYLE = -16
                    style_ptr = user32.GetWindowLongPtrW(root, GWL_STYLE)
                    style = ctypes.cast(style_ptr, ctypes.c_void_p).value or 0
                    
                    print(f"[VST Debug] Scan Match: hwnd={root}, style={hex(style)}")
                    
                    # Force Windows title bar styles and standard controls
                    WS_POPUP = 0x80000000
                    WS_CAPTION = 0x00C00000
                    WS_SYSMENU = 0x00080000
                    WS_THICKFRAME = 0x00040000
                    WS_MINIMIZEBOX = 0x00020000
                    
                    new_style = (style | WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX)
                    new_style = new_style & ~0x40000000  # Remove WS_CHILD
                    user32.SetWindowLongPtrW(root, GWL_STYLE, ctypes.c_void_p(new_style))
                    
                    # Set main window as owner
                    GWLP_HWNDPARENT = -8
                    main_hwnd = int(self.winId())
                    user32.SetWindowLongPtrW(root, GWLP_HWNDPARENT, ctypes.c_void_p(main_hwnd))
                    
                    # Snap below signal_flow_widget
                    try:
                        snap_pos = self._get_vst_snap_position(cw, ch)
                        snap_x, snap_y = snap_pos
                    except Exception:
                        snap_x, snap_y = 100, 200
                    
                    try:
                        apply_dark_theme_to_hwnd(root)
                    except Exception:
                        pass
                    
                    SWP_NOZORDER = 0x0004
                    SWP_FRAMECHANGED = 0x0020
                    SWP_SHOWWINDOW = 0x0040
                    user32.SetWindowPos(root, 0, snap_x, snap_y, cw, ch,
                                        SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW)
                    
                    # Stop scanner timer
                    self._enforce_timer.stop()
            except Exception:
                pass

    def _get_vst_snap_position(self, vst_w, vst_h):
        """Calculate screen position to snap VST window just below the signal flow widget."""
        # Get the global (screen) rect of the signal_flow_widget bottom-left
        try:
            flow = self.signal_flow_widget
            top_left_global = flow.mapToGlobal(flow.rect().bottomLeft())
            snap_x = top_left_global.x()
            snap_y = top_left_global.y() + 4  # 4px gap
            
            # Ensure the window doesn't go off-screen to the right
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                screen_geo = screen.availableGeometry()
                if snap_x + vst_w > screen_geo.right():
                    snap_x = max(screen_geo.left(), screen_geo.right() - vst_w)
                if snap_y + vst_h > screen_geo.bottom():
                    # Place above the signal_flow_widget instead
                    top_global = flow.mapToGlobal(flow.rect().topLeft())
                    snap_y = max(screen_geo.top(), top_global.y() - vst_h - 4)
            return (snap_x, snap_y)
        except Exception:
            return (100, 200)

    def closeEvent(self, event):
        """Release audio stream explicitly when app terminates."""
        if self.project_dirty:
            reply = self.show_themed_message_box(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before exiting?",
                QMessageBox.Icon.Question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                if self.on_save_project():
                    pass
                else:
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        else:
            reply = self.show_themed_message_box(
                "Exit Graphite",
                "Are you sure you want to exit Graphite DAW?",
                QMessageBox.Icon.Question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.audio_engine.stop_stream()
        try:
            self.close_active_vst()
        except Exception:
            pass
        try:
            from audio_engine import clean_temp_vsts
            clean_temp_vsts()
        except Exception:
            pass
        super().closeEvent(event)

    def toggle_play_pause(self):
        if self.audio_engine.play_state == "playing":
            self.on_transport_pause()
        else:
            self.on_transport_play()

    def toggle_play_stop(self):
        if self.audio_engine.play_state == "playing":
            self.on_transport_stop()
        else:
            self.on_transport_play()

    def toggle_record(self):
        if self.audio_engine.play_state == "recording":
            self.on_transport_stop()
        else:
            self.on_transport_record()

    def on_transport_play(self):
        self.audio_engine.start_playback()
        self.update_transport_ui()
        self.update_stream_btn_style()
        
    def on_transport_pause(self):
        self.audio_engine.pause_playback()
        self.update_transport_ui()
        self.update_stream_btn_style()
        if hasattr(self, 'timeline'):
            self.timeline.update_widgets()
            self.timeline.update_track_layout()
        
    def on_transport_stop(self):
        self.audio_engine.stop_playback()
        self.update_transport_ui()
        self.update_stream_btn_style()
        if hasattr(self, 'timeline'):
            self.timeline.update_widgets()
            self.timeline.update_track_layout()
        
    def on_transport_record(self):
        self.audio_engine.start_recording()
        self.update_transport_ui()
        self.update_stream_btn_style()

    def update_transport_ui(self):
        state = self.audio_engine.play_state
        if not hasattr(self, 'timeline') or not hasattr(self.timeline, 'btn_play_pause'):
            return
            
        self.timeline.btn_play_pause.setStyleSheet("")
        self.timeline.btn_record.setStyleSheet("")
        
        if state == "playing":
            self.timeline.btn_play_pause.setIcon(self.timeline.icon_pause)
            self.timeline.btn_play_pause.setToolTip("Pause")
            self.timeline.btn_play_pause.setStyleSheet("background-color: #ffffff; border-color: #ffffff; color: #000000;")
        else:
            self.timeline.btn_play_pause.setIcon(self.timeline.icon_play)
            self.timeline.btn_play_pause.setToolTip("Play")
            if state == "paused":
                self.timeline.btn_play_pause.setStyleSheet("background-color: #222225; border-color: #444448; color: #ffffff;")
                
        if state == "recording":
            self.timeline.btn_record.setStyleSheet("background-color: #ff0033; border-color: #ff0033; color: #ffffff;")

    def update_transport_ui(self):
        state = self.audio_engine.play_state
        if not hasattr(self, 'timeline') or not hasattr(self.timeline, 'btn_play_pause'):
            return
            
        self.timeline.btn_play_pause.setStyleSheet("")
        self.timeline.btn_record.setStyleSheet("")
        
        if state == "playing":
            self.timeline.btn_play_pause.setIcon(self.timeline.icon_pause)
            self.timeline.btn_play_pause.setToolTip("Pause")
            self.timeline.btn_play_pause.setStyleSheet("background-color: #ffffff; border-color: #ffffff; color: #000000;")
        else:
            self.timeline.btn_play_pause.setIcon(self.timeline.icon_play)
            self.timeline.btn_play_pause.setToolTip("Play")
            if state == "paused":
                self.timeline.btn_play_pause.setStyleSheet("background-color: #222225; border-color: #444448; color: #ffffff;")
                
        if state == "recording":
            self.timeline.btn_record.setStyleSheet("background-color: #ff0033; border-color: #ff0033; color: #ffffff;")
