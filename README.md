# Vesper Automator

A specialized automation pipeline for decoding, processing, and organizing multi-sensor data from Vesper Wildlife Tags.

> **Update:** This tool now features custom reverse-engineered parsers for both **IMU data** (`.BIN`) and **Audio data** (`.BIN`), significantly reducing the dependency on the proprietary VesperApp. Native processing is now supported for Accelerometer, Gyroscope, Magnetometer, and Microphone data.

## 🛠️ Build & Quick Start

### 1. Prerequisites

- **Python 3.12+**
- **VesperApp / GeoTag.exe** (Required *only* if processing GPS data).
- **Windows 10/11** (Recommended if using legacy GPS tools).

### 2. Installation

Clone the repository:

```bash
git clone https://github.com/dasilva98/vesper-automator
cd vesper-automator

```

Set up the virtual environment:

```bash
# Create environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

```

Install dependencies:

```bash
pip install -r requirements.txt

```

### 3. Configuration1. Open `config.yaml`.
2. Update `gps_cli_path` (if using GPS features).
3. Set your `raw_data_dir` path.
* *Note: IMU and Audio parsing do not require external app paths.*



### 4. Running the Tool
To run the main processing pipeline:

```bash
python -m src.main

```

## 🧰 Diagnostic Tools
We include standalone analyzers for inspecting raw binary files and diagnosing signal integrity issues. Use these if you encounter corrupted files, weird noises (clicks/pops), or unknown sensor firmware.

**1. Metadata & Header Analyzer (IMU/General):**

```bash
# Check metadata and hidden timestamps
python src/utils/bin_analyzer.py data/raw/00M.BIN

# Inspect header hex dump (first 200 bytes)
python src/utils/bin_analyzer.py data/raw/00M.BIN --hex

```

**2. Audio Signal Diagnostics:**
Detects and analyzes specific Vesper audio artifacts like "Startup Pops" and "64KB Block Clicks".

```bash
# Diagnose signal discontinuities and periodicity
python src/utils/audio_diagnose.py data/raw/0U.BIN

# Inspect specific artifact hex dumps (e.g., show first 10 glitches)
python src/utils/audio_diagnose.py data/raw/0U.BIN --show 10 --threshold 5000

```

## 📂 Project Structure
```text
vesper-automator/
├── config.yaml              # Global settings and paths
├── LICENSE                  # GNU GPLv3 License
├── data/                    # Data storage (Ignored by Git)
│   ├── raw/                 # Input .BIN files
│   └── processed/           # Final Output files (WAV, CSV, Metadata)
├── src/
│   ├── main.py              # Pipeline entry point
│   ├── core/                # Crawler, Logger, Finisher logic
│   ├── utils/               # Shared utilities
│   │   └── audio_diagnose.py# Audio signal integrity tool
|   │   └── bin_analyzer.py  # Binary format inspector & debugger
│   ├── parsers/             # Native Python decoders
│   │   ├── imu_parser.py    # Decodes 10-DOF sensor data
│   │   └── audio_parser.py  # Decodes PCM Audio + Artifact Removal
│   └── wrappers/            # External tool wrappers (GPS only)
└── tests/                   # Unit tests

```

## 🧪 Audio Features
The native audio parser (`src/parsers/audio_parser.py`) automatically handles specific hardware quirks found in Vesper `.BIN` files:

* **Startup Pop Removal:** Trims the initial ~17ms of sensor wake-up noise (`0x8000` DC offset).
* **Click Removal:** Surgically removes the 14-byte metadata footers inserted every 64KB, ensuring seamless audio.
* **Drift Correction:** Extracts embedded timestamps from data blocks into `metadata/*.txt` for precise timing verification.

## 🤝 Contribution Guidelines
We follow **Conventional Commits**. Please format commit messages as follows:

* `Feat: Add native Audio parser`
* `Fix: Resolve 64KB block clicking noise`
* `Docs: Update tools usage`
* `Refactor: Optimize file crawler`
* `Chore: Update requirements`

**Important:** Do not commit raw data files (`.BIN`, `.DAT`) or the virtual environment (`.venv/`).

## ⚖️ Disclaimer
**Unofficial Tool:** This software is an independent, open-source project and is **not affiliated with, endorsed by, or associated with Vesper** or its parent companies. The "Vesper" name is used solely for descriptive purposes to indicate compatibility with their hardware.

**Use at Your Own Risk:** This tool relies on reverse-engineered file formats. While we have verified accuracy against known firmware versions (e.g., FW 112), future firmware updates from the manufacturer may change the binary structure and break compatibility. Always keep a backup of your original raw data (`.BIN` files) before processing.
