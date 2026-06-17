from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import Qt

class LoadingPopup(QDialog):
    """
    A premium dark-themed modal loading popup with an infinite progress bar
    and a cancel button, following the Nothing aesthetic.
    """
    def __init__(self, message="LOADING...", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Please Wait")
        self.setFixedSize(320, 140)
        self.setModal(True)
        self.setObjectName("LoadingPopup")
        
        # Remove default window frames/borders
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        
        self.was_cancelled = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 15)
        layout.setSpacing(12)
        
        # Message Label
        self.lbl_message = QLabel(message.upper(), self)
        self.lbl_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setObjectName("LoadingMessage")
        layout.addWidget(self.lbl_message)
        
        # Flat infinite progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0) # Infinite busy/marquee indicator
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setObjectName("LoadingProgress")
        layout.addWidget(self.progress_bar)
        
        # Cancel Button
        self.btn_cancel = QPushButton("CANCEL", self)
        self.btn_cancel.setObjectName("CancelButton")
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("""
            QDialog#LoadingPopup {
                background-color: #0b0b0c;
                border: 1px solid #222225;
            }
            QLabel#LoadingMessage {
                color: #ffffff;
                font-family: "Consolas", monospace;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 0.5px;
                line-height: 14px;
            }
            QProgressBar#LoadingProgress {
                background-color: #151518;
                border: none;
            }
            QProgressBar#LoadingProgress::chunk {
                background-color: #ff0033;
            }
            QPushButton#CancelButton {
                background-color: #0b0b0c;
                color: #88888c;
                border: 1px solid #333333;
                font-family: "Consolas", monospace;
                font-weight: bold;
                font-size: 10px;
                padding: 4px;
            }
            QPushButton#CancelButton:hover {
                border-color: #ff0033;
                color: #ffffff;
            }
        """)

    def on_cancel_clicked(self):
        self.was_cancelled = True
        self.reject()
