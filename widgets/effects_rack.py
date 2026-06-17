import os
import math
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QScrollArea, QFileDialog, QSizePolicy, QMessageBox,
    QMenu
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPainterPath, QLinearGradient, QBrush, QPainter, QPen
from pedalboard import (
    NoiseGate, Distortion, Chorus, Phaser, Delay, Reverb,
    PitchShift, Compressor, LowpassFilter, HighpassFilter, load_plugin
)
from audio_engine import EffectWrapper, TubeOverdrive
from widgets.knob import CustomKnob

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
        # Black titlebar
        DWMWA_CAPTION_COLOR = 35
        black_color = ctypes.c_int(0x00000000)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR,
            ctypes.byref(black_color), ctypes.sizeof(black_color)
        )
        
        # White text
        DWMWA_TEXT_COLOR = 36
        white_color = ctypes.c_int(0x00FFFFFF)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_TEXT_COLOR,
            ctypes.byref(white_color), ctypes.sizeof(white_color)
        )
        
        # Dark gray border (#222225 -> COLORREF is 0x00252222)
        DWMWA_BORDER_COLOR = 34
        border_color = ctypes.c_int(0x00252222)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_BORDER_COLOR,
            ctypes.byref(border_color), ctypes.sizeof(border_color)
        )
        
        # Force redraw of the window frame
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception as e:
        print(f"Failed to apply dark theme to hwnd: {e}")


def scan_for_vst3s(search_paths):
    vst_list = []
    for path in search_paths:
        if not os.path.exists(path):
            continue
        try:
            for root, dirs, files in os.walk(path):
                vst_dirs = [d for d in dirs if d.lower().endswith('.vst3')]
                for d in vst_dirs:
                    full_path = os.path.join(root, d)
                    name = os.path.splitext(d)[0]
                    vst_list.append((name, full_path))
                
                dirs[:] = [d for d in dirs if not d.lower().endswith('.vst3')]
                
                for f in files:
                    if f.lower().endswith('.vst3'):
                        full_path = os.path.join(root, f)
                        name = os.path.splitext(f)[0]
                        if not any(item[1] == full_path for item in vst_list):
                            vst_list.append((name, full_path))
        except Exception as e:
            print(f"Error scanning VST path {path}: {e}")
    vst_list.sort(key=lambda x: x[0].lower())
    return vst_list

# Map of parameter names to their UI configurations
PARAM_METADATA = {
    "threshold_db": {"label": "Threshold", "min": -80.0, "max": 0.0, "default": -40.0, "unit": "dB", "decimals": 1},
    "ratio": {"label": "Ratio", "min": 1.0, "max": 20.0, "default": 4.0, "unit": ":1", "decimals": 1},
    "attack_ms": {"label": "Attack", "min": 0.1, "max": 200.0, "default": 2.0, "unit": "ms", "decimals": 1},
    "release_ms": {"label": "Release", "min": 10.0, "max": 2000.0, "default": 150.0, "unit": "ms", "decimals": 0},
    "drive_db": {"label": "Drive", "min": 0.0, "max": 50.0, "default": 20.0, "unit": "dB", "decimals": 1},
    "tone": {"label": "Tone", "min": 0.0, "max": 1.0, "default": 0.5, "unit": "", "decimals": 2},
    "level_db": {"label": "Level", "min": -20.0, "max": 20.0, "default": 0.0, "unit": "dB", "decimals": 1},
    "rate_hz": {"label": "Rate", "min": 0.05, "max": 10.0, "default": 1.0, "unit": "Hz", "decimals": 2},
    "depth": {"label": "Depth", "min": 0.0, "max": 1.0, "default": 0.5, "unit": "", "decimals": 2},
    "feedback": {"label": "Feedback", "min": 0.0, "max": 0.99, "default": 0.25, "unit": "", "decimals": 2},
    "mix": {"label": "Mix", "min": 0.0, "max": 1.0, "default": 0.5, "unit": "", "decimals": 2},
    "delay_seconds": {"label": "Delay", "min": 0.01, "max": 2.0, "default": 0.3, "unit": "s", "decimals": 2},
    "room_size": {"label": "Room Size", "min": 0.0, "max": 1.0, "default": 0.5, "unit": "", "decimals": 2},
    "damping": {"label": "Damping", "min": 0.0, "max": 1.0, "default": 0.5, "unit": "", "decimals": 2},
    "wet_level": {"label": "Wet Level", "min": 0.0, "max": 1.0, "default": 0.3, "unit": "", "decimals": 2},
    "dry_level": {"label": "Dry Level", "min": 0.0, "max": 1.0, "default": 0.7, "unit": "", "decimals": 2},
    "width": {"label": "Width", "min": 0.0, "max": 1.0, "default": 1.0, "unit": "", "decimals": 2},
    "semitones": {"label": "Pitch", "min": -12.0, "max": 12.0, "default": 0.0, "unit": "st", "decimals": 1},
    "cutoff_frequency_hz": {"label": "Cutoff", "min": 20.0, "max": 20000.0, "default": 1000.0, "unit": "Hz", "decimals": 0},
}

