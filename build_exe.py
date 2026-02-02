import PyInstaller.__main__
import os
import shutil
import platform
import sys
import stat

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
NAME_BASE = "WildlifeTag_Automator"
VERSION = "1.1"
BUILD_TYPE = "Beta"

# Base Name (No extension yet)
APP_NAME = f"{NAME_BASE}_v{VERSION}" 
FOLDER_NAME = f"{NAME_BASE}_{BUILD_TYPE}"

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
    f'--name={APP_NAME}',
    '--onefile',
    '--console',
    # Use the dynamic separator here
    f'--add-data=config.yaml{path_separator}.', 
    '--hidden-import=pandas',
    '--hidden-import=numpy',
    '--hidden-import=scipy.spatial.transform._rotation_groups',
    '--clean',
    '--noconfirm',
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
    os.makedirs(os.path.join(final_folder_path, "logs"))        # Log folder
    os.makedirs(os.path.join(final_folder_path, "data_input"))  # Input folder
    os.makedirs(os.path.join(final_folder_path, "data_output")) # Output folder

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
    print(f"[Warning] 'external_tools' folder not found. GeoTag features will fail.")

# E. Write the User Manual (README.txt)
readme_path = os.path.join(final_folder_path, "README.txt")
with open(readme_path, "w", encoding="utf-8") as f:
    f.write(f"WILDLIFETAG AUTOMATOR v{VERSION}\n")
    f.write("===============================================================\n")
    f.write("A pipeline for decoding IMU, Audio, and GPS data from Vesper Tags.\n\n")

    f.write("[ QUICK START ]\n")
    f.write("1. Copy your raw session folders (e.g. '20250918_tag1') into 'data_input'.\n")
    f.write("2. Double-click the .exe file.\n")
    f.write("3. Wait for the process to finish (check the window for progress).\n")
    f.write("4. Find your results in 'data_output'.\n\n")

    f.write("[ OUTPUTS ]\n")
    f.write("- IMU:  Converted to .CSV with precise timestamps.\n")
    f.write("- AUD:  Converted to .WAV (artifacts removed).\n")
    f.write("- GPS:  Converted to .DAT snapshots and decoded to .CSV (if GeoTag is present).\n\n")
    
    f.write("[ TROUBLESHOOTING ]\n")
    f.write("- If the window closes immediately, check the 'logs' folder.\n")
    f.write("- Ensure 'external_tools' contains GeoTag.exe for GPS coordinates.\n")
    f.write("- If you see 'Windows protected your PC', click 'More Info' -> 'Run Anyway'.\n\n")
    
    f.write("[ HOW TO PROCESS THE NEXT BATCH ] (Session 2, 3, etc.)\n")
    
    f.write("* CLEAN UP FIRST:\n")
    f.write("  Before starting a new batch, please delete the old files from 'data_input'\n")
    f.write("  and move your results out of 'data_output' (save them to your permanent storage).\n\n")
    f.write("  [WHY?] The tool processes EVERYTHING inside the input folder. If you\n")
    f.write("  leave old files there, it will re-scan and re-process them. This is\n")
    f.write("  safe, but wastes time and might be confusing.\n\n")

    f.write("* RESTART:\n")
    f.write("  Just run the .exe again. You do not need to unzip the tool or change\n")
    f.write("  settings again unless your hard drive letter changes.\n\n")

    f.write("===============================================================\n")
    f.write("LEGAL NOTICE:\n")
    f.write("This software is an independent research tool. It is NOT affiliated with,\n")
    f.write("authorized, or endorsed by A.S.D. (Alexander Schwartz Developments).\n")
    f.write("Vesper is a registered trademark of A.S.D.\n")
    
print(f"\n[OK] Build Complete!")
if current_os == "Windows":
    print(f"Go to the 'dist' folder and ZIP the '{FOLDER_NAME}' folder.")
else:
    print(f"⚠️  NOTE: You built this on {current_os}. The binary '{binary_name}' will NOT run on Windows OS.")