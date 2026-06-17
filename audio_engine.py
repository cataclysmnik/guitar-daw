import os
os.environ["SD_ENABLE_ASIO"] = "1"

import sounddevice as sd
import numpy as np
import threading
from pedalboard import Pedalboard, Distortion, HighpassFilter, LowpassFilter, Gain

class KarplusStrongString:
    """Simulates a plucked string using the Karplus-Strong algorithm."""
    def __init__(self, frequency, sample_rate, decay=0.998, pluck_amp=0.25):
        self.decay = decay
        self.delay_len = int(round(sample_rate / frequency))
        if self.delay_len < 2:
            self.delay_len = 2
        # Initialize buffer with random noise
        self.buffer = (np.random.rand(self.delay_len) * 2.0 - 1.0) * pluck_amp
        self.index = 0

    def generate(self, num_samples):
        out = np.zeros(num_samples, dtype=np.float32)
        for i in range(num_samples):
            val = self.buffer[self.index]
            out[i] = val
            next_idx = (self.index + 1) % self.delay_len
            new_val = 0.5 * (val + self.buffer[next_idx]) * self.decay
            self.buffer[self.index] = new_val
            self.index = next_idx
        return out

def precompute_guitar_loop(sample_rate=44100):
    """Pre-computes an 8-second arpeggiated guitar loop using Karplus-Strong."""
    duration = 8.0  # seconds
    total_samples = int(duration * sample_rate)
    loop_data = np.zeros(total_samples, dtype=np.float32)
    
    # 120 BPM -> 1 beat = 0.5 seconds
    bpm = 120.0
    samples_per_beat = int((60.0 / bpm) * sample_rate)
    
    # Pluck schedule (beat_time, frequency)
    # E minor (beats 0-7), A minor (beats 8-15)
    plucks = [
        # E minor arpeggio
        (0.0, 82.41),   # E2
        (0.5, 123.47),  # B2
        (1.0, 164.81),  # E3
        (1.5, 196.00),  # G3
        (2.0, 246.94),  # B3
        (2.5, 329.63),  # E4
        (3.0, 246.94),  # B3
        (3.5, 196.00),  # G3
        
        # A minor arpeggio
        (4.0, 110.00),  # A2
        (4.5, 164.81),  # E3
        (5.0, 220.00),  # A3
        (5.5, 261.63),  # C4
        (6.0, 329.63),  # E4
        (6.5, 261.63),  # C4
        (7.0, 220.00),  # A3
        (7.5, 164.81),  # E3
    ]
    
    # Simulate string plucks
    active_strings = []
    
    for sample_idx in range(total_samples):
        # Trigger any pluck scheduled for this sample
        for beat, freq in plucks:
            trigger_sample = int(beat * samples_per_beat)
            if sample_idx == trigger_sample:
                active_strings.append(
                    KarplusStrongString(freq, sample_rate, decay=0.9982, pluck_amp=0.22)
                )
        
        # Sum active strings
        val = 0.0
        finished_strings = []
        for string in active_strings:
            s_val = string.buffer[string.index]
            val += s_val
            
            # Feedback step
            next_idx = (string.index + 1) % string.delay_len
            new_val = 0.5 * (s_val + string.buffer[next_idx]) * string.decay
            string.buffer[string.index] = new_val
            string.index = next_idx
            
            # Simple cleanup for decayed string to keep memory low
            if np.max(np.abs(string.buffer)) < 0.0001:
                finished_strings.append(string)
                
        for s in finished_strings:
            if s in active_strings:
                active_strings.remove(s)
                
        loop_data[sample_idx] = val

    # Normalize loop output
    max_val = np.max(np.abs(loop_data))
    if max_val > 0.0:
        loop_data = (loop_data / max_val) * 0.75
        
    return loop_data


class TunerBuffer:
    """A thread-safe circular buffer for streaming input to the tuner."""
    def __init__(self, size=8192):
        self.size = size
        self.buffer = np.zeros(size, dtype=np.float32)
        self.write_ptr = 0
        self.lock = threading.Lock()

    def write(self, data):
        if data is None or len(data) == 0:
            return
        with self.lock:
            n = len(data)
            if n > self.size:
                data = data[-self.size:]
                n = self.size
            end = self.write_ptr + n
            if end <= self.size:
                self.buffer[self.write_ptr:end] = data
            else:
                first_part = self.size - self.write_ptr
                self.buffer[self.write_ptr:] = data[:first_part]
                self.buffer[:n - first_part] = data[first_part:]
            self.write_ptr = (self.write_ptr + n) % self.size

    def read_latest(self, n):
        with self.lock:
            if n > self.size:
                n = self.size
            start = (self.write_ptr - n) % self.size
            end = self.write_ptr
            if start < end:
                return self.buffer[start:end].copy()
            else:
                return np.concatenate([self.buffer[start:], self.buffer[:end]])