EFFECT_TYPES = {
    "Noise Gate": "NoiseGate",
    "Overdrive": "Distortion",
    "Chorus": "Chorus",
    "Phaser": "Phaser",
    "Delay": "Delay",
    "Reverb": "Reverb",
    "Pitch Shift": "PitchShift",
    "Compressor": "Compressor",
    "Lowpass Filter": "LowpassFilter",
    "Highpass Filter": "HighpassFilter",
}



class EffectCard(QFrame):
    """Visual card representing a single effect in the track rack."""
    effectChanged = Signal()  # Emitted when parameter, bypass, or delete changes
    effectDuplicated = Signal(object) # Emitted when duplicate action is triggered
    
    def __init__(self, wrapper, track, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.track = track
        self.is_selected = False
        self.drag_start_position = None
        self.setProperty("selected", False)
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("EffectCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        
        # Calculate responsive width based on parameter/knob count
        num_knobs = 0
        if self.wrapper.effect_type != "VST3":
            from project_manager import EFFECT_CLASSES
            if self.wrapper.effect_type in EFFECT_CLASSES:
                _, params = EFFECT_CLASSES[self.wrapper.effect_type]
                num_knobs = sum(1 for p in params if p in PARAM_METADATA)
        else:
            num_knobs = 2
        
        card_width = max(250, 30 + num_knobs * 80)
        self.setMinimumWidth(card_width)
        self.setMaximumWidth(card_width + 30)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        
        # --- HEADER ROW ---
        header = QHBoxLayout()
        header.setSpacing(6)
        
        # Bypass toggle (power icon)
        self.btn_bypass = QPushButton("⏻")
        self.btn_bypass.setCheckable(True)
        self.btn_bypass.setChecked(not self.wrapper.is_active)  # Checked is bypassed/off
        self.btn_bypass.setObjectName("BypassButton")
        self.btn_bypass.setToolTip("Toggle Bypass")
        self.btn_bypass.clicked.connect(self.on_bypass_toggle)
        header.addWidget(self.btn_bypass)
        
        # Effect Name Label
        self.label_name = QLabel(self.wrapper.name)
        self.label_name.setObjectName("EffectNameLabel")
        header.addWidget(self.label_name)
        
        header.addStretch()
        
        if self.wrapper.effect_type == "VST3":
            self.btn_settings = QPushButton("⚙")
            self.btn_settings.setObjectName("SettingsButton")
            self.btn_settings.setToolTip("Open VST Settings")
            self.btn_settings.clicked.connect(self.open_vst_editor)
            header.addWidget(self.btn_settings)
        
        # Delete Button (X)
        self.btn_delete = QPushButton("✕")
        self.btn_delete.setObjectName("DeleteButton")
        self.btn_delete.setToolTip("Remove Effect")
        self.btn_delete.clicked.connect(self.on_delete_clicked)
        header.addWidget(self.btn_delete)
        
        layout.addLayout(header)
        
        # --- BODY ROW (Knobs / Settings) ---
        body = QHBoxLayout()
        body.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        body.setSpacing(15)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.wrapper.effect_type != "VST3":
            # Render custom knobs for built-in effects
            from project_manager import EFFECT_CLASSES
            if self.wrapper.effect_type in EFFECT_CLASSES:
                _, params = EFFECT_CLASSES[self.wrapper.effect_type]
                for p_name in params:
                    if p_name in PARAM_METADATA:
                        meta = PARAM_METADATA[p_name]
                        curr_val = getattr(self.wrapper.effect, p_name, meta["default"])
                        
                        knob = CustomKnob(
                            label=meta["label"].upper(),
                            min_val=meta["min"],
                            max_val=meta["max"],
                            default_val=meta["default"],
                            unit=meta["unit"],
                            decimals=meta["decimals"]
                        )
                        knob.setValue(curr_val)
                        knob.valueChanged.connect(
                            lambda val, name=p_name: self.on_parameter_changed(name, val)
                        )
                        body.addWidget(knob)
                body.addStretch()
        else:
            body.addStretch()
            self.knob_mix = CustomKnob(
                label="MIX",
                min_val=0.0,
                max_val=100.0,
                default_val=100.0,
                unit="%",
                decimals=0
            )
            self.knob_mix.setValue(getattr(self.wrapper, "mix", 1.0) * 100.0)
            self.knob_mix.valueChanged.connect(self.on_vst_mix_changed)
            body.addWidget(self.knob_mix)
            
            self.knob_gain = CustomKnob(
                label="GAIN",
                min_val=-24.0,
                max_val=12.0,
                default_val=0.0,
                unit="dB",
                decimals=1
            )
            self.knob_gain.setValue(getattr(self.wrapper, "gain_db", 0.0))
            self.knob_gain.valueChanged.connect(self.on_vst_gain_changed)
            body.addWidget(self.knob_gain)
            body.addStretch()
                        
        layout.addLayout(body)
        layout.addStretch()
        
        # Apply Card Styles
        self.setStyleSheet("""
            EffectCard {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
            }
            QPushButton#BypassButton {
                font-family: "Consolas", "Courier New", monospace;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
                min-width: 26px;
                min-height: 26px;
                max-width: 26px;
                max-height: 26px;
                color: #000000;
                background-color: #ffffff;
                border: 1px solid #ffffff;
            }
            QPushButton#BypassButton:checked {
                color: #88888c;
                background-color: #0b0b0c;
                border-color: #222225;
            }
            QLabel#EffectNameLabel {
                color: #ffffff;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QPushButton#SettingsButton {
                color: #88888c;
                font-family: "Consolas", "Courier New", monospace;
                font-weight: bold;
                background: transparent;
                border: none;
                font-size: 13px;
                min-width: 20px;
                min-height: 20px;
            }
            QPushButton#SettingsButton:hover {
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }
            QPushButton#DeleteButton {
                color: #88888c;
                font-family: "Consolas", "Courier New", monospace;
                font-weight: bold;
                background: transparent;
                border: none;
                font-size: 12px;
                min-width: 20px;
                min-height: 20px;
            }
            QPushButton#DeleteButton:hover {
                color: #ff0033;
                background-color: rgba(255, 0, 51, 0.1);
                border-radius: 10px;
            }
            QLabel#VstPathLabel {
                color: #888888;
                font-size: 10px;
                font-family: "Segoe UI", sans-serif;
            }
            EffectCard[selected="true"] {
                border-color: #ffffff;
                background-color: #121214;
            }
        """)
        
    def on_bypass_toggle(self):
        # Wrapper is bypassed if bypass button is checked
        self.wrapper.is_active = not self.btn_bypass.isChecked()
        self.track.update_pedalboard()
        self.effectChanged.emit()
        
    def on_parameter_changed(self, param_name, value):
        if hasattr(self.wrapper.effect, param_name):
            setattr(self.wrapper.effect, param_name, value)

    def on_vst_mix_changed(self, value):
        self.wrapper.mix = value / 100.0
        self.effectChanged.emit()

    def on_vst_gain_changed(self, value):
        self.wrapper.gain_db = value
        self.effectChanged.emit()

    def set_selected(self, selected):
        if self.is_selected == selected:
            return
        self.is_selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def open_vst_editor(self):
        main_window = self.window()
        if hasattr(main_window, 'open_vst_in_tab'):
            main_window.open_vst_in_tab(self, self.wrapper)
        else:
            if hasattr(self.wrapper.effect, "show_editor"):
                self.wrapper.effect.show_editor()
            else:
                QMessageBox.warning(self, "VST3 Editor", "This plugin does not support a custom editor interface.")
            
    def mousePressEvent(self, event):
        child = self.childAt(event.pos())
        if child in (None, self, self.label_name) or (hasattr(self, 'lbl_vst_path') and child == self.lbl_vst_path) or isinstance(child, QLabel):
            effects_rack = self.find_effects_rack()
            if effects_rack:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: effects_rack.select_card(self))
                
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_start_position = event.pos()
                
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.wrapper.effect_type == "VST3":
                self.open_vst_editor()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if not hasattr(self, 'drag_start_position') or self.drag_start_position is None:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return
            
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import QMimeData
        
        drag = QDrag(self)
        mime_data = QMimeData()
        try:
            effect_idx = self.track.effects.index(self.wrapper)
            mime_data.setText(f"effect:{effect_idx}")
        except ValueError:
            return
        drag.setMimeData(mime_data)
        
        pixmap = self.grab()
        scaled_pixmap = pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation)
        drag.setPixmap(scaled_pixmap)
        drag.setHotSpot(event.pos() * (200 / pixmap.width()))
        
        drag.exec(Qt.DropAction.MoveAction)
        self.drag_start_position = None

    def contextMenuEvent(self, event):
        from PySide6.QtGui import QAction
        
        effects_rack = self.find_effects_rack()
        if effects_rack:
            effects_rack.select_card(self)
            
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0b0b0c;
                color: #e2e2e5;
                border: 1px solid #222225;
            }
            QMenu::item:selected {
                background-color: #222225;
                color: #ffffff;
            }
        """)
        
        action_duplicate = QAction("Duplicate Effect", self)
        action_duplicate.triggered.connect(self.trigger_duplicate)
        menu.addAction(action_duplicate)
        
        menu.addSeparator()
        
        action_delete = QAction("Delete Effect", self)
        action_delete.triggered.connect(self.on_delete_clicked)
        menu.addAction(action_delete)
        
        menu.exec(event.globalPos())

    def trigger_duplicate(self):
        self.effectDuplicated.emit(self.wrapper)

    def find_effects_rack(self):
        p = self.parent()
        while p:
            if isinstance(p, EffectsRack):
                return p
            p = p.parent()
        return None

    def on_delete_clicked(self):
        self.track.effects.remove(self.wrapper)
        self.track.update_pedalboard()
        self.effectChanged.emit()

class EffectsContainer(QWidget):
    def __init__(self, effects_rack, parent=None):
        super().__init__(parent)
        self.effects_rack = effects_rack
        self.setAcceptDrops(True)
        self.drop_indicator_x = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("effect:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("effect:"):
            drop_pos = event.position().toPoint()
            self.drop_indicator_x = self.effects_rack.calculate_drop_line_x(drop_pos.x())
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_indicator_x = None
        self.update()
        event.accept()

    def dropEvent(self, event):
        mime_text = event.mimeData().text()
        if mime_text.startswith("effect:"):
            try:
                effect_idx = int(mime_text.split(":")[1])
            except ValueError:
                event.ignore()
                return
            
            drop_pos = event.position().toPoint()
            self.drop_indicator_x = None
            self.update()
            self.effects_rack.reorder_effects(effect_idx, drop_pos.x())
            event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drop_indicator_x is not None:
            from PySide6.QtGui import QPainter, QPen, QColor
            painter = QPainter(self)
            try:
                painter.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine))
                painter.drawLine(self.drop_indicator_x, 0, self.drop_indicator_x, self.height())
            finally:
                painter.end()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.effects_rack.show_vst_menu_at(event.globalPosition().toPoint())
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.effects_rack.show_empty_space_context_menu(event.globalPos())
class EffectsRack(QWidget):
    """Rack panel containing list of active effects and add menus."""
    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        self.selected_track = None
        self.selected_effect_wrapper = None
        self.signal_flow_widget = None
        
        self.setup_ui()

    def set_signal_flow_widget(self, flow_widget):
        self.signal_flow_widget = flow_widget
        if self.selected_track and self.signal_flow_widget:
            self.signal_flow_widget.set_track(self.selected_track)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # --- TOP PANEL: Add Effect Controls ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        
        self.lbl_title = QLabel("Effects Rack")
        self.lbl_title.setObjectName("RackTitle")
        self.lbl_title.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        top_bar.addWidget(self.lbl_title)
        
        top_bar.addStretch()
        
        self.combo_fx = QComboBox()
        self.combo_fx.setObjectName("AddEffectCombo")
        self.combo_fx.addItem("Add Built-in Effect...", None)
        for name in EFFECT_TYPES.keys():
            self.combo_fx.addItem(name, EFFECT_TYPES[name])
        self.combo_fx.activated.connect(self.on_combo_fx_activated)
        top_bar.addWidget(self.combo_fx)
        
        self.btn_add_vst = QPushButton("Load VST3...")
        self.btn_add_vst.setObjectName("AddVstButton")
        self.vst_menu = QMenu(self)
        self.vst_menu.aboutToShow.connect(self.populate_vst_menu)
        self.btn_add_vst.setMenu(self.vst_menu)
        top_bar.addWidget(self.btn_add_vst)
        
        layout.addLayout(top_bar)
        
        # --- MIDDLE PANEL: Scrolling list of cards ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("RackScrollArea")
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scroll_widget = EffectsContainer(self)
        self.scroll_widget.setObjectName("RackScrollWidget")
        self.scroll_layout = QHBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(10)
        self.scroll_layout.addStretch()  # Pin elements to the left
        
        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area)
        
        # Styling
        self.setStyleSheet("""
            QLabel#RackTitle {
                color: #ffffff;
                font-family: "Consolas", "Courier New", monospace;
            }
            QComboBox#AddEffectCombo {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
                color: #88888c;
                padding: 5px 10px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                min-width: 150px;
            }
            QPushButton#AddFxButton {
                background-color: #0b0b0c;
                color: #88888c;
                font-family: "Consolas", "Courier New", monospace;
                font-weight: bold;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
            }
            QPushButton#AddFxButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
                border-color: #444448;
            }
            QPushButton#AddVstButton {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
                color: #88888c;
                font-family: "Consolas", "Courier New", monospace;
                font-weight: bold;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton#AddVstButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
                border-color: #444448;
            }
            #RackScrollArea {
                background: transparent;
            }
            #RackScrollWidget {
                background: transparent;
            }
        """)
        
    def set_track(self, track):
        """Sets the active track and redraws cards."""
        self.selected_track = track
        if self.signal_flow_widget:
            self.signal_flow_widget.set_track(track)
        self.refresh_rack()
        
    def select_card(self, card):
        self.selected_effect_wrapper = card.wrapper if card else None
        if self.signal_flow_widget:
            self.signal_flow_widget.refresh_flow()
        
        # Go through all cards and update their selected state
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item:
                w = item.widget()
                if isinstance(w, EffectCard):
                    w.set_selected(w == card)

    def on_effect_duplicated(self, wrapper):
        if not self.selected_track:
            return
        import project_manager
        try:
            serialized = project_manager.serialize_effect(wrapper)
            new_wrapper = project_manager.deserialize_effect(serialized)
            if new_wrapper:
                idx = self.selected_track.effects.index(wrapper)
                self.selected_track.effects.insert(idx + 1, new_wrapper)
                try:
                    self.selected_track.update_pedalboard(self.audio_engine.sample_rate)
                except Exception as e:
                    self.selected_track.effects.remove(new_wrapper)
                    raise e
                self.refresh_rack()
                self.mark_dirty()
                if self.signal_flow_widget:
                    self.signal_flow_widget.refresh_flow()
        except Exception as e:
            print(f"Error duplicating effect: {e}")

    def calculate_drop_line_x(self, drop_x):
        cards = []
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and isinstance(item.widget(), EffectCard):
                cards.append(item.widget())
        if not cards:
            return 0
        for card in cards:
            card_geom = card.geometry()
            card_x_center = card_geom.x() + card_geom.width() / 2
            if drop_x < card_x_center:
                return card_geom.x() - 5
        last_card_geom = cards[-1].geometry()
        return last_card_geom.x() + last_card_geom.width() + 5

    def reorder_effects(self, dragged_effect_index, drop_x):
        if not self.selected_track:
            return
        effects = self.selected_track.effects
        if dragged_effect_index >= len(effects):
            return
        dragged_wrapper = effects[dragged_effect_index]
        cards = []
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and isinstance(item.widget(), EffectCard):
                cards.append(item.widget())
        new_index = 0
        inserted = False
        for i, card in enumerate(cards):
            if card.wrapper == dragged_wrapper:
                continue
            card_x_center = card.geometry().x() + card.geometry().width() / 2
            if drop_x < card_x_center:
                new_index = i
                inserted = True
                break
        if not inserted:
            new_index = len(cards) - 1
            if new_index < 0:
                new_index = 0
        old_index = dragged_effect_index
        if old_index == new_index:
            return
        dragged_card = None
        for card in cards:
            if card.wrapper == dragged_wrapper:
                dragged_card = card
                break
        if not dragged_card:
            return
        card_width = dragged_card.width()
        from PySide6.QtCore import QVariantAnimation
        self.reorder_anim = QVariantAnimation(self)
        self.reorder_anim.setDuration(120)
        self.reorder_anim.setStartValue(card_width)
        self.reorder_anim.setEndValue(0)
        def on_collapse_val(val):
            dragged_card.setFixedWidth(val)
        self.reorder_anim.valueChanged.connect(on_collapse_val)
        def on_collapse_finished():
            self.reorder_anim.valueChanged.disconnect()
            try:
                self.reorder_anim.finished.disconnect()
            except RuntimeError:
                pass
            self.selected_track.effects.remove(dragged_wrapper)
            self.selected_track.effects.insert(new_index, dragged_wrapper)
            self.selected_track.update_pedalboard(self.audio_engine.sample_rate)
            self.refresh_rack()
            self.mark_dirty()
            new_cards = []
            for i in range(self.scroll_layout.count()):
                item = self.scroll_layout.itemAt(i)
                if item and isinstance(item.widget(), EffectCard):
                    new_cards.append(item.widget())
            new_dragged_card = None
            for card in new_cards:
                if card.wrapper == dragged_wrapper:
                    new_dragged_card = card
                    break
            if not new_dragged_card:
                return
            self.reorder_anim_expand = QVariantAnimation(self)
            self.reorder_anim_expand.setDuration(120)
            self.reorder_anim_expand.setStartValue(0)
            self.reorder_anim_expand.setEndValue(card_width)
            def on_expand_val(val):
                new_dragged_card.setFixedWidth(val)
            self.reorder_anim_expand.valueChanged.connect(on_expand_val)
            def on_expand_finished():
                num_knobs = 0
                if new_dragged_card.wrapper.effect_type != "VST3":
                    from project_manager import EFFECT_CLASSES
                    if new_dragged_card.wrapper.effect_type in EFFECT_CLASSES:
                        _, params = EFFECT_CLASSES[new_dragged_card.wrapper.effect_type]
                        num_knobs = sum(1 for p in params if p in PARAM_METADATA)
                else:
                    num_knobs = 2
                cw = max(250, 30 + num_knobs * 80)
                new_dragged_card.setMinimumWidth(cw)
                new_dragged_card.setMaximumWidth(cw + 30)
                new_dragged_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
                new_dragged_card.updateGeometry()
            self.reorder_anim_expand.finished.connect(on_expand_finished)
            self.reorder_anim_expand.start()
            if self.signal_flow_widget:
                self.signal_flow_widget.refresh_flow()
        self.reorder_anim.finished.connect(on_collapse_finished)
        self.reorder_anim.start()

    def refresh_rack(self):
        """Clears and rebuilds the effects list."""
        if self.signal_flow_widget:
            self.signal_flow_widget.refresh_flow()
            
        # Clear existing card widgets (except the spacer stretch)
        while self.scroll_layout.count() > 1:
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        if not self.selected_track:
            self.lbl_title.setText("Effects Rack (No Track Selected)")
            self.combo_fx.setEnabled(False)
            self.btn_add_vst.setEnabled(False)
            return
            
        self.lbl_title.setText(f"Effects Rack: {self.selected_track.name}")
        self.combo_fx.setEnabled(True)
        self.btn_add_vst.setEnabled(True)
        
        # Verify selected effect wrapper is still in effects list
        if self.selected_effect_wrapper not in self.selected_track.effects:
            if self.selected_track.effects:
                self.selected_effect_wrapper = self.selected_track.effects[0]
            else:
                self.selected_effect_wrapper = None
                
        selected_card = None
        # Insert cards for each effect (above the stretch spacer)
        for wrapper in self.selected_track.effects:
            card = EffectCard(wrapper, self.selected_track)
            card.effectChanged.connect(self.refresh_rack)
            card.effectChanged.connect(self.mark_dirty)
            card.effectDuplicated.connect(self.on_effect_duplicated)
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, card)
            
            if wrapper == self.selected_effect_wrapper:
                card.set_selected(True)
                selected_card = card
            else:
                card.set_selected(False)
                
    def mark_dirty(self):
        main_win = self.window()
        if main_win and hasattr(main_win, 'mark_project_dirty'):
            main_win.mark_project_dirty()
                
    def on_combo_fx_activated(self, index):
        if not self.selected_track:
            return
        fx_type = self.combo_fx.itemData(index)
        if not fx_type:
            return
        display_name = self.combo_fx.itemText(index)
        self.add_builtin_effect_by_type(fx_type, display_name)
        self.combo_fx.setCurrentIndex(0)

    def add_builtin_effect_by_type(self, fx_type, display_name):
        if not self.selected_track:
            return
        effect_obj = None
        try:
            if fx_type == "NoiseGate":
                effect_obj = NoiseGate(threshold_db=-45, ratio=10, attack_ms=1.5, release_ms=80.0)
            elif fx_type == "Distortion":
                effect_obj = TubeOverdrive(drive_db=15.0, tone=0.5, level_db=0.0)
            elif fx_type == "Chorus":
                effect_obj = Chorus(rate_hz=1.2, depth=0.3, feedback=0.1, mix=0.4)
            elif fx_type == "Phaser":
                effect_obj = Phaser(rate_hz=1.0, depth=0.5, feedback=0.0, mix=0.5)
            elif fx_type == "Delay":
                effect_obj = Delay(delay_seconds=0.3, feedback=0.3, mix=0.4)
            elif fx_type == "Reverb":
                effect_obj = Reverb(room_size=0.6, damping=0.4, wet_level=0.25, dry_level=0.85, width=1.0)
            elif fx_type == "PitchShift":
                effect_obj = PitchShift(semitones=0)
            elif fx_type == "Compressor":
                effect_obj = Compressor(threshold_db=-18.0, ratio=3.5, attack_ms=5.0, release_ms=100.0)
            elif fx_type == "LowpassFilter":
                effect_obj = LowpassFilter(cutoff_frequency_hz=1500)
            elif fx_type == "HighpassFilter":
                effect_obj = HighpassFilter(cutoff_frequency_hz=80)
        except Exception as e:
            main_window = self.window()
            if hasattr(main_window, 'show_themed_message_box'):
                main_window.show_themed_message_box("Effect Error", f"Could not create effect: {e}", QMessageBox.Icon.Critical)
            else:
                QMessageBox.critical(self, "Effect Error", f"Could not create effect: {e}")
            return
            
        if effect_obj:
            wrapper = EffectWrapper(effect_obj, display_name, fx_type, is_active=True)
            self.selected_track.effects.append(wrapper)
            try:
                self.selected_track.update_pedalboard(self.audio_engine.sample_rate if self.audio_engine else 44100)
            except Exception as e:
                self.selected_track.effects.remove(wrapper)
                raise e
            self.refresh_rack()
            self.mark_dirty()

    def show_vst_menu_at(self, global_pos):
        self.populate_vst_menu()
        self.vst_menu.exec(global_pos)

    def show_empty_space_context_menu(self, global_pos):
        if not self.selected_track:
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0b0b0c;
                color: #e2e2e5;
                border: 1px solid #222225;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #222225;
                color: #ffffff;
            }
        """)
        
        vst_sub = menu.addMenu("Add VST")
        vst_sub.setStyleSheet(menu.styleSheet())
        
        search_paths = getattr(self.audio_engine, "vst_search_paths", ["C:\\Program Files\\Common Files\\VST3"])
        scanned_vsts = scan_for_vst3s(search_paths)
        if scanned_vsts:
            for name, path in scanned_vsts:
                action = vst_sub.addAction(name)
                action.triggered.connect(lambda checked=False, p=path: self.load_scanned_vst3(p))
            vst_sub.addSeparator()
        action_browse = vst_sub.addAction("Browse for VST3 file...")
        action_browse.triggered.connect(self.on_load_vst3)
        
        fx_sub = menu.addMenu("Add Effect")
        fx_sub.setStyleSheet(menu.styleSheet())
        for name, fx_type in EFFECT_TYPES.items():
            action = fx_sub.addAction(name)
            action.triggered.connect(lambda checked=False, t=fx_type, n=name: self.add_builtin_effect_by_type(t, n))
            
        menu.addSeparator()
        
        action_clear = menu.addAction("Clear All")
        action_clear.triggered.connect(self.clear_all_effects)
        
        menu.exec(global_pos)

    def clear_all_effects(self):
        if not self.selected_track:
            return
        main_window = self.window()
        if hasattr(main_window, 'show_themed_message_box'):
            reply = main_window.show_themed_message_box(
                "Clear All Effects",
                "Are you sure you want to clear all effects from this track?",
                QMessageBox.Icon.Question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self, "Clear All Effects",
                "Are you sure you want to clear all effects from this track?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        if reply == QMessageBox.StandardButton.Yes:
            self.selected_track.effects.clear()
            self.selected_track.update_pedalboard(self.audio_engine.sample_rate if self.audio_engine else 44100)
            self.refresh_rack()
            self.mark_dirty()
            
    def on_load_vst3(self):
        if not self.selected_track:
            return
            
        file_filter = "VST3 Plugins (*.vst3)"
        dlg = QFileDialog(self)
        dlg.setWindowTitle("Select VST3 Plugin File")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setNameFilter(file_filter)
        dlg.setDirectory("C:\\Program Files\\Common Files\\VST3")
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        apply_dark_theme_to_hwnd(int(dlg.winId()))
        
        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            file_path = dlg.selectedFiles()[0]
            self.load_scanned_vst3(file_path)
 
    def populate_vst_menu(self):
        self.vst_menu.clear()
        self.vst_menu.setStyleSheet("""
            QMenu {
                background-color: #000000;
                color: #88888c;
                border: 1px solid #222225;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 20px;
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
        """)
        
        search_paths = getattr(self.audio_engine, "vst_search_paths", ["C:\\Program Files\\Common Files\\VST3"])
        scanned_vsts = scan_for_vst3s(search_paths)
        
        if scanned_vsts:
            for name, path in scanned_vsts:
                action = self.vst_menu.addAction(name)
                action.triggered.connect(lambda checked=False, p=path: self.load_scanned_vst3(p))
            self.vst_menu.addSeparator()
            
        action_browse = self.vst_menu.addAction("Browse for VST3 file...")
        action_browse.triggered.connect(self.on_load_vst3)

    def load_scanned_vst3(self, file_path):
        if not self.selected_track:
            return
            
        main_window = self.window()
        from widgets.loading_popup import LoadingPopup
        popup = LoadingPopup(f"LOADING VST PLUGIN:\n{os.path.basename(file_path).upper()}", main_window)
        popup.show()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        was_running = False
        if self.audio_engine:
            was_running = self.audio_engine.is_running
            self.audio_engine.stop_stream()
            
        try:
            if popup.was_cancelled:
                return
            from audio_engine import load_vst_plugin
            vst_obj = load_vst_plugin(file_path)
            filename = os.path.splitext(os.path.basename(file_path))[0]
            
            wrapper = EffectWrapper(vst_obj, filename, "VST3", is_active=True)
            wrapper.original_vst_path = file_path
            self.selected_track.effects.append(wrapper)
            try:
                self.selected_track.update_pedalboard(self.audio_engine.sample_rate if self.audio_engine else 44100)
            except Exception as e:
                self.selected_track.effects.remove(wrapper)
                raise e
            
            self.refresh_rack()
            
            if hasattr(main_window, 'mark_project_dirty'):
                main_window.mark_project_dirty()
        except Exception as e:
            err_text = f"Failed to load VST3 plugin at {file_path}.\n\nError details: {e}"
            if hasattr(main_window, 'show_themed_message_box'):
                main_window.show_themed_message_box("VST3 Error", err_text, QMessageBox.Icon.Critical)
            else:
                QMessageBox.warning(self, "VST3 Error", err_text)
        finally:
            popup.close()
            if was_running and self.audio_engine:
                self.audio_engine.start_stream()
