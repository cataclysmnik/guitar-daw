from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QSlider,
    QComboBox, QPushButton, QLineEdit, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from widgets.knob import CustomKnob
from widgets.level_meter import LevelMeter

class TrackCard(QFrame):
    """Card-style Track widget displaying track settings and VU meter."""
    trackSelected = Signal(object)  # Emitted when the card is clicked/selected
    trackRemoved = Signal(object)   # Emitted when delete button is pressed
    
    def __init__(self, track, audio_engine, parent=None):
        super().__init__(parent)
        self.track = track
        self.audio_engine = audio_engine
        self.is_selected = False
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(150)
        self.setObjectName("TrackCard")
        self.setProperty("selected", False)
        
        self.setup_ui()
        
        # Setup level meter polling timer
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.update_levels)
        self.poll_timer.start(33)  # Polling level at ~30 FPS
        
    def setup_ui(self):
        # Master horizontal layout for card contents
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 10, 10)
        main_layout.setSpacing(12)
        
        # --- PANEL 1: Track Details & State Buttons ---
        details_layout = QVBoxLayout()
        details_layout.setSpacing(6)
        
        # Row 1: Track Number, Name & Delete Button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)
        
        # Track Number Badge
        self.lbl_num = QLabel(f"{self.track.track_id:02d}")
        self.lbl_num.setObjectName("TrackNumberLabel")
        header_layout.addWidget(self.lbl_num)
        
        # Editable Track Name
        self.name_edit = QLineEdit(self.track.name)
        self.name_edit.setObjectName("TrackNameEdit")
        self.name_edit.setToolTip("Double-click to rename track")
        self.name_edit.editingFinished.connect(self.on_rename)
        header_layout.addWidget(self.name_edit)
        
        # Sleek small Delete Button
        self.btn_delete = QPushButton("×")
        self.btn_delete.setObjectName("DeleteTrackButton")
        self.btn_delete.setToolTip("Delete Track")
        self.btn_delete.clicked.connect(self.on_delete_clicked)
        self.btn_delete.setFixedSize(18, 18)
        header_layout.addWidget(self.btn_delete)
        
        details_layout.addLayout(header_layout)
        
        # Row 2: Controls Row (M, S, R, FX)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)
        
        self.btn_mute = QPushButton("M")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setChecked(self.track.mute)
        self.btn_mute.setObjectName("MuteButton")
        self.btn_mute.setToolTip("Mute Track")
        self.btn_mute.clicked.connect(self.on_mute_clicked)
        
        self.btn_solo = QPushButton("S")
        self.btn_solo.setCheckable(True)
        self.btn_solo.setChecked(self.track.solo)
        self.btn_solo.setObjectName("SoloButton")
        self.btn_solo.setToolTip("Solo Track")
        self.btn_solo.clicked.connect(self.on_solo_clicked)
        
        self.btn_arm = QPushButton("R")
        self.btn_arm.setCheckable(True)
        self.btn_arm.setChecked(self.track.armed)
        self.btn_arm.setObjectName("ArmButton")
        self.btn_arm.setToolTip("Arm Track for Input Monitoring")
        self.btn_arm.clicked.connect(self.on_arm_clicked)
        
        self.btn_fx = QPushButton("FX")
        self.btn_fx.setObjectName("FxButton")
        self.btn_fx.setToolTip("View/edit effects rack for this track")
        self.btn_fx.clicked.connect(self.on_fx_clicked)
        
        controls_layout.addWidget(self.btn_mute)
        controls_layout.addWidget(self.btn_solo)
        controls_layout.addWidget(self.btn_arm)
        controls_layout.addWidget(self.btn_fx)
        controls_layout.addStretch()
        
        details_layout.addLayout(controls_layout)
        
        # Row 3: Input Channel Selector
        self.combo_input = QComboBox()
        self.combo_input.setObjectName("InputChannelCombo")
        self.combo_input.setToolTip("Select Track Input Channel")
        self.populate_inputs()
        self.combo_input.currentIndexChanged.connect(self.on_input_changed)
        details_layout.addWidget(self.combo_input)
        
        main_layout.addLayout(details_layout)
        
        # --- PANEL 2: Panning Knob ---
        panning_layout = QVBoxLayout()
        panning_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Custom Pan Knob
        self.pan_knob = CustomKnob(
            label="PAN",
            min_val=-1.0,
            max_val=1.0,
            default_val=self.track.pan,
            decimals=2
        )
        self.pan_knob.valueChanged.connect(self.on_pan_changed)
        panning_layout.addWidget(self.pan_knob)
        
        main_layout.addLayout(panning_layout)
        
        # --- PANEL 3: Volume Fader ---
        vol_layout = QVBoxLayout()
        vol_layout.setSpacing(4)
        vol_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.vol_slider = QSlider(Qt.Orientation.Vertical)
        self.vol_slider.setMinimum(-600)  # -60.0 dB
        self.vol_slider.setMaximum(60)    # +6.0 dB
        self.vol_slider.setValue(int(self.track.volume * 10))
        self.vol_slider.setObjectName("VolumeSlider")
        self.vol_slider.valueChanged.connect(self.on_volume_changed)
        vol_layout.addWidget(self.vol_slider)
        
        self.vol_label = QLabel("0.0 dB")
        self.vol_label.setObjectName("VolDbLabel")
        self.vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vol_label.setFont(QFont("Consolas", 8))
        vol_layout.addWidget(self.vol_label)
        self.update_volume_label(self.track.volume)
        
        main_layout.addLayout(vol_layout)
        
        # --- PANEL 4: Custom vertical LED VU Meter ---
        self.level_meter = LevelMeter()
        main_layout.addWidget(self.level_meter)
        
        self.setStyleSheet("""
            TrackCard {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
            }
            TrackCard[selected="true"] {
                background-color: #000000;
                border: 1px solid #ffffff;
            }
            TrackCard:hover {
                border-color: #444448;
            }
            
            QLabel#TrackNumberLabel {
                color: #555558;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 13px;
                font-weight: bold;
            }
            TrackCard[selected="true"] QLabel#TrackNumberLabel {
                color: #ffffff;
            }
            
            QLineEdit#TrackNameEdit {
                background: transparent;
                color: #e2e2e5;
                border: none;
                border-bottom: 1px solid transparent;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 13px;
                font-weight: bold;
                padding-bottom: 1px;
            }
            QLineEdit#TrackNameEdit:focus {
                border-bottom: 1px solid #ffffff;
                color: #ffffff;
            }
            QLineEdit#TrackNameEdit:hover {
                background-color: rgba(255, 255, 255, 0.02);
            }
            
            QPushButton#MuteButton, QPushButton#SoloButton, QPushButton#ArmButton, QPushButton#FxButton {
                font-family: "Consolas", "Courier New", monospace;
                font-size: 10px;
                font-weight: bold;
                border-radius: 4px;
                min-width: 26px;
                min-height: 26px;
                max-width: 26px;
                max-height: 26px;
                color: #88888c;
                background-color: #0b0b0c;
                border: 1px solid #222225;
            }
            QPushButton#MuteButton:hover, QPushButton#SoloButton:hover, QPushButton#ArmButton:hover, QPushButton#FxButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
                border-color: #444448;
            }
            
            QPushButton#MuteButton:checked {
                background-color: #ffffff;
                color: #000000;
                border-color: #ffffff;
            }
            QPushButton#SoloButton:checked {
                background-color: #ffffff;
                color: #000000;
                border-color: #ffffff;
            }
            QPushButton#ArmButton:checked {
                background-color: #ff0033; /* Nothing brand red */
                color: #ffffff;
                border-color: #ff0033;
            }
            
            QPushButton#FxButton[fxState="active"] {
                background-color: #ffffff;
                border-color: #ffffff;
                color: #000000;
            }
            QPushButton#FxButton[fxState="inactive"] {
                background-color: #2a2a2d;
                border-color: #444448;
                color: #88888c;
            }
            QPushButton#FxButton[fxState="none"] {
                background-color: #0b0b0c;
                border-color: #222225;
                color: #88888c;
            }
            
            QComboBox#InputChannelCombo {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
                color: #88888c;
                padding: 4px 6px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QComboBox#InputChannelCombo:hover {
                border-color: #444448;
                background-color: #1a1a1c;
                color: #ffffff;
            }
            QComboBox#InputChannelCombo QAbstractItemView {
                background-color: #0b0b0c;
                color: #d4d4d4;
                border: 1px solid #222225;
                selection-background-color: #222225;
                selection-color: #ffffff;
            }
            
            QPushButton#DeleteTrackButton {
                background-color: transparent;
                border: none;
                color: #444448;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
                text-align: center;
            }
            QPushButton#DeleteTrackButton:hover {
                color: #ff0033;
                background-color: rgba(255, 0, 51, 0.1);
                border-radius: 9px;
            }
            
            QSlider#VolumeSlider::groove:vertical {
                background: #000000;
                width: 4px;
                border-radius: 2px;
            }
            QSlider#VolumeSlider::sub-page:vertical {
                background: #000000;
                width: 4px;
                border-radius: 2px;
            }
            QSlider#VolumeSlider::add-page:vertical {
                background: #ffffff;
                width: 4px;
                border-radius: 2px;
            }
            QSlider#VolumeSlider::handle:vertical {
                background: #ffffff;
                border: 1px solid #000000;
                height: 18px;
                width: 12px;
                margin-left: -4px;
                margin-right: -4px;
                border-radius: 2px;
            }
            QSlider#VolumeSlider::handle:vertical:hover {
                background: #ffffff;
                border-color: #ff0033;
            }
            
            QLabel#VolDbLabel {
                color: #555558;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 9px;
            }
        """)

    def populate_inputs(self):
        """Populates the input selector dropdown filtering by global device settings."""
        self.combo_input.clear()
        
        if self.audio_engine.enable_inputs:
            first_in = self.audio_engine.input_first_channel
            last_in = self.audio_engine.input_last_channel
            for i in range(first_in, last_in + 1):
                self.combo_input.addItem(f"Input Channel {i+1}", i)
                
        # Add Demo Loop option
        self.combo_input.addItem("Guitar Demo Loop", "loop")
        
        # Set current selection
        idx = self.combo_input.findData(self.track.input_channel)
        if idx >= 0:
            self.combo_input.setCurrentIndex(idx)
        else:
            self.combo_input.setCurrentIndex(self.combo_input.count() - 1)  # Default to loop if not found

    def update_levels(self):
        """Updates the LED VU level meter with the current peak dB."""
        self.level_meter.set_level(self.track.level_history)
        self.update_fx_status()

    def update_fx_status(self):
        """Updates the FX button color to show if effects are loaded and active."""
        has_active = any(wrap.is_active for wrap in self.track.effects)
        has_inactive = any(not wrap.is_active for wrap in self.track.effects)
        
        if has_active:
            self.btn_fx.setProperty("fxState", "active")
        elif has_inactive:
            self.btn_fx.setProperty("fxState", "inactive")
        else:
            self.btn_fx.setProperty("fxState", "none")
            
        self.btn_fx.style().unpolish(self.btn_fx)
        self.btn_fx.style().polish(self.btn_fx)

    def set_selected(self, selected):
        """Sets selected state and updates dynamic styles."""
        if self.is_selected == selected:
            return
        self.is_selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        if selected:
            self.trackSelected.emit(self.track)

    def update_selection_style(self):
        """Fallback for backwards compatibility, updates styles using selected property."""
        self.setProperty("selected", self.is_selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        """Select track when clicking anywhere on the card."""
        self.set_selected(True)
        super().mousePressEvent(event)
        
    def on_rename(self):
        new_name = self.name_edit.text().strip()
        if new_name:
            self.track.name = new_name
            self.update()
            
    def on_mute_clicked(self):
        self.track.mute = self.btn_mute.isChecked()
        
    def on_solo_clicked(self):
        self.track.solo = self.btn_solo.isChecked()
        
    def on_arm_clicked(self):
        self.track.armed = self.btn_arm.isChecked()
        
    def on_input_changed(self):
        ch_data = self.combo_input.currentData()
        if ch_data is not None:
            self.track.input_channel = ch_data
            
    def on_volume_changed(self):
        val_db = self.vol_slider.value() / 10.0
        self.track.volume = val_db
        self.update_volume_label(val_db)
        
    def update_volume_label(self, val_db):
        if val_db <= -60.0:
            self.vol_label.setText("-inf dB")
        else:
            self.vol_label.setText(f"{val_db:+.1f} dB")
            
    def on_pan_changed(self, value):
        self.track.pan = value
        
    def on_fx_clicked(self):
        self.set_selected(True)
        # We can handle custom actions/notifications for fx rack focus
        
    def on_delete_clicked(self):
        self.trackRemoved.emit(self.track)
