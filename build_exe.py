import PyInstaller.__main__
import os
import shutil

# --- VERSION CONFIGURATION ---
NAME_BASE = "WildlifeTag_Automator"
VERSION = "0.1.0"
BUILD_TYPE = "Alpha" 

# File Name Example: WildlifeTag_Automator_v0.1.0.exe
APP_NAME = f"{NAME_BASE}_v{VERSION}" 
# Folder Name Example: WildlifeTag_Automator_Alpha
FOLDER_NAME = f"{NAME_BASE}_{BUILD_TYPE}"

# 1. Clean previous builds
if os.path.exists("dist"):
    shutil.rmtree("dist")
if os.path.exists("build"):
    shutil.rmtree("build")

# 2. Define PyInstaller Arguments
entry_point = "src/main.py"
args = [
    entry_point,
    f'--name={APP_NAME}', # The .exe name
    '--onefile',
    '--console',
    '--add-data=config.yaml;.', 
    '--hidden-import=pandas',
    '--hidden-import=numpy',
    '--hidden-import=scipy.spatial.transform._rotation_groups',
    '--clean',
    '--noconfirm',
]

print(f">>> Building {APP_NAME}...")
PyInstaller.__main__.run(args)

# --- POST-BUILD ORGANIZATION ---
print(f"\n>>> Organizing Output into '{FOLDER_NAME}'...")

dist_root = "dist"
final_folder_path = os.path.join(dist_root, FOLDER_NAME)

# A. Create the Root Folder Structure
if not os.path.exists(final_folder_path):
    os.makedirs(final_folder_path)
    os.makedirs(os.path.join(final_folder_path, "logs"))        # Log folder
    os.makedirs(os.path.join(final_folder_path, "data_input"))  # Input folder
    os.makedirs(os.path.join(final_folder_path, "data_output")) # Output folder

# B. Move the Executable
src_exe = os.path.join(dist_root, f"{APP_NAME}.exe")
dst_exe = os.path.join(final_folder_path, f"{APP_NAME}.exe")
if os.path.exists(src_exe):
    shutil.move(src_exe, dst_exe)

# C. Copy Config
if os.path.exists("config.yaml"):
    shutil.copy("config.yaml", os.path.join(final_folder_path, "config.yaml"))