class TubeOverdrive(Pedalboard):
    """Skeuomorphic Tube Screamer model wrapping HPF, Distortion, Gain (Level), and LPF."""
    def __init__(self, drive_db=15.0, tone=0.5, level_db=0.0):
        self._drive_db = drive_db
        self._tone = tone
        self._level_db = level_db
        
        self.hpf = HighpassFilter(cutoff_frequency_hz=self._map_tone_to_hpf(tone))
        self.dist = Distortion(drive_db=drive_db)
        self.gain = Gain(gain_db=level_db)
        self.lpf = LowpassFilter(cutoff_frequency_hz=self._map_tone_to_lpf(tone))
        
        super().__init__([self.hpf, self.dist, self.gain, self.lpf])
        
    def _map_tone_to_hpf(self, tone):
        # tone=0 -> HPF=350Hz (tighter, mid hump), tone=1 -> HPF=120Hz (fatter)
        return 350.0 - tone * 230.0
        
    def _map_tone_to_lpf(self, tone):
        # tone=0 -> LPF=2200Hz (warmer, dark), tone=1 -> LPF=6500Hz (brighter, screaming)
        return 2200.0 + tone * 4300.0
        
    @property
    def drive_db(self):
        return self._drive_db
        
    @drive_db.setter
    def drive_db(self, val):
        self._drive_db = val
        self.dist.drive_db = val
        
    @property
    def tone(self):
        return self._tone
        
    @tone.setter
    def tone(self, val):
        self._tone = val
        self.hpf.cutoff_frequency_hz = self._map_tone_to_hpf(val)
        self.lpf.cutoff_frequency_hz = self._map_tone_to_lpf(val)
        
    @property
    def level_db(self):
        return self._level_db
        
    @level_db.setter
    def level_db(self, val):
        self._level_db = val
        self.gain.gain_db = val


class AudioItem:
    """Represents an audio clip on the timeline."""
    def __init__(self, start_sample, sample_rate, file_path=None, audio_data=None):
        self.start_sample = start_sample
        self.sample_rate = sample_rate
        self.file_path = file_path
        self.audio_data = audio_data  # 2D numpy array: shape (channels, samples)
        self.offset_samples = 0
        self.length_samples = 0
        
        if file_path and os.path.exists(file_path):
            self.load_from_wav(file_path)
        elif audio_data is not None:
            self.length_samples = audio_data.shape[1]
            
    def load_from_wav(self, file_path):
        # Primary: try soundfile (supports 24-bit, 32-bit float, etc.)
        try:
            import soundfile as sf
            data, sr = sf.read(file_path, dtype='float32')
            self.sample_rate = sr
            if data.ndim == 1:
                self.audio_data = np.reshape(data, (1, -1))
            else:
                self.audio_data = data.T  # shape (channels, samples)
            self.length_samples = self.audio_data.shape[1]
            return
        except Exception as e:
            print(f"soundfile failed to load {file_path}, trying wave module: {e}")

        # Secondary fallback: wave module (only supports 16-bit/8-bit PCM)
        import wave
        try:
            with wave.open(file_path, 'rb') as w:
                ch = w.getnchannels()
                width = w.getsampwidth()
                self.sample_rate = w.getframerate()
                nframes = w.getnframes()
                if nframes == 0:
                    self.audio_data = None
                    self.length_samples = 0
                    return
                frames = w.readframes(nframes)
                if width == 2:
                    raw_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
                    self.audio_data = np.reshape(raw_data, (-1, ch)).T  # shape (channels, samples)
                elif width == 1:
                    raw_data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                    self.audio_data = np.reshape(raw_data, (1, -1))
                else:
                    self.audio_data = None
                
                if self.audio_data is not None:
                    self.length_samples = self.audio_data.shape[1]
                else:
                    self.length_samples = 0
        except Exception as e:
            print(f"Failed to load WAV file {file_path}: {e}")
            self.audio_data = None
            self.length_samples = 0
            
    def save_to_wav(self, file_path):
        if self.audio_data is None:
            return
        # Primary: try soundfile
        try:
            import soundfile as sf
            # soundfile expects (samples, channels)
            data_to_write = self.audio_data.T
            sf.write(file_path, data_to_write, self.sample_rate, subtype='PCM_16')
            return
        except Exception as e:
            print(f"soundfile failed to save {file_path}, trying wave module: {e}")

        # Secondary fallback: wave module
        import wave
        try:
            ch = self.audio_data.shape[0]
            with wave.open(file_path, 'wb') as w:
                w.setnchannels(ch)
                w.setsampwidth(2)  # 16-bit
                w.setframerate(self.sample_rate)
                # Reshape to interleaved PCM frames
                interleaved = self.audio_data.T.flatten()
                int_data = (np.clip(interleaved, -1.0, 1.0) * 32767.0).astype(np.int16)
                w.writeframes(int_data.tobytes())
        except Exception as e:
            print(f"Failed to save WAV file {file_path}: {e}")


class EffectWrapper:
    """Wraps an individual Pedalboard effect or VST3 plugin with metadata."""
    def __init__(self, effect_obj, name, effect_type, is_active=True):
        self.effect = effect_obj
        self.name = name
        self.effect_type = effect_type
        self.is_active = is_active
        self.original_vst_path = None


