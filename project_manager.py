import json
import base64
import os
from pedalboard import (
    NoiseGate, Distortion, Chorus, Phaser, Delay, Reverb,
    PitchShift, Compressor, LowpassFilter, HighpassFilter, load_plugin
)
from audio_engine import Track, EffectWrapper, AudioItem, TubeOverdrive

# Map of effect types to their Pedalboard class and standard parameters
EFFECT_CLASSES = {
    "NoiseGate": (NoiseGate, ["threshold_db", "ratio", "attack_ms", "release_ms"]),
    "Distortion": (TubeOverdrive, ["drive_db", "tone", "level_db"]),
    "Chorus": (Chorus, ["rate_hz", "depth", "feedback", "mix"]),
    "Phaser": (Phaser, ["rate_hz", "depth", "feedback", "mix"]),
    "Delay": (Delay, ["delay_seconds", "feedback", "mix"]),
    "Reverb": (Reverb, ["room_size", "damping", "wet_level", "dry_level", "width"]),
    "PitchShift": (PitchShift, ["semitones"]),
    "Compressor": (Compressor, ["threshold_db", "ratio", "attack_ms", "release_ms"]),
    "LowpassFilter": (LowpassFilter, ["cutoff_frequency_hz"]),
    "HighpassFilter": (HighpassFilter, ["cutoff_frequency_hz"]),
}

def serialize_effect(wrapper):
    """Converts an EffectWrapper to a JSON-serializable dictionary."""
    data = {
        "effect_type": wrapper.effect_type,
        "name": wrapper.name,
        "is_active": wrapper.is_active,
        "mix": getattr(wrapper, "mix", 1.0),
        "gain_db": getattr(wrapper, "gain_db", 0.0),
        "parameters": {}
    }
    
    if wrapper.effect_type == "VST3":
        # For VST3 plugins, store path and raw_state
        original_path = getattr(wrapper, "original_vst_path", None)
        if not original_path:
            original_path = getattr(wrapper.effect, "path", "")
        data["vst_path"] = original_path
        try:
            # raw_state is bytes, encode as base64 string
            raw_state = wrapper.effect.raw_state
            data["raw_state"] = base64.b64encode(raw_state).decode("utf-8")
        except Exception as e:
            print(f"Error serializing VST3 state: {e}")
            data["raw_state"] = ""
    elif wrapper.effect_type in EFFECT_CLASSES:
        _, params = EFFECT_CLASSES[wrapper.effect_type]
        for p in params:
            if hasattr(wrapper.effect, p):
                data["parameters"][p] = getattr(wrapper.effect, p)
                
    return data

def deserialize_effect(data):
    """Creates an EffectWrapper from a serialized dictionary."""
    effect_type = data["effect_type"]
    name = data["name"]
    is_active = data.get("is_active", True)
    
    if effect_type == "VST3":
        vst_path = data.get("vst_path", "")
        if not vst_path or not os.path.exists(vst_path):
            print(f"VST3 file not found: {vst_path}")
            return None
        try:
            from audio_engine import load_vst_plugin
            effect_obj = load_vst_plugin(vst_path)
            raw_state_b64 = data.get("raw_state", "")
            if raw_state_b64:
                effect_obj.raw_state = base64.b64decode(raw_state_b64)
            wrapper = EffectWrapper(effect_obj, name, "VST3", is_active)
            wrapper.original_vst_path = vst_path
            wrapper.mix = data.get("mix", 1.0)
            wrapper.gain_db = data.get("gain_db", 0.0)
            return wrapper
        except Exception as e:
            print(f"Failed to load VST3 plugin at {vst_path}: {e}")
            return None
            
    elif effect_type in EFFECT_CLASSES:
        klass, params = EFFECT_CLASSES[effect_type]
        init_args = {}
        for p in params:
            if p in data["parameters"]:
                init_args[p] = data["parameters"][p]
        try:
            effect_obj = klass(**init_args)
            wrapper = EffectWrapper(effect_obj, name, effect_type, is_active)
            wrapper.mix = data.get("mix", 1.0)
            wrapper.gain_db = data.get("gain_db", 0.0)
            return wrapper
        except Exception as e:
            print(f"Failed to instantiate effect {effect_type}: {e}")
            return None
            
    return None

