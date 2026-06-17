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
        
    def set_scroll_offset(self, offset):
        self.scroll_offset = offset
        self.update()
        
    def set_zoom(self, pixels_per_second):
        self.pixels_per_second = pixels_per_second
        self.update()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_scrubbing = True
            self.update_cursor_pos(event.position().x())
            
    def mouseMoveEvent(self, event):
        if self.is_scrubbing:
            self.update_cursor_pos(event.position().x())
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
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
                    
            # Draw Playhead Cap (Red Triangle)
            sr = self.audio_engine.sample_rate if self.audio_engine else 44100
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
        Returns (item, track, hover_type) where hover_type can be:
        - "resize_left"
        - "resize_right"
        - "move"
        - None
        """
        track_idx = int(y // self.lane_height)
        if track_idx < 0 or track_idx >= len(self.audio_engine.tracks):
            return None, None, None
            
        track = self.audio_engine.tracks[track_idx]
        margin = 8
        
        with track.lock:
            items_copy = list(track.items)
            
        best_item = None
        best_type = None
        min_dist = float('inf')
        
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
                    best_item = item
                    best_type = "resize_left"
                # Check near right edge
                elif dist_right <= margin and dist_right < min_dist:
                    min_dist = dist_right
                    best_item = item
                    best_type = "resize_right"
                # Inside item
                elif item_start_x < x < item_end_x:
                    if min_dist == float('inf'):
                        best_item = item
                        best_type = "move"
                        
        if best_item:
            return best_item, track, best_type
        return None, None, None

    def mousePressEvent(self, event):
        self.setFocus()  # Ensure widget gets focus so it can receive key events!
        x = event.position().x()
        y = event.position().y()
        
        item, track, hover_type = self.get_hover_state(x, y)
        
        # Emit track selection even if clicked on empty space
        track_idx = int(y // self.lane_height)
        if track_idx < len(self.audio_engine.tracks):
            self.trackSelected.emit(track_idx)
            
        if item and track:
            self.selected_item = item
            self.selected_track_for_item = track
            
            self.active_drag_item = item
            self.drag_track = track
            self.active_drag_mode = hover_type
            
            sample_rate = self.audio_engine.sample_rate
            click_sample = int((x / self.pixels_per_second) * sample_rate)
            
            # Store initial states
            self.drag_click_x = x
            self.drag_start_sample = item.start_sample
            self.drag_offset_samples = item.offset_samples
            self.drag_length_samples = item.length_samples
            
            # For moving: click offset inside the item
            self.drag_offset_samples_click = click_sample - item.start_sample
            
            if hover_type in ("resize_left", "resize_right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif hover_type == "move":
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        else:
            self.selected_item = None
            self.selected_track_for_item = None
            self.active_drag_item = None
            self.active_drag_mode = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
            # Set playhead position on empty lane
            time_seconds = max(0.0, x / self.pixels_per_second)
            self.timeClicked.emit(time_seconds)
            self.update()
            
    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        
        if self.active_drag_item:
            sample_rate = self.audio_engine.sample_rate
            
            if self.active_drag_mode == "move":
                new_start = int((x / self.pixels_per_second) * sample_rate) - self.drag_offset_samples_click
                new_start = max(0, new_start)
                with self.drag_track.lock:
                    self.active_drag_item.start_sample = new_start
                    
                # Shift clip between tracks when dragging vertically
                target_track_idx = int(y // self.lane_height)
                target_track_idx = max(0, min(len(self.audio_engine.tracks) - 1, target_track_idx))
                target_track = self.audio_engine.tracks[target_track_idx]
                if target_track != self.drag_track:
                    with self.drag_track.lock:
                        if self.active_drag_item in self.drag_track.items:
                            self.drag_track.items.remove(self.active_drag_item)
                    with target_track.lock:
                        target_track.items.append(self.active_drag_item)
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
                
                actual_delta = new_start - self.drag_start_sample
                new_offset = self.drag_offset_samples + actual_delta
                
                # Check bounds for new_offset
                max_offset = self.active_drag_item.audio_data.shape[1] - min_len
                new_offset = max(0, min(new_offset, max_offset))
                
                actual_delta = new_offset - self.drag_offset_samples
                new_start = self.drag_start_sample + actual_delta
                new_length = timeline_end - new_start
                
                with self.drag_track.lock:
                    self.active_drag_item.start_sample = new_start
                    self.active_drag_item.offset_samples = new_offset
                    self.active_drag_item.length_samples = new_length
                    
            elif self.active_drag_mode == "resize_right":
                mouse_sample = int((x / self.pixels_per_second) * sample_rate)
                click_mouse_sample = int((self.drag_click_x / self.pixels_per_second) * sample_rate)
                delta_samples = mouse_sample - click_mouse_sample
                
                new_length = self.drag_length_samples + delta_samples
                min_len = int(0.05 * sample_rate)
                max_len = self.active_drag_item.audio_data.shape[1] - self.active_drag_item.offset_samples
                new_length = max(min_len, min(new_length, max_len))
                
                with self.drag_track.lock:
                    self.active_drag_item.length_samples = new_length
                    
            self.update_geometry()
        else:
            # Hover cursor update
            item, track, hover_type = self.get_hover_state(x, y)
            if hover_type in ("resize_left", "resize_right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif hover_type == "move":
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
    def mouseReleaseEvent(self, event):
        if self.active_drag_item:
            self.active_drag_item = None
            self.drag_track = None
            self.active_drag_mode = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
    def mouseDoubleClickEvent(self, event):
        # Double-click empty track lane space to import WAV
        y = event.position().y()
        track_idx = int(y // self.lane_height)
        if track_idx < len(self.audio_engine.tracks):
            track = self.audio_engine.tracks[track_idx]
            
            # Select file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Audio File (WAV)",
                "",
                "Audio Files (*.wav)"
            )
            if file_path:
                x = event.position().x()
                sample_rate = self.audio_engine.sample_rate
                start_sample = int((x / self.pixels_per_second) * sample_rate)
                
                # Create and add item
                item = AudioItem(start_sample, sample_rate, file_path=file_path)
                if item.audio_data is not None:
                    # Copy WAV next to project later, or keep path
                    with track.lock:
                        track.items.append(item)
                    track.update_pedalboard(self.audio_engine.sample_rate)
                    self.update_geometry()
                    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            if self.selected_item and self.selected_track_for_item:
                track = self.selected_track_for_item
                item = self.selected_item
                
                with track.lock:
                    if item in track.items:
                        track.items.remove(item)
                
                self.selected_item = None
                self.selected_track_for_item = None
                self.update_geometry()
                self.update()
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
            elif event.key() == Qt.Key.Key_V:
                if hasattr(self, 'clipboard_clip') and self.clipboard_clip is not None:
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
                        
                        with target_track.lock:
                            target_track.items.append(new_item)
                            
                        self.selected_item = new_item
                        self.selected_track_for_item = target_track
                        self.update_geometry()
                        self.update()
        else:
            super().keyPressEvent(event)
            
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        zoom_factor = 1.15 if delta > 0 else 0.85
        self.zoomChanged.emit(zoom_factor)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            w = self.width()
            h = self.height()
            
            # 1. Alternate Track Lane backgrounds
            tracks = self.audio_engine.tracks
            for idx in range(len(tracks)):
                y_pos = idx * self.lane_height
                bg_color = QColor("#0b0b0c") if idx % 2 == 0 else QColor("#050505")
                painter.fillRect(0, y_pos, w, self.lane_height, bg_color)
                
                # Draw lane bottom border
                painter.setPen(QPen(QColor("#222225"), 1))
                painter.drawLine(0, y_pos + self.lane_height - 1, w, y_pos + self.lane_height - 1)
                
            # 2. Draw Items & Waveforms
            for t_idx, track in enumerate(tracks):
                y_center = t_idx * self.lane_height + int(self.lane_height / 2)
                y_top = t_idx * self.lane_height + 5
                draw_h = self.lane_height - 10
                
                with track.lock:
                    items_copy = list(track.items)
                    
                # Prepare live recording item if track is recording
                is_recording = (self.audio_engine.play_state == "recording")
                live_item = None
                if is_recording and track.armed:
                    with self.audio_engine.lock:
                        buffers = self.audio_engine.recording_buffers.get(track.track_id)
                        if buffers and len(buffers) > 0:
                            try:
                                live_data = np.concatenate(buffers)
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
                    if item.audio_data is None:
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
                    elif item == self.selected_item:
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
                    else:
                        painter.setPen(QColor("#88888c"))
                        name_str = os.path.basename(item.file_path) if item.file_path else "Recorded Clip"
                    
                    # Clip text to container width
                    metrics = painter.fontMetrics()
                    elided_str = metrics.elidedText(name_str, Qt.TextElideMode.ElideRight, int(item_width - 10))
                    painter.drawText(start_x + 5, y_top + 12, elided_str)
                    
                    # Draw Waveform Outline
                    if is_live:
                        painter.setPen(QPen(QColor("#ff0033"), 1.0))
                    else:
                        painter.setPen(QPen(QColor("#e2e2e5"), 1.0))
                    
                    # Sub-sample waveform for speed
                    half_h = int(draw_h / 2.5)
                    # Compute min-max for each pixel column
                    # Map audio_data channel 0
                    ch_data = item.audio_data[0]
                    
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
                        
            # 3. Draw Vertical Playhead Cursor Line
            sr = self.audio_engine.sample_rate if self.audio_engine else 44100
            playhead_sec = self.audio_engine.playhead_samples / sr
            playhead_x = int(playhead_sec * self.pixels_per_second)
            
            painter.setPen(QPen(QColor("#ff0033"), 1.2))
            painter.drawLine(playhead_x, 0, playhead_x, h)
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
        track_idx = max(0, int(y // self.lane_height))
        
        wav_files = [url.toLocalFile() for url in urls if url.toLocalFile().lower().endswith('.wav')]
        if not wav_files:
            return
            
        # If dropping below existing tracks, create a new track
        if track_idx >= len(self.audio_engine.tracks):
            track = self.audio_engine.add_track("Imported Track")
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.refresh_track_cards()
        else:
            track = self.audio_engine.tracks[track_idx]
            
        for file_path in wav_files:
            if os.path.exists(file_path):
                # Create and load AudioItem
                item = AudioItem(start_sample, sample_rate, file_path=file_path)
                if item.audio_data is not None:
                    with track.lock:
                        track.items.append(item)
                    track.update_pedalboard(self.audio_engine.sample_rate)
                    
        self.update_geometry()

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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icons_dir = os.path.join(base_dir, "public", "icons")
        
        icon_stop = QIcon(os.path.join(icons_dir, "stop.svg"))
        icon_play = QIcon(os.path.join(icons_dir, "play.svg"))
        icon_pause = QIcon(os.path.join(icons_dir, "pause.svg"))
        icon_record = QIcon(os.path.join(icons_dir, "record.svg"))
        icon_prev = QIcon(os.path.join(icons_dir, "previous.svg"))
        icon_ff = QIcon(os.path.join(icons_dir, "fastforward.svg"))
        
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
