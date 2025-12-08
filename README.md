# Vesper Automator

A specialized automation pipeline for decoding, processing, and organizing multi-sensor data from Vesper Wildlife Tags.

> **Update:** This tool now features a custom reverse-engineered parser for IMU data (`.BIN`), removing the dependency on the proprietary VesperApp for accelerometer, gyroscope, and magnetometer processing.

## 🛠️ Build & Quick Start

### 1. Prerequisites

- **Python 3.12+**
- **VesperApp / GeoTag.exe** (Required *only* if processing GPS or Audio data).
- **Windows 10/11** (Recommended for legacy tool compatibility).

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

### 3. Configuration

1. Open `config.yaml`.
2. Update `gps_cli_path` (if using GPS features).
3. Set your `raw_data_dir` path.
   * *Note: IMU parsing does not require external app paths.*

### 4. Running the Tool

To run the main processing pipeline:

```bash
python -m src.main
```

## 🧰 Diagnostic Tools

We include a standalone analyzer for inspecting raw binary files. Use this if you encounter corrupted files or unknown sensor firmware.

**Binary Analyzer:**
```bash
# Check metadata and hidden timestamps
python tools/bin_analyzer.py data/raw/00M.BIN

# Inspect header hex dump (first 200 bytes)
python tools/bin_analyzer.py data/raw/00M.BIN --hex

# Sanity check first 3 data packets
python tools/bin_analyzer.py data/raw/00M.BIN --data
```

## 📂 Project Structure

```text
vesper-automator/
├── config.yaml              # Global settings and paths
├── LICENSE                  # GNU GPLv3 License
├── data/                    # Data storage (Ignored by Git)
│   ├── raw/                 # Input .BIN files
│   └── processed/           # Final Output files
├── tools/                   # Standalone utilities
│   └── bin_analyzer.py      # Binary format inspector & debugger
├── src/
│   ├── main.py              # Pipeline entry point
│   ├── core/                # Crawler, Logger, Finisher logic
│   ├── parsers/             # Native Python decoders (imu_parser.py)
│   └── wrappers/            # External tool wrappers (GPS/Audio)
└── tests/                   # Unit tests
```

## 🤝 Contribution Guidelines

We follow **Conventional Commits**. Please format commit messages as follows:

- `Feat: Add native IMU parser`
- `Fix: Resolve BCD timestamp offset`
- `Docs: Update tools usage`
- `Refactor: Optimize file crawler`
- `Chore: Update requirements`

**Important:** Do not commit raw data files (`.BIN`, `.DAT`) or the virtual environment (`.venv/`).

## ⚖️ Disclaimer

**Unofficial Tool:** This software is an independent, open-source project and is **not affiliated with, endorsed by, or associated with Vesper** or its parent companies. The "Vesper" name is used solely for descriptive purposes to indicate compatibility with their hardware.

**Use at Your Own Risk:** This tool relies on reverse-engineered file formats. While we have verified accuracy against known firmware versions (e.g., FW 112), future firmware updates from the manufacturer may change the binary structure and break compatibility. Always keep a backup of your original raw data (`.BIN` files) before processing.