def save_project(file_path, audio_engine):
    """Saves the current audio engine state to a JSON file."""
    project_data = {
        "version": "1.0",
        "global_settings": {
            "audio_system": audio_engine.audio_system,
            "input_device_index": audio_engine.input_device_index,
            "output_device_index": audio_engine.output_device_index,
            "enable_inputs": audio_engine.enable_inputs,
            "input_first_channel": audio_engine.input_first_channel,
            "input_last_channel": audio_engine.input_last_channel,
            "output_first_channel": audio_engine.output_first_channel,
            "output_last_channel": audio_engine.output_last_channel,
            "request_sample_rate": audio_engine.request_sample_rate,
            "sample_rate": audio_engine.sample_rate,
            "request_block_size": audio_engine.request_block_size,
            "block_size": audio_engine.block_size,
            "thread_priority": audio_engine.thread_priority,
            "pre_zero_buffers": audio_engine.pre_zero_buffers,
            "ignore_asio_reset": audio_engine.ignore_asio_reset,
            "allow_project_override_sr": audio_engine.allow_project_override_sr,
            "demo_loop_active": audio_engine.demo_loop_active,
            "main_volume": audio_engine.main_volume
        },
        "tracks": []
    }
    
    with audio_engine.lock:
        for track in audio_engine.tracks:
            track_data = {
                "track_id": track.track_id,
                "name": track.name,
                "volume": track.volume,
                "pan": track.pan,
                "mute": track.mute,
                "solo": track.solo,
                "armed": track.armed,
                "input_channel": track.input_channel,
                "effects": [],
                "items": [],
                "arm_regions": getattr(track, "arm_regions", [])
            }
            
            with track.lock:
                for fx in track.effects:
                    fx_data = serialize_effect(fx)
                    track_data["effects"].append(fx_data)
                for item in track.items:
                    rel_path = os.path.relpath(item.file_path, os.path.dirname(file_path)) if (item.file_path and file_path) else ""
                    item_data = {
                        "start_sample": item.start_sample,
                        "sample_rate": item.sample_rate,
                        "file_path": rel_path,
                        "offset_samples": item.offset_samples,
                        "length_samples": item.length_samples
                    }
                    track_data["items"].append(item_data)
                    
            project_data["tracks"].append(track_data)
            
    try:
        with open(file_path, "w") as f:
            json.dump(project_data, f, indent=4)
        print(f"Project saved to {file_path}")
        return True
    except Exception as e:
        print(f"Failed to save project: {e}")
        return False

def load_project(file_path, audio_engine):
    """Loads a project from JSON file into the audio engine."""
    if not os.path.exists(file_path):
        print(f"Project file not found: {file_path}")
        return False
        
    try:
        with open(file_path, "r") as f:
            project_data = json.load(f)
            
        globals_cfg = project_data.get("global_settings", {})
        
        # Stop stream while loading
        was_running = audio_engine.is_running
        audio_engine.stop_stream()
        
        # Restore globals
        audio_engine.audio_system = globals_cfg.get("audio_system")
        audio_engine.input_device_index = globals_cfg.get("input_device_index")
        audio_engine.output_device_index = globals_cfg.get("output_device_index")
        audio_engine.enable_inputs = globals_cfg.get("enable_inputs", True)
        audio_engine.input_first_channel = globals_cfg.get("input_first_channel", 0)
        audio_engine.input_last_channel = globals_cfg.get("input_last_channel", 1)
        audio_engine.output_first_channel = globals_cfg.get("output_first_channel", 0)
        audio_engine.output_last_channel = globals_cfg.get("output_last_channel", 1)
        audio_engine.request_sample_rate = globals_cfg.get("request_sample_rate", True)
        audio_engine.sample_rate = globals_cfg.get("sample_rate", audio_engine.get_system_sample_rate())
        audio_engine.request_block_size = globals_cfg.get("request_block_size", True)
        audio_engine.block_size = globals_cfg.get("block_size", 256)
        audio_engine.thread_priority = globals_cfg.get("thread_priority", "ASIO Default / MMCSS Pro Audio / Time Critical")
        audio_engine.pre_zero_buffers = globals_cfg.get("pre_zero_buffers", True)
        audio_engine.ignore_asio_reset = globals_cfg.get("ignore_asio_reset", True)
        audio_engine.allow_project_override_sr = globals_cfg.get("allow_project_override_sr", True)
        audio_engine.demo_loop_active = globals_cfg.get("demo_loop_active", False)
        audio_engine.main_volume = globals_cfg.get("main_volume", 0.0)
        
        # Clear existing tracks
        with audio_engine.lock:
            audio_engine.tracks.clear()
            
            # Load tracks
            for tr_data in project_data.get("tracks", []):
                track = Track(tr_data["track_id"], tr_data["name"])
                track.volume = tr_data["volume"]
                track.pan = tr_data["pan"]
                track.mute = tr_data["mute"]
                track.solo = tr_data["solo"]
                track.armed = tr_data.get("armed", True)
                track.input_channel = tr_data.get("input_channel", 0)
                track.arm_regions = tr_data.get("arm_regions", [])
                
                # Deserialized effects list
                effects_list = []
                for fx_data in tr_data.get("effects", []):
                    wrapper = deserialize_effect(fx_data)
                    if wrapper:
                        effects_list.append(wrapper)
                
                track.effects = effects_list
                track.update_pedalboard()
                
                # Deserialized timeline items
                track.items = []
                for item_data in tr_data.get("items", []):
                    rel_path = item_data.get("file_path", "")
                    if rel_path and file_path:
                        abs_path = os.path.abspath(os.path.join(os.path.dirname(file_path), rel_path))
                    else:
                        abs_path = ""
                    item = AudioItem(
                        start_sample=item_data["start_sample"],
                        sample_rate=item_data["sample_rate"],
                        file_path=abs_path
                    )
                    if "offset_samples" in item_data:
                        item.offset_samples = item_data["offset_samples"]
                    if "length_samples" in item_data:
                        item.length_samples = item_data["length_samples"]
                    track.items.append(item)
                    
                audio_engine.tracks.append(track)
            audio_engine.tracks_list_cache = list(audio_engine.tracks)
                
        # Restart stream if it was running or as default
        if was_running:
            audio_engine.start_stream()
            
        print(f"Project loaded from {file_path}")
        return True
    except Exception as e:
        print(f"Failed to load project: {e}")
        return False
