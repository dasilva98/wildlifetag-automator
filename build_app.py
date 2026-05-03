import os
import platform
import shutil
import stat
import sys

import PyInstaller.__main__

from src.core.constants import BINARY_NAME_BASE, BUILD_TYPE, VERSION


# --- HELPERS ---
def remove_readonly(func, path, _):
    """
    Error handler for shutil.rmtree.
    If a file is read-only (common on Windows builds), this clears the
    read-only attribute and retries the deletion.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        print(f"Warning: Could not delete {path}: {e}")


# --- VERSION CONFIGURATION ---
# Base Name
APP_NAME = f"{BINARY_NAME_BASE}_v{VERSION}"
FOLDER_NAME = f"{BINARY_NAME_BASE}_{BUILD_TYPE}"

# 1. Clean previous builds
print(">>> Cleaning up previous build artifacts...")
if os.path.exists("dist"):
    # Fix: Use onexc handler to unlock read-only files before deleting
    shutil.rmtree("dist", onexc=remove_readonly)

if os.path.exists("build"):
    shutil.rmtree("build", onexc=remove_readonly)

# 2. Determine OS-specific settings
current_os = platform.system()
path_separator = os.pathsep  # ';' on Windows, ':' on Linux/Mac

# Define the expected output binary name based on OS
if current_os == "Windows":
    binary_name = f"{APP_NAME}.exe"
else:
    binary_name = APP_NAME  # Linux/Mac binaries usually have no extension

# 3. Define PyInstaller Arguments
entry_point = "src/main.py"
args = [
    entry_point,
    f"--name={APP_NAME}",
    "--onefile",
    "--console",
    # Use the dynamic separator here
    f"--add-data=config.yaml{path_separator}.",
    "--hidden-import=pandas",
    "--hidden-import=numpy",
    "--hidden-import=scipy.spatial.transform._rotation_groups",
    "--clean",
    "--noconfirm",
]

print(f">>> Building {APP_NAME} on {current_os}...")
PyInstaller.__main__.run(args)

# --- POST-BUILD ORGANIZATION ---
print(f"\n>>> Organizing Output into '{FOLDER_NAME}'...")

dist_root = "dist"
final_folder_path = os.path.join(dist_root, FOLDER_NAME)

# A. Create the Root Folder Structure
if not os.path.exists(final_folder_path):
    os.makedirs(final_folder_path)
    os.makedirs(os.path.join(final_folder_path, "logs"))  # Log folder
    os.makedirs(os.path.join(final_folder_path, "data_input"))  # Input folder
    os.makedirs(os.path.join(final_folder_path, "data_output"))  # Output folder

# B. Move the Executable
# We look for the binary name determined by the OS above
src_exe = os.path.join(dist_root, binary_name)
dst_exe = os.path.join(final_folder_path, binary_name)

if os.path.exists(src_exe):
    shutil.move(src_exe, dst_exe)
    print(f"[Move] Moved binary to {dst_exe}")
else:
    print(f"[Error] Could not find build artifact: {src_exe}")

# C. Copy Config
if os.path.exists("config.yaml"):
    shutil.copy("config.yaml", os.path.join(final_folder_path, "config.yaml"))

# D. Copy External Tools if they exist
src_tools = "external_tools"
dst_tools = os.path.join(final_folder_path, "external_tools")

if os.path.exists(src_tools):
    shutil.copytree(src_tools, dst_tools, dirs_exist_ok=True)
    print(f"[OK] Copied external tools to {dst_tools}")
else:
    print(
        f"[Warning] 'external_tools' folder not found. GeoTag features will be unavailable."
    )

# E. Write the User Manual (README.txt)
readme_path = os.path.join(final_folder_path, "README.txt")
with open(readme_path, "w", encoding="utf-8") as f:
    f.write(f"WILDLIFETAG AUTOMATOR v{VERSION}\n")
    f.write("===============================================================\n")
    f.write("A pipeline for decoding IMU, Audio, and GPS data from Vesper Tags.\n\n")

    f.write("[ QUICK START ]\n")
    f.write("1. Copy your raw session folders into 'data_input'.\n")
    f.write("   The tool scans recursively, so subfolders inside session folders\n")
    f.write("   are handled automatically. Example structure:\n")
    f.write("     data_input/\n")
    f.write("       20250929_tag1/\n")
    f.write("         imu/\n")
    f.write("           0M.BIN, 1M.BIN, ...\n")
    f.write("         aud/\n")
    f.write("           0U.BIN, 1U.BIN, ...\n")
    f.write("         gps/\n")
    f.write("           0G.BIN, 1G.BIN, ...\n\n")
    f.write("2. Double-click the .exe file.\n")
    f.write("3. Wait for the process to finish (check the window for progress).\n")
    f.write("4. Find your results in 'data_output'.\n\n")

    f.write("[ OUTPUTS ]\n")
    f.write("- IMU:  Converted to .CSV with precise per-packet timestamps.\n")
    f.write("        On tags with extended configuration, also includes\n")
    f.write("        Temperature (C) and Barometric Pressure (hPa) columns.\n")
    f.write("- AUD:  Converted to .WAV (48kHz, metadata artifacts removed).\n")
    f.write("- GPS:  Converted to .DAT snapshots and decoded to .CSV\n")
    f.write("        (requires GeoTag tools in external_tools/CG/ — see below).\n\n")

    f.write("[ GPS DECODING — EXTERNAL TOOLS REQUIRED ]\n")
    f.write(
        "GPS coordinate decoding requires two tools from your VesperApp installation.\n"
    )
    f.write("Copy them into the following locations:\n")
    f.write("  external_tools/CG/GeoTag/       <- GeoTag.exe and its sidecar files\n")
    f.write("  external_tools/CG/GeoTagEngine/ <- GeoTagEngine.exe and its DLLs\n")
    f.write("If these are missing, all other sensors still process normally.\n")
    f.write("The processing report will flag missing GPS tools explicitly.\n\n")

    f.write("[ TROUBLESHOOTING ]\n")
    f.write("- If the window closes immediately, check the 'logs' folder.\n")
    f.write(
        "- If you see 'Windows protected your PC', click 'More Info' -> 'Run Anyway'.\n"
    )
    f.write("- GPS not decoding? Ensure GeoTag.exe is in external_tools/CG/GeoTag/\n")
    f.write("  and GeoTagEngine.exe is in external_tools/CG/GeoTagEngine/.\n\n")

    f.write("[ HOW TO PROCESS THE NEXT BATCH ] (Session 2, 3, etc.)\n")

    f.write("* CLEAN UP FIRST:\n")
    f.write(
        "  Before starting a new batch, please delete the old files from 'data_input'\n"
    )
    f.write(
        "  and move your results out of 'data_output' (save them to your permanent storage).\n\n"
    )
    f.write("  [WHY?] The tool processes EVERYTHING inside the input folder. If you\n")
    f.write("  leave old files there, it will re-scan and re-process them. This is\n")
    f.write("  safe, but wastes time and might be confusing.\n\n")

    f.write("* RESTART:\n")
    f.write("  Just run the .exe again. You do not need to unzip the tool or change\n")
    f.write("  settings again unless your hard drive letter changes.\n\n")

    f.write("===============================================================\n")
    f.write("LEGAL NOTICE:\n")
    f.write(
        "This software is an independent research tool. It is NOT affiliated with,\n"
    )
    f.write("authorized, or endorsed by A.S.D. (Alexander Schwartz Developments).\n")
    f.write("Vesper is a registered trademark of A.S.D.\n")

print(f"\n[OK] Build Complete!")
if current_os == "Windows":
    print(f"Go to the 'dist' folder and ZIP the '{FOLDER_NAME}' folder.")
else:
    print(
        f"⚠️  NOTE: You built this on {current_os}. The binary '{binary_name}' will NOT run on Windows OS."
    )
