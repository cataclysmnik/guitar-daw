import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFileDialog, QSplitter, QSlider,
    QMessageBox, QTabWidget, QFrame, QMenuBar, QSizeGrip, QStackedWidget
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QAction, QKeySequence
from audio_engine import AudioEngine
from widgets.track_card import TrackCard
from widgets.effects_rack import EffectsRack
from widgets.level_meter import LevelMeter
from widgets.audio_settings import AudioSettingsDialog
from widgets.timeline import TimelineScrollContainer
from widgets.tuner import GuitarTunerWidget
from widgets.metronome import GuitarMetronomeWidget
import project_manager

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
        
        # --- 2. MULTI-SPLIT WORKSPACE LAYOUT (Reaper-Style) ---
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setObjectName("MainVerticalSplitter")
        
        top_workspace = QSplitter(Qt.Orientation.Horizontal)
        top_workspace.setObjectName("TopWorkspaceSplitter")
        
        # Left Panel: Scrollable Track Headers List (TCP)
        self.tracks_scroll = QScrollArea()
        self.tracks_scroll.setObjectName("TracksScrollArea")
        self.tracks_scroll.setWidgetResizable(True)
        self.tracks_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tracks_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.tracks_container = QWidget()
        self.tracks_container.setObjectName("TracksContainer")
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 30, 0, 0)  # Offset 30px top margin to align with Timeline Ruler
        self.tracks_layout.setSpacing(10)
        self.tracks_layout.addStretch()
        
        self.tracks_scroll.setWidget(self.tracks_container)
        top_workspace.addWidget(self.tracks_scroll)
        
        # Right Panel: Waveform Timeline
        self.timeline = TimelineScrollContainer(self.audio_engine, self)
        top_workspace.addWidget(self.timeline)
        
        top_workspace.setSizes([320, 680])
        main_splitter.addWidget(top_workspace)
        
        # Bottom Dock: Tabbed Mixer, Tuner & Metronome Panel
        self.bottom_dock = QTabWidget()
        self.bottom_dock.setObjectName("BottomDockTabs")
        
        # Instantiate effects rack (will be placed inside VST Settings tab later)
        self.effects_rack = EffectsRack(self.audio_engine)
        
        # Utilities Tab (Tuner and Metronome side-by-side)
        utility_widget = QWidget()
        utility_widget.setObjectName("UtilitiesWidget")
        utility_layout = QHBoxLayout(utility_widget)
        utility_layout.setContentsMargins(5, 5, 5, 5)
        utility_layout.setSpacing(10)
        
        self.tuner_widget = GuitarTunerWidget(self.audio_engine)
        utility_layout.addWidget(self.tuner_widget, 1)
        
        # Subtle vertical separator line between them
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("color: #333333; margin: 10px 0;")
        utility_layout.addWidget(separator)
        
        self.metronome_widget = GuitarMetronomeWidget(self.audio_engine)
        utility_layout.addWidget(self.metronome_widget, 1)
        
        self.bottom_dock.addTab(utility_widget, "Utilities")
        
        main_splitter.addWidget(self.bottom_dock)
        
        main_splitter.setSizes([450, 250])
        
        # main_splitter will be added inside the WORKSPACE tab page below
        
        # Synchronize vertical scrolls
        self.tracks_scroll.verticalScrollBar().valueChanged.connect(self.timeline.scroll_area.verticalScrollBar().setValue)
        self.timeline.scroll_area.verticalScrollBar().valueChanged.connect(self.tracks_scroll.verticalScrollBar().setValue)
        
        # Build initial track widgets
        self.refresh_track_cards()
        
        # --- 3. BOTTOM MASTER BAR / STATUS ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setObjectName("BottomBar")
        bottom_bar.setContentsMargins(15, 8, 15, 8)
        bottom_bar.setSpacing(15)
        
        self.lbl_status = QLabel("Audio Engine: RUNNING | Latency: Low Latency Mode")
        self.lbl_status.setObjectName("StatusLabel")
        bottom_bar.addWidget(self.lbl_status)
        
        bottom_bar.addSpacing(20)
        
        bottom_bar.addStretch()
        
        # Master Volume Controls
        lbl_master = QLabel("MASTER VOLUME")
        lbl_master.setObjectName("MasterVolLabel")
        bottom_bar.addWidget(lbl_master)
        
        self.slider_master = QSlider(Qt.Orientation.Horizontal)
        self.slider_master.setMinimum(-600)  # -60 dB
        self.slider_master.setMaximum(60)    # +6 dB
        self.slider_master.setValue(int(self.audio_engine.main_volume * 10))
        self.slider_master.setObjectName("MasterSlider")
        self.slider_master.setMinimumWidth(150)
        self.slider_master.valueChanged.connect(self.on_master_volume_changed)
        bottom_bar.addWidget(self.slider_master)
        
        self.lbl_master_db = QLabel("0.0 dB")
        self.lbl_master_db.setObjectName("MasterDbLabel")
        self.lbl_master_db.setFont(QFont("Consolas", 8))
        bottom_bar.addWidget(self.lbl_master_db)
        self.update_master_volume_label(self.audio_engine.main_volume)
        
        # Master VU meter (placed horizontally or vertically, level meter is vertical)
        self.master_level_meter = LevelMeter()
        self.master_level_meter.setMinimumSize(25, 60)
        self.master_level_meter.setMaximumHeight(65)
        bottom_bar.addWidget(self.master_level_meter)
        
        # Size grip for frameless resizing
        size_grip = QSizeGrip(self)
        bottom_bar.addWidget(size_grip)
        
        # Create Main Tab Widget
        self.main_tabs = QTabWidget(self)
        self.main_tabs.setObjectName("MainTabs")
        self.main_tabs.currentChanged.connect(self.on_tab_changed)
        
        # Tab 1: Workspace
        self.workspace_tab = QWidget()
        workspace_tab_layout = QVBoxLayout(self.workspace_tab)
        workspace_tab_layout.setContentsMargins(0, 0, 0, 0)
        workspace_tab_layout.setSpacing(10)
        workspace_tab_layout.addWidget(main_splitter)
        workspace_tab_layout.addLayout(bottom_bar)
        
        self.main_tabs.addTab(self.workspace_tab, "WORKSPACE")
        
        # Tab 2: VST Settings
        self.vst_settings_tab = QWidget()
        vst_settings_layout = QVBoxLayout(self.vst_settings_tab)
        vst_settings_layout.setContentsMargins(10, 10, 10, 10)
        vst_settings_layout.setSpacing(0)
        
        # Put effects rack directly in the tab layout (no splitter, no vst_stack container)
        vst_settings_layout.addWidget(self.effects_rack)
        self.main_tabs.addTab(self.vst_settings_tab, "EFFECTS")
        
        content_layout.addWidget(self.main_tabs)
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
        
        # Build cards for each track in audio engine
        for track in self.audio_engine.tracks:
            card = TrackCard(track, self.audio_engine)
            card.trackSelected.connect(self.on_track_selected)
            card.trackRemoved.connect(self.on_track_removed)
            card.btn_fx.clicked.connect(lambda t=track: self.focus_fx_rack(t))
            
            self.tracks_layout.insertWidget(self.tracks_layout.count() - 1, card)
            self.track_cards.append(card)
            
        # Select first track if available
        if self.track_cards:
            self.track_cards[0].set_selected(True)
        else:
            self.effects_rack.set_track(None)
            self.selected_track = None
            
        if hasattr(self, 'timeline'):
            self.timeline.update_track_layout()

    def on_track_selected(self, track):
        """Deselects other cards and selects this track."""
        self.close_active_vst(switch_tab=False)
        self.selected_track = track
        self.audio_engine.selected_track_id = track.track_id if track else None
        for card in self.track_cards:
            if card.track == track:
                card.set_selected(True)
            else:
                card.set_selected(False)
                
        # Link to effects rack
        self.effects_rack.set_track(track)
        
    def focus_fx_rack(self, track):
        """Forces selecting the track and highlighting the effects rack."""
        self.on_track_selected(track)
        self.main_tabs.setCurrentIndex(1)
        
    def on_add_track(self):
        """Adds a track to audio engine and UI."""
        new_track = self.audio_engine.add_track()
        card = TrackCard(new_track, self.audio_engine)
        card.trackSelected.connect(self.on_track_selected)
        card.trackRemoved.connect(self.on_track_removed)
        card.btn_fx.clicked.connect(lambda t=new_track: self.focus_fx_rack(t))
        
        self.tracks_layout.insertWidget(self.tracks_layout.count() - 1, card)
        self.track_cards.append(card)
        
        # Select it immediately
        card.set_selected(True)
        
        if hasattr(self, 'timeline'):
            self.timeline.update_track_layout()
        
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
            self.lbl_status.setText("Audio Engine: RUNNING | Low Latency")
        else:
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
        val_db = self.slider_master.value() / 10.0
        self.audio_engine.main_volume = val_db
        self.update_master_volume_label(val_db)
        
    def update_master_volume_label(self, val_db):
        if val_db <= -60.0:
            self.lbl_master_db.setText("-inf dB")
        else:
            self.lbl_master_db.setText(f"{val_db:+.1f} dB")

    def update_master_levels(self):
        """Polls main engine peak VU dB and updates GUI meter."""
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
            self.slider_master.setValue(0)
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
            success = project_manager.save_project(file_path, self.audio_engine)
            if success:
                self.show_themed_message_box(
                    "Project Saved",
                    f"Successfully saved session to:\n{os.path.basename(file_path)}",
                    QMessageBox.Icon.Information
                )
            else:
                self.show_themed_message_box(
                    "Save Error",
                    "Failed to save project file.",
                    QMessageBox.Icon.Critical
                )
 
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
            success = project_manager.load_project(file_path, self.audio_engine)
            if success:
                # Rebuild cards and GUI state
                self.refresh_track_cards()
                self.slider_master.setValue(int(self.audio_engine.main_volume * 10))
                self.update_master_volume_label(self.audio_engine.main_volume)
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
                WS_MAXIMIZEBOX = 0x00010000
                
                new_style = (style | WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
                user32.SetWindowLongPtrW(root, GWL_STYLE, ctypes.c_void_p(new_style))
                
                # Force frame change to apply styling immediately
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_FRAMECHANGED = 0x0020
                user32.SetWindowPos(root, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
                
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
        if index == 0:
            if self.active_vst_card:
                self.close_active_vst()

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
                    WS_MAXIMIZEBOX = 0x00010000
                    
                    new_style = (style | WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
                    user32.SetWindowLongPtrW(root, GWL_STYLE, ctypes.c_void_p(new_style))
                    
                    # Force frame change to apply styling immediately
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_NOZORDER = 0x0004
                    SWP_FRAMECHANGED = 0x0020
                    user32.SetWindowPos(root, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
                    
                    # Stop scanner timer
                    self._enforce_timer.stop()
            except Exception:
                pass

    def closeEvent(self, event):
        """Release audio stream explicitly when app terminates."""
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
