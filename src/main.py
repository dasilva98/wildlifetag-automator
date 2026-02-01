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

from src.core.finisher import FileFinisher
from src.wrappers.gps_cli import run_geotag

def load_config(config_path="config.yaml"):
    """Loads configuration from the YAML file"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def generate_summary(stats, logger, processed_folder):
    """
    Generates a professional text summary of the session.
    """
    lines = []
    lines.append("="*60)
    lines.append(f"          WILDLIFETAG AUTOMATOR - REPORT CARD")
    lines.append("="*60)
    lines.append(f"Date:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Files:     {stats['total']} Total Found")
    lines.append("-" * 60)
    lines.append(f"| {'SENSOR':<10} | {'TOTAL':<8} | {'SUCCESS':<8} | {'FAILED':<8} |")
    lines.append("-" * 60)
    lines.append(f"| {'IMU':<10} | {stats['total_imu']:<8} | {stats['success_imu']:<8} | {stats['failed_imu']:<8} |")
    lines.append(f"| {'AUDIO':<10} | {stats['total_aud']:<8} | {stats['success_aud']:<8} | {stats['failed_aud']:<8} |")
    lines.append(f"| {'GPS':<10} | {stats['total_gps']:<8} | {stats['success_gps']:<8} | {stats['failed_gps']:<8} |")
    lines.append("-" * 60)
 
    if stats['errors']:
        lines.append("\nERROR LOG (First 50):")
        lines.append("-" * 20)
        for err in stats['errors'][:50]:
            lines.append(f"  [X] {os.path.basename(err['file'])}")
            lines.append(f"      -> {err['reason']}")
            
        if len(stats['errors']) > 50:
             lines.append(f"\n... and {len(stats['errors']) - 50} more errors.")
            
    lines.append("="*60)
    lines.append("END OF REPORT")

    report_content = "\n".join(lines)

    # Print summary to console (limit length)
    for line in lines[:15]:
        logger.info(line)
    if len(lines) > 15:
        logger.info("... (Full report saved to file)")

    # Save to file
    reports_dir = os.path.join(processed_folder, "report_cards")
    os.makedirs(reports_dir, exist_ok=True)
    
    report_filename = f"Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = os.path.join(reports_dir, report_filename)
    
    try:
        with open(report_path, "w") as f:
            f.write(report_content)
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
    logger.info("--- WildlifeTag Automator Started ---")

    # Load Config
    try:
        config = load_config()
        logger.info("Configuration loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return
    
    # Setup Paths & Objects 
    raw_folder = config.get("raw_data_folder", "./data/raw")
    processed_folder = config.get("processed_folder", "./data/processed")
    finisher = FileFinisher(processed_folder)

    # Crawl files
    all_sessions = find_raw_files(raw_folder)

    # Summary stats container
    stats = {
        "total": 0,
        "total_imu": 0, "total_aud": 0, "total_gps": 0,
        "success_imu": 0, "success_aud": 0, "success_gps": 0,
        "failed_imu": 0, "failed_aud": 0, "failed_gps": 0,
        "errors": [] 
    }

    # --- MAIN LOOP: Iterate over each Tag/Session ---
    for session_id, files_map in all_sessions.items():
        logger.info(f"Processing Session: {session_id}")

        # ==========================================
        # 1. PROCESS IMU FILES
        # ==========================================
        imu_files = files_map['imu']
        stats['total_imu'] += len(imu_files)
        
        imu_files.sort(key=extract_file_number)
        imu_df = pd.DataFrame()
        session_device_id = None
        last_meta = None 

        if imu_files:
            logger.info(f"Starting IMU Parser on {len(imu_files)} files...")
            
            for filepath in tqdm(imu_files, desc=f"IMU ({session_id})", unit="file"):
                try:
                    df, meta = parse_imu_file(filepath)
                    if df is not None and not df.empty:
                        stats['success_imu'] += 1
                        imu_df = pd.concat([imu_df, df], ignore_index=True)
                        if session_device_id is None and meta:
                            session_device_id = meta.get('DeviceID', 'UnknownTag')
                            last_meta = meta
                    else:
                        stats['failed_imu'] += 1
                        stats['errors'].append({"file": filepath, "reason": "Empty IMU Data"})
                except Exception as e:
                    stats['failed_imu'] += 1
                    stats['errors'].append({"file": filepath, "reason": f"IMU Crash: {e}"})
        
            if not imu_df.empty:
                imu_df = imu_df.sort_values(by='Time')
                start_time = imu_df['Time'].iloc[0]
                end_time = imu_df['Time'].iloc[-1]
                
                if last_meta: last_meta['Start_Time'] = start_time
                success = finisher.save_imu_csv(imu_df, uid=session_device_id)
                
                if success and last_meta:
                    finisher.generate_metadata_file(last_meta, end_time=end_time)
        else:
            logger.warning("No IMU files found.")

        # ==========================================
        # 2. PROCESS AUDIO FILES
        # ==========================================
        audio_files = files_map['aud']
        stats['total_aud'] += len(audio_files)

        if audio_files:
            logger.info(f"Starting Audio Parser on {len(audio_files)} files...")   

            for filepath in tqdm(audio_files, desc=f"Audio ({session_id})", unit="file"):
                try:
                    success, meta, audio_data, timestamps = parse_audio_file(filepath)

                    if success:
                        stats['success_aud'] += 1
                        end_time = None
                        if audio_data is not None and len(audio_data) > 0 and meta:
                            duration = len(audio_data) / meta['SampleRate']
                            end_time = meta['Start_Time'] + timedelta(seconds=duration)
                        
                        if audio_data is not None and len(audio_data) > 0:
                            finisher.save_aud_wav(audio_data, meta)
                            
                        if meta:
                            finisher.generate_metadata_file(meta, end_time=end_time, time_stamps=timestamps)
                    else:
                        stats['failed_aud'] += 1
                        stats['errors'].append({"file": filepath, "reason": "Audio Parse Failed"})

                except Exception as e:
                    stats['failed_aud'] += 1
                    stats['errors'].append({"file": filepath, "reason": f"Audio Crash: {e}"})

        # ==========================================
        # 3. PROCESS GPS FILES (Per Session Isolation)
        # ==========================================
        gps_files = files_map['gps']
        stats['total_gps'] += len(gps_files)
        
        # Track valid snapshots just for this session
        session_gps_valid_count = 0
        
        # Define Session-Specific Output Paths
        # data/processed/gps/snapshots/Session_01/
        if session_device_id:
            rel_snap_dir = os.path.join(processed_folder, "gps", "snapshots", session_device_id)
            rel_decode_dir = os.path.join(processed_folder, "gps", "decoded", session_device_id)
        else:
            rel_snap_dir = os.path.join(processed_folder, "gps", "snapshots", session_id)
            rel_decode_dir = os.path.join(processed_folder, "gps", "decoded", session_id)

        # CRITICAL: Convert to Absolute Paths for External Tools
        # This fixes the mixed slashes AND the "path not found" error
        abs_snap_dir = os.path.abspath(rel_snap_dir)
        abs_decode_dir = os.path.abspath(rel_decode_dir)

        if gps_files:
            logger.info(f"Starting GPS Parser on {len(gps_files)} files...")
            
            for filepath in tqdm(gps_files, desc=f"GPS ({session_id})", unit="file"):
                # We pass the specific session directory to the parser
                success = parse_gps_file(filepath, abs_snap_dir)
                
                if success:
                    stats['success_gps'] += 1
                    session_gps_valid_count += 1
                else:
                    stats['failed_gps'] += 1
                    stats['errors'].append({"file": filepath, "reason": "GPS Parse Failed"})
            
            # --- RUN GEOTAG (Per Session) ---
            if session_gps_valid_count > 0:
                logger.info(f"   -> Launching GeoTag for {session_id}...")
                
                geo_success = run_geotag(dat_folder=abs_snap_dir, output_dir=abs_decode_dir)
                
                if geo_success:
                    logger.info(f"   [SUCCESS] Coordinates decoded for {session_id} Tag")
                    
                    # Finalize the CSV (Rename & Move)
                    if session_device_id:
                        finisher.process_gps_output(abs_decode_dir, session_device_id)
                    else:
                        finisher.process_gps_output(abs_decode_dir, session_id)
                else:
                    logger.error(f"   [ERROR] GeoTag failed for {session_id} Tag")
                    stats['errors'].append({"file": f"GeoTag_{session_id}", "reason": "External tool failure"})

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
        print("   CRITICAL ERROR - PLEASE SEND SCREENSHOT TO DEVELOPER")
        print("!"*60 + "\n")
        traceback.print_exc()
        input("[!] Press Enter to exit...")