import subprocess
import os
import logging

logger = logging.getLogger("wildlifetag_automator")

def run_geotag(dat_folder: str, output_dir: str, geotag_exe: str, engine_exe: str) -> tuple:
    """
    Wraps the VesperApp GeoTag.exe CLI to decode snapshots into coordinates.
    
    Args:
        dat_folder: Path to the folder containing .DAT snapshot files.
        output_dir: Path where the resulting CSV/KML should be saved.
        geotag_exe: Absolute path to GeoTag.exe.
        engine_exe: Absolute path to GeoTagEngine.exe.
        
    Returns: 
        (bool, str): (Success?, Message)
    """
    
    # --- 1. VALIDATION & SETUP ---
    # Ensure all paths are absolute to prevent issues with changing CWD
    dat_folder = os.path.abspath(dat_folder)
    output_dir = os.path.abspath(output_dir)
    geotag_rel, engine_rel = geotag_exe, engine_exe
    geotag_exe = os.path.abspath(geotag_exe)
    engine_exe = os.path.abspath(engine_exe)

    if not os.path.exists(geotag_exe):
        # Get current working directory (project root)
        project_root = os.getcwd() 
        
        # Convert full path to relative (e.g., "external_tools/...")
        short_path = os.path.relpath(geotag_exe, start=project_root)

        return False, f"GeoTag.exe missing at: {short_path}"

    if not os.path.exists(engine_exe):
        # Get current working directory (project root)
        project_root = os.getcwd() 
        
        # Convert full path to relative (e.g., "external_tools/...")
        short_path = os.path.relpath(engine_rel, start=project_root)

        return False, f"GeoTagEngine.exe missing at: {short_path}"

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

    logger.info(f"Launching GeoTag on session: {os.path.basename(dat_folder)}")
    
    # --- 3. EXECUTION ---
    try:
        # cwd is set to the folder containing GeoTag.exe.
        # This is CRITICAL for legacy tools to find their DLLs/config files.
        working_dir = os.path.dirname(geotag_exe)
        
        result = subprocess.run(
            cmd,
            capture_output=False,  # capture=True keeps the main console clean
            text=True,
            cwd=working_dir 
        )

        if result.returncode != 0:
            # Extract the last 200 characters of stderr for the log
            err_snippet = result.stderr.strip()[-200:] if result.stderr else "No error output captured."
            logger.error(f"GeoTag Failed: {err_snippet}")
            return False, f"Exit Code {result.returncode}: {err_snippet}"

        return True, "GeoTag finished successfully"

    except Exception as e:
        logger.exception("Subprocess execution failed")
        return False, f"Subprocess Crash: {str(e)}"