class Track:
    """Represents a DAW Audio Track."""
    def __init__(self, track_id, name="Track"):
        self.track_id = track_id
        self.name = name
        self.volume = 0.0      # dB, range: -60.0 to +6.0
        self.pan = 0.0         # -1.0 (Left) to +1.0 (Right)
        self.mute = False
        self.solo = False
        self.armed = True
        self.input_channel = 0  # int channel index, or "loop"
        self.effects = []      # list of EffectWrapper objects
        self.items = []        # list of AudioItem objects
        
        # The compiled Pedalboard object
        self.pedalboard = Pedalboard([])
        self.level_history = -60.0  # Recent peak level in dB
        self.lock = threading.Lock()
        
    def update_pedalboard(self, sample_rate=44100):
        """Constructs a new Pedalboard chain atomically."""
        with self.lock:
            active_fx = [wrap.effect for wrap in self.effects if wrap.is_active]
            self.pedalboard = Pedalboard(active_fx)
            # Run a dummy processing block on the main thread to force VST3/JUCE
            # initialization to happen on the main thread before the audio callback uses it.
            try:
                import numpy as np
                dummy_in = np.zeros((1, 128), dtype=np.float32)
                self.pedalboard(dummy_in, sample_rate)
            except Exception as e:
                print(f"Warning: Dummy pedalboard initialization failed: {e}")


