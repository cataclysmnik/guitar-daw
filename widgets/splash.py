import os
from PySide6.QtWidgets import QSplashScreen, QApplication
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPen, QBrush, QPainterPath

class GraphiteSplashScreen(QSplashScreen):
    """A premium, dynamically drawn splash screen for Graphite DAW."""
    def __init__(self):
        super().__init__()
        # Set window properties: frameless, stay on top, transparent background support
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(520, 320)
        
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
            
            # 1. Outer container (Sleek dark graphite rounded rect)
            bg_color = QColor("#141415")
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            rect = self.rect()
            painter.drawRoundedRect(rect, 8, 8)
            
            # Draw a thin professional graphite border
            border_pen = QPen(QColor("#2d2d30"), 1)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 8, 8)
            
            # 2. Draw Vector Waveform or logo.svg in the middle
            logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logo.svg")
            if os.path.exists(logo_path):
                try:
                    from PySide6.QtSvg import QSvgRenderer
                    from PySide6.QtCore import QRectF
                    renderer = QSvgRenderer(logo_path)
                    logo_rect = QRectF(260.0 - 50.0, 170.0 - 50.0, 100.0, 100.0)
                    renderer.render(painter, logo_rect)
                except Exception as e:
                    print(f"Failed to render logo.svg on splash: {e}")
                    # Fallback to wave path
                    wave_pen = QPen()
                    wave_pen.setWidth(2)
                    wave_gradient = QLinearGradient(100, 160, 420, 160)
                    wave_gradient.setColorAt(0, QColor("#2d2d30"))
                    wave_gradient.setColorAt(0.5, QColor("#8e8e93"))
                    wave_gradient.setColorAt(1, QColor("#2d2d30"))
                    wave_pen.setBrush(QBrush(wave_gradient))
                    painter.setPen(wave_pen)
                    path = QPainterPath()
                    path.moveTo(80, 160)
                    path.cubicTo(160, 90, 200, 230, 260, 160)
                    path.cubicTo(320, 90, 360, 230, 440, 160)
                    painter.drawPath(path)
            else:
                wave_pen = QPen()
                wave_pen.setWidth(2)
                
                # Subtle horizontal gray gradient for the waveform lines
                wave_gradient = QLinearGradient(100, 160, 420, 160)
                wave_gradient.setColorAt(0, QColor("#2d2d30"))
                wave_gradient.setColorAt(0.5, QColor("#8e8e93"))
                wave_gradient.setColorAt(1, QColor("#2d2d30"))
                wave_pen.setBrush(QBrush(wave_gradient))
                painter.setPen(wave_pen)
                
                # Symmetric wave path
                path = QPainterPath()
                path.moveTo(80, 160)
                path.cubicTo(160, 90, 200, 230, 260, 160)
                path.cubicTo(320, 90, 360, 230, 440, 160)
                painter.drawPath(path)
            
            # 3. Typography
            # Brand title
            font_title = QFont("Segoe UI", 26, QFont.Weight.Bold)
            font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6)
            painter.setFont(font_title)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRect(0, 70, self.width(), 50), Qt.AlignmentFlag.AlignCenter, "GRAPHITE")
            
            # Brand sub-header
            font_sub = QFont("Segoe UI", 8, QFont.Weight.Medium)
            font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
            painter.setFont(font_sub)
            painter.setPen(QColor("#7a7a7d"))
            painter.drawText(QRect(0, 115, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "DIGITAL AUDIO WORKSTATION")
            
            # 4. Progress bar line (sleek and modern 3px)
            bar_y = 260
            bar_x = 40
            bar_w = self.width() - 80
            bar_h = 3
            
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
                
            # 5. Status Text
            font_status = QFont("Segoe UI", 9)
            painter.setFont(font_status)
            painter.setPen(QColor("#8e8e93"))
            painter.drawText(QRect(bar_x, bar_y + 10, bar_w, 20), Qt.AlignmentFlag.AlignLeft, self.status_message)
        finally:
            painter.end()
