import subprocess
import os
import sys
import logging

logger = logging.getLogger("wildlifetag_automator")

def get_base_path():
    """
    Returns the base directory of the application.
    - If running as a script: returns the folder containing src/
    - If running as compiled .exe: returns the folder containing the .exe
    """
    if getattr(sys, 'frozen', False):
        # If run as a compiled .exe, the base is where the .exe lives
        return os.path.dirname(sys.executable)
    else:
        # If run as a script, we are in src/wrappers/, so we go up 2 levels
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def run_geotag(dat_folder: str, output_dir: str) -> bool:
    """
    Runs GeoTag.exe with GeoTagEngine.exe to decode .DAT files.
    """
    base_dir = get_base_path()
    
    # Construct paths relative to the project root
    # Expected structure: root/external_tools/CG/GeoTag/GeoTag.exe
    tool_root = os.path.join(base_dir, "external_tools", "CG")
    
    geotag_exe = os.path.join(tool_root, "GeoTag", "GeoTag.exe")
    engine_exe = os.path.join(tool_root, "GeoTagEngine", "GeoTagEngine.exe")

    # Validation
    if not os.path.exists(geotag_exe):
        logger.error(f"External tool missing: {geotag_exe}")
        logger.error("Make sure 'external_tools' folder is next to the executable.")
        return False

    if not os.path.exists(engine_exe):
        logger.error(f"External tool missing: {engine_exe}")
        return False

    if not os.path.exists(dat_folder):
        logger.warning(f"No snapshot folder found at: {dat_folder}")
        return False

    os.makedirs(output_dir, exist_ok=True)

    # Command Construction
    cmd = [
        geotag_exe,
        "-t",
        f"--download={dat_folder}",
        f"--decode={output_dir}",
        f"--geotagengine={engine_exe}",
        "--pattern=snap.*.dat"
    ]

    logger.info(f"Launching GeoTag on: {os.path.basename(dat_folder)}")
    
    # Execution
    try:
        # cwd=... is CRITICAL. Many legacy tools fail if not run from their own dir.
        working_dir = os.path.dirname(geotag_exe)
        
        result = subprocess.run(
            cmd,
            capture_output=True, # Hide the pop-up window
            text=True,
            cwd=working_dir 
        )

        if result.returncode != 0:
            logger.error(f"GeoTag Failed (Code {result.returncode})")
            logger.error(f"STDERR: {result.stderr}")
            return False

        logger.info("GeoTag decoding successful.")
        return True

    except Exception as e:
        logger.error(f"GeoTag execution crashed: {e}")
        return False