from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QComboBox, QPushButton, QLineEdit, QSizePolicy, QWidget
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from widgets.level_meter import LevelMeter

class WheelIgnoredComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class DoubleClickLineEdit(QLineEdit):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
    def mouseDoubleClickEvent(self, event):
        self.setReadOnly(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
        self.selectAll()
        super().mouseDoubleClickEvent(event)
        
    def focusOutEvent(self, event):
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.deselect()
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        if self.isReadOnly():
            event.ignore()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self.clearFocus()
        else:
            super().keyPressEvent(event)

class TrackCard(QFrame):
    """Card-style Track widget displaying track settings and VU meter."""
    trackSelected = Signal(object)  # Emitted when the card is clicked/selected
    trackRemoved = Signal(object)   # Emitted when delete button is pressed
    trackDuplicated = Signal(object) # Emitted when duplicate action is triggered
    
    def __init__(self, track, audio_engine, parent=None):
        super().__init__(parent)
        self.track = track
        self.audio_engine = audio_engine
        self.is_selected = False
        self._small_layout_active = False
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(60)
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
        self.header_layout = QHBoxLayout()
        self.header_layout.setSpacing(6)
        
        # Track Number Badge
        self.lbl_num = QLabel(f"{self.track.track_id:02d}")
        self.lbl_num.setObjectName("TrackNumberLabel")
        self.header_layout.addWidget(self.lbl_num)
        
        # Editable Track Name
        self.name_edit = DoubleClickLineEdit(self.track.name)
        self.name_edit.setObjectName("TrackNameEdit")
        self.name_edit.setToolTip("Double-click to rename track")
        self.name_edit.editingFinished.connect(self.on_rename)
        self.header_layout.addWidget(self.name_edit)
        
        # Sleek small Delete Button
        self.btn_delete = QPushButton("×")
        self.btn_delete.setObjectName("DeleteTrackButton")
        self.btn_delete.setToolTip("Delete Track")
        self.btn_delete.clicked.connect(self.on_delete_clicked)
        self.btn_delete.setFixedSize(18, 18)
        self.header_layout.addWidget(self.btn_delete)
        
        details_layout.addLayout(self.header_layout)
        
        # Row 2: Controls Row (M, S, R, FX)
        self.controls_widget = QWidget()
        self.controls_widget.setObjectName("TrackControlsWidget")
        self.controls_layout = QHBoxLayout(self.controls_widget)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(4)
        
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
        
        self.controls_layout.addWidget(self.btn_mute)
        self.controls_layout.addWidget(self.btn_solo)
        self.controls_layout.addWidget(self.btn_arm)
        self.controls_layout.addStretch()
        
        details_layout.addWidget(self.controls_widget)
        
        # Row 3: Input Channel Selector
        self.combo_input = WheelIgnoredComboBox()
        self.combo_input.setObjectName("InputChannelCombo")
        self.combo_input.setToolTip("Select Track Input Channel")
        self.populate_inputs()
        self.combo_input.currentIndexChanged.connect(self.on_input_changed)
        details_layout.addWidget(self.combo_input)
        
        main_layout.addLayout(details_layout)
        
        # --- PANEL 2: Custom vertical LED VU Meter ---
        self.level_meter = LevelMeter()
        main_layout.addWidget(self.level_meter)
        
        self.setStyleSheet("""
            TrackCard {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
            }
            TrackCard:hover {
                background-color: #151518;
                border-color: #88888c;
            }
            TrackCard[selected="true"] {
                background-color: #000000;
                border: 1px solid #ffffff;
            }
            TrackCard[selected="true"]:hover {
                background-color: #121214;
                border-color: #ffffff;
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
            if self.combo_input.count() > 0:
                # Default to first active input channel or loop, and update track state
                default_idx = 0
                self.combo_input.setCurrentIndex(default_idx)
                self.track.input_channel = self.combo_input.itemData(default_idx)
            else:
                self.combo_input.setCurrentIndex(self.combo_input.count() - 1)  # Default to loop if not found
                self.track.input_channel = "loop"

    def update_levels(self):
        """Updates the LED VU level meter with the current peak dB."""
        self.level_meter.set_level(self.track.level_history)



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
        was_selected = self.is_selected
        self.set_selected(True)
        if was_selected:
            main_win = self.window()
            if main_win and hasattr(main_win, 'on_track_selected'):
                main_win.on_track_selected(self.track)
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
        
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
        mime_data.setText(str(self.track.track_id))
        drag.setMimeData(mime_data)
        
        # Grab a scaled-down screenshot of the card for the drag preview
        pixmap = self.grab()
        scaled_pixmap = pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation)
        drag.setPixmap(scaled_pixmap)
        drag.setHotSpot(event.pos() * (200 / pixmap.width()))
        
        drag.exec(Qt.DropAction.MoveAction)
        self.drag_start_position = None
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        show_combo = (h >= 115)
        self.combo_input.setVisible(show_combo)
        
        # Adjust layout margins and spacing dynamically to fit small sizes
        if h < 85:
            self.layout().setContentsMargins(8, 4, 8, 4)
            self.layout().setSpacing(6)
        else:
            self.layout().setContentsMargins(12, 10, 10, 10)
            self.layout().setSpacing(12)
        
        is_small = (h < 85)
        if is_small != self._small_layout_active:
            self._small_layout_active = is_small
            if is_small:
                # Hide controls widget container
                self.controls_widget.setVisible(False)
                # Move buttons into the header layout (before the delete button)
                self.header_layout.insertWidget(2, self.btn_mute)
                self.header_layout.insertWidget(3, self.btn_solo)
                self.header_layout.insertWidget(4, self.btn_arm)
            else:
                # Move buttons back to controls_layout
                self.controls_layout.insertWidget(0, self.btn_mute)
                self.controls_layout.insertWidget(1, self.btn_solo)
                self.controls_layout.insertWidget(2, self.btn_arm)
                # Show controls widget container
                self.controls_widget.setVisible(True)
                
        # Ensure buttons remain visible at all times
        self.btn_mute.setVisible(True)
        self.btn_solo.setVisible(True)
        self.btn_arm.setVisible(True)
        
    def mark_dirty(self):
        main_win = self.window()
        if main_win and hasattr(main_win, 'mark_project_dirty'):
            main_win.mark_project_dirty()

    def on_rename(self):
        new_name = self.name_edit.text().strip()
        if new_name:
            self.track.name = new_name
            self.update()
            self.mark_dirty()
            
    def on_mute_clicked(self):
        self.track.mute = self.btn_mute.isChecked()
        self.mark_dirty()
        
    def on_solo_clicked(self):
        self.track.solo = self.btn_solo.isChecked()
        self.mark_dirty()
        
    def on_arm_clicked(self):
        self.track.armed = self.btn_arm.isChecked()
        self.mark_dirty()
        
        main_win = self.window()
        if main_win and hasattr(main_win, 'btn_arm_exclusive') and main_win.btn_arm_exclusive.isChecked():
            if self.track.armed:
                for card in main_win.track_cards:
                    if card != self:
                        card.track.armed = False
                        if hasattr(card, 'btn_arm'):
                            card.btn_arm.setChecked(False)
        
    def on_input_changed(self):
        ch_data = self.combo_input.currentData()
        if ch_data is not None:
            self.track.input_channel = ch_data
            self.mark_dirty()
            
    def on_volume_changed(self):
        val_db = self.vol_slider.value() / 10.0
        self.track.volume = val_db
        self.update_volume_label(val_db)
        self.mark_dirty()
        
    def update_volume_label(self, val_db):
        if val_db <= -60.0:
            self.vol_label.setText("-inf dB")
        else:
            self.vol_label.setText(f"{val_db:+.1f} dB")
            
    def on_pan_changed(self, value):
        self.track.pan = value
        self.mark_dirty()
        

        
    def on_delete_clicked(self):
        self.trackRemoved.emit(self.track)
        
    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        self.set_selected(True)
        
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
        
        action_rename = QAction("Rename Track", self)
        action_rename.triggered.connect(self.trigger_rename)
        menu.addAction(action_rename)
        
        action_duplicate = QAction("Duplicate Track", self)
        action_duplicate.triggered.connect(self.trigger_duplicate)
        menu.addAction(action_duplicate)
        
        menu.addSeparator()
        
        action_delete = QAction("Delete Track", self)
        action_delete.triggered.connect(self.on_delete_clicked)
        menu.addAction(action_delete)
        
        menu.exec(event.globalPos())

    def trigger_rename(self):
        self.name_edit.setReadOnly(False)
        self.name_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def trigger_duplicate(self):
        self.trackDuplicated.emit(self.track)
