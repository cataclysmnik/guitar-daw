# Graphite Guitar DAW

[![GitHub Release](https://img.shields.io/github/v/release/cataclysmnik/graphite?color=000000&label=Release&style=flat-square)](https://github.com/cataclysmnik/graphite/releases)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg?color=000000&style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg?color=000000&style=flat-square)](LICENSE)

Graphite is a lightweight, high-performance Digital Audio Workstation (DAW) tailored specifically for guitarists. Built with Python and PySide6, it delivers a sleek, low-latency recording environment optimized for real-time performance and host-based digital signal processing (DSP). 

With a premium dark aesthetic inspired by the "Nothing" design language, Graphite features a custom frameless window, responsive vector-based waveforms, and support for VST3 plugins via Spotify's `pedalboard` engine.

---

## Key Features

- **High-Performance Audio Engine:** 
  - Low-latency real-time audio thread utilizing `sounddevice` and `pedalboard`.
  - Lock-free and allocation-free audio callback path to prevent audio dropouts (crackles/pops) even with complex VST3 chains.
  - Wide hardware driver support including ASIO (recommended on Windows), WASAPI, DirectSound, and MME.
- **Dynamic Auto-Arm Zones:**
  - Create timeline-based auto-arm regions to automatically arm and disarm tracks at specific parts of a song.
  - Supports non-destructive recording clip trimming to match defined arming zones exactly.
  - Move, resize, and drag auto-arm regions between tracks.
- **Advanced Track Arming Modes:**
  - **Standard**: Manual toggling of track recording states.
  - **Union**: Allows simultaneous recording on multiple armed tracks.
  - **Exclusive**: Arming one track automatically disarms all other tracks to streamline single-input takes.
- **VST3 Host & Signal Flow:**
  - Load, reorder, and configure VST3 plugins dynamically.
  - A visual, vertical **Signal Flow Editor** to easily inspect and reorder the effects chain.
  - Built-in pedal simulations: `TubeOverdrive`, Reverb, Delay, Chorus, and Compressor.
- **Built-in Guitarist Tools:**
  - **Guitar Tuner**: A high-precision chromatic tuner.
  - **Visual Metronome**: Metronome with custom sound options and tap tempo.
- **Modern Timeline & Mixer:**
  - Non-destructive clip editing, resizing, and track management.
  - Dedicated multi-channel mixer with pan, volume faders, and peak meters.
  - Drag-and-drop support to import external `.wav` files directly into track lanes.
- **Project Serialization & Export:**
  - Save full sessions including all track layouts, audio clips, and full VST3 plugin states in JSON-based `.graphite` format.
  - Export final master mixes to high-fidelity WAV (16/24-bit) or MP3 formats.

---

## Installation

### Method 1: Using Pre-built Installer (Recommended for general use)
If you do not want to install Python, you can use the standalone installer:
1. Navigate to the **[Releases Tab](https://github.com/cataclysmnik/graphite/releases)** on GitHub.
2. Download the latest installer executable (e.g., `Graphite_0.9.0_Installer.exe`).
3. Run the installer and follow the setup wizard to install it normally.

> [!NOTE]
> Standalone builds include a bundled Python runtime and all necessary dependencies out-of-the-box.

### Method 2: Installing from Source (Git Clone)
To run or develop Graphite locally from source:

#### 1. Prerequisites
Ensure you have the following installed on your machine:
- **Python 3.10 or higher** (Ensure Python is added to your system `PATH`)
- **ASIO Drivers** (e.g., ASIO4ALL or your audio interface's native ASIO driver) for low-latency recording.

#### 2. Clone the Repository
```bash
git clone https://github.com/cataclysmnik/graphite.git
cd graphite
```

#### 3. Create a Virtual Environment (Recommended)
```bash
python -m venv .venv
# Activate on Windows:
.venv\Scripts\activate
# Activate on macOS/Linux:
source .venv/bin/activate
```

#### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 5. Launch the Application
```bash
python main.py
```

---

## Usage Guide

### 1. Configure Your Audio Interface
Before recording, set up your audio settings to minimize latency:
1. Open settings via **Audio > Audio Device Settings...** (or press `Ctrl + ,`).
2. Select your driver model (choose **ASIO** on Windows for optimal performance).
3. Select your input/output devices and set the active channel range.
4. Set the buffer size (e.g., **128** or **256** samples) to achieve optimal latency without introducing buffer under-runs.

### 2. Working with Auto-Arm Zones
Auto-arm zones allow you to define exactly when specific tracks should record or play back:
- **Create a Zone:** Hold `Shift` and double-click in an empty space on any track lane.
- **Move / Drag:** Click and drag the center of the zone to reposition it in time or move it to a different track.
- **Resize:** Click and drag the left or right edges of the zone to adjust the exact start and end times.
- **Record:** When recording starts, Graphite will automatically arm and record audio only when the playhead enters these zones.

### 3. Adding and Reordering Effects
- Select a track to display its effects rack in the bottom dock.
- Click **Add Built-in Effect** to add high-quality native guitar pedals, or click **Load VST3** to load external plugin files (`.vst3`).
- Drag-and-drop effects in the list to change their placement in the audio processing chain.

---

## Project Structure

- `main.py` - Application entry point; handles GUI bootstrapping.
- `audio_engine.py` - Core lock-free audio thread handling real-time I/O, VSTs, and mixing.
- `project_manager.py` - Controls saving/loading of `.graphite` project files.
- `theme_utils.py` - Custom frameless title bar and Windows DWM integration.
- `widgets/` - PySide6 custom widgets:
  - `main_window.py` - Main workspace coordinator.
  - `timeline.py` - Timeline arranger, auto-arm zones, and ruler.
  - `mixer.py` - Master faders and channel strip components.
  - `effects_rack.py` - Built-in pedals and VST hosting interface.
  - `tuner.py` / `metronome.py` - Precision utilities for guitar practice.

---

## Troubleshooting

- **No Sound / Audio Device Error:** Make sure your audio interface is not being used exclusively by another program. Select a different host API (e.g. WASAPI instead of ASIO) if testing on a system without dedicated ASIO hardware.
- **Audio Crackles or Pops:** Increase your buffer size (e.g., from 64 to 128 or 256 samples) in the Audio Settings dialog.
- **VST3 Failures:** Ensure you are loading 64-bit VST3 plugins (`.vst3` folders or files) that match your system architecture.

---

## License

Graphite is distributed under the MIT License. See `LICENSE` for details.