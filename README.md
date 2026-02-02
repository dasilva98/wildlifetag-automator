> **DISCLAIMER** This is an unofficial, independent research tool developed by students at the University of Göttingen for the German Primate Center (DPZ). It is **not** affiliated with, authorized, or endorsed by A.S.D. (Alexander Schwartz Developments). All product names are property of their respective owners and are used here solely for identification and compatibility purposes.

🐒 ⚙️ WildlifeTag Automator
=====================
> **Version:** 1.1 (Beta)

A specialized automation pipeline for decoding, processing, and organizing multi-sensor data from Vesper Wildlife Tags.

This tool serves as a "One-Click" solution to convert raw binary dumps from wildlife tags into analysis-ready formats. It natively handles proprietary binary decoding, timestamp synchronization, and artifact removal, while wrapping external tools for coordinate decoding.

🚀 Key Features & Technical Capabilities
-----------------------

The native parsers automatically handle specific hardware quirks found in the raw binary files:

### 1. Smart Parsing & Decoding
* **IMU Processing:** Converts raw `.BIN` sensor data directly into standard `.CSV` files. It automatically identifies valid sessions and flags corrupt or empty recordings.
* **Audio Processing:** Converts raw `.BIN` files into standard `.WAV` format (48kHz).
    * *Startup Pop Removal:* Automatically trims the initial ~17ms of sensor wake-up noise.
    * *Click Removal:* Surgically removes the 14-byte metadata footers inserted every 64KB, ensuring seamless audio.
* **GPS Processing:** Decodes proprietary GPS binary files into `.DAT` snapshots, automatically correcting timestamp errors (e.g., Year 2037 bug) and formatting the data for the Vesper GeoTag software.

### 2. Per-Session Isolation
To prevent data mixing between different animals/tags:
* The tool identifies sessions automatically based on folder structure.
* GPS snapshots are isolated into session-specific subfolders (`processed/gps/snapshots/Session_ID/`).
* External decoding tools are run strictly on these isolated folders.

### 3. Integrated GeoTag Pipeline
* **Automated Wrapping:** The tool automatically launches `GeoTag.exe` (if present in `external_tools/`) to decode snapshots into coordinates.
* **CSV Finalization:** Parses the output `Track-geoTag.csv`, extracts the true Start/End timestamps, and renames it to `START_END_SessionID.csv` for easy sorting.

### 4. Reporting & Logging
* **Traffic Light Stats:** Distinguishes between **SUCCESS** (Green), **WARNING** (Yellow - e.g., Empty File), and **FAILURE** (Red - Crash).
* **Inventory Dashboard:** Generates a detailed "Session Inventory" table showing exactly which sensors recorded data and for how long.
* **Scientific Yield:** Automatically calculates total Audio Duration (hours) and GPS Fix counts.
* **Report Cards:** Generates a detailed text summary after every run in `data/processed/report_cards/`.

🛠️ Build & Quick Start
-----------------------

### 1. Prerequisites

* **Python 3.12+**
* **GeoTag.exe** and **GeoTagEngine.exe** (both from the VesperApp installation folder) These are required for GPS coordinate decoding, and should be placed in `external_tools/`.
* **Windows 10/11** (Recommended if using `GeoTag` and `GeoTagEngine` GPS tools).

### 2. Installation

Clone the repository:

    git clone https://github.com/dasilva98/wildlifetag-automator
    cd wildlifetag-automator

Set up the virtual environment:

    # Create environment
    python -m venv .venv
    
    # Activate (Windows)
    .venv\Scripts\activate
    
    # Activate (Linux/Mac)
    source .venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

### 3. Configuration

1.  Open `config.yaml`.
2.  Update `raw_data_folder` to point to your input directory.
3.  Update `processed_folder` to point to where you want the results.
4.  **Note:** The tool automatically looks for `GeoTag.exe` inside the `external_tools/` folder. No path configuration is needed for GPS tools.

### 4. Running the Tool

To run the main processing pipeline:

    python -m src.main

🧰 Diagnostic Tools
-------------------

We include standalone analyzers for inspecting raw binary files and diagnosing signal integrity issues.

### 1. Metadata & Header Analyzer (IMU/General)

    # Check metadata and hidden timestamps
    python src/utils/bin_analyzer.py data/raw/00M.BIN
    
    # Inspect header hex dump (first 200 bytes)
    python src/utils/bin_analyzer.py data/raw/00M.BIN --hex

### 2. Audio Signal Diagnostics

    # Diagnose signal discontinuities and periodicity
    python src/utils/audio_diagnose.py data/raw/0U.BIN

📦 Creating the Standalone .EXE
-----------------------
To build the distribution folder:

    python build_exe.py

This will create a `dist/WildlifeTag_Automator_Beta` folder containing the executable, config, and required structure.

*Note: You must manually copy your `external_tools/` folder into the `dist/` folder if the build script does not detect it automatically.*

📂 Project Structure
--------------------

    wildlifetag-automator/
    ├── config.yaml              # Global settings and paths
    ├── build_exe.py             # PyInstaller script for standalone builds
    ├── external_tools/          # Place GeoTag.exe here (Ignored by Git)
    ├── data/                    # Data storage (Ignored by Git)
    │   ├── raw/                 # Input .BIN files
    │   └── processed/           # Final Output files
    │       ├── imu/             # CSVs
    │       ├── aud/             # WAVs
    │       ├── report_cards/    # Text summaries
    │       └── gps/
    │           ├── snapshots/   # Intermediate .DAT files (Per Session)
    │           └── decoded/     # Final Coordinates (Per Session)
    ├── src/
    │   ├── main.py              # Pipeline entry point
    │   ├── core/                # Crawler, Logger, Finisher logic
    │   ├── utils/               # Shared utilities
    │   │   └── bin_analyzer.py  # Binary format inspector & debugger
    │   ├── parsers/             # Native Python decoders
    │   │   ├── imu_parser.py    # Decodes 10-DOF sensor data to CSV
    │   │   ├── audio_parser.py  # Decodes PCM Audio + Artifact Removal
    │   │   └── gps_parser.py    # Decodes GPS Binary to Snapshot (.DAT)
    │   └── wrappers/            # External tool wrappers

🤝 Contribution
--------------------------
We follow Conventional Commits. Please format commit messages as follows:

* `Feat`: Add native Audio parser
* `Fix`: Resolve 64KB block clicking noise
* `Docs`: Update tools usage
* `Refactor`: Optimize file crawler

**Important:** Do not commit raw data files (.BIN, .DAT).

📜 License
----------------------------
This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.

⚖️ Legal Notice & Disclaimer
----------------------------
**WildlifeTag Automator** (the "Software") is an unofficial, independent, open-source tool.

1.  **Non-Affiliation:** This project is not affiliated, associated, authorized, endorsed by, or in any way officially connected with A.S.D. (Alexander Schwartz Developments), or any of its subsidiaries. The official A.S.D. website can be found at asd-tech.com.
2.  **Trademarks:** The names Vesper, VesperTag, and VesperApp are registered trademarks of A.S.D. Use of these names within this project is strictly for nominative purposes to identify the specific hardware data formats this tool is designed to process.
3.  **Independent Implementation:** While public documentation and legacy references were consulted to understand data structures, this Software was built from scratch. The processing architecture was independently developed using modern data science libraries to ensure high performance and data integrity. No source code was translated or ported from the original manufacturer's software.