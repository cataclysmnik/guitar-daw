import os
import numpy as np
import platform
import subprocess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFormLayout, QDialogButtonBox, QMessageBox,
    QGroupBox, QRadioButton, QDoubleSpinBox, QLineEdit, QFileDialog, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

class ExportWorker(QThread):
    """Worker thread that executes the offline project mixdown render."""
    progress = Signal(int)
    finished = Signal(bool, str)
    
    def __init__(self, audio_engine, file_path, start_time, end_time, sample_rate, bit_depth, channels, format_type):
        super().__init__()
        self.audio_engine = audio_engine
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        self.channels = channels
        self.format_type = format_type
        
    def run(self):
        success, message = self.audio_engine.render_project_offline(
            file_path=self.file_path,
            start_time_sec=self.start_time,
            end_time_sec=self.end_time,
            sample_rate=self.sample_rate,
            bit_depth=self.bit_depth,
            channels=self.channels,
            format_type=self.format_type,
            progress_callback=self.progress.emit
        )
        self.finished.emit(success, message)


class ExportDialog(QDialog):
    """Settings dialog for configuring and executing timeline audio exports."""
    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        self.worker = None
        
        self.setWindowTitle("Export Audio (Render)")
        self.setMinimumSize(480, 440)
        self.setObjectName("ExportDialog")
        
        self.setup_ui()
        self.calculate_project_length()
        self.load_export_settings()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)
        
        # --- Group 1: Output File path ---
        path_group = QGroupBox("Output File")
        path_layout = QHBoxLayout(path_group)
        path_layout.setSpacing(8)
        
        self.txt_path = QLineEdit()
        self.txt_path.setObjectName("PathLineEdit")
        # Default filename in user's working dir
        self.txt_path.setText(os.path.join(os.getcwd(), "project_export.wav"))
        path_layout.addWidget(self.txt_path)
        
        btn_browse = QPushButton("Browse...")
        btn_browse.setObjectName("BrowseButton")
        btn_browse.clicked.connect(self.on_browse)
        path_layout.addWidget(btn_browse)
        main_layout.addWidget(path_group)
        
        # --- Group 2: Render Settings ---
        settings_group = QGroupBox("Format Settings")
        settings_layout = QFormLayout(settings_group)
        settings_layout.setSpacing(10)
        
        # File Format Selection
        self.combo_format = QComboBox()
        self.combo_format.addItems(["WAV Audio File (.wav)", "MP3 Audio File (.mp3)"])
        self.combo_format.currentIndexChanged.connect(self.on_format_changed)
        settings_layout.addRow(QLabel("File format:"), self.combo_format)
        
        # Sample Rate
        self.combo_sr = QComboBox()
        self.combo_sr.addItems(["44100 Hz", "48000 Hz", "88200 Hz", "96000 Hz"])
        # Select engine sample rate by default
        current_engine_sr = str(self.audio_engine.sample_rate)
        idx = self.combo_sr.findText(current_engine_sr, Qt.MatchFlag.MatchContains)
        if idx >= 0:
            self.combo_sr.setCurrentIndex(idx)
        settings_layout.addRow(QLabel("Sample rate:"), self.combo_sr)
        
        # Bit Depth
        self.combo_depth = QComboBox()
        self.combo_depth.addItem("16-bit PCM WAV (CD Quality)", 16)
        self.combo_depth.addItem("24-bit PCM WAV (Studio Quality)", 24)
        settings_layout.addRow(QLabel("Bit depth:"), self.combo_depth)
        
        # Channels
        self.combo_channels = QComboBox()
        self.combo_channels.addItem("Stereo", "stereo")
        self.combo_channels.addItem("Mono", "mono")
        settings_layout.addRow(QLabel("Channels:"), self.combo_channels)
        
        main_layout.addWidget(settings_group)
        
        # --- Group 3: Export Range ---
        range_group = QGroupBox("Render Bounds")
        range_layout = QVBoxLayout(range_group)
        range_layout.setSpacing(8)
        
        self.radio_entire = QRadioButton("Entire Project length")
        self.radio_entire.setChecked(True)
        self.radio_entire.toggled.connect(self.toggle_range_inputs)
        range_layout.addWidget(self.radio_entire)
        
        self.radio_custom = QRadioButton("Custom Time Range (Seconds)")
        self.radio_custom.toggled.connect(self.toggle_range_inputs)
        range_layout.addWidget(self.radio_custom)
        
        # Custom time bounds sub-row
        self.bounds_widget = QGroupBox()
        self.bounds_widget.setFlat(True)
        self.bounds_widget.setStyleSheet("QGroupBox { border: none; margin: 0px; padding: 0px; }")
        bounds_layout = QHBoxLayout(self.bounds_widget)
        bounds_layout.setContentsMargins(20, 0, 0, 0)
        bounds_layout.setSpacing(10)
        
        bounds_layout.addWidget(QLabel("Start:"))
        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(0.0, 3600.0)
        self.spin_start.setSuffix("s")
        self.spin_start.setDecimals(2)
        bounds_layout.addWidget(self.spin_start)
        
        bounds_layout.addWidget(QLabel("End:"))
        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(0.1, 3600.0)
        self.spin_end.setValue(30.0)
        self.spin_end.setSuffix("s")
        self.spin_end.setDecimals(2)
        bounds_layout.addWidget(self.spin_end)
        
        range_layout.addWidget(self.bounds_widget)
        main_layout.addWidget(range_group)
        
        # --- Progress Bar (Hidden by default) ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setObjectName("ExportProgress")
        main_layout.addWidget(self.progress_bar)
        
        # --- Dialog Action Buttons ---
        self.button_box = QDialogButtonBox()
        
        self.btn_render = self.button_box.addButton("Render Offline", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_render.setObjectName("RenderButton")
        
        self.btn_open_folder = self.button_box.addButton("Open Folder", QDialogButtonBox.ButtonRole.ActionRole)
        self.btn_open_folder.setObjectName("OpenFolderButton")
        self.btn_open_folder.setEnabled(False)
        
        self.btn_close = self.button_box.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        
        self.btn_render.clicked.connect(self.start_render)
        self.btn_open_folder.clicked.connect(self.open_export_folder)
        self.btn_close.clicked.connect(self.reject)
        main_layout.addWidget(self.button_box)
        
        self.toggle_range_inputs()
        
        # Graphite QSS Styles
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QGroupBox {
                border: 1px solid #333333;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
                color: #e0e0e0;
                font-weight: bold;
                font-family: "Segoe UI", sans-serif;
            }
            QLabel {
                color: #cccccc;
                font-family: "Segoe UI", sans-serif;
                font-size: 11px;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 4px;
                font-size: 11px;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
                border-color: #666666;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                color: #e0e0e0;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3e3e32;
                color: #ffffff;
            }
            QPushButton#RenderButton {
                background-color: #2b5a30;
                border-color: #2b5a30;
                font-weight: bold;
                color: white;
            }
            QPushButton#RenderButton:hover {
                background-color: #35703c;
            }
            QPushButton#OpenFolderButton {
                background-color: #2a2d32;
                border-color: #3e4249;
                color: #e0e0e0;
            }
            QPushButton#OpenFolderButton:hover {
                background-color: #3e4249;
                color: #ffffff;
            }
            QPushButton#OpenFolderButton:disabled {
                background-color: #1e1e1e;
                border-color: #2d2d2d;
                color: #555555;
            }
            QRadioButton {
                color: #cccccc;
                font-size: 11px;
            }
            QProgressBar {
                background-color: #252526;
                border: 1px solid #333333;
                border-radius: 3px;
                text-align: center;
                color: #ffffff;
                font-size: 10px;
                height: 16px;
            }
            QProgressBar::chunk {
                background-color: #2b5a30;
            }
        """)
        
    def calculate_project_length(self):
        """Finds length of the longest track item on the timeline to set default render bounds."""
        max_sec = 0.0
        for track in self.audio_engine.tracks:
            for item in track.items:
                if item.audio_data is not None:
                    end_sec = (item.start_sample + item.audio_data.shape[1]) / item.sample_rate
                    max_sec = max(max_sec, end_sec)
                    
        # Fallback to 10s if timeline is empty
        if max_sec <= 0.0:
            max_sec = 10.0
            
        self.spin_end.setValue(max_sec)
        
    def toggle_range_inputs(self):
        self.bounds_widget.setEnabled(self.radio_custom.isChecked())
        
    def on_format_changed(self):
        is_wav = (self.combo_format.currentIndex() == 0)
        self.combo_depth.setEnabled(is_wav)
        file_path = self.txt_path.text().strip()
        if file_path:
            base, _ = os.path.splitext(file_path)
            ext = ".wav" if is_wav else ".mp3"
            self.txt_path.setText(base + ext)
            
    def on_browse(self):
        is_wav = (self.combo_format.currentIndex() == 0)
        filter_str = "WAV Audio Files (*.wav)" if is_wav else "MP3 Audio Files (*.mp3)"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Rendered Mixdown",
            self.txt_path.text(),
            filter_str
        )
        if file_path:
            ext = ".wav" if is_wav else ".mp3"
            if not file_path.lower().endswith(ext):
                file_path += ext
            self.txt_path.setText(file_path)
            
    def open_export_folder(self):
        file_path = self.txt_path.text().strip()
        folder_path = os.path.dirname(os.path.abspath(file_path))
        if os.path.exists(folder_path):
            try:
                if platform.system() == "Windows":
                    os.startfile(folder_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", folder_path])
                else:
                    subprocess.run(["xdg-open", folder_path])
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open folder: {e}")
                
    def start_render(self):
        file_path = self.txt_path.text().strip()
        if not file_path:
            QMessageBox.warning(self, "Invalid File", "Please select a valid output path.")
            return
            
        # Parse params
        sr_text = self.combo_sr.currentText()
        sample_rate = int(sr_text.replace(" Hz", ""))
        bit_depth = self.combo_depth.currentData()
        channels = self.combo_channels.currentData()
        
        format_idx = self.combo_format.currentIndex()
        format_type = "wav" if format_idx == 0 else "mp3"
        
        # Auto-append correct extension if not present
        ext = ".wav" if format_type == "wav" else ".mp3"
        if not file_path.lower().endswith(ext):
            file_path += ext
            self.txt_path.setText(file_path)
            
        # Save export settings to QSettings
        from PySide6.QtCore import QSettings
        settings = QSettings("GraphiteStudio", "GraphiteDAW")
        settings.setValue("export/format", format_idx)
        settings.setValue("export/sample_rate", sample_rate)
        settings.setValue("export/bit_depth", bit_depth)
        settings.setValue("export/channels", channels)
        settings.setValue("export/range", 0 if self.radio_entire.isChecked() else 1)
        settings.setValue("export/custom_start", self.spin_start.value())
        settings.setValue("export/custom_end", self.spin_end.value())
        settings.setValue("export/path", file_path)
        
        if self.radio_entire.isChecked():
            start_time = 0.0
            # Calculate live project end
            max_sec = 0.0
            for track in self.audio_engine.tracks:
                for item in track.items:
                    if item.audio_data is not None:
                        end_sec = (item.start_sample + item.audio_data.shape[1]) / item.sample_rate
                        max_sec = max(max_sec, end_sec)
            end_time = max_sec if max_sec > 0 else 10.0
        else:
            start_time = self.spin_start.value()
            end_time = self.spin_end.value()
            if start_time >= end_time:
                QMessageBox.warning(self, "Invalid Bounds", "Start time must be less than end time.")
                return
                
        # Disable controls during render
        self.btn_render.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.btn_open_folder.setEnabled(False)
        self.txt_path.setEnabled(False)
        self.combo_format.setEnabled(False)
        self.combo_sr.setEnabled(False)
        self.combo_depth.setEnabled(False)
        self.combo_channels.setEnabled(False)
        self.radio_entire.setEnabled(False)
        self.radio_custom.setEnabled(False)
        self.bounds_widget.setEnabled(False)
        
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        # Stop real-time engine stream while rendering to avoid hardware resource conflicts
        self.was_stream_running = self.audio_engine.is_running
        self.audio_engine.stop_stream()
        
        # Launch QThread background worker
        self.worker = ExportWorker(
            self.audio_engine, file_path, start_time, end_time,
            sample_rate, bit_depth, channels, format_type
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_render_finished)
        self.worker.start()
        
    def on_render_finished(self, success, message):
        # Re-enable inputs
        self.btn_render.setEnabled(True)
        self.btn_close.setEnabled(True)
        self.txt_path.setEnabled(True)
        self.combo_format.setEnabled(True)
        self.combo_sr.setEnabled(True)
        self.combo_depth.setEnabled(self.combo_format.currentIndex() == 0)
        self.combo_channels.setEnabled(True)
        self.radio_entire.setEnabled(True)
        self.radio_custom.setEnabled(True)
        self.toggle_range_inputs()
        self.progress_bar.setVisible(False)
        
        # Restart main engine stream if it was running before
        if self.was_stream_running:
            self.audio_engine.start_stream()
            
        if success:
            self.btn_open_folder.setEnabled(True)
            QMessageBox.information(self, "Export Complete", "Audio rendered and exported successfully!")
        else:
            self.btn_open_folder.setEnabled(False)
            QMessageBox.critical(self, "Export Error", f"Failed to export project:\n{message}")
            
    def load_export_settings(self):
        from PySide6.QtCore import QSettings
        settings = QSettings("GraphiteStudio", "GraphiteDAW")
        
        # Load format
        format_idx = settings.value("export/format", 0, type=int)
        if 0 <= format_idx < self.combo_format.count():
            self.combo_format.setCurrentIndex(format_idx)
            
        # Load sample rate
        sr_val = settings.value("export/sample_rate", 0, type=int)
        if sr_val > 0:
            idx = self.combo_sr.findText(str(sr_val), Qt.MatchFlag.MatchContains)
            if idx >= 0:
                self.combo_sr.setCurrentIndex(idx)
                
        # Load bit depth
        depth_val = settings.value("export/bit_depth", 16, type=int)
        idx = self.combo_depth.findData(depth_val)
        if idx >= 0:
            self.combo_depth.setCurrentIndex(idx)
            
        # Load channels
        chan_val = settings.value("export/channels", "stereo", type=str)
        idx = self.combo_channels.findData(chan_val)
        if idx >= 0:
            self.combo_channels.setCurrentIndex(idx)
            
        # Load range bounds
        range_mode = settings.value("export/range", 0, type=int)
        if range_mode == 1:
            self.radio_custom.setChecked(True)
            self.spin_start.setValue(settings.value("export/custom_start", 0.0, type=float))
            self.spin_end.setValue(settings.value("export/custom_end", 10.0, type=float))
        else:
            self.radio_entire.setChecked(True)
            
        # Load last path
        last_path = settings.value("export/path", "", type=str)
        if last_path:
            dir_name = os.path.dirname(last_path)
            if os.path.exists(dir_name):
                is_wav = (self.combo_format.currentIndex() == 0)
                ext = ".wav" if is_wav else ".mp3"
                base, _ = os.path.splitext(last_path)
                self.txt_path.setText(base + ext)
