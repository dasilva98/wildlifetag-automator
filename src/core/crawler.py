import os
import logging

logger = logging.getLogger("vesper_automator")

def find_raw_files(root_folder):
    """
    Scans root_folder to find all .BIN files, organized by Tag/Session.
    
    Returns:
        dict: {
            "20250929_vesper1": {"gps": [], "aud": [], "imu": []},
            "20250929_vesper2": {"gps": [], "aud": [], "imu": []},
            ...
        }
    """
    logger.info(f"Scanning for files in: {root_folder}")

    if not os.path.exists(root_folder):
        logger.error(f"Raw data folder not found: {root_folder}")
        return {}

    # Structure: { "session_name": { "gps": [], "aud": [], "imu": [] } }
    sessions_map = {}

    # 1. Identify Session Folders (Direct children of 'raw')
    try:
        # Get immediate subdirectories (the tags/sessions)
        session_dirs = [d for d in os.listdir(root_folder) if os.path.isdir(os.path.join(root_folder, d))]
    except Exception as e:
        logger.error(f"Error reading directory structure: {e}")
        return {}

    total_files = 0

    for session in session_dirs:
        session_path = os.path.join(root_folder, session)
        
        # Initialize map for this specific tag
        sessions_map[session] = {
            "gps": [],
            "aud": [],
            "imu": []
        }
        
        # 2. Walk ONLY inside this session folder
        for dirpath, _, filenames in os.walk(session_path):
            for filename in filenames:
                if filename.upper().endswith(".BIN"):
                    full_path = os.path.join(dirpath, filename)
                    lower_path = full_path.lower()
                    
                    # Sort by sensor type
                    if "gps" in lower_path:
                        sessions_map[session]["gps"].append(full_path)
                    elif "aud" in lower_path:
                        sessions_map[session]["aud"].append(full_path)
                    elif "imu" in lower_path:
                        sessions_map[session]["imu"].append(full_path)
                    else:
                        logger.warning("WARNING: SENSOR TYPE NOT FOUND")
                        pass
                    
                    total_files += 1

        # Log stats for this specific tag
        s_counts = sessions_map[session]
        logger.info(f"Found Tag '{session}': {len(s_counts['gps'])} GPS, {len(s_counts['aud'])} Audio, {len(s_counts['imu'])} IMU")

    logger.info(f"Scan complete. Found {total_files} files across {len(sessions_map)} tags.")
    return sessions_map