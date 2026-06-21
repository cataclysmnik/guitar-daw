import os
from PySide6.QtWidgets import QSplashScreen, QApplication
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPen, QBrush, QPainterPath, QPixmap

class GraphiteSplashScreen(QSplashScreen):
    """A premium splash screen for Graphite DAW displaying splashscreen.png."""
    def __init__(self):
        super().__init__()
        # Set window properties: frameless, transparent background support
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # Load splashscreen image
        from theme_utils import get_resource_path
        self.pixmap = QPixmap(get_resource_path("splashscreen.png"))
        if not self.pixmap.isNull():
            self.pixmap = self.pixmap.scaledToWidth(600, Qt.TransformationMode.SmoothTransformation)
            # Increase height to provide extra room at the bottom for loading bar and text
            self.resize(self.pixmap.width(), self.pixmap.height() + 45)
        else:
            self.resize(600, 445)
        
        # Center the splash screen on the primary monitor
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        
        self.status_message = "Initializing Graphite..."
        self.progress = 10
        
    def set_status(self, message, progress):
        """Updates the status text and progress bar, triggering immediate repaint."""
        self.status_message = message
        self.progress = progress
        self.update()
        QApplication.processEvents()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # 1. Background container (Sleek dark graphite rounded rect behind everything)
            bg_color = QColor("#141415")
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 8, 8)
            
            # 2. Draw splashscreen.png (without vertical stretching)
            if not self.pixmap.isNull():
                painter.drawPixmap(0, 0, self.pixmap.width(), self.pixmap.height(), self.pixmap)
            
            # Draw a thin professional graphite border around the entire widget
            border_pen = QPen(QColor("#2d2d30"), 1)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
            
            # 3. Progress bar line (sleek and modern 3px)
            bar_h = 3
            bar_x = 40
            bar_w = self.width() - 80
            bar_y = self.height() - 35
            
            # Inactive bar
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#2c2c2e")))
            painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 1.5, 1.5)
            
            # Active loading bar
            progress_w = int(bar_w * (self.progress / 100.0))
            if progress_w > 0:
                active_gradient = QLinearGradient(bar_x, bar_y, bar_x + progress_w, bar_y)
                active_gradient.setColorAt(0, QColor("#8e8e93"))
                active_gradient.setColorAt(1, QColor("#ffffff"))
                painter.setBrush(QBrush(active_gradient))
                painter.drawRoundedRect(bar_x, bar_y, progress_w, bar_h, 1.5, 1.5)
                
            # 3. Status Text
            font_status = QFont("Segoe UI", 9)
            painter.setFont(font_status)
            painter.setPen(QColor("#8e8e93"))
            painter.drawText(QRect(bar_x, bar_y + 10, bar_w, 20), Qt.AlignmentFlag.AlignLeft, self.status_message)
        finally:
            painter.end()
