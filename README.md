> **DISCLAIMER** This is an unofficial, independent research tool developed by students at the University of Göttingen for the German Primate Center (DPZ). It is **not** affiliated with A.S.D. (Alexander Schwartz Developments). All product names are property of their respective owners and are used here solely for identification and compatibility purposes.

🐒 ⚙️ WildlifeTag Automator
=====================
![Version](https://img.shields.io/badge/version-1.2-114488)
[![DPZ Lab][dpz-badge]](https://www.dpz.eu/en/about-us)
![License](https://img.shields.io/badge/License-GPLv3-blue)

A specialized automation pipeline for decoding, processing, and organizing multi-sensor data from Vesper Wildlife Tags.

This tool serves as a "One-Click" solution to convert raw binary dumps from wildlife tags into analysis-ready formats. It natively handles proprietary binary decoding, timestamp synchronization, and artifact removal, while wrapping external tools for coordinate decoding.

🚀 Key Features
-----------------------

The native parsers automatically handle specific hardware quirks found in the raw binary files:

### 1. Signal Processing & Cleaning
* **IMU Processing:** Converts raw `.BIN` sensor data directly into standard `.CSV` files. It automatically identifies valid sessions and flags corrupt or empty recordings.
* **Audio Processing:** Converts raw `.BIN` files into standard `.WAV` format (48kHz).
    * *Startup Pop Removal:* Automatically trims the initial ~17ms of sensor wake-up noise.
    * *Click Removal:* Surgically removes the 14-byte metadata footers inserted every 64KB, ensuring seamless audio.
* **GPS Processing:** Decodes proprietary GPS binary files into `.DAT` snapshots; these files are then automatically processed by 'GeoTag.exe' to generate coordinate data points.

### 2. Reporting & Analytics (New)
The new `RunReporter` engine provides better insights into your recording's efficiency:
* **Session Inventory:** Automatically groups files by "Session ID" (Animal/Tag) and calculates the exact recording window (Start $\to$ End).
* **Scientific Yield:** Calculates total **Audio Hours** and **GPS Fix Efficiency** (Fixes vs. Attempts) per session.
* **Run Time Tracking:** Tracks the total execution time of the processing pipeline.
* **Traffic Light Stats:** Distinguishes between **SUCCESS** (Green), **WARNING** (Yellow - e.g., Empty File), and **FAILURE** (Red - Crash).

### 3. Integrated GeoTag Pipeline
* **Automated Wrapping:** The tool automatically launches `GeoTag.exe` (if present in `external_tools/`) to decode snapshots into coordinates.
* **CSV Finalization:** Parses the output `Track-geoTag.csv`, extracts the true Start/End timestamps, and renames it to `START_END_SessionID.csv` for easy sorting.

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

    # Check metadata, precision timestamps, and header type
    python tools/header_inspector.py data/raw/00M.BIN
    
    # Inspect header hex dump (first 200 bytes)
    python tools/header_inspector.py data/raw/00M.BIN --hex

### 2. Audio Signal Diagnostics

    # Diagnose signal discontinuities and periodicity
    python tools/audio_inspector.py data/raw/0U.BIN

📦 Creating the Standalone .EXE
-----------------------
To build the distribution folder:

    python build_app.py

This will create a `dist/WildlifeTag_Automator_Beta` folder containing the executable, config, and required structure.

*Note: You must manually copy your `external_tools/` folder into the `dist/` folder if the build script does not detect it automatically.*

📂 Project Structure
--------------------

    wildlifetag-automator/
    ├── config.yaml              # Global settings and paths
    ├── requirements.txt         # Python dependencies
    ├── build_app.py             # PyInstaller script for standalone builds
    ├── external_tools/          # Place GeoTag.exe here (Ignored by Git)
    ├── tools/                   # Standalone diagnostic scripts
    │   ├── header_inspector.py  # Binary format inspector & debugger
    │   └── audio_inspector.py   # Signal integrity checker
    ├── data/                    # Data storage (Ignored by Git)
    │   ├── raw/                 # Input .BIN files
    │   └── processed/           # Final Output files
    │       ├── imu/             # CSVs
    │       ├── aud/             # WAVs
    │       ├── report_cards/    # Text summaries
    │       └── gps/
    │           ├── snapshots/   # Intermediate .DAT files (Per Session)
    │           └── decoded/     # Final Coordinates (Per Session)
    └── src/
        ├── main.py              # Pipeline entry point
        ├── core/                # Core Application Logic
        │   ├── file_scanner.py  # Crawls raw data & maps sessions
        │   ├── export_manager.py# Handles file saving & conversions
        │   ├── run_reporter.py  # Generates run statistics & summaries
        │   ├── binary_decoder.py# Centralized binary decoding math
        │   ├── logger.py        # Logging configuration
        │   └── constants.py     # Versioning & magic numbers
        ├── parsers/             # Native Python decoders
        │   ├── imu_parser.py    # Decodes 10-DOF sensor data to CSV
        │   ├── audio_parser.py  # Decodes PCM Audio + Artifact Removal
        │   └── gps_parser.py    # Decodes GPS Binary to Snapshot (.DAT)
        └── wrappers/            # External tool wrappers
            └── geotag_wrapper.py# Wrapper for Vesper GeoTag.exe

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

1.  **Non-Affiliation:** This project is not in any way officially connected with A.S.D. (Alexander Schwartz Developments), or any of its subsidiaries. The official A.S.D. website can be found at asd-tech.com.
2.  **Trademarks:** The names Vesper, VesperTag, and VesperApp are registered trademarks of A.S.D. Use of these names within this project is strictly for nominative purposes to identify the specific hardware data formats this tool is designed to process.
3.  **Independent Implementation:** While public documentation and legacy references were consulted to understand data structures, this Software was built from scratch. The processing architecture was independently developed using modern data science libraries to ensure high performance and data integrity. No source code was translated or ported from the original manufacturer's software.

[dpz-badge]: https://img.shields.io/badge/Developed_at-DPZ-009941?logo=data:image/svg+xml;base64,PHN2ZyB2ZXJzaW9uPSIxLjIiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIgdmlld0JveD0iMCAwIDQ2MiA0NjAiIHdpZHRoPSI0NjIiIGhlaWdodD0iNDYwIj4KCTxzdHlsZT4KCQkuczAgeyBmaWxsOiAjMDA5OTQxIH0gCgk8L3N0eWxlPgoJPGcgaWQ9IkJhY2tncm91bmQiPgoJCTxwYXRoIGlkPSJQYXRoIDEiIGZpbGwtcnVsZT0iZXZlbm9kZCIgY2xhc3M9InMwIiBkPSJtMjM2IDAuNDZjMjUuMjIgMC4zMSAyNy4yMiAwLjQ3IDQxLjUgMy40NiA4LjI1IDEuNzMgMjEuMDcgNS4xOSAyOC41IDcuNjggNy40MyAyLjQ5IDE5LjggNy42IDI3LjUgMTEuMzUgNy43IDMuNzUgMTguNzMgOS45NSAyNC41IDEzLjc3IDUuNzcgMy44MiAxNC4xIDkuOCAxOC41IDEzLjI4IDQuNCAzLjQ4IDEzLjE5IDExLjU0IDE5LjUzIDE3LjkxIDYuMzQgNi4zOCAxNS4zOSAxNi43NiAyMC4xIDIzLjA5IDQuNzIgNi4zMyAxMC44NyAxNS4zMyAxMy42NyAyMCAyLjggNC42OCA3LjgxIDE0LjI0IDExLjE0IDIxLjI1IDMuMzMgNy4wMSA2LjA2IDEzLjY1IDYuMDYgMTQuNzUgMCAxLjEgMC40IDIuMTEgMC44OCAyLjI1IDAuNDkgMC4xNCAyLjQ3IDUuMiA0LjQxIDExLjI1IDEuOTQgNi4wNSA0LjQzIDE1LjI4IDUuNTMgMjAuNSAxLjEgNS4yMiAyLjU0IDEzLjU1IDMuMiAxOC41cTEuMiA5IDAuNzEgMzYuNWMtMC40NCAyNC44LTAuNzQgMjguNy0zLjExIDM5Ljc1LTEuNDQgNi43NC00LjI1IDE3LjMxLTYuMjQgMjMuNS0xLjk5IDYuMTktNC4wMSAxMS4zNi00LjUgMTEuNS0wLjQ4IDAuMTQtMC44OCAxLjE1LTAuODggMi4yNSAwIDEuMS0xLjgyIDYuMTYtNC4wNSAxMS4yNS0yLjIzIDUuMDktNi4zNSAxMy4zLTkuMTYgMTguMjUtMi44MSA0Ljk1LTcuOSAxMy4wNS0xMS4zMSAxOC0zLjQxIDQuOTUtOS43OSAxMy4yNy0xNC4xOCAxOC41LTQuMzkgNS4yMy0xMS43NiAxMy4wNS0xNi4zOSAxNy4zOS00LjYzIDQuMzQtMTIuMDEgMTAuNzgtMTYuNDEgMTQuMzEtNC40IDMuNTMtMTMuMTggOS43MS0xOS41IDEzLjczLTYuMzIgNC4wMi0xNS4yMSA5LjE2LTE5Ljc1IDExLjQ0LTQuNTQgMi4yNy0xMi42NCA1Ljg4LTE4IDguMDItNS4zNiAyLjEzLTE0LjI1IDUuMjMtMTkuNzUgNi44OC01LjUgMS42NC0xNC43MyAzLjk0LTIwLjUgNS4xLTUuNzcgMS4xNS0xNC41NSAyLjU1LTE5LjUgMy4xMS00Ljk1IDAuNTUtMTIuOTQgMS4wMS0yNi41IDEuMDJ2LTExNWgxMy43NWM3LjU2IDAgMTcuNTctMC40NyAyMi4yNS0xLjA1IDQuNjgtMC41OCAxMS44Ny0xLjc0IDE2LTIuNTcgNC4xMi0wLjgzIDEyLjIzLTMuMDggMTgtNSA1Ljc3LTEuOTIgMTMuODctNS4xIDE4LTcuMDYgNC4xMi0xLjk3IDExLjEtNS45MiAxNS41LTguNzggNC40LTIuODUgMTEuODItOC4zOSAxNi41LTEyLjMxIDQuNjgtMy45MiAxMC43NS05LjY5IDEzLjUtMTIuODEgMi43NS0zLjEyIDcuNTctOS4xMSAxMC43MS0xMy4zIDMuMTMtNC4xOSA3Ljk0LTExLjg5IDEwLjY4LTE3LjEyIDIuNzUtNS4yMyA2LjU3LTE0LjIzIDguNTEtMjAgMS45My01Ljc3IDQuMjYtMTQuNzggNS4xNy0yMCAxLjI3LTcuMzUgMS41My0xMy4yNCAxLjEyLTI2LTAuMzEtOS41Ny0xLjIyLTE5LjY1LTIuMTgtMjQtMC45MS00LjEyLTMuMDItMTEuNTUtNC43LTE2LjUtMS42OC00Ljk1LTUuMDktMTMuMDUtNy41Ny0xOC0yLjQ4LTQuOTUtNi42My0xMi4xNS05LjIzLTE2LTIuNTktMy44NS03LjU5LTEwLjM1LTExLjExLTE0LjQ0LTMuNTItNC4wOC05Ljc4LTEwLjMxLTEzLjktMTMuODItNC4xMy0zLjUxLTkuOTgtOC4wMy0xMy0xMC4wMy0zLjAyLTItOS41NS01Ljc1LTE0LjUtOC4zNC00Ljk1LTIuNTktMTMuNzMtNi4zNS0xOS41LTguMzUtNS43Ny0yLTE1LjU2LTQuNTEtMjEuNzUtNS41OC03LjA3LTEuMjItMTUuOS0xLjk0LTIzLjc1LTEuOTQtNy45MyAwLTE2LjYxIDAuNzItMjMuNzUgMS45Ni02LjE5IDEuMDgtMTUuNTMgMy4zMS0yMC43NSA0Ljk1LTUuMjIgMS42NS0xNC40NSA1LjUxLTIwLjUgOC42LTYuMDUgMy4wOC0xNC41MyA4LjE2LTE4Ljg1IDExLjI5LTQuMzIgMy4xNC0xMS4yNiA4Ljg1LTE1LjQyIDEyLjctNC4xNiAzLjg1LTEwLjQ3IDEwLjYtMTQuMDIgMTUtMy41NCA0LjQtOC44MyAxMi4wNS0xMS43NSAxNy0yLjkyIDQuOTUtNi45NCAxMi44Mi04Ljk0IDE3LjUtMiA0LjY4LTQuNzQgMTIuMzItNi4wNyAxNy0xLjM0IDQuNjgtMy4xMSAxMy0zLjk0IDE4LjUtMC44NiA1LjczLTEuNSAxNi45NC0xLjUxIDQyLjVsLTExNC41LTAuNS0wLjMtNmMtMC4xNy0zLjMgMC40My0xMi4zIDEuMzItMjAgMC45LTcuOCAzLjMyLTIwLjY0IDUuNDYtMjkgMi4xMi04LjI1IDUuNDktMTkuMjggNy41LTI0LjUgMi01LjIyIDYuMDQtMTQuNDUgOC45OS0yMC41IDIuOTQtNi4wNSA3LjktMTUuMDUgMTEuMDEtMjAgMy4xMS00Ljk1IDguODktMTMuMjggMTIuODMtMTguNSAzLjk0LTUuMjIgMTMuMDItMTUuMzUgMjAuMTgtMjIuNSA3LjE2LTcuMTUgMTcuNTEtMTYuNCAyMy4wMS0yMC41NCA1LjUtNC4xNSAxNS40LTEwLjc3IDIyLTE0LjcyIDYuNi0zLjk1IDE4LjE5LTkuOSAyNS43NS0xMy4yMSA3LjU2LTMuMzIgMTguODEtNy41NyAyNS05LjQ1IDYuMTktMS44OCAxNS45Ny00LjM4IDIxLjc1LTUuNTYgNS43OC0xLjE4IDEzLjY1LTIuNTMgMTcuNS0zLjAxIDMuODUtMC40NyAxOC45My0wLjcyIDMzLjUtMC41NXptLTExMyAyMzEuNTRoMTAydjEwMmgtMTAyeiIvPgoJPC9nPgo8L3N2Zz4=