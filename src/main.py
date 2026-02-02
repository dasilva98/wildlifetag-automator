import yaml
import os
import sys
import traceback
import pandas as pd
import re

from tqdm import tqdm
from datetime import datetime, timedelta
from src.core.logger import setup_logger
from src.core.crawler import find_raw_files
from src.parsers.imu_parser import parse_imu_file
from src.parsers.audio_parser import parse_audio_file
from src.parsers.gps_parser import parse_gps_file
from src.wrappers.gps_cli import run_geotag

from src.core.finisher import FileFinisher

def load_config(config_path="config.yaml"):
    """Loads configuration from the YAML file"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def resolve_config_path(path):
    """
    Resolves a path from config.yaml relative to the Application Root.
    Handles 'frozen' state (running as .exe) vs script state.
    """
    if os.path.isabs(path):
        return path

    # Determine App Root
    if getattr(sys, 'frozen', False):
        # If .exe, root is where the .exe is
        base_dir = os.path.dirname(sys.executable)
    else:
        # If script (src/main.py), root is two levels up (wildlifetag-automator/)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    return os.path.abspath(os.path.join(base_dir, path))

def generate_summary(stats, logger, processed_folder):
    """
    Generates a Traffic Light report (Success / Warning / Fail).
    """
    lines = []
    lines.append("="*65)
    lines.append(f"          WILDLIFETAG AUTOMATOR - REPORT CARD")
    lines.append("="*65)
    lines.append(f"Date:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Files:     {stats['total']} Total Found")
    lines.append("-" * 65)
    # Added "EMPTY" column for Warnings
    lines.append(f"| {'SENSOR':<10} | {'TOTAL':<8} | {'SUCCESS':<8} | {'EMPTY':<8} | {'FAILED':<8} |")
    lines.append("-" * 65)
    
    # Fill the grid
    lines.append(f"| {'IMU':<10} | {stats['total_imu']:<8} | {stats['success_imu']:<8} | {stats['warn_imu']:<8} | {stats['failed_imu']:<8} |")
    lines.append(f"| {'AUDIO':<10} | {stats['total_aud']:<8} | {stats['success_aud']:<8} | {stats['warn_aud']:<8} | {stats['failed_aud']:<8} |")
    lines.append(f"| {'GPS':<10} | {stats['total_gps']:<8} | {stats['success_gps']:<8} | {stats['warn_gps']:<8} | {stats['failed_gps']:<8} |")
    lines.append("-" * 65)
 
    # SECTION 1: WARNINGS (Valid files, no data)
    warnings = [e for e in stats['errors'] if e.get('type') == 'WARN']
    if warnings:
        lines.append("\n[!] WARNINGS (Empty Files - No Data Recorded):")
        for w in warnings[:20]:
            lines.append(f"   -> {os.path.basename(w['file'])}")
        if len(warnings) > 20: lines.append(f"   ... and {len(warnings)-20} more.")

    # SECTION 2: CRITICAL ERRORS (Crashes/Corruption)
    errors = [e for e in stats['errors'] if e.get('type') == 'CRITICAL']
    if errors:
        lines.append("  [X] CRITICAL FAILURES (Action Required):".center(65, "="))
        for err in errors:
            lines.append(f"   -> {err['reason']}")
            if 'file' in err: lines.append(f"      File: {err['file']}")
            
    lines.append("="*65)
    lines.append("END OF REPORT")

    report_content = "\n".join(lines)

    # Print summary to console
    for line in lines[:20]: logger.info(line)
    if len(lines) > 20: logger.info("... (Full report saved to file)")

    # Save to file
    reports_dir = os.path.join(processed_folder, "report_cards")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, f"Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    
    try:
        with open(report_path, "w") as f: f.write(report_content)
        logger.info(f"\n[Report] Saved to: {report_path}")
    except Exception as e:
        logger.error(f"Failed to write summary report file: {e}")

def extract_file_number(filepath):
    match = re.search(r'(\d+)', os.path.basename(filepath))
    return int(match.group(1)) if match else 0

def main():

    pd.set_option('display.max_columns', None)

    # Setup Logging
    logger = setup_logger("wildlifetag_automator", log_dir="./logs")
    logger.info("============== WildlifeTag Automator Started ===============")

    # Load Config
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return
    
    # Setup Paths & Objects 
    raw_folder = config.get("raw_data_folder", "./data/raw")
    processed_folder = config.get("processed_folder", "./data/processed")
    
    # Initiate Finisher
    finisher = FileFinisher(processed_folder)

    # Crawl files
    all_sessions = find_raw_files(raw_folder)

    # STATS STRUCTURE
    stats = {
        "total": 0, 
        "total_imu": 0, "success_imu": 0, "warn_imu": 0, "failed_imu": 0,
        "total_aud": 0, "success_aud": 0, "warn_aud": 0, "failed_aud": 0,
        "total_gps": 0, "success_gps": 0, "warn_gps": 0, "failed_gps": 0,
        "errors": [] # Dictionaries look like: {'type': 'WARN'|'CRITICAL', 'file': name, 'reason': msg}
    }

    # ======== MAIN LOOP ======== (Iterates over each Recording/Tag/Session)
    for session_id, files_map in all_sessions.items():
        logger.info(f"Processing Session: {session_id}")

        # ==========================================
        # 1. IMU PROCESSING
        # ==========================================
        imu_files = files_map['imu']
        stats['total_imu'] += len(imu_files)
        
        # Sort by file number to ensure chronological concatenation
        imu_files.sort(key=extract_file_number) 
        
        imu_df = pd.DataFrame()
        session_device_id = None
        last_meta = None 

        if imu_files:
            logger.info(f"Starting IMU Parser on {len(imu_files)} files...")
            
            for filepath in tqdm(imu_files, desc=f"IMU ({session_id})", unit="file"):
                try:
                # --- PARSER UNPACKING ---
                # Parser now returns (status, message, df, meta)
                # status: "SUCCESS", "EMPTY", "FAIL"
                    status, msg, df, meta = parse_imu_file(filepath)

                    # CASE 1: VALID DATA
                    if status == "SUCCESS":
                        stats['success_imu'] += 1
                        # Safe to assume df is valid and populated here
                        imu_df = pd.concat([imu_df, df], ignore_index=True)
                        
                        # Capture DeviceID from the first valid file found
                        if session_device_id is None and meta:
                            session_device_id = meta.get('DeviceID', 'UnknownTag')
                            last_meta = meta
                            
                    # CASE 2: EMPTY PAYLOAD (Warning)
                    elif status == "EMPTY":
                        stats['warn_imu'] += 1
                        stats['errors'].append({
                            "type": "WARN", 
                            "file": filepath, 
                            "reason": msg  # e.g. "No sensor data rows found"
                        })

                    # CASE 3: CORRUPT / HEADER INVALID (Error)
                    else: # status == "FAIL"
                        stats['failed_imu'] += 1
                        stats['errors'].append({
                            "type": "CRITICAL", 
                            "file": filepath, 
                            "reason": msg # e.g. "Header parse error"
                        })

                except Exception as e:
                    # Catch crashes during concat or ID extraction
                    stats['failed_imu'] += 1
                    stats['errors'].append({"type": "CRITICAL", "file": filepath, "reason": f"Processing crash: {e}"})
        
            # --- SAVE MERGED IMU CSV ---
            if not imu_df.empty:
                try:
                    # Re-sort everything by time just in case file numbering and 
                    # timestamps didn't perfectly align.
                    imu_df = imu_df.sort_values(by='Time')
                    start_time = imu_df['Time'].iloc[0]
                    end_time = imu_df['Time'].iloc[-1]

                    # Update metadata with the actual chronological start
                    if last_meta: last_meta['Start_Time'] = start_time
                    
                    success = finisher.save_imu_csv(imu_df, uid=session_device_id)
                    if success and last_meta:
                        finisher.generate_metadata_file(last_meta, end_time=end_time)

                except Exception as e:
                    logger.error(f"Failed to finalize IMU session {session_id}: {e}")
        else:
            logger.warning("No IMU files found.")

        # ==========================================
        # 2. AUDIO PROCESSING
        # ==========================================
        audio_files = files_map['aud']
        stats['total_aud'] += len(audio_files)

        audio_files.sort(key=extract_file_number)

        if audio_files:
            logger.info(f"Starting Audio Parser on {len(audio_files)} files...")   
            for filepath in tqdm(audio_files, desc=f"Audio ({session_id})", unit="file"):
                try:
                    # --- PARSER UNPACKING ---
                    # Returns: (status, message, meta, audio_data, timestamps)
                    status, msg, meta, audio_data, timestamps = parse_audio_file(filepath)

                    # CASE 1: SUCCESSFUL PARSE
                    if status == "SUCCESS":
                        stats['success_aud'] += 1
                        
                        # Double-check meta/data existence to satisfy linter safety
                        if meta and audio_data is not None:
                            # Calculate end_time based on sample count / sample rate
                            duration = len(audio_data) / meta['SampleRate']
                            end_time = meta['Start_Time'] + timedelta(seconds=duration)
                            
                            # Write WAV and accompanying metadata/timestamp files
                            finisher.save_aud_wav(audio_data, meta)
                            finisher.generate_metadata_file(meta, end_time=end_time, time_stamps=timestamps)
                    
                    # CASE 2: SILENT / EMPTY FILE (Warning)
                    elif status == "EMPTY":
                        stats['warn_aud'] += 1
                        stats['errors'].append({
                            "type": "WARN", 
                            "file": filepath, 
                            "reason": msg # e.g. "Silent file (0 samples)"
                        })

                    # CASE 3: CRITICAL ERROR (Corrupt binary or logic crash)
                    else: # status == "FAIL"
                        stats['failed_aud'] += 1
                        stats['errors'].append({
                            "type": "CRITICAL", 
                            "file": filepath, 
                            "reason": msg # e.g. "Header crash: ..."
                        })

                except Exception as e:
                    stats['failed_aud'] += 1
                    stats['errors'].append({"type": "CRITICAL", "file": filepath, "reason": f"Unexpected loop crash: {e}"})

        # ==========================================
        # 3. PROCESS GPS FILES
        # ==========================================
        gps_files = files_map['gps']
        stats['total_gps'] += len(gps_files)

        # Sort files to ensure chronological processing
        gps_files.sort(key=extract_file_number)

        session_gps_valid_count = 0
        session_ref_time = "Unknown Time"
        
        # --- INITIAL PATH SETUP ---
        # We start with the Session ID because that is all we know before parsing.
        session_snap_dir = os.path.join(processed_folder, "gps", "snapshots", session_id)
        session_decode_dir = os.path.join(processed_folder, "gps", "decoded", session_id)
        
        abs_snap_dir = os.path.abspath(session_snap_dir)
        abs_decode_dir = os.path.abspath(session_decode_dir)

        if gps_files:
            logger.info(f"Starting GPS Parser on {len(gps_files)} files...")
            
            # 1. RUN PARSER LOOP (Extracts binary snapshots and detects dates)
            for filepath in tqdm(gps_files, desc=f"GPS ({session_id})", unit="file"):
                
                # GPS parser returns Tuple (Status, Message)
                status, reason_msg = parse_gps_file(filepath, abs_snap_dir)

                if status == "SUCCESS":
                    stats['success_gps'] += 1
                    session_gps_valid_count += 1

                    # Grab timestamp from the filename of the FIRST valid file generated
                    # This allows us to date-stamp the session folder later.
                    if session_ref_time == "Unknown Time" and "Skipped" not in reason_msg:
                        try:
                            generated_files = os.listdir(abs_snap_dir)
                            if generated_files:
                                # Look for filename pattern: snap.YYYY_MM_DD
                                match = re.search(r'snap\.(\d{4}_\d{2}_\d{2})', generated_files[0])
                                if match: session_ref_time = match.group(1)
                        except Exception: 
                            pass

                elif status == "EMPTY":
                    stats['warn_gps'] += 1
                    stats['errors'].append({
                        "type": "WARN", 
                        "file": filepath, 
                        "reason": reason_msg
                    })

                else: # status == "FAIL"
                    stats['failed_gps'] += 1
                    stats['errors'].append({
                        "type": "CRITICAL", 
                        "file": filepath, 
                        "reason": reason_msg
                    })


            # 2. DYNAMIC FOLDER RENAMING (Date + Device ID)

            # We rename the folder from the generic Session ID to a 
            # human-readable YYYY_MM_DD-DeviceID format.
            final_id = session_id


            if session_ref_time != "Unknown Time":
                try:
                    # Determine the best ID to use
                    # If we found a real internal ID (from IMU/Audio), use it.
                    if session_device_id and session_device_id != "UnknownTag":
                        final_id = session_device_id

                    # Construct new name: e.g. "2025_09_29-4764505D"
                    new_folder_name = f"{session_ref_time}-{final_id}"
                    
                    # Define new Absolute Paths
                    parent_snap = os.path.dirname(abs_snap_dir)
                    parent_decode = os.path.dirname(abs_decode_dir)
                    
                    new_snap_dir = os.path.join(parent_snap, new_folder_name)
                    new_decode_dir = os.path.join(parent_decode, new_folder_name)
                    
                    # Rename the physical Snapshot Directory
                    if os.path.exists(abs_snap_dir) and not os.path.exists(new_snap_dir):
                        os.rename(abs_snap_dir, new_snap_dir)
                        logger.info(f"   -> Renamed session folder to: {new_folder_name}")
                        
                        # UPDATE POINTERS so GeoTag uses the NEW path
                        abs_snap_dir = new_snap_dir
                        abs_decode_dir = new_decode_dir
                        
                    elif os.path.exists(new_snap_dir):
                        # Idempotency: If folder already exists, just update pointers
                        abs_snap_dir = new_snap_dir
                        abs_decode_dir = new_decode_dir

                except Exception as e:
                    logger.warning(f"Could not rename session folder: {e}")
            
            # 3. RUN GEOTAG 
            if session_gps_valid_count > 0:
                logger.info(f"   -> Launching GeoTag for {final_id}...")
                
                # Resolve external tool paths from config
                raw_cli_path = config.get("gps_cli_path", "./external_tools/CG/GeoTag/GeoTag.exe")
                raw_eng_path = config.get("gps_engine_path", "./external_tools/CG/GeoTagEngine/GeoTagEngine.exe")
                
                cli_path = resolve_config_path(raw_cli_path)
                eng_path = resolve_config_path(raw_eng_path)

                # Execute the external GeoTag CLI
                geo_success, geo_msg = run_geotag(
                    dat_folder=abs_snap_dir, 
                    output_dir=abs_decode_dir,
                    geotag_exe=cli_path,
                    engine_exe=eng_path
                )
                
                if geo_success:
                    # Finalize the decoded GPS output into the master CSV/database
                    finisher.process_gps_output(abs_decode_dir, final_id)
                else:
                    err_msg = f"GeoTag Tool Failed | Session: {final_id} | Reason: {geo_msg}"
                    logger.error(f"  [CRITICAL ERROR] {err_msg}")
                    stats['errors'].append({
                        "type": "CRITICAL", 
                        "file": "External Tool", 
                        "reason": err_msg
                    })

    # Final Report
    stats["total"] = stats["total_imu"] + stats["total_aud"] + stats["total_gps"]
    generate_summary(stats, logger, processed_folder)

if __name__ == "__main__":
    try:
        main()
        print("\n" + "="*60)
        print("[SUCCESS] PROCESSING COMPLETE")
        print("="*60)
        input("Press Enter to exit...") 
        
    except Exception as e:
        print("\n\n" + "!"*60)
        print("   CRITICAL ERROR")
        print("!"*60 + "\n")
        traceback.print_exc()
        input("[!] Press Enter to exit...")