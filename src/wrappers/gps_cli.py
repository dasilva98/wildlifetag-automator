import subprocess
import os
import sys
import logging

logger = logging.getLogger("wildlifetag_automator")

def run_geotag(dat_folder: str, output_dir: str, geotag_exe: str, engine_exe: str) -> tuple:
    """
    Runs GeoTag.exe using the specific paths provided from config.
    Returns: (success, message)
    """
    
    # --- 1. VALIDATION ---
    # We trust main.py passed us absolute paths, but we check existence just in case.
    if not os.path.exists(geotag_exe):
        return False, f"GeoTag.exe missing at: {geotag_exe}"

    if not os.path.exists(engine_exe):
        return False, f"GeoTagEngine.exe missing at: {engine_exe}"

    if not os.path.exists(dat_folder):
        return False, f"Snapshot folder not found: {dat_folder}"

    os.makedirs(output_dir, exist_ok=True)

    # --- 2. COMMAND CONSTRUCTION ---
    cmd = [
        geotag_exe,
        "-t",
        f"--download={dat_folder}",
        f"--decode={output_dir}",
        f"--geotagengine={engine_exe}",
        "--pattern=snap.*.dat"
    ]

    logger.info(f"Launching GeoTag on: {os.path.basename(dat_folder)}")
    
    # --- 3. EXECUTION ---
    try:
        # cwd=... is CRITICAL. We run from the directory of the GeoTag executable
        # so it can find its own dependencies (DLLs, config files, etc).
        working_dir = os.path.dirname(geotag_exe)
        
        result = subprocess.run(
            cmd,
            capture_output=False, 
            text=True,
            cwd=working_dir 
        )

        if result.returncode != 0:
            err_snippet = result.stderr.strip()[-200:] if result.stderr else "No error output"
            return False, f"Exit Code {result.returncode}: {err_snippet}"

        return True, "GeoTag finished successfully"

    except Exception as e:
        return False, f"Subprocess Crash: {str(e)}"