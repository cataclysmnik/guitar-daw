from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont

class LevelMeter(QWidget):
    """Custom vertical LED VU meter with peak hold and clip indicator."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(12, 30)
        self.setMaximumSize(35, 300)
        
        self.current_db = -60.0
        self.peak_db = -60.0
        self.peak_hold_ticks = 0
        self.clip_active = False
        self.clip_ticks = 0
        
        # Color definitions (professional studio theme)
        self.color_green = QColor("#4d9a5b")
        self.color_yellow = QColor("#c18f3b")
        self.color_red = QColor("#a63e3e")
        
        self.color_green_off = QColor("#1a261c")
        self.color_yellow_off = QColor("#2c2518")
        self.color_red_off = QColor("#2b1919")
        
        # Repaint timer to handle decay animations smoothly
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_decay)
        self.timer.start(33)  # ~30 FPS
        
    def set_level(self, db):
        """Sets current dB level and updates peak/clip flags."""
        db = max(-60.0, min(6.0, db))
        self.current_db = db
        
        # Handle peak hold
        if db >= self.peak_db:
            self.peak_db = db
            self.peak_hold_ticks = 30  # Hold for ~1 second
        
        # Handle clip indicator
        if db >= 0.0:
            self.clip_active = True
            self.clip_ticks = 60  # Light up for ~2 seconds
            
        self.update()
        
    def update_decay(self):
        """Decays peak hold indicator and clip timer."""
        # Decay peak hold
        if self.peak_hold_ticks > 0:
            self.peak_hold_ticks -= 1
        else:
            self.peak_db = max(-60.0, self.peak_db - 0.8)  # Gradual decay
            
        # Decay clip indicator
        if self.clip_ticks > 0:
            self.clip_ticks -= 1
            if self.clip_ticks == 0:
                self.clip_active = False
                
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            w = self.width()
            h = self.height()
            
            # 1. Draw solid dark background casing
            painter.setPen(QPen(QColor("#3e3e42"), 1.0))
            painter.setBrush(QBrush(QColor("#18181c")))
            painter.drawRoundedRect(0, 0, w - 1, h - 1, 3, 3)
            
            # 2. Geometry calculations
            margin_x = 2 if h < 80 else 3
            clip_height = 4 if h < 80 else 8
            margin_y = 2 if h < 80 else 5
            meter_y_start = margin_y + clip_height + margin_y
            meter_height = h - meter_y_start - margin_y
            meter_width = w - (margin_x * 2)
            
            # 3. Draw Clip LED at the top
            clip_rect = QRectF(margin_x, margin_y, meter_width, clip_height)
            if self.clip_active:
                painter.setBrush(QBrush(self.color_red))
                painter.setPen(QPen(self.color_red.lighter(), 1.0))
            else:
                painter.setBrush(QBrush(self.color_red_off))
                painter.setPen(QPen(QColor("#444"), 0.5))
            painter.drawRect(clip_rect)
            
            # 4. Draw segmented LED bars
            num_segments = 12 if h < 80 else 24
            seg_spacing = 1.0 if h < 80 else 1.5
            total_spacing_h = (num_segments - 1) * seg_spacing
            seg_h = max(1.0, (meter_height - total_spacing_h) / num_segments)
            
            min_db = -60.0
            max_db = 3.0
            
            # Draw from bottom (lowest db) to top (highest db)
            for i in range(num_segments):
                # Calculate dB for this segment
                # i = 0 is bottom, i = num_segments - 1 is top
                seg_db = min_db + (i / (num_segments - 1)) * (max_db - min_db)
                
                # Y coordinate of segment
                # Note: y = 0 is top of canvas, so draw from bottom-up
                y_pos = meter_y_start + meter_height - ((i + 1) * seg_h + i * seg_spacing)
                seg_rect = QRectF(margin_x, y_pos, meter_width, seg_h)
                
                # Determine color and whether it's active
                is_on = self.current_db >= seg_db
                
                if seg_db < -12.0:
                    brush_color = self.color_green if is_on else self.color_green_off
                elif seg_db < -3.0:
                    brush_color = self.color_yellow if is_on else self.color_yellow_off
                else:
                    brush_color = self.color_red if is_on else self.color_red_off
                    
                painter.setBrush(QBrush(brush_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(seg_rect)
                
            # 5. Draw Peak Hold line
            if self.peak_db > min_db:
                # Map peak db to Y coordinate
                norm_peak = (self.peak_db - min_db) / (max_db - min_db)
                norm_peak = max(0.0, min(1.0, norm_peak))
                
                peak_y = meter_y_start + meter_height - (norm_peak * meter_height)
                
                # Peak hold line color depends on value
                if self.peak_db < -12.0:
                    peak_color = self.color_green
                elif self.peak_db < -3.0:
                    peak_color = self.color_yellow
                else:
                    peak_color = self.color_red
                    
                painter.setPen(QPen(peak_color, 1.5))
                painter.drawLine(int(margin_x), int(peak_y), int(w - margin_x), int(peak_y))
        finally:
            painter.end()