# D. Write the User Manual (README.txt) with FINAL DISCLAIMER
readme_path = os.path.join(final_folder_path, "README.txt")
with open(readme_path, "w", encoding="utf-8") as f:
    # --- HEADER DISCLAIMER ---
    f.write("DISCLAIMER: This is an unofficial, independent research tool developed at DPZ.\n")
    f.write("It is NOT affiliated with, authorized, or endorsed by A.S.D. (Alexander Schwartz Developments).\n")
    f.write("\n")

    # --- USER GUIDE ---
    f.write("="*72 + "\n")
    f.write(f"           WILDLIFETAG AUTOMATOR - {BUILD_TYPE} v{VERSION} (USER GUIDE)\n")
    f.write("="*72 + "\n\n")

    f.write("This is the first standalone version of the WildlifeTag Automator.\n")
    f.write("It automatically detects and processes raw data from Docking Station dumps\n")
    f.write("(IMU, Audio, and GPS) and converts them into analysis-ready formats\n")
    f.write("(.CSV, .WAV, .DAT) in a single step.\n\n")

    f.write("-" * 72 + "\n")
    f.write("  KEY FEATURES\n")
    f.write("-" * 72 + "\n")
    f.write("* Automatic Crawling:\n")
    f.write("  No need to manually select subfolders. The tool recursively scans the\n")
    f.write("  input folder, detects the sensor type (IMU/GPS/Audio), and processes\n")
    f.write("  everything it finds.\n\n")

    f.write("* IMU Processing:\n")
    f.write("  Converts raw binary to legacy-format .CSV files (including precise timestamps).\n\n")

    f.write("* Audio Processing:\n")
    f.write("  Converts raw database files into standard .WAV format.\n\n")

    f.write("* GPS Processing:\n")
    f.write("  Extracts 'Snapshot' files ready for GeoTag processing or the secondary\n")
    f.write("  pipeline for the original VesperApp.\n\n")

    f.write("* Reporting & Logs:\n")
    f.write("  - Generates a Metadata .txt file for every recording (Hardware IDs, settings).\n")
    f.write("  - Creates a Summary Report listing exactly which files succeeded/failed.\n")
    f.write("  - Saves detailed Logs for troubleshooting.\n\n")

    f.write("-" * 72 + "\n")
    f.write("  INSTRUCTIONS: HOW TO USE\n")
    f.write("-" * 72 + "\n\n")

    f.write("1. UNZIP THE FOLDER\n")
    f.write(f"   Extract the entire '{FOLDER_NAME}' zip file to your desktop.\n")
    f.write("   (Do not run the .exe from inside the zip file!)\n\n")

    f.write("2. PREPARE YOUR DATA\n")
    f.write("   - Open the 'data_input' folder.\n")
    f.write("   - Copy your raw session folders (e.g., '20250918_vesper1') directly\n")
    f.write("     from the Docking Station dump into this folder.\n")
    f.write("   - You do NOT need to reorganize or rename the folders.\n\n")

    f.write("3. RUN THE TOOL\n")
    f.write(f"   - Double-click '{APP_NAME}.exe'.\n")
    f.write("   - A black terminal window will appear. This is normal!\n")
    f.write("   - It will display live progress for every file being processed.\n\n")

    f.write("4. GET YOUR RESULTS\n")
    f.write("   - When the tool finishes and displays [SUCCESS], press Enter to close.\n")
    f.write("   - Open the 'data_output' folder to find your processed files sorted\n")
    f.write("     by sensor type (imu, aud, gps).\n")
    f.write("   - Check 'data_output/report_cards/' for a summary of the run.\n\n")

    f.write("-" * 72 + "\n")
    f.write("  HOW TO PROCESS THE NEXT BATCH (Session 2, 3, etc.)\n")
    f.write("-" * 72 + "\n")
    f.write("* CLEAN UP FIRST:\n")
    f.write("  Before starting a new batch, please delete the old files from 'data_input'\n")
    f.write("  and move your results out of 'data_output' (save them to your permanent storage).\n\n")
    f.write("  [WHY?] The tool processes EVERYTHING inside the input folder. If you\n")
    f.write("  leave old files there, it will re-scan and re-process them. This is\n")
    f.write("  safe, but wastes time and might be confusing.\n\n")

    f.write("* RESTART:\n")
    f.write("  Just run the .exe again. You do not need to unzip the tool or change\n")
    f.write("  settings again unless your hard drive letter changes.\n\n")

    f.write("-" * 72 + "\n")
    f.write("  TROUBLESHOOTING\n")
    f.write("-" * 72 + "\n")
    f.write("[!] Antivirus Warning:\n")
    f.write("    Windows might say 'Windows protected your PC'. Click 'More Info' ->\n")
    f.write("    'Run Anyway'. (This happens because this is a private Alpha tool and\n")
    f.write("    is not digitally signed by Microsoft).\n\n")

    f.write("[!] Crashes or Errors:\n")
    f.write("    If the black window turns red or shows an error message, please:\n")
    f.write("    1. Take a screenshot or copy the text.\n")
    f.write("    2. Send it to the developer.\n")
    f.write("    (The window is designed to stay open so you have time to capture this).\n\n")
    
    f.write("="*72 + "\n\n")

    # --- FOOTER LEGAL NOTICE ---
    f.write("LEGAL NOTICE:\n")
    f.write("**Non-Affiliation:** This project is not affiliated, associated, authorized, endorsed by, or in any way officially connected with **A.S.D.**\n\n")
    f.write("**Trademarks:** Vesper is a registered trademark of A.S.D. Used solely for identification.\n\n")
    f.write("**Independent Implementation:** Software built from scratch using independent research.\n")

print(f"\n[OK] Build Complete!")
print(f"Go to the 'dist' folder and ZIP the '{FOLDER_NAME}' folder.")