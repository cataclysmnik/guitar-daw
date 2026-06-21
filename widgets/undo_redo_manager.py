import os
import base64
from audio_engine import AudioItem, Track
import project_manager

class UndoRedoManager:
    def __init__(self, main_window, max_depth=50):
        self.main_window = main_window
        self.audio_engine = main_window.audio_engine
        self.max_depth = max_depth
        self.undo_stack = []
        self.redo_stack = []

    def get_project_snapshot(self):
        """
        Creates a deep metadata snapshot of the project state,
        keeping references to large numpy audio buffers instead of copying them.
        """
        snapshot = {
            "global_settings": {
                "main_volume": self.audio_engine.main_volume,
                "loop_enabled": getattr(self.audio_engine, "loop_enabled", False),
                "loop_start": getattr(self.audio_engine, "loop_start", 0),
                "loop_end": getattr(self.audio_engine, "loop_end", 0),
            },
            "tracks": [],
            "selected_track_id": self.audio_engine.selected_track_id
        }
        
        for track in self.audio_engine.tracks:
            # Serialize effects
            serialized_effects = []
            for fx in track.effects:
                try:
                    serialized_effects.append(project_manager.serialize_effect(fx))
                except Exception as e:
                    print(f"Error serializing effect in snapshot: {e}")
                    
            # Clone items recursively
            def clone_item(item):
                c = AudioItem(
                    start_sample=item.start_sample,
                    sample_rate=item.sample_rate,
                    file_path=item.file_path,
                    audio_data=item.audio_data # Ref same numpy array (no duplication)
                )
                c.offset_samples = item.offset_samples
                c.length_samples = item.length_samples
                c.active_take_index = item.active_take_index
                c.comp_expanded = item.comp_expanded
                c.comp_ranges = [list(r) for r in item.comp_ranges]
                c.takes = [clone_item(take) for take in item.takes]
                c.custom_name = getattr(item, "custom_name", None)
                if hasattr(item, '_cached_waveform'):
                    c._cached_waveform = item._cached_waveform
                if hasattr(item, '_cached_comp_waveform'):
                    c._cached_comp_waveform = item._cached_comp_waveform
                return c

            track_items = []
            with track.lock:
                for item in track.items:
                    track_items.append(clone_item(item))
            
            track_snapshot = {
                "track_id": track.track_id,
                "name": track.name,
                "volume": track.volume,
                "pan": track.pan,
                "mute": track.mute,
                "solo": track.solo,
                "armed": track.armed,
                "input_channel": track.input_channel,
                "arm_regions": list(getattr(track, "arm_regions", [])),
                "effects": serialized_effects,
                "items": track_items
            }
            snapshot["tracks"].append(track_snapshot)
            
        return snapshot

    def restore_project_snapshot(self, snapshot):
        """
        Restores the project state from a snapshot, optimizing to avoid
        unnecessary audio engine restarts and plugin reloads.
        """
        # Determine if we actually need to stop the stream.
        # We only stop/restart if track count/IDs changed or a VST plugin was added/removed/replaced.
        need_hard_reset = False
        
        current_track_ids = [t.track_id for t in self.audio_engine.tracks]
        snapshot_track_ids = [tr_data["track_id"] for tr_data in snapshot["tracks"]]
        
        if current_track_ids != snapshot_track_ids:
            need_hard_reset = True
        else:
            # Check if any VST plugin was added, removed, or changed paths
            for t, tr_data in zip(self.audio_engine.tracks, snapshot["tracks"]):
                if len(t.effects) != len(tr_data["effects"]):
                    need_hard_reset = True
                    break
                for fx, fx_data in zip(t.effects, tr_data["effects"]):
                    if fx.effect_type != fx_data["effect_type"]:
                        need_hard_reset = True
                        break
                    if fx.effect_type == "VST3":
                        existing_path = getattr(fx, "original_vst_path", "")
                        snap_path = fx_data.get("vst_path", "")
                        if existing_path != snap_path:
                            need_hard_reset = True
                            break
                if need_hard_reset:
                    break
                    
        from project_manager import EFFECT_CLASSES
        
        if need_hard_reset:
            was_running = self.audio_engine.is_running
            self.audio_engine.stop_stream()
            
            with self.audio_engine.lock:
                self.audio_engine.tracks.clear()
                for tr_data in snapshot["tracks"]:
                    track = Track(tr_data["track_id"], tr_data["name"])
                    track.volume = tr_data["volume"]
                    track.pan = tr_data["pan"]
                    track.mute = tr_data["mute"]
                    track.solo = tr_data["solo"]
                    track.armed = tr_data["armed"]
                    track.input_channel = tr_data["input_channel"]
                    track.arm_regions = tr_data["arm_regions"]
                    
                    effects_list = []
                    for fx_data in tr_data["effects"]:
                        try:
                            wrapper = project_manager.deserialize_effect(fx_data)
                            if wrapper:
                                effects_list.append(wrapper)
                        except Exception as e:
                            print(f"Error deserializing effect in hard restore: {e}")
                    track.effects = effects_list
                    track.update_pedalboard(self.audio_engine.sample_rate)
                    track.items = tr_data["items"]
                    self.audio_engine.tracks.append(track)
                    
                self.audio_engine.tracks_list_cache = list(self.audio_engine.tracks)
                
            if was_running:
                self.audio_engine.start_stream()
        else:
            # SOFT RESET: Maintain tracks and VSTs, just restore parameters and items.
            # This is instantaneous and does not disrupt the audio stream.
            with self.audio_engine.lock:
                for track, tr_data in zip(self.audio_engine.tracks, snapshot["tracks"]):
                    with track.lock:
                        track.name = tr_data["name"]
                        track.volume = tr_data["volume"]
                        track.pan = tr_data["pan"]
                        track.mute = tr_data["mute"]
                        track.solo = tr_data["solo"]
                        track.armed = tr_data["armed"]
                        track.input_channel = tr_data["input_channel"]
                        track.arm_regions = tr_data["arm_regions"]
                        track.items = tr_data["items"]
                        
                        # Reconcile/update effects parameters
                        for fx, fx_data in zip(track.effects, tr_data["effects"]):
                            fx.name = fx_data["name"]
                            fx.is_active = fx_data["is_active"]
                            fx.mix = fx_data.get("mix", 1.0)
                            fx.gain_db = fx_data.get("gain_db", 0.0)
                            
                            if fx.effect_type == "VST3" and "raw_state" in fx_data:
                                try:
                                    raw_state_b64 = fx_data.get("raw_state", "")
                                    if raw_state_b64:
                                        raw_state_bytes = base64.b64decode(raw_state_b64)
                                        if fx.effect.raw_state != raw_state_bytes:
                                            fx.effect.raw_state = raw_state_bytes
                                except Exception as e:
                                    print(f"Error restoring VST3 parameters: {e}")
                            elif fx.effect_type in EFFECT_CLASSES:
                                _, params = EFFECT_CLASSES[fx.effect_type]
                                for p in params:
                                    if p in fx_data["parameters"] and hasattr(fx.effect, p):
                                        new_val = fx_data["parameters"][p]
                                        if getattr(fx.effect, p) != new_val:
                                            setattr(fx.effect, p, new_val)
                                        
                    track.update_pedalboard(self.audio_engine.sample_rate)
                        
        globals_cfg = snapshot["global_settings"]
        self.audio_engine.main_volume = globals_cfg.get("main_volume", 0.0)
        self.audio_engine.loop_enabled = globals_cfg.get("loop_enabled", False)
        self.audio_engine.loop_start = globals_cfg.get("loop_start", 0)
        self.audio_engine.loop_end = globals_cfg.get("loop_end", 0)
        self.audio_engine.selected_track_id = snapshot.get("selected_track_id")
        return need_hard_reset

    def push_state(self, action_name="Action"):
        """Saves current state to the undo stack."""
        try:
            snapshot = self.get_project_snapshot()
            self.undo_stack.append((action_name, snapshot))
            self.redo_stack.clear()
            if len(self.undo_stack) > self.max_depth:
                self.undo_stack.pop(0)
        except Exception as e:
            print(f"Failed to push undo state: {e}")

    def undo(self):
        if not self.undo_stack:
            return
        action_name, snapshot = self.undo_stack.pop()
        # Save current state for redo
        current_state = self.get_project_snapshot()
        self.redo_stack.append((action_name, current_state))
        
        hard_reset = self.restore_project_snapshot(snapshot)
        self.refresh_ui(hard_reset)
        print(f"Undid: {action_name}")

    def redo(self):
        if not self.redo_stack:
            return
        action_name, snapshot = self.redo_stack.pop()
        # Save current state for undo
        current_state = self.get_project_snapshot()
        self.undo_stack.append((action_name, current_state))
        
        hard_reset = self.restore_project_snapshot(snapshot)
        self.refresh_ui(hard_reset)
        print(f"Redid: {action_name}")

    def refresh_ui(self, hard_reset=False):
        """Refreshes all GUI widgets to match the updated audio engine state."""
        if hard_reset:
            # 1. Update track cards in main window
            self.main_window.refresh_track_cards()
            
            # 2. Rebuild mixer
            if hasattr(self.main_window, 'mixer_widget') and self.main_window.mixer_widget:
                self.main_window.mixer_widget.rebuild()
                
            # 3. Update timeline
            if hasattr(self.main_window, 'timeline') and self.main_window.timeline:
                self.main_window.timeline.update_track_layout()
        else:
            # Soft UI update: update widget states in place (no deletion/creation)
            for card in self.main_window.track_cards:
                if hasattr(card, 'update_ui_states'):
                    card.update_ui_states()
                    
            if hasattr(self.main_window, 'mixer_widget') and self.main_window.mixer_widget:
                for strip in self.main_window.mixer_widget.strips:
                    if hasattr(strip, 'update_ui_states'):
                        strip.update_ui_states()
        
        # Reselect the active track if it exists
        selected_track = None
        if self.audio_engine.selected_track_id:
            selected_track = next((t for t in self.audio_engine.tracks if t.track_id == self.audio_engine.selected_track_id), None)
            
        if selected_track:
            self.main_window.on_track_selected(selected_track)
        else:
            if self.main_window.track_cards:
                self.main_window.on_track_selected(self.main_window.track_cards[0].track)
            else:
                self.main_window.on_track_selected(None)
                
        # Always redraw the timeline waveforms/clips
        if hasattr(self.main_window, 'timeline') and self.main_window.timeline:
            self.main_window.timeline.update()
            
        # Rebuild master volume fader
        if hasattr(self.main_window, 'mixer_widget') and self.main_window.mixer_widget and hasattr(self.main_window.mixer_widget, 'master'):
            self.main_window.mixer_widget.master.update_volume_ui()
            
        # Update title bar status
        self.main_window.mark_project_dirty()