class AudioEngine:
    """Manages sounddevice input/output audio streams and mixing DSP."""
    def get_system_sample_rate(self):
        """Queries the system (WASAPI) default sample rate to prevent driver conflicts on Windows."""
        try:
            import sounddevice as sd
            for api in sd.query_hostapis():
                if "wasapi" in api['name'].lower():
                    default_out = api.get('default_output_device')
                    if default_out is not None and default_out >= 0:
                        dev_info = sd.query_devices(default_out)
                        return int(dev_info.get('default_samplerate', 44100))
        except Exception:
            pass
        return 44100

    def __init__(self):
        self.tracks = []
        
        # Advanced audio settings matching professional layouts
        self.audio_system = None           # Host API index (e.g. WASAPI, ASIO, MME)
        self.input_device_index = None     # Specific device index
        self.output_device_index = None    # Specific device index
        self.enable_inputs = True
        self.input_first_channel = 0
        self.input_last_channel = 1        # Stereo input default (channels 0 and 1)
        self.output_first_channel = 0
        self.output_last_channel = 1       # Stereo output default (channels 0 and 1)
        
        self.request_sample_rate = True
        self.sample_rate = self.get_system_sample_rate()
        self.request_block_size = True
        self.block_size = 256
        
        # Mock settings matching reaper casing
        self.thread_priority = "ASIO Default / MMCSS Pro Audio / Time Critical"
        self.pre_zero_buffers = True
        self.ignore_asio_reset = True
        self.allow_project_override_sr = True
        
        self.demo_loop_active = False
        self.is_running = False
        self.stream = None
        self.main_volume = 0.0  # dB, range: -60.0 to +6.0
        self.main_level_history = [-60.0, -60.0]
        
        self.play_state = "stopped"         # "stopped", "playing", "paused", "recording"
        self.playhead_samples = 0           # current playback cursor position in samples
        self.recording_buffers = {}         # track_id -> list of numpy arrays
        self.recording_start_sample = 0
        
        self.guitar_loop = precompute_guitar_loop(self.sample_rate)
        self.guitar_loop_idx = 0
        self.vst_search_paths = ["C:\\Program Files\\Common Files\\VST3"]
        self.lock = threading.RLock()
        self.tuner_buffer = TunerBuffer(8192)
        self.selected_track_id = 1
        
        # Metronome settings
        self.metronome_enabled = False
        self.bpm = 120.0
        self.time_sig_numerator = 4
        self.time_sig_denominator = 4
        self.metronome_volume_db = -12.0
        self.click_accent = None
        self.click_normal = None
        self.metronome_click_pos = -1
        self.metronome_current_click = None
        self.precompute_metronome_clicks()
        
        self.load_settings()
        
    def save_settings(self):
        """Saves advanced audio engine settings to a JSON file."""
        import json
        settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_settings.json")
        try:
            settings_data = {
                "audio_system": self.audio_system,
                "input_device_index": self.input_device_index,
                "output_device_index": self.output_device_index,
                "enable_inputs": self.enable_inputs,
                "input_first_channel": self.input_first_channel,
                "input_last_channel": self.input_last_channel,
                "output_first_channel": self.output_first_channel,
                "output_last_channel": self.output_last_channel,
                "request_sample_rate": self.request_sample_rate,
                "sample_rate": self.sample_rate,
                "request_block_size": self.request_block_size,
                "block_size": self.block_size,
                "pre_zero_buffers": self.pre_zero_buffers,
                "ignore_asio_reset": self.ignore_asio_reset,
                "allow_project_override_sr": self.allow_project_override_sr,
                "thread_priority": self.thread_priority,
                "vst_search_paths": self.vst_search_paths
            }
            with open(settings_path, "w") as f:
                json.dump(settings_data, f, indent=4)
        except Exception as e:
            print(f"Failed to save audio settings: {e}")

    def load_settings(self):
        """Loads advanced audio engine settings from JSON file if it exists."""
        import json
        settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_settings.json")
        if not os.path.exists(settings_path):
            return
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
            self.audio_system = data.get("audio_system", self.audio_system)
            self.input_device_index = data.get("input_device_index", self.input_device_index)
            self.output_device_index = data.get("output_device_index", self.output_device_index)
            self.enable_inputs = data.get("enable_inputs", self.enable_inputs)
            self.input_first_channel = data.get("input_first_channel", self.input_first_channel)
            self.input_last_channel = data.get("input_last_channel", self.input_last_channel)
            self.output_first_channel = data.get("output_first_channel", self.output_first_channel)
            self.output_last_channel = data.get("output_last_channel", self.output_last_channel)
            self.request_sample_rate = data.get("request_sample_rate", self.request_sample_rate)
            self.sample_rate = data.get("sample_rate", self.sample_rate)
            self.request_block_size = data.get("request_block_size", self.request_block_size)
            self.block_size = data.get("block_size", self.block_size)
            self.pre_zero_buffers = data.get("pre_zero_buffers", self.pre_zero_buffers)
            self.ignore_asio_reset = data.get("ignore_asio_reset", self.ignore_asio_reset)
            self.allow_project_override_sr = data.get("allow_project_override_sr", self.allow_project_override_sr)
            self.thread_priority = data.get("thread_priority", self.thread_priority)
            self.vst_search_paths = data.get("vst_search_paths", ["C:\\Program Files\\Common Files\\VST3"])
        except Exception as e:
            print(f"Failed to load audio settings: {e}")
            
    def precompute_metronome_clicks(self):
        """Precomputes click waveforms at current sample rate."""
        length_samples = int(self.sample_rate * 0.04)  # 40ms duration
        t = np.arange(length_samples) / self.sample_rate
        decay = np.exp(-t * 120.0)
        self.click_accent = (np.sin(2 * np.pi * 1000.0 * t) * decay).astype(np.float32)
        self.click_normal = (np.sin(2 * np.pi * 600.0 * t) * decay).astype(np.float32)
            
    def get_host_apis(self):
        """Returns list of available host APIs (ASIO, WASAPI, MME, DirectSound, WDM-KS)."""
        try:
            return [(idx, api['name']) for idx, api in enumerate(sd.query_hostapis())]
        except Exception:
            return []
            
    def get_devices_for_api(self, api_idx):
        """Returns input and output devices belonging to a specific Host API."""
        devices = sd.query_devices()
        inputs = []
        outputs = []
        for idx, dev in enumerate(devices):
            if dev['hostapi'] == api_idx:
                if dev['max_input_channels'] > 0:
                    inputs.append((idx, dev['name']))
                if dev['max_output_channels'] > 0:
                    outputs.append((idx, dev['name']))
        return inputs, outputs
        
    def get_devices(self):
        """Returns lists of available input and output devices for compatibility."""
        devices = sd.query_devices()
        inputs = []
        outputs = []
        
        for idx, dev in enumerate(devices):
            try:
                hostapi_name = sd.query_hostapis(dev['hostapi'])['name']
            except Exception:
                hostapi_name = "Unknown"
            if dev['max_input_channels'] > 0:
                inputs.append((idx, f"{dev['name']} ({hostapi_name})"))
            if dev['max_output_channels'] > 0:
                outputs.append((idx, f"{dev['name']} ({hostapi_name})"))
                
        return inputs, outputs
        
    def start_stream(self):
        """Starts PortAudio stream with requested ranges, sample rate, and API choices."""
        self.stop_stream()
        
        devices = sd.query_devices()
        default_in = sd.default.device[0]
        default_out = sd.default.device[1]
        
        # 1. Resolve Audio System API index
        api_idx = self.audio_system
        if api_idx is None:
            try:
                default_dev = default_out if default_out is not None else default_in
                if default_dev is not None and default_dev >= 0:
                    api_idx = devices[default_dev]['hostapi']
            except Exception:
                api_idx = 0
        self.audio_system = api_idx
        
        # Get devices for active system
        inputs_for_api, outputs_for_api = self.get_devices_for_api(api_idx)
        valid_in_ids = [idx for idx, _ in inputs_for_api]
        valid_out_ids = [idx for idx, _ in outputs_for_api]
        
        # 2. Resolve input device index
        in_idx = self.input_device_index
        if in_idx not in valid_in_ids:
            try:
                api_info = sd.query_hostapis(api_idx)
                default_in_dev = api_info['default_input_device']
                in_idx = default_in_dev if default_in_dev >= 0 else (valid_in_ids[0] if valid_in_ids else None)
            except Exception:
                in_idx = valid_in_ids[0] if valid_in_ids else None
        self.input_device_index = in_idx
        
        # 3. Resolve output device index
        out_idx = self.output_device_index
        if out_idx not in valid_out_ids:
            try:
                api_info = sd.query_hostapis(api_idx)
                default_out_dev = api_info['default_output_device']
                out_idx = default_out_dev if default_out_dev >= 0 else (valid_out_ids[0] if valid_out_ids else None)
            except Exception:
                out_idx = valid_out_ids[0] if valid_out_ids else None
        self.output_device_index = out_idx
        
        # 4. Resolve parameters
        sr = self.sample_rate if self.request_sample_rate else None
        if sr is None:
            if out_idx is not None and out_idx >= 0:
                sr = int(devices[out_idx]['default_samplerate'])
            else:
                sr = self.get_system_sample_rate()
                
        bs = self.block_size if self.request_block_size else 0
        
        self.is_running = True
        
        # Re-initialize guitar loop if sample rate changed
        if abs((len(self.guitar_loop) / 8.0) - sr) > 10.0:
            self.guitar_loop = precompute_guitar_loop(sr)
            self.guitar_loop_idx = 0
            
        # Re-initialize metronome clicks if sample rate changed
        if self.click_accent is None or abs(len(self.click_accent) / 0.04 - sr) > 10.0:
            self.sample_rate = sr
            self.precompute_metronome_clicks()
            
        # 5. Resolve Channels
        num_in_channels = 0
        if self.enable_inputs and in_idx is not None and in_idx >= 0:
            max_in = devices[in_idx]['max_input_channels']
            first_in = min(self.input_first_channel, max_in - 1)
            last_in = min(self.input_last_channel, max_in - 1)
            if first_in > last_in:
                first_in, last_in = last_in, first_in
            self.input_first_channel = first_in
            self.input_last_channel = last_in
            num_in_channels = last_in + 1
            
        num_out_channels = 2
        if out_idx is not None and out_idx >= 0:
            max_out = devices[out_idx]['max_output_channels']
            first_out = min(self.output_first_channel, max_out - 1)
            last_out = min(self.output_last_channel, max_out - 1)
            if first_out > last_out:
                first_out, last_out = last_out, first_out
            self.output_first_channel = first_out
            self.output_last_channel = last_out
            num_out_channels = last_out + 1
            
        # 6. Stream activation
        if self.enable_inputs and in_idx is not None and in_idx >= 0 and num_in_channels > 0:
            try:
                self.stream = sd.Stream(
                    device=(in_idx, out_idx),
                    samplerate=sr,
                    blocksize=bs,
                    channels=(num_in_channels, num_out_channels),
                    dtype='float32',
                    callback=self._duplex_callback
                )
                self.stream.start()
                print(f"Full-duplex stream started successfully (In API: {api_idx}, In: {in_idx}, Out: {out_idx}).")
                return True
            except Exception as e:
                print(f"Failed to start full-duplex stream: {e}. Falling back to output-only stream...")
                
        if out_idx is not None and out_idx >= 0:
            try:
                self.stream = sd.OutputStream(
                    device=out_idx,
                    samplerate=sr,
                    blocksize=bs,
                    channels=num_out_channels,
                    dtype='float32',
                    callback=self._output_callback
                )
                self.stream.start()
                print(f"Output-only stream started successfully (API: {api_idx}, Out: {out_idx}).")
                return True
            except Exception as e:
                print(f"Failed to start fallback output stream: {e}")
                self.is_running = False
                self.stream = None
                return False
                
        self.is_running = False
        return False
        
    def stop_stream(self):
        """Stops the audio stream thread."""
        self.is_running = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            
    def start_playback(self):
        """Starts stream if needed and sets play state to playing."""
        if not self.is_running:
            self.start_stream()
        with self.lock:
            if self.play_state == "recording":
                self.stop_recording()
            self.play_state = "playing"

    def pause_playback(self):
        """Pauses the playhead progression."""
        was_recording = False
        with self.lock:
            if self.play_state == "recording":
                was_recording = True
            self.play_state = "paused"
        if was_recording:
            self.stop_recording_data()

    def stop_playback(self):
        """Stops playback, resets playhead to start (0.0s)."""
        was_recording = False
        with self.lock:
            if self.play_state == "recording":
                was_recording = True
            self.play_state = "stopped"
            self.playhead_samples = 0
            self.metronome_click_pos = -1
            self.metronome_current_click = None
        if was_recording:
            self.stop_recording_data()

    def start_recording(self):
        """Starts recording on armed tracks."""
        if not self.is_running:
            self.start_stream()
        with self.lock:
            armed_any = any(t.armed for t in self.tracks)
            if not armed_any:
                self.play_state = "playing" # fallback
                return
            self.play_state = "recording"
            self.recording_start_sample = self.playhead_samples
            self.recording_buffers.clear()

    def stop_recording(self):
        """Stops recording state and saves recorded blocks."""
        with self.lock:
            if self.play_state != "recording":
                return
            self.play_state = "playing"
        self.stop_recording_data()

    def stop_recording_data(self):
        """Appends recorded blocks to respective track items and saves WAVs."""
        import uuid
        
        # 1. Safely extract and clear the buffers under the engine lock
        buffers_to_process = []
        start_sample = 0
        sr = 44100
        
        with self.lock:
            start_sample = self.recording_start_sample
            sr = self.sample_rate
            for track_id, buffers in list(self.recording_buffers.items()):
                if not buffers:
                    continue
                track = next((t for t in self.tracks if t.track_id == track_id), None)
                if track:
                    # Copy the buffers list and clear it from engine
                    buffers_to_process.append((track, list(buffers)))
            self.recording_buffers.clear()
            
        # 2. Process and perform disk I/O outside the engine lock
        for track, buffers in buffers_to_process:
            try:
                recorded_audio = np.concatenate(buffers)
                audio_2d = np.reshape(recorded_audio, (1, -1))
                
                filename = f"recorded_track_{track.track_id}_{uuid.uuid4().hex[:6]}.wav"
                file_path = os.path.join(os.getcwd(), filename)
                
                item = AudioItem(start_sample, sr, file_path=file_path, audio_data=audio_2d)
                try:
                    item.save_to_wav(file_path)
                except Exception as e:
                    print(f"Failed to save recorded WAV: {e}")
                
                with track.lock:
                    track.items.append(item)
            except Exception as e:
                print(f"Error processing recorded data for Track {track.name}: {e}")

    def add_track(self, name=None):
        """Adds a track to the engine and returns it."""
        with self.lock:
            track_id = len(self.tracks) + 1
            if not name:
                name = f"Track {track_id}"
            new_track = Track(track_id, name)
            self.tracks.append(new_track)
            return new_track
            
    def remove_track(self, track_id):
        """Removes a track by its ID."""
        with self.lock:
            self.tracks = [t for t in self.tracks if t.track_id != track_id]
            
    def render_project_offline(self, file_path, start_time_sec, end_time_sec, sample_rate, bit_depth, channels="stereo", format_type="wav", progress_callback=None):
        """Renders the timeline project to a WAV or MP3 file offline (faster than real-time)."""
        import soundfile as sf
        import numpy as np
        
        # Calculate sample ranges
        start_sample = int(start_time_sec * sample_rate)
        end_sample = int(end_time_sec * sample_rate)
        total_samples = end_sample - start_sample
        if total_samples <= 0:
            return False, "Invalid time range."
            
        # Define block size for render
        block_size = 512
        
        # We need a copy of the tracks to prevent lock contention
        with self.lock:
            tracks_copy = list(self.tracks)
            
        try:
            channels_count = 2 if channels == "stereo" else 1
            
            # Determine format and subtype for soundfile
            sf_format = 'WAV'
            sf_subtype = 'PCM_16'
            
            if format_type == "mp3":
                sf_format = 'MP3'
                sf_subtype = None
            else:
                sf_format = 'WAV'
                if bit_depth == 24:
                    sf_subtype = 'PCM_24'
                else:
                    sf_subtype = 'PCM_16'
            
            with sf.SoundFile(file_path, mode='w', samplerate=sample_rate, channels=channels_count, format=sf_format, subtype=sf_subtype) as sf_file:
                # Render loop
                curr_sample = start_sample
                
                # We want to display progress
                while curr_sample < end_sample:
                    frames = min(block_size, end_sample - curr_sample)
                    
                    # Output block accumulator
                    mixed_block = np.zeros((frames, 2), dtype=np.float32)
                    
                    # Render each track
                    for track in tracks_copy:
                        if track.mute:
                            continue
                            
                        # Fetch track items playback
                        track_playback = np.zeros(frames, dtype=np.float32)
                        with track.lock:
                            items = list(track.items)
                            
                        for item in items:
                            if item.audio_data is None:
                                continue
                                
                            # Convert item samples to target sample rate
                            item_start = int((item.start_sample / item.sample_rate) * sample_rate)
                            item_len = int((item.length_samples / item.sample_rate) * sample_rate)
                            item_end = item_start + item_len
                            
                            # Check overlap with current render block
                            overlap_start = max(curr_sample, item_start)
                            overlap_end = min(curr_sample + frames, item_end)
                            
                            if overlap_start < overlap_end:
                                # Slices
                                read_start = overlap_start - item_start
                                read_end = overlap_end - item_start
                                write_offset = overlap_start - curr_sample
                                length = overlap_end - overlap_start
                                
                                # Resample the sub-segment of item.audio_data to target sample rate
                                orig_start = item.offset_samples + int((read_start / sample_rate) * item.sample_rate)
                                orig_end = item.offset_samples + int((read_end / sample_rate) * item.sample_rate)
                                orig_chunk = item.audio_data[0, orig_start:orig_end]
                                
                                if len(orig_chunk) > 0:
                                    # Resample orig_chunk to length
                                    orig_indices = np.arange(len(orig_chunk))
                                    target_indices = np.linspace(0, len(orig_chunk) - 1, length)
                                    resampled_chunk = np.interp(target_indices, orig_indices, orig_chunk)
                                    track_playback[write_offset : write_offset + length] += resampled_chunk
                                    
                        # Process through track pedalboard
                        pedalboard_in = np.reshape(track_playback, (1, -1)).astype(np.float32)
                        try:
                            # Run pedalboard (at target sample rate)
                            pedalboard_out = track.pedalboard(pedalboard_in, sample_rate, reset=False)
                        except Exception as e:
                            print(f"Pedalboard offline render error: {e}")
                            pedalboard_out = np.zeros((1, frames), dtype=np.float32)
                            
                        # Reshape to stereo
                        out_ch = pedalboard_out.shape[0]
                        if out_ch == 1:
                            left = pedalboard_out[0, :]
                            right = pedalboard_out[0, :]
                        else:
                            left = pedalboard_out[0, :]
                            right = pedalboard_out[1, :]
                            
                        # Apply volume & pan
                        vol_gain = 10.0 ** (track.volume / 20.0)
                        g_l = np.cos(np.pi / 4.0 * (track.pan + 1.0)) * vol_gain
                        g_r = np.sin(np.pi / 4.0 * (track.pan + 1.0)) * vol_gain
                        
                        mixed_block[:, 0] += left * g_l
                        mixed_block[:, 1] += right * g_r
                        
                    # Apply main volume
                    main_gain = 10.0 ** (self.main_volume / 20.0)
                    mixed_block *= main_gain
                    
                    # Clip output
                    np.clip(mixed_block, -1.0, 1.0, out=mixed_block)
                    
                    # Output mono or stereo
                    if channels == "mono":
                        mono_data = 0.5 * (mixed_block[:, 0] + mixed_block[:, 1])
                        interleaved = mono_data
                    else:
                        interleaved = mixed_block
                        
                    # Write block via soundfile
                    sf_file.write(interleaved)
                        
                    curr_sample += frames
                    if progress_callback:
                        progress_callback(int((curr_sample - start_sample) / total_samples * 100))
                        
            return True, "Export successful!"
        except Exception as e:
            return False, f"Failed during render: {e}"
            
    def _duplex_callback(self, indata, outdata, frames, time, status):
        """Callback for full-duplex audio processing. Console printing is omitted for latency stability."""
        self._process_audio(indata, outdata, frames)
        
    def _output_callback(self, outdata, frames, time, status):
        """Callback for output-only audio processing. Console printing is omitted for latency stability."""
        self._process_audio(None, outdata, frames)
        
    def _process_audio(self, indata, outdata, frames):
        """Core DSP mixing routine."""
        if not self.is_running:
            outdata.fill(0)
            return
            
        # Prepare mixed stereo output accumulator
        mixed_out = np.zeros((frames, 2), dtype=np.float32)
        
        with self.lock:
            play_active = self.play_state in ("playing", "recording")
            is_recording_state = self.play_state == "recording"
            curr_playhead = self.playhead_samples
            
        # Prepare demo loop chunk if needed
        demo_input = None
        if self.demo_loop_active:
            with self.lock:
                idx = self.guitar_loop_idx
                loop_len = len(self.guitar_loop)
                # Read block (wrap circularly)
                if idx + frames <= loop_len:
                    demo_input = self.guitar_loop[idx:idx+frames]
                else:
                    first_part = self.guitar_loop[idx:]
                    second_part = self.guitar_loop[:frames - len(first_part)]
                    demo_input = np.concatenate([first_part, second_part])
                self.guitar_loop_idx = (idx + frames) % loop_len
                
        # Determine if any unmuted tracks are soloed
        with self.lock:
            tracks_copy = list(self.tracks)
            
        has_solo = any(t.solo for t in tracks_copy if not t.mute)
        
        for track in tracks_copy:
            # Skip tracks that are muted or not part of solo routing
            if track.mute:
                track.level_history = -60.0
                continue
            if has_solo and not track.solo:
                track.level_history = -60.0
                continue
                
            # 1. Fetch real-time input block (if armed)
            realtime_in = None
            if track.armed:
                if track.input_channel == "loop":
                    realtime_in = demo_input
                elif self.demo_loop_active:
                    realtime_in = demo_input
                elif indata is not None:
                    try:
                        ch_idx = int(track.input_channel)
                        if ch_idx < indata.shape[1]:
                            realtime_in = indata[:, ch_idx]
                    except (ValueError, TypeError):
                        pass
                        
            if realtime_in is None:
                realtime_in = np.zeros(frames, dtype=np.float32)
                
            # Write realtime_in to tuner circular buffer if track is armed and selected
            if track.armed and track.track_id == self.selected_track_id:
                self.tuner_buffer.write(realtime_in)
                
            # If recording, append real-time input to recording buffers
            if is_recording_state and track.armed:
                with self.lock:
                    if track.track_id not in self.recording_buffers:
                        self.recording_buffers[track.track_id] = []
                    self.recording_buffers[track.track_id].append(realtime_in.copy())
                    
            # 2. Fetch playback from recorded items (if play is active)
            playback_in = np.zeros(frames, dtype=np.float32)
            if play_active:
                with track.lock:
                    items_copy = list(track.items)
                for item in items_copy:
                    if item.audio_data is None:
                        continue
                    item_len = item.length_samples
                    item_start = item.start_sample
                    item_end = item_start + item_len
                    
                    # Check overlap of item with current playhead
                    overlap_start = max(curr_playhead, item_start)
                    overlap_end = min(curr_playhead + frames, item_end)
                    
                    if overlap_start < overlap_end:
                        read_offset = (overlap_start - item_start) + item.offset_samples
                        write_offset = overlap_start - curr_playhead
                        length = overlap_end - overlap_start
                        playback_in[write_offset : write_offset + length] += item.audio_data[0, read_offset : read_offset + length]
                        
            # Mix real-time input and playback items
            if track.armed:
                track_in = realtime_in + playback_in
            else:
                track_in = playback_in
                
            # 3. Reshape mono input to pedalboard's expected format (channels, samples)
            pedalboard_in = np.reshape(track_in, (1, -1)).astype(np.float32)
            
            # 3. Apply track effects
            try:
                with track.lock:
                    pedalboard_out = track.pedalboard(pedalboard_in, self.sample_rate, reset=False)
            except Exception as e:
                # Catch pedalboard execution exceptions (e.g. VST crash) and output silence
                print(f"Pedalboard processing error on Track {track.name}: {e}")
                pedalboard_out = np.zeros((1, frames), dtype=np.float32)
                
            # 4. Map processed output to stereo
            out_ch = pedalboard_out.shape[0]
            if out_ch == 1:
                left = pedalboard_out[0, :]
                right = pedalboard_out[0, :]
            else:
                left = pedalboard_out[0, :]
                right = pedalboard_out[1, :]
                
            # 5. Apply Volume & Pan using constant-power panning
            # Volume: map dB to linear gain
            vol_gain = 10.0 ** (track.volume / 20.0)
            
            # Constant power panning
            g_l = np.cos(np.pi / 4.0 * (track.pan + 1.0)) * vol_gain
            g_r = np.sin(np.pi / 4.0 * (track.pan + 1.0)) * vol_gain
            
            track_left = left * g_l
            track_right = right * g_r
            
            # 6. Sum to main output buffer
            mixed_out[:, 0] += track_left
            mixed_out[:, 1] += track_right
            
            # 7. Update Track VU Meter level
            peak_val = max(np.max(np.abs(track_left)), np.max(np.abs(track_right)))
            track_db = 20.0 * np.log10(peak_val) if peak_val > 1e-5 else -60.0
            # Track peak smoothing (faster rise, slower fall)
            if track_db > track.level_history:
                track.level_history = track_db
            else:
                track.level_history = track.level_history * 0.85 + track_db * 0.15
                
        # Metronome click trigger and mixing logic
        if self.metronome_enabled and play_active:
            samples_per_beat = (60.0 / self.bpm) * self.sample_rate
            k_start = int(np.ceil(curr_playhead / samples_per_beat))
            k_end = int(np.floor((curr_playhead + frames - 1) / samples_per_beat))
            
            for k in range(k_start, k_end + 1):
                write_offset = int(k * samples_per_beat - curr_playhead)
                is_accent = (k % self.time_sig_numerator == 0)
                self.metronome_current_click = self.click_accent if is_accent else self.click_normal
                self.metronome_click_pos = write_offset
                
        # Mix the active metronome click
        if self.metronome_click_pos != -1 and self.metronome_current_click is not None:
            click_src = self.metronome_current_click
            pos = self.metronome_click_pos
            
            src_start = 0
            dest_start = 0
            if pos < 0:
                src_start = -pos
                dest_start = 0
            else:
                src_start = 0
                dest_start = pos
                
            length = min(len(click_src) - src_start, frames - dest_start)
            if length > 0:
                gain = 10.0 ** (self.metronome_volume_db / 20.0)
                mixed_out[dest_start : dest_start + length, 0] += click_src[src_start : src_start + length] * gain
                mixed_out[dest_start : dest_start + length, 1] += click_src[src_start : src_start + length] * gain
                
            # Update click playhead relative to next block
            self.metronome_click_pos -= frames
            if self.metronome_click_pos <= -len(click_src):
                self.metronome_click_pos = -1
                self.metronome_current_click = None

        # 8. Apply main output gain
        main_gain = 10.0 ** (self.main_volume / 20.0)
        mixed_out *= main_gain
        
        # Update Master VU Meter level (stereo)
        main_peak_l = np.max(np.abs(mixed_out[:, 0]))
        main_peak_r = np.max(np.abs(mixed_out[:, 1]))
        
        main_db_l = 20.0 * np.log10(main_peak_l) if main_peak_l > 1e-5 else -60.0
        main_db_r = 20.0 * np.log10(main_peak_r) if main_peak_r > 1e-5 else -60.0
        
        if main_db_l > self.main_level_history[0]:
            self.main_level_history[0] = main_db_l
        else:
            self.main_level_history[0] = self.main_level_history[0] * 0.85 + main_db_l * 0.15
            
        if main_db_r > self.main_level_history[1]:
            self.main_level_history[1] = main_db_r
        else:
            self.main_level_history[1] = self.main_level_history[1] * 0.85 + main_db_r * 0.15
            
        # 9. Clip output to prevent digital distortion
        np.clip(mixed_out, -1.0, 1.0, out=mixed_out)
        
        # 10. Fill hardware buffer
        if outdata.shape[1] == 1:
            outdata[:, 0] = 0.5 * (mixed_out[:, 0] + mixed_out[:, 1])
        else:
            outdata[:, :] = mixed_out
            
        # 11. Advance playhead position
        if play_active:
            with self.lock:
                self.playhead_samples += frames


