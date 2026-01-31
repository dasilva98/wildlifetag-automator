import subprocess
import os
import logging

logger = logging.getLogger("wildlifetag_automator")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GEOTAG_EXE_PATH = os.path.abspath(
    os.path.join(BASE_DIR, "..","..", "external_tools" ,"CG", "GeoTag", "GeoTag.exe")
)

GEOTAG_ENGINE_PATH = os.path.abspath(
    os.path.join(BASE_DIR, "..","..", "external_tools" ,"CG", "GeoTagEngine", "GeoTagEngine.exe")
)


def run_geotag(dat_folder: str, output_dir: str) -> bool:
    """
    Runs GeoTag.exe with GeoTagEngine.exe.

    Args:
        dat_folder: Path to folder containing .DAT files
        output_dir: Path where decoded/geotagged results should be placed

    Returns:
        True on success, False on failure
    """

    if not os.path.exists(GEOTAG_EXE_PATH):
        logger.error(f"GeoTag exe not found: {GEOTAG_EXE_PATH}")
        return False

    if not os.path.exists(GEOTAG_ENGINE_PATH):
        logger.error(f"GeoTagEngine exe not found: {GEOTAG_ENGINE_PATH}")
        return False

    if not os.path.isdir(dat_folder):
        logger.error(f"DAT folder not found: {dat_folder}")
        return False

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        GEOTAG_EXE_PATH,
        "-t",
        f"--download={dat_folder}",
        f"--decode={output_dir}",
        f"--geotagengine={GEOTAG_ENGINE_PATH}",
        "--pattern=snap.*.dat"
    ]

    logger.info("Running GeoTag...")
    logger.debug("GeoTag command: %s", " ".join(cmd))

    geotag_dir = os.path.dirname(GEOTAG_EXE_PATH)
    try:
        result = subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            check=False,  # we handle return codes manually
            cwd=geotag_dir
        )

        if result.stdout:
            logger.debug(f"GeoTag stdout:\n{result.stdout}")

        if result.stderr:
            logger.warning(f"GeoTag stderr:\n{result.stderr}")

        if result.returncode != 0:
            logger.error(
                f"GeoTag failed with exit code {result.returncode}"
            )
            return False

        logger.info("GeoTag completed successfully")
        return True

    except Exception:
        logger.exception("GeoTag execution crashed")
        return False
