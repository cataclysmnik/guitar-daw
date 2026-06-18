import os
import numpy as np
os.environ["SD_ENABLE_ASIO"] = "1"

from audio_engine import AudioEngine, AudioItem
import project_manager
from pedalboard import Reverb

def test_daw_serialization():
    print("Initializing test engine...")
    engine = AudioEngine()
    # Ensure stream does not start for this non-interactive test
    engine.stop_stream()
    
    # 1. Clear default tracks
    engine.tracks.clear()
    
    # 2. Add custom track with parameters
    track = engine.add_track("Clean Rhythm")
    track.volume = -6.5
    track.pan = -0.3
    track.armed = True
    track.input_channel = 1
    track.arm_regions = [[22050, 44100]]
    
    # Create a dummy WAV file to test AudioItem serialization
    test_wav_path = "test_item.wav"
    # Generate 0.5s of 440Hz sine wave, stereo
    sample_rate = 44100
    t = np.linspace(0, 0.5, int(sample_rate * 0.5), endpoint=False)
    sine = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    stereo_data = np.stack([sine, sine]) # shape (2, 22050)
    
    # Create and save AudioItem
    item = AudioItem(start_sample=44100, sample_rate=sample_rate, file_path=test_wav_path, audio_data=stereo_data)
    item.save_to_wav(test_wav_path)
    
    # Add AudioItem to the track
    track.items.append(item)
    
    # 3. Add Reverb effect
    from audio_engine import EffectWrapper
    reverb_effect = Reverb(room_size=0.75, damping=0.3)
    wrapper = EffectWrapper(reverb_effect, "Reverb", "Reverb", is_active=True)
    track.effects.append(wrapper)
    track.update_pedalboard()
    
    # 4. Save to temporary file
    temp_file = "test_temp.graphite"
    print(f"Saving test project to {temp_file}...")
    save_ok = project_manager.save_project(temp_file, engine)
    assert save_ok, "Failed to save project!"
    
    # 5. Clear tracks and settings in memory
    engine.tracks.clear()
    engine.main_volume = -999.0
    
    # 6. Load back
    print(f"Loading test project from {temp_file}...")
    load_ok = project_manager.load_project(temp_file, engine)
    assert load_ok, "Failed to load project!"
    
    # Stop stream if it restarted automatically during load
    engine.stop_stream()
    
    # 7. Assertions to verify correctness
    print("Verifying loaded state...")
    assert len(engine.tracks) == 1, f"Expected 1 track, got {len(engine.tracks)}"
    
    loaded_track = engine.tracks[0]
    assert loaded_track.name == "Clean Rhythm", f"Expected 'Clean Rhythm', got '{loaded_track.name}'"
    assert abs(loaded_track.volume - (-6.5)) < 1e-5, f"Expected volume -6.5, got {loaded_track.volume}"
    assert abs(loaded_track.pan - (-0.3)) < 1e-5, f"Expected pan -0.3, got {loaded_track.pan}"
    assert loaded_track.armed is True, f"Expected armed True, got {loaded_track.armed}"
    assert loaded_track.input_channel == 1, f"Expected input channel 1, got {loaded_track.input_channel}"
    assert loaded_track.arm_regions == [[22050, 44100]], f"Expected arm_regions [[22050, 44100]], got {loaded_track.arm_regions}"
    
    assert len(loaded_track.effects) == 1, f"Expected 1 effect, got {len(loaded_track.effects)}"
    loaded_fx = loaded_track.effects[0]
    assert loaded_fx.effect_type == "Reverb", f"Expected Reverb, got {loaded_fx.effect_type}"
    assert loaded_fx.is_active is True, "Expected effect to be active"
    assert abs(loaded_fx.effect.room_size - 0.75) < 1e-5, f"Expected room_size 0.75, got {loaded_fx.effect.room_size}"
    assert abs(loaded_fx.effect.damping - 0.3) < 1e-5, f"Expected damping 0.3, got {loaded_fx.effect.damping}"
    
    # Verify the AudioItem was loaded properly
    assert len(loaded_track.items) == 1, f"Expected 1 timeline item, got {len(loaded_track.items)}"
    loaded_item = loaded_track.items[0]
    assert loaded_item.start_sample == 44100, f"Expected start_sample 44100, got {loaded_item.start_sample}"
    assert loaded_item.sample_rate == sample_rate, f"Expected sample_rate {sample_rate}, got {loaded_item.sample_rate}"
    assert loaded_item.audio_data is not None, "Expected loaded audio_data to be populated"
    assert loaded_item.audio_data.shape == (2, 22050), f"Expected audio_data shape (2, 22050), got {loaded_item.audio_data.shape}"
    
    # Verify absolute path resolution
    expected_abs_path = os.path.abspath(test_wav_path)
    assert os.path.normpath(loaded_item.file_path) == os.path.normpath(expected_abs_path), \
        f"Expected path {expected_abs_path}, got {loaded_item.file_path}"
    
    # Cleanup
    if os.path.exists(temp_file):
        os.remove(temp_file)
    if os.path.exists(test_wav_path):
        os.remove(test_wav_path)
        
    print("SUCCESS: All serialization and deserialization assertions passed (including timeline AudioItems)!")