_temp_vst_dir = None
_temp_vst_instances = []

def get_temp_vst_dir():
    global _temp_vst_dir
    if _temp_vst_dir is None:
        import tempfile
        import os
        # Create a directory inside system temp dir specifically for Graphite DAW VSTs
        _temp_vst_dir = tempfile.mkdtemp(prefix="graphite_vst_")
    return _temp_vst_dir

def clean_temp_vsts():
    global _temp_vst_dir, _temp_vst_instances
    import shutil
    import os
    # We try to remove all temporary copies
    for path in _temp_vst_instances:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass
    _temp_vst_instances.clear()
    
    if _temp_vst_dir and os.path.exists(_temp_vst_dir):
        try:
            shutil.rmtree(_temp_vst_dir, ignore_errors=True)
        except Exception:
            pass
        _temp_vst_dir = None

def load_vst_plugin(vst_path):
    """Loads a VST plugin by making a unique copy of its DLL to avoid handle/state collisions."""
    import uuid
    import shutil
    import os
    from pedalboard import load_plugin
    
    if not os.path.exists(vst_path):
        raise FileNotFoundError(f"VST plugin not found: {vst_path}")
        
    # Create a unique subdirectory under the temp VST directory
    base_temp = get_temp_vst_dir()
    unique_id = uuid.uuid4().hex[:8]
    inst_dir = os.path.join(base_temp, f"inst_{unique_id}")
    os.makedirs(inst_dir, exist_ok=True)
    
    # We copy the VST3 bundle (either folder or file)
    vst_name = os.path.basename(vst_path)
    temp_path = os.path.join(inst_dir, vst_name)
    
    if os.path.isdir(vst_path):
        shutil.copytree(vst_path, temp_path)
    else:
        shutil.copy(vst_path, temp_path)
        
    _temp_vst_instances.append(temp_path)
    
    # Load from the copied temporary path
    return load_plugin(temp_path)
