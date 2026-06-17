import numpy as np
import sounddevice as sd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFormLayout, QDialogButtonBox, QMessageBox,
    QGroupBox, QCheckBox, QLineEdit, QStackedWidget, QWidget, QSizePolicy,
    QListWidget, QFileDialog
)
from PySide6.QtCore import Qt

from theme_utils import FramelessWindowMixin

class AudioSettingsDialog(FramelessWindowMixin, QDialog):
    """Dialog for configuring advanced Reaper-style audio device settings."""
    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 500)  # Lower minimum height now that it scrolls
        self.setObjectName("AudioSettingsDialog")
        
        self.setup_ui()
        self.init_frameless(self.title_bar)
        self.load_settings()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Add Custom Title Bar
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from theme_utils import CustomTitleBar
        self.title_bar = CustomTitleBar(self, title_text="SETTINGS", can_minimize=False)
        main_layout.addWidget(self.title_bar)
        
        from PySide6.QtWidgets import QScrollArea, QFrame
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        content_widget = QWidget(self.scroll_area)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 15, 15, 15)
        content_layout.setSpacing(12)
        
        # --- AUDIO DEVICE SETTINGS GROUP BOX ---
        group_box = QGroupBox("Audio device settings")
        group_box.setObjectName("SettingsGroupBox")
        group_layout = QVBoxLayout(group_box)
        group_layout.setContentsMargins(15, 15, 15, 15)
        group_layout.setSpacing(10)
        
        # Audio System selector
        sys_layout = QHBoxLayout()
        sys_layout.addWidget(QLabel("Audio system:"))
        self.combo_system = QComboBox()
        self.combo_system.setObjectName("SystemCombo")
        self.combo_system.currentIndexChanged.connect(self.on_system_changed)
        sys_layout.addWidget(self.combo_system)
        sys_layout.addStretch()
        group_layout.addLayout(sys_layout)
        
        # Stacked Widget to switch layouts between ASIO and Non-ASIO (MME, WASAPI, etc.)
        self.stacked_devices = QStackedWidget()
        
        # PAGE 1: ASIO Layout Page
        self.page_asio = QWidget()
        asio_layout = QVBoxLayout(self.page_asio)
        asio_layout.setContentsMargins(0, 0, 0, 0)
        asio_layout.setSpacing(8)
        
        driver_layout = QHBoxLayout()
        driver_layout.addWidget(QLabel("ASIO Driver:"))
        self.combo_asio_driver = QComboBox()
        self.combo_asio_driver.setObjectName("AsioDriverCombo")
        self.combo_asio_driver.currentIndexChanged.connect(self.on_asio_driver_changed)
        driver_layout.addWidget(self.combo_asio_driver)
        driver_layout.addStretch()
        asio_layout.addLayout(driver_layout)
        
        # Checkbox: Enable Inputs (ASIO)
        self.chk_asio_inputs = QCheckBox("Enable inputs:")
        self.chk_asio_inputs.setChecked(True)
        self.chk_asio_inputs.stateChanged.connect(self.on_asio_inputs_toggled)
        asio_layout.addWidget(self.chk_asio_inputs)
        
        # Input channel ranges (ASIO)
        self.widget_asio_in_ranges = QWidget()
        asio_in_grid = QFormLayout(self.widget_asio_in_ranges)
        asio_in_grid.setContentsMargins(20, 0, 0, 0)
        asio_in_grid.setSpacing(6)
        
        self.combo_asio_in_first = QComboBox()
        self.combo_asio_in_last = QComboBox()
        asio_in_grid.addRow("first", self.combo_asio_in_first)
        asio_in_grid.addRow("last", self.combo_asio_in_last)
        asio_layout.addWidget(self.widget_asio_in_ranges)
        
        self.stacked_devices.addWidget(self.page_asio)
        
        # PAGE 2: Non-ASIO Layout Page (MME, WASAPI, DirectSound)
        self.page_standard = QWidget()
        std_layout = QVBoxLayout(self.page_standard)
        std_layout.setContentsMargins(0, 0, 0, 0)
        std_layout.setSpacing(8)
        
        # Input device dropdown
        indev_layout = QHBoxLayout()
        indev_layout.addWidget(QLabel("Input Device:"))
        self.combo_std_input = QComboBox()
        self.combo_std_input.setObjectName("InputDeviceCombo")
        self.combo_std_input.currentIndexChanged.connect(self.on_std_input_changed)
        indev_layout.addWidget(self.combo_std_input)
        indev_layout.addStretch()
        std_layout.addLayout(indev_layout)
        
        # Checkbox: Enable Inputs (Standard)
        self.chk_std_inputs = QCheckBox("Enable inputs:")
        self.chk_std_inputs.setChecked(True)
        self.chk_std_inputs.stateChanged.connect(self.on_std_inputs_toggled)
        std_layout.addWidget(self.chk_std_inputs)
        
        # Input channel ranges (Standard)
        self.widget_std_in_ranges = QWidget()
        std_in_grid = QFormLayout(self.widget_std_in_ranges)
        std_in_grid.setContentsMargins(20, 0, 0, 0)
        std_in_grid.setSpacing(6)
        
        self.combo_std_in_first = QComboBox()
        self.combo_std_in_last = QComboBox()
        std_in_grid.addRow("first", self.combo_std_in_first)
        std_in_grid.addRow("last", self.combo_std_in_last)
        std_layout.addWidget(self.widget_std_in_ranges)
        
        # Output device dropdown
        outdev_layout = QHBoxLayout()
        outdev_layout.addWidget(QLabel("Output Device:"))
        self.combo_std_output = QComboBox()
        self.combo_std_output.setObjectName("OutputDeviceCombo")
        self.combo_std_output.currentIndexChanged.connect(self.on_std_output_changed)
        outdev_layout.addWidget(self.combo_std_output)
        outdev_layout.addStretch()
        std_layout.addLayout(outdev_layout)
        
        self.stacked_devices.addWidget(self.page_standard)
        group_layout.addWidget(self.stacked_devices)
        
        # --- OUTPUT RANGE (SHARED) ---
        group_layout.addWidget(QLabel("Output range:"))
        self.widget_out_ranges = QWidget()
        out_grid = QFormLayout(self.widget_out_ranges)
        out_grid.setContentsMargins(20, 0, 0, 0)
        out_grid.setSpacing(6)
        
        self.combo_out_first = QComboBox()
        self.combo_out_last = QComboBox()
        out_grid.addRow("first", self.combo_out_first)
        out_grid.addRow("last", self.combo_out_last)
        group_layout.addWidget(self.widget_out_ranges)
        
        # --- SAMPLE RATE & BLOCK SIZE REQUESTS ---
        req_layout = QHBoxLayout()
        req_layout.setSpacing(10)
        
        self.chk_req_sr = QCheckBox("Request sample rate:")
        self.chk_req_sr.setChecked(True)
        self.chk_req_sr.stateChanged.connect(lambda state: self.edit_req_sr.setEnabled(state == 2))
        req_layout.addWidget(self.chk_req_sr)
        
        self.edit_req_sr = QComboBox()
        self.edit_req_sr.addItems(["22050", "44100", "48000", "88200", "96000"])
        self.edit_req_sr.setEditable(True)
        self.edit_req_sr.setObjectName("RequestInput")
        self.edit_req_sr.setFixedWidth(80)
        req_layout.addWidget(self.edit_req_sr)
        
        req_layout.addSpacing(10)
        
        self.chk_req_bs = QCheckBox("Request block size:")
        self.chk_req_bs.setChecked(True)
        self.chk_req_bs.stateChanged.connect(lambda state: self.edit_req_bs.setEnabled(state == 2))
        req_layout.addWidget(self.chk_req_bs)
        
        self.edit_req_bs = QComboBox()
        self.edit_req_bs.addItems(["64", "128", "256", "512", "1024", "2048"])
        self.edit_req_bs.setEditable(True)
        self.edit_req_bs.setObjectName("RequestInput")
        self.edit_req_bs.setFixedWidth(80)
        req_layout.addWidget(self.edit_req_bs)
        
        req_layout.addStretch()
        group_layout.addLayout(req_layout)
        
        # --- ASIO CONFIG BUTTON ---
        self.btn_asio_config = QPushButton("ASIO Configuration...")
        self.btn_asio_config.setObjectName("AsioConfigButton")
        self.btn_asio_config.clicked.connect(self.on_asio_config_clicked)
        group_layout.addWidget(self.btn_asio_config)
        
        # --- ADDITIONAL OPTIONS ---
        self.chk_pre_zero = QCheckBox("Pre-zero output buffers, useful on some hardware (higher CPU use)")
        self.chk_pre_zero.setChecked(True)
        group_layout.addWidget(self.chk_pre_zero)
        
        self.chk_ignore_reset = QCheckBox("Ignore ASIO reset messages (needed for some buggy drivers)")
        self.chk_ignore_reset.setChecked(True)
        group_layout.addWidget(self.chk_ignore_reset)
        
        content_layout.addWidget(group_box)
        
        # --- BOTTOM SETTINGS ---
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(QLabel("Audio thread priority:"))
        self.combo_priority = QComboBox()
        self.combo_priority.addItems([
            "ASIO Default / MMCSS Pro Audio / Time Critical",
            "Normal",
            "High Priority",
            "Realtime / Extreme"
        ])
        self.combo_priority.setObjectName("PriorityCombo")
        bottom_row.addWidget(self.combo_priority)
        bottom_row.addStretch()
        content_layout.addLayout(bottom_row)
        
        self.chk_override_sr = QCheckBox("Allow projects to override device sample rate")
        self.chk_override_sr.setChecked(True)
        content_layout.addWidget(self.chk_override_sr)
        
        # --- VST PLUGIN SEARCH PATHS GROUP BOX ---
        vst_group = QGroupBox("VST plug-in search paths")
        vst_group.setObjectName("VstGroupBox")
        vst_layout = QVBoxLayout(vst_group)
        vst_layout.setContentsMargins(15, 15, 15, 15)
        vst_layout.setSpacing(8)
        
        self.list_vst_paths = QListWidget()
        self.list_vst_paths.setObjectName("VstPathsList")
        vst_layout.addWidget(self.list_vst_paths)
        
        vst_btn_layout = QHBoxLayout()
        self.btn_add_path = QPushButton("Add Path...")
        self.btn_add_path.setObjectName("VstPathButton")
        self.btn_add_path.clicked.connect(self.on_add_vst_path)
        vst_btn_layout.addWidget(self.btn_add_path)
        
        self.btn_remove_path = QPushButton("Remove Path")
        self.btn_remove_path.setObjectName("VstPathButton")
        self.btn_remove_path.clicked.connect(self.on_remove_vst_path)
        vst_btn_layout.addWidget(self.btn_remove_path)
        vst_btn_layout.addStretch()
        
        vst_layout.addLayout(vst_btn_layout)
        content_layout.addWidget(vst_group)

        # --- STARTUP PROJECT GROUP BOX ---
        startup_group = QGroupBox("Startup project")
        startup_group.setObjectName("StartupGroupBox")
        startup_layout = QHBoxLayout(startup_group)
        startup_layout.setContentsMargins(15, 15, 15, 15)
        startup_layout.setSpacing(10)
        
        self.edit_startup_path = QLineEdit()
        self.edit_startup_path.setObjectName("StartupPathEdit")
        self.edit_startup_path.setReadOnly(True)
        self.edit_startup_path.setPlaceholderText("No startup project file set (will load default project)")
        self.edit_startup_path.setStyleSheet("""
            QLineEdit#StartupPathEdit {
                background-color: #000000;
                border: 1px solid #333333;
                color: #ffffff;
                padding: 4px 8px;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
        """)
        startup_layout.addWidget(self.edit_startup_path, 1)
        
        self.btn_browse_startup = QPushButton("Browse...")
        self.btn_browse_startup.setObjectName("VstPathButton")
        self.btn_browse_startup.clicked.connect(self.on_browse_startup_project)
        startup_layout.addWidget(self.btn_browse_startup)
        
        self.btn_clear_startup = QPushButton("Clear")
        self.btn_clear_startup.setObjectName("VstPathButton")
        self.btn_clear_startup.clicked.connect(self.on_clear_startup_project)
        startup_layout.addWidget(self.btn_clear_startup)
        
        content_layout.addWidget(startup_group)

        # OK / CANCEL BUTTONS (outside scroll area)
        buttons_widget = QWidget(self)
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(15, 5, 15, 15)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.on_accept)
        self.button_box.rejected.connect(self.reject)
        buttons_layout.addWidget(self.button_box)
        
        self.scroll_area.setWidget(content_widget)
        main_layout.addWidget(self.scroll_area)
        main_layout.addWidget(buttons_widget)
        
        # Stylesheet styling to match Nothing design aesthetic
        self.setStyleSheet("""
            QDialog#AudioSettingsDialog {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #222225;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: #000000;
                width: 8px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #222225;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #ff0033;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QGroupBox#SettingsGroupBox {
                border: 1px solid #333333;
                border-radius: 0px;
                margin-top: 10px;
                padding-top: 15px;
                color: #ffffff;
                font-family: "Consolas", monospace;
                font-weight: bold;
            }
            QGroupBox#VstGroupBox, QGroupBox#StartupGroupBox {
                border: 1px solid #333333;
                border-radius: 0px;
                margin-top: 10px;
                padding-top: 15px;
                color: #ffffff;
                font-family: "Consolas", monospace;
                font-weight: bold;
            }
            QLabel {
                color: #888888;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QComboBox {
                background-color: #000000;
                border: 1px solid #333333;
                border-radius: 0px;
                color: #ffffff;
                padding: 4px 8px;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QComboBox:focus {
                border-color: #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #000000;
                color: #ffffff;
                selection-background-color: #ffffff;
                selection-color: #000000;
                border: 1px solid #333333;
            }
            QCheckBox {
                color: #ffffff;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #333333;
                border-radius: 0px;
                background-color: #000000;
            }
            QCheckBox::indicator:checked {
                background-color: #ffffff;
                border-color: #ffffff;
            }
            QComboBox#RequestInput {
                background-color: #000000;
                border: 1px solid #333333;
                color: #ffffff;
                padding: 2px;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QComboBox#RequestInput:focus {
                border-color: #ffffff;
            }
            QPushButton#AsioConfigButton {
                background-color: #000000;
                border: 1px solid #333333;
                border-radius: 0px;
                color: #ffffff;
                font-family: "Consolas", monospace;
                font-weight: bold;
                padding: 6px 12px;
                font-size: 11px;
                margin-top: 5px;
            }
            QPushButton#AsioConfigButton:hover {
                border-color: #ffffff;
            }
            QDialogButtonBox QPushButton {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #333333;
                border-radius: 0px;
                padding: 5px 15px;
                min-width: 70px;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QDialogButtonBox QPushButton:hover {
                border-color: #ffffff;
            }
            QListWidget#VstPathsList {
                background-color: #000000;
                border: 1px solid #333333;
                border-radius: 0px;
                color: #ffffff;
                font-family: "Consolas", monospace;
                font-size: 11px;
                min-height: 80px;
            }
            QListWidget#VstPathsList::item:selected {
                background-color: #ffffff;
                color: #000000;
            }
            QPushButton#VstPathButton {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #333333;
                border-radius: 0px;
                padding: 5px 15px;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QPushButton#VstPathButton:hover {
                border-color: #ffffff;
            }
        """)

    def load_settings(self):
        """Loads available host APIs and initializes values."""
        apis = self.audio_engine.get_host_apis()
        self.combo_system.clear()
        for idx, name in apis:
            self.combo_system.addItem(name, idx)
            
        # Select current system index
        sys_idx = self.combo_system.findData(self.audio_engine.audio_system)
        if sys_idx >= 0:
            self.combo_system.setCurrentIndex(sys_idx)
        else:
            self.combo_system.setCurrentIndex(0)
            
        # Load sample rate & block size values
        self.chk_req_sr.setChecked(self.audio_engine.request_sample_rate)
        self.edit_req_sr.setCurrentText(str(self.audio_engine.sample_rate))
        self.edit_req_sr.setEnabled(self.audio_engine.request_sample_rate)
        
        self.chk_req_bs.setChecked(self.audio_engine.request_block_size)
        self.edit_req_bs.setCurrentText(str(self.audio_engine.block_size))
        self.edit_req_bs.setEnabled(self.audio_engine.request_block_size)
        
        # Load additional options
        self.chk_pre_zero.setChecked(self.audio_engine.pre_zero_buffers)
        self.chk_ignore_reset.setChecked(self.audio_engine.ignore_asio_reset)
        self.chk_override_sr.setChecked(self.audio_engine.allow_project_override_sr)
        
        pri_idx = self.combo_priority.findText(self.audio_engine.thread_priority)
        if pri_idx >= 0:
            self.combo_priority.setCurrentIndex(pri_idx)
            
        # Load VST paths
        self.list_vst_paths.clear()
        for p in self.audio_engine.vst_search_paths:
            self.list_vst_paths.addItem(p)
            
        # Load startup project path
        self.edit_startup_path.setText(getattr(self.audio_engine, "startup_project_path", ""))
            
    def on_system_changed(self):
        """Switches visual layout based on host API (ASIO vs. standard)."""
        sys_name = self.combo_system.currentText()
        api_idx = self.combo_system.currentData()
        
        if api_idx is None:
            return
            
        # Group by ASIO or other
        is_asio = "asio" in sys_name.lower()
        if is_asio:
            self.stacked_devices.setCurrentWidget(self.page_asio)
            self.btn_asio_config.setVisible(True)
            self.chk_ignore_reset.setVisible(True)
            self.populate_asio_drivers(api_idx)
        else:
            self.stacked_devices.setCurrentWidget(self.page_standard)
            self.btn_asio_config.setVisible(False)
            self.chk_ignore_reset.setVisible(False)
            self.populate_std_devices(api_idx)
            
    def populate_asio_drivers(self, api_idx):
        """Loads ASIO drivers into the dropdown."""
        self.combo_asio_driver.clear()
        inputs, outputs = self.audio_engine.get_devices_for_api(api_idx)
        
        # ASIO is unified, inputs and outputs show same device drivers
        # Combine unique device names/indexes
        drivers = {}
        for idx, name in inputs:
            drivers[name] = idx
        for idx, name in outputs:
            drivers[name] = idx
            
        for name, idx in drivers.items():
            self.combo_asio_driver.addItem(name, idx)
            
        # Select current driver
        drv_idx = self.combo_asio_driver.findData(self.audio_engine.output_device_index)
        if drv_idx >= 0:
            self.combo_asio_driver.setCurrentIndex(drv_idx)
        elif self.combo_asio_driver.count() > 0:
            self.combo_asio_driver.setCurrentIndex(0)
            
        self.on_asio_driver_changed()
        
    def populate_std_devices(self, api_idx):
        """Loads standard sound cards into input/output dropdowns."""
        self.combo_std_input.clear()
        self.combo_std_output.clear()
        
        inputs, outputs = self.audio_engine.get_devices_for_api(api_idx)
        
        for idx, name in inputs:
            self.combo_std_input.addItem(name, idx)
        for idx, name in outputs:
            self.combo_std_output.addItem(name, idx)
            
        # Select current devices
        in_idx = self.combo_std_input.findData(self.audio_engine.input_device_index)
        if in_idx >= 0:
            self.combo_std_input.setCurrentIndex(in_idx)
        elif self.combo_std_input.count() > 0:
            self.combo_std_input.setCurrentIndex(0)
            
        out_idx = self.combo_std_output.findData(self.audio_engine.output_device_index)
        if out_idx >= 0:
            self.combo_std_output.setCurrentIndex(out_idx)
        elif self.combo_std_output.count() > 0:
            self.combo_std_output.setCurrentIndex(0)
            
        self.chk_std_inputs.setChecked(self.audio_engine.enable_inputs)
        self.on_std_inputs_toggled()
        self.on_std_output_changed()

    def on_asio_driver_changed(self):
        """Updates channel range selectors for the active ASIO driver."""
        dev_idx = self.combo_asio_driver.currentData()
        if dev_idx is None:
            return
            
        devices = sd.query_devices()
        dev_info = devices[dev_idx]
        
        # Enable inputs state
        self.chk_asio_inputs.setChecked(self.audio_engine.enable_inputs)
        self.on_asio_inputs_toggled()
        
        # Populate input channels
        max_in = dev_info['max_input_channels']
        self.combo_asio_in_first.clear()
        self.combo_asio_in_last.clear()
        for i in range(max_in):
            label = f"{i+1}: In {i+1}"
            self.combo_asio_in_first.addItem(label, i)
            self.combo_asio_in_last.addItem(label, i)
            
        # Populate output channels
        max_out = dev_info['max_output_channels']
        self.combo_out_first.clear()
        self.combo_out_last.clear()
        for i in range(max_out):
            label = f"{i+1}: Out {i+1}"
            self.combo_out_first.addItem(label, i)
            self.combo_out_last.addItem(label, i)
            
        # Set selections
        self.set_channel_combo_selections(
            self.combo_asio_in_first, self.combo_asio_in_last,
            self.audio_engine.input_first_channel, self.audio_engine.input_last_channel, max_in
        )
        self.set_channel_combo_selections(
            self.combo_out_first, self.combo_out_last,
            self.audio_engine.output_first_channel, self.audio_engine.output_last_channel, max_out
        )

    def on_std_input_changed(self):
        """Updates channel range selectors when standard input device changes."""
        dev_idx = self.combo_std_input.currentData()
        if dev_idx is None:
            return
            
        devices = sd.query_devices()
        max_in = devices[dev_idx]['max_input_channels']
        
        self.combo_std_in_first.clear()
        self.combo_std_in_last.clear()
        for i in range(max_in):
            label = f"{i+1}: In {i+1}"
            self.combo_std_in_first.addItem(label, i)
            self.combo_std_in_last.addItem(label, i)
            
        self.set_channel_combo_selections(
            self.combo_std_in_first, self.combo_std_in_last,
            self.audio_engine.input_first_channel, self.audio_engine.input_last_channel, max_in
        )

    def on_std_output_changed(self):
        """Updates channel range selectors when standard output device changes."""
        dev_idx = self.combo_std_output.currentData()
        if dev_idx is None:
            return
            
        devices = sd.query_devices()
        max_out = devices[dev_idx]['max_output_channels']
        
        self.combo_out_first.clear()
        self.combo_out_last.clear()
        for i in range(max_out):
            label = f"{i+1}: Out {i+1}"
            self.combo_out_first.addItem(label, i)
            self.combo_out_last.addItem(label, i)
            
        self.set_channel_combo_selections(
            self.combo_out_first, self.combo_out_last,
            self.audio_engine.output_first_channel, self.audio_engine.output_last_channel, max_out
        )

    def set_channel_combo_selections(self, first_combo, last_combo, saved_first, saved_last, max_chans):
        """Helper to safely set channel indexes."""
        if max_chans <= 0:
            return
            
        # Clean defaults
        first_idx = min(saved_first, max_chans - 1)
        last_idx = min(saved_last, max_chans - 1)
        if first_idx > last_idx:
            first_idx, last_idx = last_idx, first_idx
            
        idx_f = first_combo.findData(first_idx)
        if idx_f >= 0:
            first_combo.setCurrentIndex(idx_f)
            
        idx_l = last_combo.findData(last_idx)
        if idx_l >= 0:
            last_combo.setCurrentIndex(idx_l)
        elif last_combo.count() > 0:
            # default to last available
            last_combo.setCurrentIndex(last_combo.count() - 1)

    def on_asio_inputs_toggled(self):
        """Enables/disables input selectors for ASIO mode."""
        active = self.chk_asio_inputs.isChecked()
        self.widget_asio_in_ranges.setEnabled(active)
        
    def on_std_inputs_toggled(self):
        """Enables/disables input selectors for standard mode."""
        active = self.chk_std_inputs.isChecked()
        self.combo_std_input.setEnabled(active)
        self.widget_std_in_ranges.setEnabled(active)
        
    def on_asio_config_clicked(self):
        """ASIO configuration dialog message."""
        QMessageBox.information(
            self,
            "ASIO Configuration",
            "The ASIO driver configuration utility (buffer sizes, clock source) is managed "
            "directly by your audio interface's hardware software.\n\n"
            "Please open your interface's control software from the Windows Start menu or the system tray "
            "to adjust hardware ASIO settings."
        )

    def on_accept(self):
        """Saves values to engine and restarts the stream."""
        api_idx = self.combo_system.currentData()
        sys_name = self.combo_system.currentText()
        is_asio = "asio" in sys_name.lower()
        
        self.audio_engine.audio_system = api_idx
        
        if is_asio:
            # ASIO Mode
            drv_idx = self.combo_asio_driver.currentData()
            self.audio_engine.input_device_index = drv_idx
            self.audio_engine.output_device_index = drv_idx
            self.audio_engine.enable_inputs = self.chk_asio_inputs.isChecked()
            
            if self.audio_engine.enable_inputs:
                self.audio_engine.input_first_channel = self.combo_asio_in_first.currentData()
                self.audio_engine.input_last_channel = self.combo_asio_in_last.currentData()
            
            self.audio_engine.output_first_channel = self.combo_out_first.currentData()
            self.audio_engine.output_last_channel = self.combo_out_last.currentData()
        else:
            # Standard Mode (WASAPI, MME, DirectSound)
            self.audio_engine.enable_inputs = self.chk_std_inputs.isChecked()
            if self.audio_engine.enable_inputs:
                self.audio_engine.input_device_index = self.combo_std_input.currentData()
                self.audio_engine.input_first_channel = self.combo_std_in_first.currentData()
                self.audio_engine.input_last_channel = self.combo_std_in_last.currentData()
            else:
                self.audio_engine.input_device_index = None
                
            self.audio_engine.output_device_index = self.combo_std_output.currentData()
            self.audio_engine.output_first_channel = self.combo_out_first.currentData()
            self.audio_engine.output_last_channel = self.combo_out_last.currentData()
            
        # Save request options
        self.audio_engine.request_sample_rate = self.chk_req_sr.isChecked()
        try:
            self.audio_engine.sample_rate = int(self.edit_req_sr.currentText())
        except ValueError:
            pass
            
        self.audio_engine.request_block_size = self.chk_req_bs.isChecked()
        try:
            self.audio_engine.block_size = int(self.edit_req_bs.currentText())
        except ValueError:
            pass
            
        # Mock settings
        self.audio_engine.pre_zero_buffers = self.chk_pre_zero.isChecked()
        self.audio_engine.ignore_asio_reset = self.chk_ignore_reset.isChecked()
        self.audio_engine.allow_project_override_sr = self.chk_override_sr.isChecked()
        self.audio_engine.thread_priority = self.combo_priority.currentText()
        
        # Save VST paths
        vst_paths = []
        for i in range(self.list_vst_paths.count()):
            vst_paths.append(self.list_vst_paths.item(i).text())
        self.audio_engine.vst_search_paths = vst_paths
        
        # Save startup project path
        self.audio_engine.startup_project_path = self.edit_startup_path.text()
        
        # Apply changes and restart stream
        was_running = self.audio_engine.is_running
        success = self.audio_engine.start_stream()
        
        if success:
            self.audio_engine.save_settings()
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "Audio Setup Failed",
                "Failed to initialize the stream with selected parameters.\n\n"
                "Please select different devices or buffer configurations."
            )

    def on_add_vst_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select VST3 Search Folder")
        if folder:
            items = [self.list_vst_paths.item(i).text() for i in range(self.list_vst_paths.count())]
            if folder not in items:
                self.list_vst_paths.addItem(folder)
                
    def on_remove_vst_path(self):
        curr_row = self.list_vst_paths.currentRow()
        if curr_row >= 0:
            self.list_vst_paths.takeItem(curr_row)

    def on_browse_startup_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Startup Project File", "", "Graphite Project Files (*.graphite *.gtrp);;Graphite Project (*.graphite);;All Files (*)"
        )
        if file_path:
            self.edit_startup_path.setText(file_path)

    def on_clear_startup_project(self):
        self.edit_startup_path.clear()
