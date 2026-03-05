import yaml
import os
import sys
import traceback
import pandas as pd
import re

from tqdm import tqdm
from datetime import datetime, timedelta

from src.core.logger import setup_logger
from src.core.file_scanner import scan_raw_files
from src.core.run_reporter import RunReporter
from src.core.export_manager import ExportManager
from src.core.constants import FULL_APP_NAME

from src.parsers.imu_parser import parse_imu_file
from src.parsers.audio_parser import parse_audio_file
from src.parsers.gps_parser import extract_gps_snapshots

from src.wrappers.geotag_wrapper import run_geotag

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

def extract_sequence_index(filepath):
    match = re.search(r'(\d+)', os.path.basename(filepath))
    return int(match.group(1)) if match else 0

def main():

    pd.set_option('display.max_columns', None)

    # Setup Logging
    logger = setup_logger("wildlifetag_automator", log_dir="./logs")
    logger.info(f"============== {FULL_APP_NAME} Started ===============")

    # Load Config
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return
    
    # Setup Paths & Objects 
    raw_folder = config.get("raw_data_folder", "./data/raw")
    processed_folder = config.get("processed_folder", "./data/processed")
    
    # Instantiate Reporter
    reporter = RunReporter()

    # Initiate Exporter Manager
    exporter = ExportManager(processed_folder)

    # Scan all files in the input/raw folder
    all_sessions = scan_raw_files(raw_folder)

    # ======== MAIN LOOP ======== (Iterates over each Recording/Tag/Session)
    for session_id, files_map in all_sessions.items():
        logger.info(f"Processing Session: {session_id}")

        # ---Initialize Session Metrics---
        sess_metrics = {
            "id": session_id,
            "start_time": None, "end_time": None, # For Calendar Window
            
            # Inventory Counts
            "imu_ok": 0, 
            "aud_ok": 0, 
            "gps_ok": 0, 
            "gps_attempts": 0, # Total snapshots attempted
            "duration_imu_sec": 0.0,
            "duration_aud_sec": 0.0,

            # Scientific Yield
            "aud_duration": 0.0,
            "gps_fixes": 0,
            
            "files_total": 0 # (From A: Required for internal logic)
        }
        
        # Helper to update time range
        def update_range(t_start, t_end):
            if t_start:
                if sess_metrics["start_time"] is None or t_start < sess_metrics["start_time"]:
                    sess_metrics["start_time"] = t_start
            if t_end:
                if sess_metrics["end_time"] is None or t_end > sess_metrics["end_time"]:
                    sess_metrics["end_time"] = t_end

        # ==========================================
        # 1. IMU PROCESSING
        # ==========================================
        imu_files = files_map['imu']
        sess_metrics["files_total"] += len(imu_files)
        
        # Sort by file number to ensure chronological concatenation
        imu_files.sort(key=extract_sequence_index) 
        
        imu_df = pd.DataFrame()
        session_device_id = None
        last_meta = None 

        if imu_files:
            logger.info(f"Starting IMU Parser on {len(imu_files)} binary files...")
            
            for filepath in tqdm(imu_files, desc=f"IMU ({session_id})", unit="file"):
                try:
                    # --- PARSER UNPACKING ---
                    # Parser now returns (status, message, df, meta)
                    # status: "SUCCESS", "EMPTY", "FAIL"
                    status, msg, df, meta = parse_imu_file(filepath)
                    
                    # If the data is valid
                    if status == "SUCCESS":
                        sess_metrics["imu_ok"] += 1

                        # Safe to assume df is valid and populated here
                        imu_df = pd.concat([imu_df, df], ignore_index=True)
                        
                        # Capture DeviceID from the first valid file found
                        if session_device_id is None and meta:
                            session_device_id = meta.get('DeviceID', 'UnknownTag')
                            sess_metrics['id'] = session_device_id
                            last_meta = meta
                    
                    # Log result in the reporter
                    reporter.log_file_result("imu", status, filepath, msg)
                except Exception as e:
                    # Catch crashes during concat or ID extraction, and send it to the reporter
                    reporter.log_file_result("imu", "FAIL", filepath, f"Unexpected loop crash: {e}")
        
            # --- SAVE MERGED IMU CSV ---
            if not imu_df.empty:
                try:
                    # Re-sort everything by time just in case file numbering and 
                    # timestamps didn't perfectly align.
                    imu_df = imu_df.sort_values(by='Time')
                    t_start = imu_df['Time'].iloc[0]
                    t_end = imu_df['Time'].iloc[-1]

                    update_range(t_start, t_end)

                    # Calculate recorded duration (For Data Yield info)
                    # Duration = Total Samples / Sample Rate
                    if last_meta and last_meta.get('SampleRate', 0) > 0:
                        sess_metrics["duration_imu_sec"] = len(imu_df) / last_meta['SampleRate']
                    else:
                        # Fallback just in case SampleRate is missing
                        sess_metrics["duration_imu_sec"] = (t_end - t_start).total_seconds()

                    if last_meta: last_meta['Start_Time'] = t_start
                    
                    success = exporter.save_imu_csv(imu_df, uid=session_device_id)
                    if success and last_meta:
                        exporter.save_session_metadata(last_meta, end_time=t_end)

                except Exception as e:
                    logger.error(f"Failed to finalize IMU session {session_id}: {e}")
        else:
            logger.warning(f"No IMU binary files found in {session_id}")

        # ==========================================
        # 2. AUDIO PROCESSING
        # ==========================================
        aud_files = files_map['aud']
        sess_metrics["files_total"] += len(aud_files)
        aud_files.sort(key=extract_sequence_index)

        if aud_files:
            logger.info(f"Starting Audio Parser on {len(aud_files)} binary files...")   
            for filepath in tqdm(aud_files, desc=f"Audio ({session_id})", unit="file"):
                try:
                    # --- PARSER UNPACKING ---
                    # Returns: (status, message, meta, audio_data, timestamps)
                    status, msg, meta, audio_data, timestamps = parse_audio_file(filepath)

                    # If the data is valid
                    if status == "SUCCESS":
                        sess_metrics["aud_ok"] += 1

                        # Robust ID extraction (if IMU failed/missing)
                        if session_device_id is None and meta:
                            session_device_id = meta.get('DeviceID', 'UnknownTag')
                            sess_metrics['id'] = session_device_id
                        
                        if meta and audio_data is not None:
                            duration = len(audio_data) / meta['SampleRate']
                            end_time = meta['Start_Time'] + timedelta(seconds=duration)
                            
                            sess_metrics["aud_duration"] += duration

                            update_range(meta['Start_Time'], end_time)

                            exporter.save_aud_wav(audio_data, meta)
                            exporter.save_session_metadata(meta, end_time=end_time, time_stamps=timestamps)
                    
                    # Log result in the reporter
                    reporter.log_file_result("aud", status, filepath, msg)
                except Exception as e:
                   # Catch crahs and send it to the reporter
                    reporter.log_file_result("aud", "FAIL", filepath, f"Unexpected loop crash: {e}")
        else:
            logger.warning(f"No audio binary files found in {session_id}")

        # ==========================================
        # 3. GPS PROCESSING
        # ==========================================
        gps_files = files_map['gps']
        sess_metrics["files_total"] += len(gps_files)
        sess_metrics["gps_attempts"] += len(gps_files)
        
        # Sort files to ensure chronological processing
        gps_files.sort(key=extract_sequence_index)

        session_gps_valid_count = 0
        session_ref_time = "Unknown Time"
        
        # --- INITIAL PATH SETUP ---
        # We start with the Session ID because that is all we know before parsing.
        session_snap_dir = os.path.join(processed_folder, "gps", "snapshots", session_id)
        session_decode_dir = os.path.join(processed_folder, "gps", "decoded", session_id)
        abs_snap_dir = os.path.abspath(session_snap_dir)
        abs_decode_dir = os.path.abspath(session_decode_dir)

        if gps_files:
            logger.info(f"Starting GPS Parser: Extracting snapshots from {len(gps_files)} binary files...")
            
            # RUN PARSER LOOP (Extracts binary snapshots and detects dates)
            for filepath in tqdm(gps_files, desc=f"GPS ({session_id})", unit="file"):
                try:
                    # GPS parser returns Tuple (Status, Message)
                    status, msg = extract_gps_snapshots(filepath, abs_snap_dir)

                    if status == "SUCCESS":
                        sess_metrics["gps_ok"] += 1
                        session_gps_valid_count += 1

                        # Grab timestamp from the filename of the FIRST valid file generated
                        # This allows us to date-stamp the session folder later.
                        if session_ref_time == "Unknown Time" and "Skipped" not in msg:
                            try:
                                generated_files = os.listdir(abs_snap_dir)
                                if generated_files:
                                    # Look for filename pattern: snap.YYYY_MM_DD
                                    match = re.search(r'snap\.(\d{4}_\d{2}_\d{2})', generated_files[0])
                                    if match: session_ref_time = match.group(1)
                            except Exception: 
                                pass
                    
                    # Log result in the reporter
                    reporter.log_file_result("aud", status, filepath, msg)
                except Exception as e:
                    # Catch crash and send it to reporter
                    reporter.log_file_result("gps", "FAIL", filepath, f"Unexpected loop crash: {e}")
            
            # DYNAMIC FOLDER RENAMING (Date + Device ID)
            # We rename the folder from the generic Session ID to a human-readable YYYY_MM_DD-DeviceID format
            final_id = session_id
            if session_ref_time != "Unknown Time":
                try:
                    if session_device_id and session_device_id != "UnknownTag":
                        final_id = session_device_id

                    new_folder_name = f"{session_ref_time}-{final_id}"
                    
                    parent_snap = os.path.dirname(abs_snap_dir)
                    parent_decode = os.path.dirname(abs_decode_dir)
                    
                    new_snap_dir = os.path.join(parent_snap, new_folder_name)
                    new_decode_dir = os.path.join(parent_decode, new_folder_name)
                    
                    # Dealing we already existing folders named like '20250929_vesper2'
                    if not os.path.exists(new_snap_dir):
                        # Target folder doesn't exist so we rename it 
                        if os.path.exists(abs_snap_dir):
                            os.rename(abs_snap_dir, new_snap_dir)
                            logger.info(f"   -> Renamed session folder to: {new_folder_name}")
                            
                            # Update pointers for GeoTag step
                            abs_snap_dir = new_snap_dir
                            abs_decode_dir = new_decode_dir
                    else:
                        # Target exists, so we assume we are resuming/overwriting
                        logger.info(f"   -> Folder {new_folder_name} exists. Using it.")

                        # Update pointers for GeoTag step
                        abs_snap_dir = new_snap_dir
                        abs_decode_dir = new_decode_dir

                except Exception as e:
                    logger.warning(f"Could not rename session folder: {e}")
            
            # 3. RUN GEOTAG 
            if session_gps_valid_count > 0:
                logger.info(f" -> Launching GeoTag...")
                
                raw_cli_path = config.get("gps_cli_path", "./external_tools/CG/GeoTag/GeoTag.exe")
                raw_eng_path = config.get("gps_engine_path", "./external_tools/CG/GeoTagEngine/GeoTagEngine.exe")
                
                cli_path = resolve_config_path(raw_cli_path)
                eng_path = resolve_config_path(raw_eng_path)

                # Execute with Robust Wrapper
                geo_success, geo_msg = run_geotag(
                    dat_folder=abs_snap_dir, 
                    output_dir=abs_decode_dir,
                    geotag_exe=cli_path,
                    engine_exe=eng_path
                )
                
                if geo_success:
                    # Export the decoded GPS output
                    success, count = exporter.finalize_geotag_csv(abs_decode_dir, final_id)
                    if success: 
                        sess_metrics["gps_fixes"] = count
                else:
                    # "GeoTag Failed (SessionID): Reason"
                    err_msg = f" [{session_device_id}]-> {geo_msg}"                  
                    logger.error(err_msg)
                    reporter.log_external_error(err_msg)

        # SAVE SESSION STATS TO REPORTER
        reporter.add_session(sess_metrics)

    # Save Processing Report
    reporter.save_report(processed_folder, logger)

    success_msg = "[SUCCESS] Processing Complete!"
    logger.info("="*100)
    logger.info(f"{success_msg:^100}")
    logger.info("="*100)

if __name__ == "__main__":
    try:
        main()
        input("Press Enter to exit...") 
        
    except Exception as e:
        critic_err_message = "[CRITICAL ERROR] Something went wrong!"
        print("\n\n" + "!"*100)
        print(f"{critic_err_message:^100}")
        print("!"*100 + "\n")
        traceback.print_exc()
        input("[!] Press Enter to exit...")