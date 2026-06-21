import os
import wave
import uuid
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFileDialog, QMessageBox, QFrame,
    QPushButton, QLabel
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QPoint, QSize, QEvent
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QIcon
from audio_engine import AudioItem
def get_event_position(event):
    """Safely extracts the position from a QDropEvent, QDragMoveEvent, or QMouseEvent in Qt6/PySide6."""
    if hasattr(event, 'position'):
        pos = event.position()
        if hasattr(pos, 'toPoint'):
            return pos.toPoint()
        return pos
    elif hasattr(event, 'pos'):
        return event.pos()
    return QPoint(0, 0)

class TimeRulerWidget(QWidget):
    """Time ruler widget displayed above the timeline track lanes."""
    timeClicked = Signal(float)  # Emitted with the selected time in seconds
    zoomChanged = Signal(float)  # Emitted when scrolling to zoom (multiplier)
    
    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        self.pixels_per_second = 50.0  # Zoom level
        self.scroll_offset = 0
        self.setMinimumHeight(30)
        self.setMaximumHeight(30)
        
        self.is_scrubbing = False
        self.drag_mode = None
        self.lanes = None
        
    def set_scroll_offset(self, offset):
        self.scroll_offset = offset
        self.update()
        
    def set_zoom(self, pixels_per_second):
        self.pixels_per_second = pixels_per_second
        self.update()
        
    def mouseDoubleClickEvent(self, event):
        if hasattr(self, 'lanes') and self.lanes:
            self.lanes.setup_loop_region()
            
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            sr = self.audio_engine.sample_rate if self.audio_engine else 44100
            x = event.position().x()
            abs_x = x + self.scroll_offset
            margin = 8
            
            if self.audio_engine.loop_enabled and self.audio_engine.loop_end > self.audio_engine.loop_start:
                loop_start_x = int((self.audio_engine.loop_start / sr) * self.pixels_per_second)
                loop_end_x = int((self.audio_engine.loop_end / sr) * self.pixels_per_second)
                
                if abs(abs_x - loop_start_x) <= margin:
                    self.drag_mode = "loop_start"
                    return
                elif abs(abs_x - loop_end_x) <= margin:
                    self.drag_mode = "loop_end"
                    return
                    
            self.is_scrubbing = True
            self.update_cursor_pos(x)
            
    def mouseMoveEvent(self, event):
        sr = self.audio_engine.sample_rate if self.audio_engine else 44100
        x = event.position().x()
        abs_x = x + self.scroll_offset
        margin = 8
        
        if getattr(self, 'drag_mode', None) == "loop_start":
            target_sample = max(0, int((abs_x / self.pixels_per_second) * sr))
            self.audio_engine.loop_start = min(target_sample, self.audio_engine.loop_end - 1)
            self.update()
            if hasattr(self, 'lanes') and self.lanes:
                self.lanes.update()
        elif getattr(self, 'drag_mode', None) == "loop_end":
            target_sample = max(0, int((abs_x / self.pixels_per_second) * sr))
            self.audio_engine.loop_end = max(self.audio_engine.loop_start + 1, target_sample)
            self.update()
            if hasattr(self, 'lanes') and self.lanes:
                self.lanes.update()
        elif self.is_scrubbing:
            self.update_cursor_pos(x)
        else:
            if self.audio_engine.loop_enabled and self.audio_engine.loop_end > self.audio_engine.loop_start:
                loop_start_x = int((self.audio_engine.loop_start / sr) * self.pixels_per_second)
                loop_end_x = int((self.audio_engine.loop_end / sr) * self.pixels_per_second)
                
                if abs(abs_x - loop_start_x) <= margin or abs(abs_x - loop_end_x) <= margin:
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_mode = None
            self.is_scrubbing = False
            
    def wheelEvent(self, event):
        # Zoom timeline horizontally on wheel scroll (Reaper-style)
        delta = event.angleDelta().y()
        zoom_factor = 1.15 if delta > 0 else 0.85
        self.zoomChanged.emit(zoom_factor)
        
    def update_cursor_pos(self, x):
        abs_x = x + self.scroll_offset
        time_seconds = max(0.0, abs_x / self.pixels_per_second)
        self.timeClicked.emit(time_seconds)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            w = self.width()
            h = self.height()
            
            # Draw background
            painter.fillRect(0, 0, w, h, QColor("#0b0b0c"))
            painter.setPen(QPen(QColor("#222225"), 1))
            painter.drawLine(0, h - 1, w, h - 1)
            
            # Translate painter horizontally to scroll matching the timeline scroll
            painter.translate(-self.scroll_offset, 0)
            
            # Draw ticks and time strings
            total_width = w + self.scroll_offset
            max_seconds = int(total_width / self.pixels_per_second) + 5
            
            # Dynamic tick spacing based on zoom levels
            if self.pixels_per_second < 15.0:
                tick_step = 10  # Draw labels every 10 seconds
                sub_step = 2
            elif self.pixels_per_second < 50.0:
                tick_step = 5   # Every 5 seconds
                sub_step = 1
            elif self.pixels_per_second < 150.0:
                tick_step = 1   # Every second
                sub_step = 0.2
            else:
                tick_step = 0.5  # Every half-second
                sub_step = 0.1
                
            font = QFont("Consolas", 8)
            painter.setFont(font)
            
            # Paint grid markers
            seconds_span = np.arange(0, max_seconds, sub_step)
            for s in seconds_span:
                x_pos = int(s * self.pixels_per_second)
                is_major = abs(s % tick_step) < 1e-5
                
                if is_major:
                    painter.setPen(QPen(QColor("#88888c"), 1))
                    painter.drawLine(x_pos, h - 12, x_pos, h - 2)
                    
                    # Format time text: M:SS or M:SS.hh
                    minutes = int(s // 60)
                    secs = s % 60
                    if tick_step < 1.0:
                        time_str = f"{minutes}:{secs:05.2f}"
                    else:
                        time_str = f"{minutes}:{int(secs):02d}"
                        
                    painter.drawText(x_pos + 3, h - 14, time_str)
                else:
                    painter.setPen(QPen(QColor("#222225"), 1))
                    painter.drawLine(x_pos, h - 6, x_pos, h - 2)
                    
            # Draw loop range if enabled
            sr = self.audio_engine.sample_rate if self.audio_engine else 44100
            if self.audio_engine.loop_enabled and self.audio_engine.loop_end > self.audio_engine.loop_start:
                loop_start_x = int((self.audio_engine.loop_start / sr) * self.pixels_per_second)
                loop_end_x = int((self.audio_engine.loop_end / sr) * self.pixels_per_second)
                
                # Draw shaded area in ruler
                painter.fillRect(loop_start_x, 0, loop_end_x - loop_start_x, h - 2, QColor(255, 255, 255, 12))
                
                # Draw left handle
                painter.setPen(QPen(QColor("#88888c"), 1.5))
                painter.drawLine(loop_start_x, 0, loop_start_x, h)
                painter.fillRect(loop_start_x, 0, 5, 8, QColor("#ffffff"))
                painter.setPen(QPen(QColor("#222225"), 1))
                painter.drawRect(loop_start_x, 0, 5, 8)
                
                # Draw right handle
                painter.setPen(QPen(QColor("#88888c"), 1.5))
                painter.drawLine(loop_end_x, 0, loop_end_x, h)
                painter.fillRect(loop_end_x - 5, 0, 5, 8, QColor("#ffffff"))
                painter.setPen(QPen(QColor("#222225"), 1))
                painter.drawRect(loop_end_x - 5, 0, 5, 8)

            # Draw Playhead Cap (Red Triangle)
            playhead_sec = self.audio_engine.playhead_samples / sr
            playhead_x = int(playhead_sec * self.pixels_per_second)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#ff0033")))
            
            points = [
                QPoint(playhead_x - 6, 2),
                QPoint(playhead_x + 6, 2),
                QPoint(playhead_x, 12)
            ]
            painter.drawPolygon(points)
        finally:
            painter.end()


class TimelineLanesWidget(QWidget):
    """Draws track lanes, items, waveforms, and the moving playhead cursor."""
    trackSelected = Signal(int)  # Emitted with track index
    timeClicked = Signal(float)   # Emitted with position in seconds
    zoomChanged = Signal(float)   # Zoom multiplier
    
    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        self.main_window = None
        self.pixels_per_second = 50.0
        self.lane_height = 150
        
        self.active_drag_item = None
        self.active_drag_mode = None  # "move", "resize_left", "resize_right"
        self.drag_track = None
        self.drag_click_x = 0
        self.drag_start_sample = 0
        self.drag_offset_samples = 0
        self.drag_length_samples = 0
        self.drag_offset_samples_click = 0
        
        self.selected_item = None
        self.selected_track_for_item = None
        self.clipboard_clip = None
        self.live_recording_cache = {}
        self.selected_items = set()
        self.box_select_start = None
        self.box_select_current = None
        
        self.right_drag_active = False
        self.right_drag_start_x = 0
        self.right_drag_current_x = 0
        self.right_drag_start_sample = 0
        self.right_drag_track = None
        
        self.comp_swipe_item = None
        self.comp_swipe_take_idx = None
        self.comp_swipe_start_sample = None
        
        self.right_swipe_item = None
        self.right_swipe_take_idx = None
        self.right_swipe_start_sample = None
        
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        
    def set_zoom(self, pixels_per_second):
        self.pixels_per_second = pixels_per_second
        self.update_geometry()
        
    def update_geometry(self):
        # Calculate maximum track bounds
        tracks_count = len(self.audio_engine.tracks)
        h = max(300, tracks_count * self.lane_height)
        
        # Verify selected track is still valid
        if self.selected_track_for_item and self.selected_track_for_item not in self.audio_engine.tracks:
            self.selected_item = None
            self.selected_track_for_item = None
            
        # Calculate maximum time bound
        max_sec = 300.0  # Default 5 minutes
        for track in self.audio_engine.tracks:
            for item in track.items:
                if item.audio_data is not None:
                    item_end = (item.start_sample + item.length_samples) / item.sample_rate
                    max_sec = max(max_sec, item_end + 15.0)  # Pad with 15s
                
        # Make sure the width expands to cover the current playhead + padding
        sr = self.audio_engine.sample_rate if self.audio_engine else 44100
        playhead_sec = self.audio_engine.playhead_samples / sr
        max_sec = max(max_sec, playhead_sec + 30.0)
        
        w = int(max_sec * self.pixels_per_second)
        self.resize(w, h)
        self.update()
        
    def get_hover_state(self, x, y):
        """
        Returns (target, target_type, track, hover_type) where target_type is "item" or "arm_region"
        and hover_type can be "resize_left", "resize_right", "move", or None.
        """
        track_idx = int(y // self.lane_height)
        if track_idx < 0 or track_idx >= len(self.audio_engine.tracks):
            return None, None, None, None
            
        track = self.audio_engine.tracks[track_idx]
        margin = 8
        
        with track.lock:
            items_copy = list(track.items)
            arm_regions_copy = list(getattr(track, "arm_regions", []))
            
        best_target = None
        best_target_type = None
        best_type = None
        min_dist = float('inf')
        
        # 1. Check audio items first
        for item in items_copy:
            if item.audio_data is None:
                continue
            item_start_x = int((item.start_sample / item.sample_rate) * self.pixels_per_second)
            item_end_x = int(((item.start_sample + item.length_samples) / item.sample_rate) * self.pixels_per_second)
            
            if item_start_x - margin <= x <= item_end_x + margin:
                dist_left = abs(x - item_start_x)
                dist_right = abs(x - item_end_x)
                
                # Check near left edge
                if dist_left <= margin and dist_left < min_dist:
                    min_dist = dist_left
                    best_target = item
                    best_target_type = "item"
                    best_type = "resize_left"
                # Check near right edge
                elif dist_right <= margin and dist_right < min_dist:
                    min_dist = dist_right
                    best_target = item
                    best_target_type = "item"
                    best_type = "resize_right"
                # Inside item
                elif item_start_x < x < item_end_x:
                    if min_dist == float('inf'):
                        best_target = item
                        best_target_type = "item"
                        best_type = "move"
                        
        # 2. Check Auto-Arm regions if no item matched
        if best_target is None:
            sr = self.audio_engine.sample_rate
            for region in arm_regions_copy:
                reg_start_x = int((region[0] / sr) * self.pixels_per_second)
                reg_end_x = int((region[1] / sr) * self.pixels_per_second)
                
                if reg_start_x - margin <= x <= reg_end_x + margin:
                    dist_left = abs(x - reg_start_x)
                    dist_right = abs(x - reg_end_x)
                    
                    if dist_left <= margin and dist_left < min_dist:
                        min_dist = dist_left
                        best_target = region
                        best_target_type = "arm_region"
                        best_type = "resize_left"
                    elif dist_right <= margin and dist_right < min_dist:
                        min_dist = dist_right
                        best_target = region
                        best_target_type = "arm_region"
                        best_type = "resize_right"
                    elif reg_start_x < x < reg_end_x:
                        if min_dist == float('inf'):
                            best_target = region
                            best_target_type = "arm_region"
                            best_type = "move"
                            
        if best_target:
            return best_target, best_target_type, track, best_type
        return None, None, None, None

            
    def get_last_clip_end_sample(self):
        max_end = 0
        for track in self.audio_engine.tracks:
            with track.lock:
                for item in track.items:
                    end_sample = item.start_sample + item.length_samples
                    if end_sample > max_end:
                        max_end = end_sample
        return max_end

    def setup_loop_region(self):
        if self.audio_engine.loop_enabled:
            self.audio_engine.loop_enabled = False
        else:
            sr = self.audio_engine.sample_rate if self.audio_engine else 44100
            last_clip_end = self.get_last_clip_end_sample()
            self.audio_engine.loop_start = 0
            if last_clip_end == 0:
                self.audio_engine.loop_end = int(5.0 * sr)
            else:
                self.audio_engine.loop_end = int(last_clip_end)
            self.audio_engine.loop_enabled = True
        self.update()
        if hasattr(self, 'ruler') and self.ruler:
            self.ruler.update()

    def mouseDoubleClickEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        target, target_type, track, hover_type = self.get_hover_state(x, y)
        is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if target is None and not is_shift:
            self.setup_loop_region()
            return
            
        # Double-click empty track lane space to import audio or create Auto-Arm zone
        track_idx = int(y // self.lane_height)
        if track_idx < len(self.audio_engine.tracks):
            track = self.audio_engine.tracks[track_idx]
            sample_rate = self.audio_engine.sample_rate
            start_sample = int((x / self.pixels_per_second) * sample_rate)
            
            # If Shift is held down, create an Auto-Arm Zone!
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Default 5 seconds
                end_sample = start_sample + int(5.0 * sample_rate)
                if not hasattr(track, "arm_regions"):
                    track.arm_regions = []
                with track.lock:
                    region = [start_sample, end_sample]
                    track.arm_regions.append(region)
                self.selected_item = region
                self.selected_target_type = "arm_region"
                self.selected_track_for_item = track
                self.update_geometry()
                self.update()
                if hasattr(self, 'main_window') and self.main_window:
                    self.main_window.mark_project_dirty()
                return
            
            # Select file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Audio File",
                "",
                "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a *.wma *.aiff *.aif);;All Files (*)"
            )
            if file_path:
                # Create and add item
                item = AudioItem(start_sample, sample_rate, file_path=file_path)
                if item.audio_data is not None:
                    # Copy WAV next to project later, or keep path
                    self.audio_engine.add_item_to_track(track, item)
                    track.update_pedalboard(self.audio_engine.sample_rate)
                    self.update_geometry()
                    if hasattr(self, 'main_window') and self.main_window:
                        self.main_window.mark_project_dirty()
                    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                self.main_window.undo_manager.push_state("Delete Clip")
            deleted_any = False
            for target in list(self.selected_items):
                for track in self.audio_engine.tracks:
                    with track.lock:
                        if target in track.items:
                            track.items.remove(target)
                            deleted_any = True
                            break
                        elif hasattr(track, "arm_regions") and target in track.arm_regions:
                            track.arm_regions.remove(target)
                            deleted_any = True
                            break
            
            if self.selected_item and not deleted_any:
                track = self.selected_track_for_item
                target = self.selected_item
                target_type = getattr(self, "selected_target_type", "item")
                if track:
                    with track.lock:
                        if target_type == "item":
                            if target in track.items:
                                track.items.remove(target)
                                deleted_any = True
                        else:
                            if hasattr(track, "arm_regions") and target in track.arm_regions:
                                track.arm_regions.remove(target)
                                deleted_any = True
                                
            if deleted_any:
                self.selected_items.clear()
                self.selected_item = None
                self.selected_target_type = None
                self.selected_track_for_item = None
                self.update_geometry()
                self.update()
                if hasattr(self, 'main_window') and self.main_window:
                    self.main_window.mark_project_dirty()
        elif event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C:
                if self.selected_item:
                    self.clipboard_clip = {
                        "file_path": self.selected_item.file_path,
                        "audio_data": self.selected_item.audio_data.copy() if self.selected_item.audio_data is not None else None,
                        "offset_samples": self.selected_item.offset_samples,
                        "length_samples": self.selected_item.length_samples,
                        "sample_rate": self.selected_item.sample_rate
                    }
            elif event.key() == Qt.Key.Key_X:
                if self.selected_item and self.selected_track_for_item:
                    if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                        self.main_window.undo_manager.push_state("Cut Clip")
                    self.clipboard_clip = {
                        "file_path": self.selected_item.file_path,
                        "audio_data": self.selected_item.audio_data.copy() if self.selected_item.audio_data is not None else None,
                        "offset_samples": self.selected_item.offset_samples,
                        "length_samples": self.selected_item.length_samples,
                        "sample_rate": self.selected_item.sample_rate
                    }
                    track = self.selected_track_for_item
                    item = self.selected_item
                    with track.lock:
                        if item in track.items:
                            track.items.remove(item)
                    self.selected_item = None
                    self.selected_track_for_item = None
                    self.update_geometry()
                    self.update()
                    if hasattr(self, 'main_window') and self.main_window:
                        self.main_window.mark_project_dirty()
            elif event.key() == Qt.Key.Key_V:
                if hasattr(self, 'clipboard_clip') and self.clipboard_clip is not None:
                    if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                        self.main_window.undo_manager.push_state("Paste Clip")
                    target_track = None
                    if self.main_window and self.main_window.selected_track:
                        target_track = self.main_window.selected_track
                    elif self.audio_engine.tracks:
                        target_track = self.audio_engine.tracks[0]
                        
                    if target_track:
                        from audio_engine import AudioItem
                        new_item = AudioItem(
                            start_sample=self.audio_engine.playhead_samples,
                            sample_rate=self.clipboard_clip["sample_rate"],
                            file_path=self.clipboard_clip["file_path"],
                            audio_data=self.clipboard_clip["audio_data"].copy() if self.clipboard_clip["audio_data"] is not None else None
                        )
                        new_item.offset_samples = self.clipboard_clip["offset_samples"]
                        new_item.length_samples = self.clipboard_clip["length_samples"]
                        
                        self.audio_engine.add_item_to_track(target_track, new_item)
                        
                        self.selected_item = new_item
                        self.selected_track_for_item = target_track
                        self.update_geometry()
                        self.update()
                        if hasattr(self, 'main_window') and self.main_window:
                            self.main_window.mark_project_dirty()
        else:
            if event.key() == Qt.Key.Key_C:
                if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                    self.main_window.undo_manager.push_state("Toggle Take Expansion")
                toggled_any = False
                for target in list(self.selected_items):
                    if getattr(target, "takes", None):
                        target.comp_expanded = not target.comp_expanded
                        toggled_any = True
                if self.selected_item and not toggled_any:
                    if getattr(self.selected_item, "takes", None):
                        self.selected_item.comp_expanded = not self.selected_item.comp_expanded
                        toggled_any = True
                if toggled_any:
                    self.update_geometry()
                    self.update()
                    if hasattr(self, 'main_window') and self.main_window:
                        self.main_window.mark_project_dirty()
                    return
            super().keyPressEvent(event)
            
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        zoom_factor = 1.15 if delta > 0 else 0.85
        self.zoomChanged.emit(zoom_factor)
        
    def get_track_height(self, track):
        base_h = self.lane_height
        max_takes = 0
        for item in track.items:
            if getattr(item, "comp_expanded", False) and getattr(item, "takes", None):
                max_takes = max(max_takes, len(item.takes))
        if max_takes > 0:
            sub_lane_h = 40
            return base_h + max_takes * sub_lane_h
        return base_h

    def get_track_top(self, target_track):
        y_curr = 0
        for track in self.audio_engine.tracks:
            if track == target_track:
                return y_curr
            y_curr += self.get_track_height(track)
        return 0

    def update_geometry(self):
        # Calculate maximum track bounds
        h = max(300, sum(self.get_track_height(t) for t in self.audio_engine.tracks))
        
        # Verify selected track is still valid
        if self.selected_track_for_item and self.selected_track_for_item not in self.audio_engine.tracks:
            self.selected_item = None
            self.selected_track_for_item = None
            
        # Calculate maximum time bound
        max_sec = 300.0  # Default 5 minutes
        for track in self.audio_engine.tracks:
            for item in track.items:
                if item.audio_data is not None or getattr(item, "takes", None):
                    item_end = (item.start_sample + item.length_samples) / item.sample_rate
                    max_sec = max(max_sec, item_end + 15.0)  # Pad with 15s
                
        # Make sure the width expands to cover the current playhead + padding
        sr = self.audio_engine.sample_rate if self.audio_engine else 44100
        playhead_sec = self.audio_engine.playhead_samples / sr
        max_sec = max(max_sec, playhead_sec + 30.0)
        
        w = int(max_sec * self.pixels_per_second)
        self.resize(w, h)
        
        # Keep track cards heights synchronized
        if hasattr(self, 'main_window') and self.main_window:
            for card in self.main_window.track_cards:
                h_target = self.get_track_height(card.track)
                if card.height() != h_target:
                    card.setFixedHeight(h_target)
                    
        self.update()
        
    def get_hover_state(self, x, y):
        """
        Returns (target, target_type, track, hover_type) where target_type is "item" or "arm_region"
        and hover_type can be "resize_left", "resize_right", "move", or None.
        """
        target_track = None
        y_curr = 0
        for track in self.audio_engine.tracks:
            h_track = self.get_track_height(track)
            if y_curr <= y < y_curr + h_track:
                target_track = track
                break
            y_curr += h_track
            
        if not target_track:
            return None, None, None, None
            
        track = target_track
        margin = 8
        
        with track.lock:
            items_copy = list(track.items)
            arm_regions_copy = list(getattr(track, "arm_regions", []))
            
        best_target = None
        best_target_type = None
        best_type = None
        min_dist = float('inf')
        
        # 1. Check audio items first
        for item in items_copy:
            if item.audio_data is None and not getattr(item, "takes", None):
                continue
            item_start_x = int((item.start_sample / item.sample_rate) * self.pixels_per_second)
            item_end_x = int(((item.start_sample + item.length_samples) / item.sample_rate) * self.pixels_per_second)
            
            # If expanded, hover on sub-lanes shouldn't trigger move/resize of parent item
            if getattr(item, "comp_expanded", False):
                # Only allow move/resize if hover is on the main track lane (y < y_curr + self.lane_height)
                if not (y_curr <= y < y_curr + self.lane_height):
                    continue

            if item_start_x - margin <= x <= item_end_x + margin:
                dist_left = abs(x - item_start_x)
                dist_right = abs(x - item_end_x)
                
                # Check near left edge
                if dist_left <= margin and dist_left < min_dist:
                    min_dist = dist_left
                    best_target = item
                    best_target_type = "item"
                    best_type = "resize_left"
                # Check near right edge
                elif dist_right <= margin and dist_right < min_dist:
                    min_dist = dist_right
                    best_target = item
                    best_target_type = "item"
                    best_type = "resize_right"
                # Inside item
                elif item_start_x < x < item_end_x:
                    if min_dist == float('inf'):
                        best_target = item
                        best_target_type = "item"
                        best_type = "move"
                        
        # 2. Check Auto-Arm regions if no item matched
        if best_target is None:
            sr = self.audio_engine.sample_rate
            for region in arm_regions_copy:
                reg_start_x = int((region[0] / sr) * self.pixels_per_second)
                reg_end_x = int((region[1] / sr) * self.pixels_per_second)
                
                if reg_start_x - margin <= x <= reg_end_x + margin:
                    dist_left = abs(x - reg_start_x)
                    dist_right = abs(x - reg_end_x)
                    
                    if dist_left <= margin and dist_left < min_dist:
                        min_dist = dist_left
                        best_target = region
                        best_target_type = "arm_region"
                        best_type = "resize_left"
                    elif dist_right <= margin and dist_right < min_dist:
                        min_dist = dist_right
                        best_target = region
                        best_target_type = "arm_region"
                        best_type = "resize_right"
                    elif reg_start_x < x < reg_end_x:
                        if min_dist == float('inf'):
                            best_target = region
                            best_target_type = "arm_region"
                            best_type = "move"
                            
        if best_target:
            return best_target, best_target_type, track, best_type
        return None, None, None, None

    def mousePressEvent(self, event):
        self.setFocus()  # Ensure widget gets focus so it can receive key events!
        x = event.position().x()
        y = event.position().y()
        click_sample = int((x / self.pixels_per_second) * self.audio_engine.sample_rate)
        
        # 1. Check if clicked on a take sub-lane (for swipe comping or de-selection)
        for track in self.audio_engine.tracks:
            y_track_top = self.get_track_top(track)
            for item in track.items:
                if item.takes and item.comp_expanded:
                    item_start = item.start_sample
                    item_end = item.start_sample + item.length_samples
                    if item_start <= click_sample <= item_end:
                        # Check which sub-lane
                        for take_idx in range(len(item.takes)):
                            sub_y_top = y_track_top + self.lane_height + take_idx * 40
                            if sub_y_top <= y <= sub_y_top + 40:
                                if event.button() == Qt.MouseButton.RightButton:
                                    if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                                        self.main_window.undo_manager.push_state("De-select Comp Region")
                                    # Start right-swipe comp de-selection!
                                    self.right_swipe_item = item
                                    self.right_swipe_take_idx = take_idx
                                    self.right_swipe_start_sample = click_sample
                                    self.drag_click_x = x
                                    self.setCursor(Qt.CursorShape.ForbiddenCursor)
                                    return
                                else:
                                    if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                                        self.main_window.undo_manager.push_state("Swipe Comp")
                                    # Start swipe comping!
                                    self.comp_swipe_item = item
                                    self.comp_swipe_take_idx = take_idx
                                    self.comp_swipe_start_sample = click_sample
                                    self.drag_click_x = x
                                    self.setCursor(Qt.CursorShape.IBeamCursor)
                                    return
                                    
        # 2. Check if clicked on any expand/collapse "C" button of a Take Folder
        for track in self.audio_engine.tracks:
            y_track_top = self.get_track_top(track)
            for item in track.items:
                if item.takes:
                    start_x = int((item.start_sample / item.sample_rate) * self.pixels_per_second)
                    # Coordinates of C button: start_x + 4 to start_x + 22, and anywhere vertically in the main track lane
                    if (start_x + 4 <= x <= start_x + 22) and (y_track_top <= y <= y_track_top + self.lane_height):
                        if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                            self.main_window.undo_manager.push_state("Toggle Take Expansion")
                        item.comp_expanded = not item.comp_expanded
                        self.update_geometry()
                        self.update()
                        if hasattr(self, 'main_window') and self.main_window:
                            self.main_window.mark_project_dirty()
                        return
                        
        # 3. Check if right button to start timeline deletion drag (on main track lane)
        if event.button() == Qt.MouseButton.RightButton:
            if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                self.main_window.undo_manager.push_state("Remove Clip Portion")
            self.right_drag_active = True
            self.right_drag_start_x = x
            self.right_drag_current_x = x
            self.right_drag_start_sample = click_sample
            
            # Find which track we clicked on
            y_curr = 0
            self.right_drag_track = None
            for track in self.audio_engine.tracks:
                h_track = self.get_track_height(track)
                if y_curr <= y < y_curr + h_track:
                    self.right_drag_track = track
                    break
                y_curr += h_track
            self.update()
            return

        target, target_type, track, hover_type = self.get_hover_state(x, y)
        
        # Emit track selection even if clicked on empty space
        y_curr = 0
        selected_idx = 0
        for idx, t in enumerate(self.audio_engine.tracks):
            h_track = self.get_track_height(t)
            if y_curr <= y < y_curr + h_track:
                selected_idx = idx
                break
            y_curr += h_track
        if selected_idx < len(self.audio_engine.tracks):
            self.trackSelected.emit(selected_idx)
            
        if target and track:
            if hasattr(self, 'main_window') and hasattr(self.main_window, 'undo_manager'):
                action = "Resize Clip" if hover_type in ("resize_left", "resize_right") else "Move Clip"
                self.main_window.undo_manager.push_state(action)
            modifiers = event.modifiers()
            if not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
                self.selected_items.clear()
            self.selected_items.add(target)
            
            self.selected_item = target
            self.selected_target_type = target_type
            self.selected_track_for_item = track
            
            self.active_drag_item = target
            self.active_drag_target_type = target_type
            self.drag_track = track
            self.active_drag_mode = hover_type
            
            sample_rate = self.audio_engine.sample_rate
            
            # Store initial states
            self.drag_click_x = x
            if target_type == "item":
                self.drag_start_sample = target.start_sample
                self.drag_offset_samples = target.offset_samples
                self.drag_length_samples = target.length_samples
                self.drag_offset_samples_click = click_sample - target.start_sample
            else: # arm_region
                self.drag_start_sample = target[0]
                self.drag_length_samples = target[1] - target[0]
                self.drag_offset_samples_click = click_sample - target[0]
            
            if hover_type in ("resize_left", "resize_right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif hover_type == "move":
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        else:
            self.selected_items.clear()
            self.selected_item = None
            self.selected_target_type = None
            self.selected_track_for_item = None
            self.active_drag_item = None
            self.active_drag_target_type = None
            self.active_drag_mode = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
            # Start box select tracking
            self.box_select_start = event.position()
            self.box_select_current = event.position()
            
            # Set playhead position on empty lane
            time_seconds = max(0.0, x / self.pixels_per_second)
            self.timeClicked.emit(time_seconds)
            self.update()
            
    def apply_comp_range(self, item, start_s, end_s, take_idx):
        new_ranges = []
        for r_start, r_end, r_take in item.comp_ranges:
            if r_end <= start_s or r_start >= end_s:
                # No overlap
                new_ranges.append([r_start, r_end, r_take])
            else:
                # Overlap exists
                if r_start < start_s:
                    new_ranges.append([r_start, start_s, r_take])
                if r_end > end_s:
                    new_ranges.append([end_s, r_end, r_take])
        
        new_ranges.append([start_s, end_s, take_idx])
        new_ranges.sort(key=lambda r: r[0])
        
        # Merge adjacent ranges with same take_idx
        merged = []
        for r in new_ranges:
            if not merged:
                merged.append(r)
            else:
                prev = merged[-1]
                if prev[2] == r[2] and prev[1] == r[0]:
                    prev[1] = r[1]
                else:
                    merged.append(r)
        item.comp_ranges = merged
        item.update_cached_comp_data()

    def remove_comp_range(self, item, start_s, end_s):
        """Punches a hole in comp_ranges for [start_s, end_s], making it silent."""
        new_ranges = []
        for r_start, r_end, r_take in item.comp_ranges:
            if r_end <= start_s or r_start >= end_s:
                # No overlap
                new_ranges.append([r_start, r_end, r_take])
            else:
                # Overlap exists, keep the non-overlapping parts
                if r_start < start_s:
                    new_ranges.append([r_start, start_s, r_take])
                if r_end > end_s:
                    new_ranges.append([end_s, r_end, r_take])
        
        new_ranges.sort(key=lambda r: r[0])
        
        # Merge adjacent ranges with same take_idx
        merged = []
        for r in new_ranges:
            if not merged:
                merged.append(r)
            else:
                prev = merged[-1]
                if prev[2] == r[2] and prev[1] == r[0]:
                    prev[1] = r[1]
                else:
                    merged.append(r)
        item.comp_ranges = merged
        item.update_cached_comp_data()

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        
        # Handle right drag deletion
        if getattr(self, "right_drag_active", False):
            self.right_drag_current_x = x
            self.update()
            return
            
        # Handle active right swipe comp de-selection
        if getattr(self, 'right_swipe_item', None) is not None:
            current_s = int((x / self.pixels_per_second) * self.audio_engine.sample_rate)
            item = self.right_swipe_item
            start_s = min(self.right_swipe_start_sample, current_s)
            end_s = max(self.right_swipe_start_sample, current_s)
            
            # Constrain to item boundaries
            start_s = max(item.start_sample, start_s)
            end_s = min(item.start_sample + item.length_samples, end_s)
            
            if start_s < end_s:
                self.remove_comp_range(item, start_s, end_s)
                self.update()
            return
            
        # Handle active swipe comping
        if hasattr(self, 'comp_swipe_item') and self.comp_swipe_item is not None:
            current_s = int((x / self.pixels_per_second) * self.audio_engine.sample_rate)
            item = self.comp_swipe_item
            take_idx = self.comp_swipe_take_idx
            start_s = min(self.comp_swipe_start_sample, current_s)
            end_s = max(self.comp_swipe_start_sample, current_s)
            
            # Constrain to item boundaries
            start_s = max(item.start_sample, start_s)
            end_s = min(item.start_sample + item.length_samples, end_s)
            
            if start_s < end_s:
                self.apply_comp_range(item, start_s, end_s, take_idx)
                self.update()
            return

        if self.active_drag_item:
            sample_rate = self.audio_engine.sample_rate
            target_type = self.active_drag_target_type
            
            if self.active_drag_mode == "move":
                new_start = int((x / self.pixels_per_second) * sample_rate) - self.drag_offset_samples_click
                new_start = max(0, new_start)
                if target_type == "item":
                    with self.drag_track.lock:
                        self.active_drag_item.start_sample = new_start
                else: # arm_region
                    with self.drag_track.lock:
                        self.active_drag_item[0] = new_start
                        self.active_drag_item[1] = new_start + self.drag_length_samples
                    
                # Shift clip/region between tracks when dragging vertically
                target_track_idx = 0
                y_curr = 0
                for idx, t in enumerate(self.audio_engine.tracks):
                    h_track = self.get_track_height(t)
                    if y_curr <= y < y_curr + h_track:
                        target_track_idx = idx
                        break
                    y_curr += h_track
                target_track_idx = max(0, min(len(self.audio_engine.tracks) - 1, target_track_idx))
                target_track = self.audio_engine.tracks[target_track_idx]
                if target_track != self.drag_track:
                    if target_type == "item":
                        with self.drag_track.lock:
                            if self.active_drag_item in self.drag_track.items:
                                self.drag_track.items.remove(self.active_drag_item)
                        self.audio_engine.add_item_to_track(target_track, self.active_drag_item)
                    else: # arm_region
                        with self.drag_track.lock:
                            if self.active_drag_item in getattr(self.drag_track, "arm_regions", []):
                                self.drag_track.arm_regions.remove(self.active_drag_item)
                        with target_track.lock:
                            if not hasattr(target_track, "arm_regions"):
                                target_track.arm_regions = []
                            target_track.arm_regions.append(self.active_drag_item)
                    self.drag_track = target_track
                    self.selected_track_for_item = target_track
            
            elif self.active_drag_mode == "resize_left":
                timeline_end = self.drag_start_sample + self.drag_length_samples
                mouse_sample = int((x / self.pixels_per_second) * sample_rate)
                click_mouse_sample = int((self.drag_click_x / self.pixels_per_second) * sample_rate)
                delta_samples = mouse_sample - click_mouse_sample
                
                new_start = self.drag_start_sample + delta_samples
                new_start = max(0, new_start)
                
                # Minimum length of 50ms
                min_len = int(0.05 * sample_rate)
                max_allowed_start = timeline_end - min_len
                new_start = min(new_start, max_allowed_start)
                
                if target_type == "item":
                    actual_delta = new_start - self.drag_start_sample
                    new_offset = self.drag_offset_samples + actual_delta
                    
                    # Check bounds for new_offset
                    max_offset = (self.active_drag_item.audio_data.shape[1] if self.active_drag_item.audio_data is not None else self.active_drag_item.length_samples) - min_len
                    new_offset = max(0, min(new_offset, max_offset))
                    
                    actual_delta = new_offset - self.drag_offset_samples
                    new_start = self.drag_start_sample + actual_delta
                    new_length = timeline_end - new_start
                    
                    with self.drag_track.lock:
                        self.active_drag_item.start_sample = new_start
                        self.active_drag_item.offset_samples = new_offset
                        self.active_drag_item.length_samples = new_length
                else: # arm_region
                    with self.drag_track.lock:
                        self.active_drag_item[0] = new_start
                    
            elif self.active_drag_mode == "resize_right":
                mouse_sample = int((x / self.pixels_per_second) * sample_rate)
                click_mouse_sample = int((self.drag_click_x / self.pixels_per_second) * sample_rate)
                delta_samples = mouse_sample - click_mouse_sample
                
                new_length = self.drag_length_samples + delta_samples
                min_len = int(0.05 * sample_rate)
                if target_type == "item":
                    max_len = (self.active_drag_item.audio_data.shape[1] if self.active_drag_item.audio_data is not None else self.active_drag_item.length_samples) - self.active_drag_item.offset_samples
                    new_length = max(min_len, min(new_length, max_len))
                    with self.drag_track.lock:
                        self.active_drag_item.length_samples = new_length
                else: # arm_region
                    new_length = max(min_len, new_length)
                    with self.drag_track.lock:
                        self.active_drag_item[1] = self.drag_start_sample + new_length
                    
            self.update_geometry()
        elif self.box_select_start is not None:
            self.box_select_current = event.position()
            
            select_rect = QRectF(self.box_select_start, self.box_select_current).normalized()
            
            self.selected_items.clear()
            self.selected_item = None
            
            # Select items intersecting the selection rectangle
            y_curr = 0
            for track_idx, track in enumerate(self.audio_engine.tracks):
                h_track = self.get_track_height(track)
                y_top = y_curr + 5
                draw_h = self.lane_height - 10
                
                with track.lock:
                    items_copy = list(track.items)
                    
                for item in items_copy:
                    if item.audio_data is None and not getattr(item, "takes", None):
                        continue
                        
                    item_len = item.length_samples
                    start_x = int((item.start_sample / item.sample_rate) * self.pixels_per_second)
                    end_x = int(((item.start_sample + item_len) / item.sample_rate) * self.pixels_per_second)
                    item_width = max(2, end_x - start_x)
                    
                    item_rect = QRectF(start_x, y_top, item_width, draw_h)
                    if select_rect.intersects(item_rect):
                        self.selected_items.add(item)
                        # Set primary selected item for compatibility
                        self.selected_item = item
                        self.selected_target_type = "item"
                        self.selected_track_for_item = track
                y_curr += h_track
            self.update()
        else:
            # Hover cursor update
            target, target_type, track, hover_type = self.get_hover_state(x, y)
            if hover_type in ("resize_left", "resize_right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif hover_type == "move":
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
    def mouseReleaseEvent(self, event):
        if getattr(self, "right_drag_active", False):
            self.right_drag_active = False
            track = getattr(self, "right_drag_track", None)
            if track:
                sample_rate = self.audio_engine.sample_rate
                start_x = min(self.right_drag_start_x, self.right_drag_current_x)
                end_x = max(self.right_drag_start_x, self.right_drag_current_x)
                start_sample = int((start_x / self.pixels_per_second) * sample_rate)
                end_sample = int((end_x / self.pixels_per_second) * sample_rate)
                if start_sample < end_sample and (end_sample - start_sample) > 100:
                    self.remove_portions_from_track(track, start_sample, end_sample)
                    self._ignore_context_menu = True
            self.right_drag_track = None
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.mark_project_dirty()
            self.update()
            return

        if getattr(self, 'right_swipe_item', None) is not None:
            self.right_swipe_item.update_cached_comp_data()
            self.right_swipe_item = None
            self.right_swipe_take_idx = None
            self.right_swipe_start_sample = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.mark_project_dirty()
            self.update()
            return

        if hasattr(self, 'comp_swipe_item') and self.comp_swipe_item is not None:
            # If the drag span is tiny, treat it as a click to select that take entirely
            drag_dist = abs(event.position().x() - self.drag_click_x)
            if drag_dist < 3:
                self.comp_swipe_item.comp_ranges.clear()
                self.comp_swipe_item.active_take_index = self.comp_swipe_take_idx
            
            self.comp_swipe_item.update_cached_comp_data()
            self.comp_swipe_item = None
            self.comp_swipe_take_idx = None
            self.comp_swipe_start_sample = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.mark_project_dirty()
            self.update()
            return

        if self.active_drag_item:
            self.active_drag_item = None
            self.active_drag_target_type = None
            self.drag_track = None
            self.active_drag_mode = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.mark_project_dirty()
        elif self.box_select_start is not None:
            self.box_select_start = None
            self.box_select_current = None
            self.update()

    def contextMenuEvent(self, event):
        if getattr(self, "_ignore_context_menu", False):
            self._ignore_context_menu = False
            event.accept()
            return
            
        pos = event.pos()
        x = pos.x()
        y = pos.y()
        target, target_type, track, hover_type = self.get_hover_state(x, y)
        
        if target and target_type == "item":
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
            
            action_convert = QAction("Convert to Backing Track...", self)
            action_convert.triggered.connect(lambda: self.convert_clip_to_backing_track(target, track))
            menu.addAction(action_convert)
            
            menu.addSeparator()
            
            action_delete = QAction("Delete Clip", self)
            action_delete.triggered.connect(lambda: self.delete_specific_clip(target, track))
            menu.addAction(action_delete)
            
            menu.exec(event.globalPos())
            event.accept()
            
    def convert_clip_to_backing_track(self, target, track):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        from widgets.backing_track_manager import get_backing_tracks_dir
        
        default_name = "Backing Track"
        if target.file_path:
            default_name = os.path.splitext(os.path.basename(target.file_path))[0]
            
        new_name, ok = QInputDialog.getText(self, "Convert Clip to Backing Track", "Enter backing track name:", text=default_name)
        if ok and new_name.strip():
            dest_dir = get_backing_tracks_dir()
            dest_path = os.path.join(dest_dir, new_name.strip() + ".wav")
            
            if os.path.exists(dest_path):
                QMessageBox.warning(self, "Duplicate Name", "A backing track with this name already exists.")
                return
                
            try:
                # Extract the visible sliced/comped audio data
                slice_data = target.get_audio_data_slice(target.start_sample, target.length_samples)
                
                # Save to WAV
                from audio_engine import AudioItem
                temp_item = AudioItem(start_sample=0, sample_rate=target.sample_rate, audio_data=slice_data)
                temp_item.save_to_wav(dest_path)
                
                # Refresh Backing Track Manager UI
                if hasattr(self.main_window, 'backing_track_manager'):
                    self.main_window.backing_track_manager.refresh_list()
                    
                QMessageBox.information(self, "Success", f"Successfully converted clip to backing track:\n{new_name.strip() + '.wav'}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to convert clip to backing track:\n{e}")
                
    def delete_specific_clip(self, target, track):
        if hasattr(self.main_window, 'undo_manager'):
            self.main_window.undo_manager.push_state("Delete Clip")
        with track.lock:
            if target in track.items:
                track.items.remove(target)
        self.selected_items.clear()
        self.selected_item = None
        self.selected_target_type = None
        self.selected_track_for_item = None
        self.update_geometry()
        self.update()
        if hasattr(self.main_window, 'mark_project_dirty'):
            self.main_window.mark_project_dirty()

    def remove_portions_from_track(self, track, start_sample, end_sample):
        """
        Removes portions of audio clips on a track within [start_sample, end_sample].
        Splits, trims, or deletes clips that overlap the range.
        """
        with track.lock:
            original_items = list(track.items)
            new_items = []
            
            for item in original_items:
                item_start = item.start_sample
                item_end = item.start_sample + item.length_samples
                
                # Case 1: Clip is completely outside the delete range
                if item_end <= start_sample or item_start >= end_sample:
                    new_items.append(item)
                    
                # Case 2: Clip is completely inside the delete range
                elif item_start >= start_sample and item_end <= end_sample:
                    # Deleted completely
                    continue
                    
                # Case 3: Delete range splits the clip in two
                elif item_start < start_sample and item_end > end_sample:
                    # Left split
                    left_len = start_sample - item_start
                    left_item = self.clone_audio_item(item)
                    left_item.length_samples = left_len
                    left_item.update_cached_comp_data()
                    new_items.append(left_item)
                    
                    # Right split
                    right_start = end_sample
                    right_len = item_end - end_sample
                    right_offset = item.offset_samples + (end_sample - item_start)
                    
                    right_item = self.clone_audio_item(item)
                    right_item.start_sample = right_start
                    right_item.offset_samples = right_offset
                    right_item.length_samples = right_len
                    right_item.update_cached_comp_data()
                    new_items.append(right_item)
                    
                # Case 4: Delete range overlaps the left side of the clip
                elif item_start >= start_sample and item_start < end_sample < item_end:
                    shift = end_sample - item_start
                    item.start_sample = end_sample
                    item.offset_samples += shift
                    item.length_samples -= shift
                    item.update_cached_comp_data()
                    new_items.append(item)
                    
                # Case 5: Delete range overlaps the right side of the clip
                elif item_start < start_sample < item_end <= end_sample:
                    item.length_samples = start_sample - item_start
                    item.update_cached_comp_data()
                    new_items.append(item)
            
            track.items = new_items

    def clone_audio_item(self, item):
        from audio_engine import AudioItem
        new_item = AudioItem(
            start_sample=item.start_sample,
            sample_rate=item.sample_rate,
            file_path=item.file_path,
            audio_data=item.audio_data
        )
        new_item.offset_samples = item.offset_samples
        new_item.length_samples = item.length_samples
        new_item.takes = [self.clone_audio_item(t) for t in item.takes] if item.takes else []
        new_item.active_take_index = item.active_take_index
        new_item.comp_ranges = [r.copy() for r in item.comp_ranges] if item.comp_ranges else []
        new_item.comp_expanded = item.comp_expanded
        if hasattr(item, "_cached_comp_data"):
            new_item._cached_comp_data = item._cached_comp_data
        return new_item
            
    def get_last_clip_end_sample(self):
        max_end = 0
        for track in self.audio_engine.tracks:
            with track.lock:
                for item in track.items:
                    end_sample = item.start_sample + item.length_samples
                    if end_sample > max_end:
                        max_end = end_sample
        return max_end

    def setup_loop_region(self):
        if self.audio_engine.loop_enabled:
            self.audio_engine.loop_enabled = False
        else:
            sr = self.audio_engine.sample_rate if self.audio_engine else 44100
            last_clip_end = self.get_last_clip_end_sample()
            self.audio_engine.loop_start = 0
            if last_clip_end == 0:
                self.audio_engine.loop_end = int(5.0 * sr)
            else:
                self.audio_engine.loop_end = int(last_clip_end)
            self.audio_engine.loop_enabled = True
        self.update()
        if hasattr(self, 'ruler') and self.ruler:
            self.ruler.update()

    def mouseDoubleClickEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        target, target_type, track, hover_type = self.get_hover_state(x, y)
        is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        
        # Double-click Take Folder to expand/collapse
        if target and target_type == "item" and getattr(target, "takes", None):
            target.comp_expanded = not target.comp_expanded
            self.update_geometry()
            self.update()
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.mark_project_dirty()
            return

        if target is None and not is_shift:
            self.setup_loop_region()
            return
            
        # Double-click empty track lane space to import audio or create Auto-Arm zone
        y_curr = 0
        track_idx = 0
        for idx, t in enumerate(self.audio_engine.tracks):
            h_track = self.get_track_height(t)
            if y_curr <= y < y_curr + h_track:
                track_idx = idx
                break
            y_curr += h_track
            
        if track_idx < len(self.audio_engine.tracks):
            track = self.audio_engine.tracks[track_idx]
            sample_rate = self.audio_engine.sample_rate
            start_sample = int((x / self.pixels_per_second) * sample_rate)
            
            # If Shift is held down, create an Auto-Arm Zone!
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Default 5 seconds
                end_sample = start_sample + int(5.0 * sample_rate)
                if not hasattr(track, "arm_regions"):
                    track.arm_regions = []
                with track.lock:
                    region = [start_sample, end_sample]
                    track.arm_regions.append(region)
                self.selected_item = region
                self.selected_target_type = "arm_region"
                self.selected_track_for_item = track
                self.update_geometry()
                self.update()
                if hasattr(self, 'main_window') and self.main_window:
                    self.main_window.mark_project_dirty()
                return
            
            # Select file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Audio File",
                "",
                "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a *.wma *.aiff *.aif);;All Files (*)"
            )
            if file_path:
                # Create and add item
                item = AudioItem(start_sample, sample_rate, file_path=file_path)
                if item.audio_data is not None:
                    # Copy WAV next to project later, or keep path
                    self.audio_engine.add_item_to_track(track, item)
                    track.update_pedalboard(self.audio_engine.sample_rate)
                    self.update_geometry()
                    if hasattr(self, 'main_window') and self.main_window:
                        self.main_window.mark_project_dirty()
                        
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            w = self.width()
            h = self.height()
            
            # 1. Alternate Track Lane backgrounds
            tracks = self.audio_engine.tracks
            y_curr = 0
            for idx, track in enumerate(tracks):
                h_track = self.get_track_height(track)
                bg_color = QColor("#0b0b0c") if idx % 2 == 0 else QColor("#050505")
                painter.fillRect(0, y_curr, w, h_track, bg_color)
                
                # Draw lane bottom border
                painter.setPen(QPen(QColor("#222225"), 1))
                painter.drawLine(0, y_curr + h_track - 1, w, y_curr + h_track - 1)
                y_curr += h_track
                
            # 2. Draw Items & Waveforms
            y_pos = 0
            for t_idx, track in enumerate(tracks):
                h_track = self.get_track_height(track)
                y_top = y_pos + 5
                draw_h = self.lane_height - 10
                y_center = y_pos + int(self.lane_height / 2)
                
                # Draw Auto-Arm Zones for this track first (as a background overlay)
                with track.lock:
                    arm_regions_copy = list(getattr(track, "arm_regions", []))
                for region in arm_regions_copy:
                    sr = self.audio_engine.sample_rate
                    start_x = int((region[0] / sr) * self.pixels_per_second)
                    end_x = int((region[1] / sr) * self.pixels_per_second)
                    region_width = max(2, end_x - start_x)
                    
                    rect = QRectF(start_x, y_top, region_width, draw_h)
                    is_selected = (self.selected_item == region or region in self.selected_items)
                    
                    if is_selected:
                        painter.setBrush(QBrush(QColor(255, 68, 68, 85)))
                        painter.setPen(QPen(QColor(255, 68, 68), 2, Qt.PenStyle.DashLine))
                    else:
                        painter.setBrush(QBrush(QColor(255, 68, 68, 45)))
                        painter.setPen(QPen(QColor(255, 68, 68, 180), 1.2, Qt.PenStyle.DashLine))
                        
                    painter.drawRoundedRect(rect, 4, 4)
                    
                    font = QFont("Consolas", 8, QFont.Weight.Bold)
                    painter.setFont(font)
                    painter.setPen(QColor(255, 170, 170))
                    painter.drawText(start_x + 6, y_top + draw_h - 10, "Auto-Arm Zone")
                
                with track.lock:
                    items_copy = list(track.items)
                    
                # Prepare live recording item if track is recording
                is_recording = (self.audio_engine.play_state == "recording")
                if not is_recording and self.live_recording_cache:
                    self.live_recording_cache.clear()
                    
                live_item = None
                has_arm_regions = len(getattr(track, "arm_regions", [])) > 0
                if is_recording and (track.armed or has_arm_regions):
                    buffers_copy = None
                    with self.audio_engine.lock:
                        buffers = self.audio_engine.recording_buffers.get(track.track_id)
                        if buffers:
                            buffers_copy = list(buffers)
                            
                    if buffers_copy:
                        try:
                            cache = self.live_recording_cache.setdefault(track.track_id, {
                                "buffers_count": 0,
                                "cached_array": np.zeros(0, dtype=np.float32)
                            })
                            
                            if len(buffers_copy) > cache["buffers_count"]:
                                new_buffers = buffers_copy[cache["buffers_count"]:]
                                if new_buffers:
                                    new_data = np.concatenate(new_buffers)
                                    cache["cached_array"] = np.concatenate([cache["cached_array"], new_data])
                                cache["buffers_count"] = len(buffers_copy)
                                
                            live_data = cache["cached_array"]
                            live_audio_data = np.reshape(live_data, (1, -1))
                            live_item = AudioItem(
                                start_sample=self.audio_engine.recording_start_sample,
                                sample_rate=self.audio_engine.sample_rate,
                                file_path=None,
                                audio_data=live_audio_data
                            )
                        except Exception as e:
                            print(f"Error drawing live recording: {e}")
                                
                items_to_draw = list(items_copy)
                if live_item is not None:
                    items_to_draw.append(live_item)
                    
                for item in items_to_draw:
                    if item.audio_data is None and not getattr(item, "takes", None):
                        continue
                        
                    is_live = (item is live_item)
                    
                    # Calculate coordinates
                    item_len = item.length_samples
                    start_x = int((item.start_sample / item.sample_rate) * self.pixels_per_second)
                    end_x = int(((item.start_sample + item_len) / item.sample_rate) * self.pixels_per_second)
                    item_width = max(2, end_x - start_x)
                    
                    # Draw clip block background
                    clip_rect = QRectF(start_x, y_top, item_width, draw_h)
                    if is_live:
                        painter.setBrush(QBrush(QColor("#2a0a0d")))
                        painter.setPen(QPen(QColor("#ff0033"), 1.0))
                    elif item in self.selected_items or item == self.selected_item:
                        painter.setBrush(QBrush(QColor("#000000")))
                        painter.setPen(QPen(QColor("#ffffff"), 1.5))
                    else:
                        painter.setBrush(QBrush(QColor("#111112")))
                        painter.setPen(QPen(QColor("#222225"), 1.0))
                    painter.drawRoundedRect(clip_rect, 4, 4)
                    
                    # Draw WAV Filename text label
                    font = QFont("Consolas", 8, QFont.Weight.Bold)
                    painter.setFont(font)
                    if is_live:
                        painter.setPen(QColor("#ff0033"))
                        name_str = "Recording Live..."
                    elif getattr(item, "takes", None):
                        painter.setPen(QColor("#ffffff"))
                        name_str = f"Take Folder ({len(item.takes)} Takes)"
                    else:
                        painter.setPen(QColor("#88888c"))
                        name_str = os.path.basename(item.file_path) if item.file_path else "Recorded Clip"
                    
                    # Clip text to container width
                    metrics = painter.fontMetrics()
                    text_x = start_x + (26 if getattr(item, "takes", None) else 5)
                    elided_str = metrics.elidedText(name_str, Qt.TextElideMode.ElideRight, int(item_width - (text_x - start_x) - 5))
                    painter.drawText(text_x, y_top + 12, elided_str)
                    
                    # Draw Expand/Collapse Button [C]
                    if getattr(item, "takes", None):
                        btn_rect = QRectF(start_x + 4, y_top + 4, 18, 18)
                        painter.setBrush(QBrush(QColor("#ffffff") if item.comp_expanded else QColor("#222225")))
                        painter.setPen(QPen(QColor("#000000") if item.comp_expanded else QColor("#ffffff"), 1.0))
                        painter.drawRoundedRect(btn_rect, 2, 2)
                        
                        painter.setPen(QColor("#000000") if item.comp_expanded else QColor("#ffffff"))
                        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "C")
                    
                    # Get waveform channel data
                    ch_data = None
                    if getattr(item, "takes", None):
                        if not hasattr(item, "_cached_comp_data") or item._cached_comp_data is None:
                            item.update_cached_comp_data()
                        if item._cached_comp_data is not None:
                            ch_data = item._cached_comp_data[0]
                    elif item.audio_data is not None:
                        ch_data = item.audio_data[0]
                        
                    # Draw Waveform Outline
                    if ch_data is not None:
                        if is_live:
                            painter.setPen(QPen(QColor("#ff0033"), 1.0))
                        else:
                            painter.setPen(QPen(QColor("#e2e2e5"), 1.0))
                        
                        # Sub-sample waveform for speed
                        half_h = int(draw_h / 2.5)
                        limit = min(item.offset_samples + item.length_samples, ch_data.shape[0])
                        samples_per_px = item.length_samples / max(1, item_width)
                        
                        for px in range(item_width):
                            px_start = item.offset_samples + int(px * samples_per_px)
                            px_end = item.offset_samples + int((px + 1) * samples_per_px)
                            px_start = min(px_start, limit)
                            px_end = min(px_end, limit)
                            
                            if px_start >= limit:
                                break
                            chunk = ch_data[px_start:px_end]
                            if len(chunk) == 0:
                                continue
                                
                            ch_min = np.min(chunk)
                            ch_max = np.max(chunk)
                            
                            line_x = start_x + px
                            line_y_top = y_center + int(ch_min * half_h)
                            line_y_bottom = y_center + int(ch_max * half_h)
                            if line_y_top == line_y_bottom:
                                line_y_bottom += 1
                            painter.drawLine(line_x, line_y_top, line_x, line_y_bottom)
                            
                    # Draw take sub-lanes if expanded
                    if getattr(item, "comp_expanded", False) and getattr(item, "takes", None):
                        for take_idx, take in enumerate(item.takes):
                            sub_y_top = y_pos + self.lane_height + take_idx * 40
                            sub_draw_h = 36
                            sub_y_center = sub_y_top + 18
                            
                            sub_start_x = int((take.start_sample / take.sample_rate) * self.pixels_per_second)
                            sub_end_x = int(((take.start_sample + take.length_samples) / take.sample_rate) * self.pixels_per_second)
                            sub_width = max(2, sub_end_x - sub_start_x)
                            
                            # Draw sub-lane block background
                            sub_rect = QRectF(sub_start_x, sub_y_top, sub_width, sub_draw_h)
                            painter.setBrush(QBrush(QColor("#111112")))
                            painter.setPen(QPen(QColor("#222225"), 1.0))
                            painter.drawRoundedRect(sub_rect, 2, 2)
                            
                            # Draw take name
                            font_sub = QFont("Consolas", 8)
                            painter.setFont(font_sub)
                            painter.setPen(QColor("#88888c"))
                            take_name = f"Take {take_idx + 1}"
                            if take.file_path:
                                take_name += f" ({os.path.basename(take.file_path)})"
                            elided_take_name = painter.fontMetrics().elidedText(take_name, Qt.TextElideMode.ElideRight, int(sub_width - 10))
                            painter.drawText(sub_start_x + 5, sub_y_top + 10, elided_take_name)
                            
                            # Draw take waveform
                            if take.audio_data is not None:
                                take_ch_data = take.audio_data[0]
                                take_limit = min(take.offset_samples + take.length_samples, take_ch_data.shape[0])
                                take_samples_per_px = take.length_samples / max(1, sub_width)
                                if not item.comp_ranges:
                                    is_active_const = (item.active_take_index == take_idx)
                                    has_ranges = False
                                else:
                                    has_ranges = True
                                    ranges_list = item.comp_ranges
                                    current_range_idx = 0
                                    num_ranges = len(ranges_list)
                                    
                                for px in range(sub_width):
                                    px_start = take.offset_samples + int(px * take_samples_per_px)
                                    px_end = take.offset_samples + int((px + 1) * take_samples_per_px)
                                    px_start = min(px_start, take_limit)
                                    px_end = min(px_end, take_limit)
                                    
                                    if px_start >= take_limit:
                                        break
                                    chunk = take_ch_data[px_start:px_end]
                                    if len(chunk) == 0:
                                        continue
                                        
                                    ch_min = np.min(chunk)
                                    ch_max = np.max(chunk)
                                    
                                    # Check if active
                                    if not has_ranges:
                                        is_active = is_active_const
                                    else:
                                        abs_sample = take.start_sample + px_start - take.offset_samples
                                        is_active = False
                                        while current_range_idx < num_ranges and ranges_list[current_range_idx][1] <= abs_sample:
                                            current_range_idx += 1
                                        if current_range_idx < num_ranges:
                                            r_start, r_end, r_take = ranges_list[current_range_idx]
                                            if r_start <= abs_sample < r_end:
                                                is_active = (r_take == take_idx)
                                                
                                    if is_active:
                                        painter.setPen(QPen(QColor("#ffffff"), 1.0))
                                    else:
                                        painter.setPen(QPen(QColor("#444448"), 1.0))
                                        
                                    line_x = sub_start_x + px
                                    line_y_top = sub_y_center + int(ch_min * (sub_draw_h / 2.5))
                                    line_y_bottom = sub_y_center + int(ch_max * (sub_draw_h / 2.5))
                                    if line_y_top == line_y_bottom:
                                        line_y_bottom += 1
                                    painter.drawLine(line_x, line_y_top, line_x, line_y_bottom)
                                    
                                    if is_active:
                                        # Draw a highlighted subtle overlay line
                                        painter.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
                                        painter.drawLine(line_x, sub_y_top + 1, line_x, sub_y_top + sub_draw_h - 1)
                                        
                y_pos += h_track
                
            # 2.5 Draw Loop Region Shading
            sr = self.audio_engine.sample_rate if self.audio_engine else 44100
            if self.audio_engine.loop_enabled and self.audio_engine.loop_end > self.audio_engine.loop_start:
                loop_start_x = int((self.audio_engine.loop_start / sr) * self.pixels_per_second)
                loop_end_x = int((self.audio_engine.loop_end / sr) * self.pixels_per_second)
                painter.fillRect(loop_start_x, 0, loop_end_x - loop_start_x, h, QColor(255, 255, 255, 8))
                pen = QPen(QColor(255, 255, 255, 60), 1.2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(loop_start_x, 0, loop_start_x, h)
                painter.drawLine(loop_end_x, 0, loop_end_x, h)

            # 3. Draw Vertical Playhead Cursor Line
            playhead_sec = self.audio_engine.playhead_samples / sr
            playhead_x = int(playhead_sec * self.pixels_per_second)
            
            painter.setPen(QPen(QColor("#ff0033"), 1.2))
            painter.drawLine(playhead_x, 0, playhead_x, h)
            
            # 4. Draw Box Selection Rectangle
            if self.box_select_start is not None and self.box_select_current is not None:
                select_rect = QRectF(self.box_select_start, self.box_select_current).normalized()
                # Draw filled transparent rectangle
                painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
                # Draw white dashed border
                painter.setPen(QPen(QColor("#ffffff"), 1.0, Qt.PenStyle.DashLine))
                painter.drawRect(select_rect)
                
            # 5. Draw Right Drag Deletion Region
            if getattr(self, "right_drag_active", False) and getattr(self, "right_drag_track", None) is not None:
                track = self.right_drag_track
                y_track_top = self.get_track_top(track)
                h_track = self.get_track_height(track)
                start_x = min(self.right_drag_start_x, self.right_drag_current_x)
                end_x = max(self.right_drag_start_x, self.right_drag_current_x)
                
                painter.fillRect(int(start_x), int(y_track_top), int(end_x - start_x), int(h_track), QColor(255, 0, 0, 45))
                painter.setPen(QPen(QColor(255, 0, 0, 180), 1.0, Qt.PenStyle.DashLine))
                painter.drawRect(int(start_x), int(y_track_top), int(end_x - start_x), int(h_track))
        finally:
            painter.end()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def import_files_at_pos(self, x, y, urls):
        sample_rate = self.audio_engine.sample_rate
        start_sample = max(0, int((x / self.pixels_per_second) * sample_rate))
        
        # Calculate track_idx with variable heights
        y_curr = 0
        track_idx = 0
        for idx, t in enumerate(self.audio_engine.tracks):
            h_track = self.get_track_height(t)
            if y_curr <= y < y_curr + h_track:
                track_idx = idx
                break
            y_curr += h_track
        
        audio_extensions = ('.wav', '.mp3', '.flac', '.ogg', '.m4a', '.wma', '.aiff', '.aif')
        audio_files = [url.toLocalFile() for url in urls if url.toLocalFile().lower().endswith(audio_extensions)]
        if not audio_files:
            return
            
        # If dropping below existing tracks, create a new track
        if track_idx >= len(self.audio_engine.tracks):
            track = self.audio_engine.add_track("Imported Track")
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.refresh_track_cards()
        else:
            track = self.audio_engine.tracks[track_idx]
            
        for file_path in audio_files:
            if os.path.exists(file_path):
                # Create and load AudioItem
                item = AudioItem(start_sample, sample_rate, file_path=file_path)
                if item.audio_data is not None:
                    # Copy WAV next to project later, or keep path
                    self.audio_engine.add_item_to_track(track, item)
                    track.update_pedalboard(self.audio_engine.sample_rate)
                    
        self.update_geometry()
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window.mark_project_dirty()

    def dropEvent(self, event):
        pos = get_event_position(event)
        self.import_files_at_pos(pos.x(), pos.y(), event.mimeData().urls())
        event.acceptProposedAction()


class TimelineScrollArea(QScrollArea):
    """Custom QScrollArea to handle drag and drop and forward events to the lanes widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        lanes = self.widget()
        if lanes and hasattr(lanes, 'import_files_at_pos'):
            pos = get_event_position(event)
            pos_in_lanes = lanes.mapFrom(self, pos)
            lanes.import_files_at_pos(pos_in_lanes.x(), pos_in_lanes.y(), event.mimeData().urls())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class TimelineScrollContainer(QWidget):
    """Integrates the ruler, lanes scrollarea, and coordinates scroll updates."""
    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self.audio_engine = audio_engine
        self.main_window = parent
        self.pixels_per_second = 60.0
        self.setAcceptDrops(True)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 1. Transport Toolbar above the Ruler
        self.toolbar = QWidget()
        self.toolbar.setObjectName("TimelineToolbar")
        self.toolbar.setFixedHeight(31)
        self.toolbar.setStyleSheet("""
            QWidget#TimelineToolbar {
                background-color: #000000;
                border-bottom: 1px solid #222225;
            }
            QPushButton#TransportButton {
                background-color: #0b0b0c;
                border: 1px solid #222225;
                border-radius: 4px;
                padding: 4px 6px;
                min-width: 28px;
                min-height: 22px;
            }
            QPushButton#TransportButton:hover {
                background-color: #1a1a1c;
                border-color: #444448;
            }
        """)
        
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(10, 4, 10, 4)
        tb_layout.setSpacing(8)
        
        # Resolve paths to public/icons
        from theme_utils import get_resource_path
        
        icon_stop = QIcon(get_resource_path("public/icons/stop.svg"))
        icon_play = QIcon(get_resource_path("public/icons/play.svg"))
        icon_pause = QIcon(get_resource_path("public/icons/pause.svg"))
        icon_record = QIcon(get_resource_path("public/icons/record.svg"))
        icon_prev = QIcon(get_resource_path("public/icons/previous.svg"))
        icon_ff = QIcon(get_resource_path("public/icons/fastforward.svg"))
        
        icon_size = QSize(12, 12)
        
        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(icon_prev)
        self.btn_prev.setIconSize(icon_size)
        self.btn_prev.setObjectName("TransportButton")
        self.btn_prev.setToolTip("Previous / Go to Start")
        if self.main_window:
            self.btn_prev.clicked.connect(self.main_window.on_transport_stop)
        tb_layout.addWidget(self.btn_prev)
        
        self.btn_stop = QPushButton()
        self.btn_stop.setIcon(icon_stop)
        self.btn_stop.setIconSize(icon_size)
        self.btn_stop.setObjectName("TransportButton")
        self.btn_stop.setToolTip("Stop")
        if self.main_window:
            self.btn_stop.clicked.connect(self.main_window.on_transport_stop)
        tb_layout.addWidget(self.btn_stop)
        
        # Store icons on the container so they can be switched dynamically
        self.icon_play = icon_play
        self.icon_pause = icon_pause
        
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setIcon(icon_play)
        self.btn_play_pause.setIconSize(icon_size)
        self.btn_play_pause.setObjectName("TransportButton")
        self.btn_play_pause.setToolTip("Play")
        if self.main_window:
            self.btn_play_pause.clicked.connect(self.main_window.toggle_play_pause)
        tb_layout.addWidget(self.btn_play_pause)
        
        self.btn_ff = QPushButton()
        self.btn_ff.setIcon(icon_ff)
        self.btn_ff.setIconSize(QSize(18, 18))
        self.btn_ff.setObjectName("TransportButton")
        self.btn_ff.setToolTip("Fast Forward to End")
        if self.main_window:
            self.btn_ff.clicked.connect(self.main_window.on_fast_forward)
        tb_layout.addWidget(self.btn_ff)
        
        self.btn_record = QPushButton()
        self.btn_record.setIcon(icon_record)
        self.btn_record.setIconSize(icon_size)
        self.btn_record.setObjectName("TransportButton")
        self.btn_record.setToolTip("Record")
        if self.main_window:
            self.btn_record.clicked.connect(self.main_window.toggle_record)
        tb_layout.addWidget(self.btn_record)
        
        tb_layout.addStretch()
        
        self.lbl_time = QLabel("0:00.00")
        self.lbl_time.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.lbl_time.setStyleSheet("color: #e0e0e0; padding-right: 10px;")
        tb_layout.addWidget(self.lbl_time)
        
        layout.addWidget(self.toolbar)
        
        # 2. Ruler
        self.ruler = TimeRulerWidget(self.audio_engine, self)
        self.ruler.set_zoom(self.pixels_per_second)
        layout.addWidget(self.ruler)
        
        # 3. Scroll area containing the track lanes
        self.scroll_area = TimelineScrollArea(self)
        self.scroll_area.setObjectName("TimelineScrollArea")
        self.scroll_area.setWidgetResizable(False)  # Let Lanes Widget set its size
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.lanes = TimelineLanesWidget(self.audio_engine, self.scroll_area)
        self.lanes.main_window = self.main_window
        self.lanes.set_zoom(self.pixels_per_second)
        self.lanes.ruler = self.ruler
        self.ruler.lanes = self.lanes
        self.scroll_area.setWidget(self.lanes)
        layout.addWidget(self.scroll_area)
        
        # 4. Signals connections
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self.ruler.set_scroll_offset)
        
        self.ruler.timeClicked.connect(self.set_playhead_pos)
        self.ruler.zoomChanged.connect(self.zoom_horizontal)
        
        self.lanes.timeClicked.connect(self.set_playhead_pos)
        self.lanes.zoomChanged.connect(self.zoom_horizontal)
        
        self.lanes.update_geometry()
        
        self.setStyleSheet("""
            QScrollArea#TimelineScrollArea {
                background-color: #050505;
            }
        """)
        
    def set_playhead_pos(self, time_seconds):
        sr = self.audio_engine.sample_rate if self.audio_engine else 44100
        self.audio_engine.playhead_samples = int(time_seconds * sr)
        self.ruler.update()
        self.lanes.update()
        
    def zoom_horizontal(self, zoom_factor):
        new_zoom = self.pixels_per_second * zoom_factor
        new_zoom = max(5.0, min(new_zoom, 1200.0))  # Clamp zoom
        self.pixels_per_second = new_zoom
        
        # Propagate zoom to widgets
        self.ruler.set_zoom(new_zoom)
        self.lanes.set_zoom(new_zoom)
        self.lanes.update_geometry()
        
    def update_widgets(self):
        # 1. Update time counter text label
        sr = self.audio_engine.sample_rate if self.audio_engine else 44100
        sec = self.audio_engine.playhead_samples / sr
        minutes = int(sec // 60)
        secs = sec % 60
        self.lbl_time.setText(f"{minutes}:{secs:05.2f}")
        
        # 2. Check if timeline needs sizing updates
        self.lanes.update_geometry()
        
        # 3. Redraw playhead and lanes waveforms
        self.lanes.update()
        self.ruler.update()
        
        # 4. Handle auto-scrolling
        if self.audio_engine.play_state in ("playing", "recording"):
            playhead_x = int(sec * self.pixels_per_second)
            scrollbar = self.scroll_area.horizontalScrollBar()
            visible_width = self.scroll_area.viewport().width()
            scroll_x = scrollbar.value()
            
            if playhead_x > scroll_x + int(visible_width * 0.9) or playhead_x < scroll_x:
                target_scroll = max(0, playhead_x - int(visible_width * 0.1))
                scrollbar.setValue(target_scroll)
                
    def update_track_layout(self):
        # Re-initialize timeline geometry when tracks are added/removed
        self.lanes.update_geometry()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        # Map drop coordinates relative to self.lanes
        pos = get_event_position(event)
        pos_in_lanes = self.lanes.mapFrom(self, pos)
        self.lanes.import_files_at_pos(pos_in_lanes.x(), pos_in_lanes.y(), event.mimeData().urls())
        event.acceptProposedAction()
