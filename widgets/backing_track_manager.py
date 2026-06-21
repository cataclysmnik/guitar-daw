import os
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QFileDialog, QMessageBox, QInputDialog, QApplication
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from audio_engine import AudioItem

def get_backing_tracks_dir():
    user_docs = os.path.expanduser("~/Documents")
    if not os.path.exists(user_docs):
        user_docs = os.path.expanduser("~")
    backing_dir = os.path.join(user_docs, "Graphite", "BackingTracks")
    os.makedirs(backing_dir, exist_ok=True)
    return backing_dir

class BackingTrackManagerWidget(QWidget):
    def __init__(self, main_window, audio_engine, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.audio_engine = audio_engine
        
        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # --- Top bar with title, search, and action buttons ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        
        lbl_title = QLabel("Backing Tracks")
        lbl_title.setObjectName("ManagerTitle")
        lbl_title.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        top_bar.addWidget(lbl_title)
        
        top_bar.addStretch()
        
        # Search filter
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter backing tracks...")
        self.search_input.setObjectName("SearchInput")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self.filter_list)
        top_bar.addWidget(self.search_input)
        
        # Import button
        btn_import = QPushButton("Import Track...")
        btn_import.setObjectName("ImportButton")
        btn_import.clicked.connect(self.import_backing_track)
        top_bar.addWidget(btn_import)
        
        # Refresh button
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setObjectName("RefreshButton")
        btn_refresh.clicked.connect(self.refresh_list)
        top_bar.addWidget(btn_refresh)
        
        # Open folder button
        btn_open_folder = QPushButton("Open Folder")
        btn_open_folder.setObjectName("FolderButton")
        btn_open_folder.clicked.connect(self.open_folder_in_explorer)
        top_bar.addWidget(btn_open_folder)
        
        layout.addLayout(top_bar)
        
        # --- List widget showing the universal files ---
        self.tracks_list = QListWidget()
        self.tracks_list.setObjectName("TracksList")
        self.tracks_list.itemDoubleClicked.connect(self.load_selected_track)
        self.tracks_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tracks_list.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.tracks_list)
        
        # Stylesheet
        self.setStyleSheet("""
            QLabel#ManagerTitle {
                color: #ffffff;
            }
            QLineEdit#SearchInput {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QPushButton {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
                color: #88888c;
                font-family: "Consolas", monospace;
                font-size: 11px;
                font-weight: bold;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #1a1a1c;
                color: #ffffff;
                border-color: #444448;
            }
            QListWidget#TracksList {
                background-color: #000000;
                border: 1px solid #222225;
                border-radius: 4px;
                color: #e2e2e5;
                font-family: "Consolas", monospace;
                font-size: 11px;
                padding: 5px;
            }
            QListWidget#TracksList::item {
                padding: 8px 10px;
                border-bottom: 1px solid #111112;
            }
            QListWidget#TracksList::item:hover {
                background-color: #1a1a1c;
                color: #ffffff;
            }
            QListWidget#TracksList::item:selected {
                background-color: #ffffff;
                color: #000000;
            }
        """)

    def refresh_list(self):
        self.tracks_list.clear()
        backing_dir = get_backing_tracks_dir()
        
        audio_extensions = ('.wav', '.mp3', '.flac', '.ogg', '.m4a', '.wma', '.aiff', '.aif')
        
        try:
            files = sorted(os.listdir(backing_dir))
        except Exception as e:
            print(f"Error reading backing tracks directory: {e}")
            return
            
        for f in files:
            if f.lower().endswith(audio_extensions):
                item = QListWidgetItem(f)
                item.setData(Qt.ItemDataRole.UserRole, os.path.join(backing_dir, f))
                self.tracks_list.addItem(item)
                
        self.filter_list()

    def filter_list(self):
        query = self.search_input.text().lower()
        for i in range(self.tracks_list.count()):
            item = self.tracks_list.item(i)
            item.setHidden(query not in item.text().lower())

    def import_backing_track(self):
        dlg = QFileDialog(self)
        dlg.setWindowTitle("Import Backing Track to Global Folder")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setNameFilter("Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a *.wma *.aiff *.aif);;All Files (*)")
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        from theme_utils import apply_dark_theme_to_hwnd
        apply_dark_theme_to_hwnd(int(dlg.winId()))
        
        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            src_path = dlg.selectedFiles()[0]
            dest_dir = get_backing_tracks_dir()
            filename = os.path.basename(src_path)
            dest_path = os.path.join(dest_dir, filename)
            
            try:
                shutil.copy2(src_path, dest_path)
                self.refresh_list()
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to copy file to backing tracks folder:\n{e}")

    def open_folder_in_explorer(self):
        backing_dir = get_backing_tracks_dir()
        try:
            os.startfile(backing_dir)
        except Exception as e:
            print(f"Failed to open backing tracks directory: {e}")

    def load_selected_track(self, item=None):
        if not item:
            item = self.tracks_list.currentItem()
        if not item:
            return
            
        file_path = item.data(Qt.ItemDataRole.UserRole)
        filename = item.text()
        
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Missing File", "The selected backing track file no longer exists.")
            self.refresh_list()
            return
            
        # Load backing track using loading popup
        from widgets.loading_popup import LoadingPopup
        popup = LoadingPopup(f"LOADING BACKING TRACK:\n{filename.upper()}", self.main_window)
        popup.show()
        QApplication.processEvents()
        
        try:
            if hasattr(self.main_window, 'undo_manager'):
                self.main_window.undo_manager.push_state(f"Load Backing Track {filename}")
                
            # Create track
            track_name = os.path.splitext(filename)[0]
            new_track = self.audio_engine.add_track(track_name)
            sample_rate = self.audio_engine.sample_rate
            
            # Load item
            loaded_item = AudioItem(start_sample=0, sample_rate=sample_rate, file_path=file_path)
            if loaded_item.audio_data is not None:
                with new_track.lock:
                    new_track.items.append(loaded_item)
                new_track.update_pedalboard(self.audio_engine.sample_rate)
                
                self.main_window.refresh_track_cards()
                self.main_window.mark_project_dirty()
                if hasattr(self.main_window, 'timeline') and self.main_window.timeline:
                    self.main_window.timeline.update_track_layout()
            else:
                QMessageBox.critical(self, "Load Error", "Failed to load audio data from backing track.")
        finally:
            popup.close()
            QApplication.processEvents()

    def show_context_menu(self, pos):
        item = self.tracks_list.itemAt(pos)
        if not item:
            return
            
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0b0b0c;
                color: #e2e2e5;
                border: 1px solid #222225;
                font-family: "Consolas", monospace;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #222225;
                color: #ffffff;
            }
        """)
        
        action_load = QAction("Load into Project", self)
        action_load.triggered.connect(lambda: self.load_selected_track(item))
        menu.addAction(action_load)
        
        action_rename = QAction("Rename...", self)
        action_rename.triggered.connect(lambda: self.rename_track_file(item))
        menu.addAction(action_rename)
        
        menu.addSeparator()
        
        action_delete = QAction("Delete File", self)
        action_delete.triggered.connect(lambda: self.delete_track_file(item))
        menu.addAction(action_delete)
        
        menu.exec(self.tracks_list.mapToGlobal(pos))

    def rename_track_file(self, item):
        old_path = item.data(Qt.ItemDataRole.UserRole)
        old_filename = item.text()
        base_name, ext = os.path.splitext(old_filename)
        
        new_name, ok = QInputDialog.getText(self, "Rename Backing Track", "New name for backing track file:", text=base_name)
        if ok and new_name.strip():
            new_filename = new_name.strip() + ext
            new_path = os.path.join(get_backing_tracks_dir(), new_filename)
            
            if os.path.exists(new_path):
                QMessageBox.warning(self, "Duplicate Name", "A file with this name already exists in the backing tracks folder.")
                return
                
            try:
                os.rename(old_path, new_path)
                self.refresh_list()
            except Exception as e:
                QMessageBox.critical(self, "Rename Error", f"Failed to rename backing track file:\n{e}")

    def delete_track_file(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        filename = item.text()
        
        reply = QMessageBox.question(
            self, "Delete Backing Track",
            f"Are you sure you want to permanently delete the backing track file '{filename}' from disk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(file_path)
                self.refresh_list()
            except Exception as e:
                QMessageBox.critical(self, "Delete Error", f"Failed to delete backing track file:\n{e}")