def test_daw_export():
    print("Initializing export test...")
    engine = AudioEngine()
    engine.stop_stream()
    
    # 1. Clear default tracks
    engine.tracks.clear()
    
    # 2. Add track and mock item
    track = engine.add_track("Lead Guitar")
    
    test_wav_path = "test_export_input.wav"
    sample_rate = 44100
    t = np.linspace(0, 1.0, sample_rate, endpoint=False)
    sine = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    stereo_data = np.stack([sine, sine]) # shape (2, 44100)
    
    item = AudioItem(start_sample=0, sample_rate=sample_rate, file_path=test_wav_path, audio_data=stereo_data)
    item.save_to_wav(test_wav_path)
    track.items.append(item)
    
    # 3. Test 16-bit Stereo Export
    export_16_path = "test_export_out_16.wav"
    print(f"Exporting to 16-bit WAV: {export_16_path}...")
    success, msg = engine.render_project_offline(
        file_path=export_16_path,
        start_time_sec=0.0,
        end_time_sec=1.0,
        sample_rate=sample_rate,
        bit_depth=16,
        channels="stereo"
    )
    assert success, f"16-bit export failed: {msg}"
    assert os.path.exists(export_16_path), "16-bit export file not found on disk"
    
    # Verify 16-bit file properties
    import wave
    with wave.open(export_16_path, 'rb') as w:
        assert w.getnchannels() == 2, f"Expected 2 channels, got {w.getnchannels()}"
        assert w.getsampwidth() == 2, f"Expected 2 bytes per sample (16-bit), got {w.getsampwidth()}"
        assert w.getframerate() == 44100, f"Expected 44100 Hz, got {w.getframerate()}"
        assert w.getnframes() == 44100, f"Expected 44100 frames, got {w.getnframes()}"
        
    # 4. Test 24-bit Stereo Export
    export_24_path = "test_export_out_24.wav"
    print(f"Exporting to 24-bit WAV: {export_24_path}...")
    success, msg = engine.render_project_offline(
        file_path=export_24_path,
        start_time_sec=0.0,
        end_time_sec=1.0,
        sample_rate=sample_rate,
        bit_depth=24,
        channels="stereo"
    )
    assert success, f"24-bit export failed: {msg}"
    assert os.path.exists(export_24_path), "24-bit export file not found on disk"
    
    # Verify 24-bit file properties
    with wave.open(export_24_path, 'rb') as w:
        assert w.getnchannels() == 2, f"Expected 2 channels, got {w.getnchannels()}"
        assert w.getsampwidth() == 3, f"Expected 3 bytes per sample (24-bit), got {w.getsampwidth()}"
        assert w.getframerate() == 44100, f"Expected 44100 Hz, got {w.getframerate()}"
        assert w.getnframes() == 44100, f"Expected 44100 frames, got {w.getnframes()}"
        
    # 5. Test MP3 Stereo Export
    export_mp3_path = "test_export_out.mp3"
    print(f"Exporting to MP3: {export_mp3_path}...")
    success, msg = engine.render_project_offline(
        file_path=export_mp3_path,
        start_time_sec=0.0,
        end_time_sec=1.0,
        sample_rate=sample_rate,
        bit_depth=16,
        channels="stereo",
        format_type="mp3"
    )
    assert success, f"MP3 export failed: {msg}"
    assert os.path.exists(export_mp3_path), "MP3 export file not found on disk"
    assert os.path.getsize(export_mp3_path) > 0, "MP3 file is empty"
    
    # Cleanup
    for path in [test_wav_path, export_16_path, export_24_path, export_mp3_path]:
        if os.path.exists(path):
            os.remove(path)
            
    print("SUCCESS: All export and offline mixdown rendering assertions passed!")

if __name__ == "__main__":
    test_daw_serialization()
    test_daw_export()

