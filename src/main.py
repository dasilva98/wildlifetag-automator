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
    Generates a professional text summary with Percentages and Per-Tag Stats.
    """
    lines = []
    lines.append("="*80)
    lines.append(f"               WILDLIFETAG AUTOMATOR v1.1 (Beta) - REPORT CARD")
    lines.append("="*80)
    lines.append(f"Date:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Files:     {stats['total']} Total Found")
    lines.append("-" * 80)
    
    # 1. MAIN STATS (With Percentages)
    def calc_pct(num, den):
        return f"{(num/den)*100:.1f}%" if den > 0 else "0.0%"

    lines.append(f"| {'SENSOR':<8} | {'TOTAL':<6} | {'OK':<6} | {'WARN':<6} | {'FAIL':<6} | {'RATE (%)':<8} |")
    lines.append("-" * 80)
    
    # IMU Row
    pct_imu = calc_pct(stats['success_imu'], stats['total_imu'])
    lines.append(f"| {'IMU':<8} | {stats['total_imu']:<6} | {stats['success_imu']:<6} | {stats['warn_imu']:<6} | {stats['failed_imu']:<6} | {pct_imu:<8} |")
    
    # Audio Row
    pct_aud = calc_pct(stats['success_aud'], stats['total_aud'])
    lines.append(f"| {'AUDIO':<8} | {stats['total_aud']:<6} | {stats['success_aud']:<6} | {stats['warn_aud']:<6} | {stats['failed_aud']:<6} | {pct_aud:<8} |")
    
    # GPS Row
    pct_gps = calc_pct(stats['success_gps'], stats['total_gps'])
    lines.append(f"| {'GPS':<8} | {stats['total_gps']:<6} | {stats['success_gps']:<6} | {stats['warn_gps']:<6} | {stats['failed_gps']:<6} | {pct_gps:<8} |")
    lines.append("-" * 80)

    # 2. PER-SESSION INVENTORY
    lines.append(" ")
    lines.append("SESSION INVENTORY & EFFICIENCY")
    
    # Adjusted column widths slightly for better alignment
    header = f"| {'SESSION ID':<18} | {'WINDOW (Start -> End)':<35} | {'AUD (h)':<7} | {'GPS (Fix/Try)':<13} | {'FILES (I/A/G)':<13} |"
    lines.append(header)
    lines.append("-" * len(header))

    for s in stats['sessions']:
        if s['start_time'] and s['end_time']:
            t1 = s['start_time'].strftime("%m-%d %H:%M")
            t2 = s['end_time'].strftime("%m-%d %H:%M")
            window_str = f"{t1} -> {t2}"
        else:
            window_str = "No Data"

        aud_hrs = f"{s['aud_duration']/3600:.1f}"
        gps_ratio = f"{s['gps_fixes']}/{s['gps_attempts']}"
        files_breakdown = f"{s['imu_ok']}/{s['aud_ok']}/{s['gps_ok']}"

        row = f"| {s['id']:<18} | {window_str:<35} | {aud_hrs:<7} | {gps_ratio:<13} | {files_breakdown:<13} |"
        lines.append(row)
    
    lines.append("-" * len(header))

    # SCIENTIFIC YIELD SECTION
    def fmt_time(seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"
    
    lines.append(" ")
    lines.append("DATA YIELD (Scientific Output):")
    lines.append(f"   > Total IMU Duration:   {fmt_time(stats['duration_imu_sec'])}")
    lines.append(f"   > Total Audio Duration: {fmt_time(stats['duration_aud_sec'])}")
    lines.append(f"   > Total GPS Fixes:      {stats['gps_fixes']} valid coordinates")
 
    # SECTION 1: WARNINGS
    warnings = [e for e in stats['errors'] if e.get('type') == 'WARN']
    if warnings:
        lines.append("\n")
        lines.append("="*80)
        lines.append("[!] WARNINGS (Empty Files - No Data Recorded)")
        lines.append("-" * 80)
        for w in warnings[:20]:
            lines.append(f"   -> {os.path.basename(w['file'])}")
        if len(warnings) > 20: lines.append(f"   ... and {len(warnings)-20} more.")

    # SECTION 2: CRITICAL ERRORS
    errors = [e for e in stats['errors'] if e.get('type') == 'CRITICAL']
    if errors:
        lines.append("="*80)
        lines.append("[X] CRITICAL FAILURES (Action Required)")
        lines.append("-" * 80)
        for err in errors:
            lines.append(f"   -> {err['reason']}")
            # FIX: Don't print 'File: External Tool' if it's redundant
            if 'file' in err and err['file'] != "External Tool":
                lines.append(f"      File: {err['file']}")
            
    lines.append("="*80)
    lines.append("END OF REPORT")

    report_content = "\n".join(lines)

    # Print summary to console
    for line in lines[:35]: logger.info(line)
    if len(lines) > 35: logger.info("... (Full report saved to file)")

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
        "duration_imu_sec": 0, "duration_aud_sec": 0, "gps_fixes": 0, # RELEVANT METRICS
        "sessions": [],
        "errors": [] # Dictionaries look like: {'type': 'WARN'|'CRITICAL', 'file': name, 'reason': msg}
    }

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
        #------

        # ==========================================
        # 1. IMU PROCESSING
        # ==========================================
        imu_files = files_map['imu']
        sess_metrics["files_total"] += len(imu_files)
        
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
                    stats['total_imu'] += 1
                    status, msg, df, meta = parse_imu_file(filepath)

                    # CASE 1: VALID DATA
                    if status == "SUCCESS":
                        stats['success_imu'] += 1
                        sess_metrics["imu_ok"] += 1
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
                    t_start = imu_df['Time'].iloc[0]
                    t_end = imu_df['Time'].iloc[-1]
                    update_range(t_start, t_end)

                    # Calculate duration
                    delta = t_end - t_start
                    stats['duration_imu_sec'] += delta.total_seconds()
                    
                    if last_meta: last_meta['Start_Time'] = t_start
                    
                    success = finisher.save_imu_csv(imu_df, uid=session_device_id)
                    if success and last_meta:
                        finisher.generate_metadata_file(last_meta, end_time=t_end)

                except Exception as e:
                    logger.error(f"Failed to finalize IMU session {session_id}: {e}")
        else:
            logger.warning("No IMU files found.")

        # ==========================================
        # 2. AUDIO PROCESSING
        # ==========================================
        aud_files = files_map['aud']
        sess_metrics["files_total"] += len(aud_files)
        aud_files.sort(key=extract_file_number)

        if aud_files:
            logger.info(f"Starting Audio Parser on {len(aud_files)} files...")   
            for filepath in tqdm(aud_files, desc=f"Audio ({session_id})", unit="file"):
                try:
                    # --- PARSER UNPACKING ---
                    # Returns: (status, message, meta, audio_data, timestamps)
                    stats['total_aud'] += 1
                    status, msg, meta, audio_data, timestamps = parse_audio_file(filepath)

                    # CASE 1: SUCCESSFUL PARSE
                    if status == "SUCCESS":
                        stats['success_aud'] += 1
                        sess_metrics["aud_ok"] += 1

                        # Robust ID extraction (if IMU failed/missing)
                        if session_device_id is None and meta:
                            session_device_id = meta.get('DeviceID', 'UnknownTag')
                        
                        if meta and audio_data is not None:
                            duration = len(audio_data) / meta['SampleRate']
                            end_time = meta['Start_Time'] + timedelta(seconds=duration)
                            
                            sess_metrics["aud_duration"] += duration
                            stats['duration_aud_sec'] += duration

                            update_range(meta['Start_Time'], end_time)

                            finisher.save_aud_wav(audio_data, meta)
                            finisher.generate_metadata_file(meta, end_time=end_time, time_stamps=timestamps)
                    
                    # CASE 2: SILENT / EMPTY FILE (Warning)
                    elif status == "EMPTY":
                        stats['warn_aud'] += 1
                        stats['errors'].append({
                            "type": "WARN", 
                            "file": filepath, 
                            "reason": msg
                        })

                    # CASE 3: CRITICAL ERROR
                    else: 
                        stats['failed_aud'] += 1
                        stats['errors'].append({
                            "type": "CRITICAL", 
                            "file": filepath, 
                            "reason": msg
                        })

                except Exception as e:
                    stats['failed_aud'] += 1
                    stats['errors'].append({"type": "CRITICAL", "file": filepath, "reason": f"Unexpected loop crash: {e}"})

        # ==========================================
        # 3. PROCESS GPS FILES
        # ==========================================
        gps_files = files_map['gps']
        sess_metrics["files_total"] += len(gps_files)
        sess_metrics["gps_attempts"] += len(gps_files)
        
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
                stats['total_gps'] += 1
                
                # GPS parser returns Tuple (Status, Message)
                status, reason_msg = parse_gps_file(filepath, abs_snap_dir)

                if status == "SUCCESS":
                    stats['success_gps'] += 1
                    sess_metrics["gps_ok"] += 1
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
                    stats['errors'].append({"type": "WARN", "file": filepath, "reason": reason_msg})

                else: 
                    stats['failed_gps'] += 1
                    stats['errors'].append({"type": "CRITICAL", "file": filepath, "reason": reason_msg})


            # 2. DYNAMIC FOLDER RENAMING (Date + Device ID)
            # We rename the folder from the generic Session ID to a 
            # human-readable YYYY_MM_DD-DeviceID format.
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
                    
                    # Rename only if target doesn't exist to prevent collision/crash
                    if not os.path.exists(new_snap_dir):
                        if os.path.exists(abs_snap_dir):
                            os.rename(abs_snap_dir, new_snap_dir)
                            logger.info(f"   -> Renamed session folder to: {new_folder_name}")
                            # Update pointers for GeoTag step
                            abs_snap_dir = new_snap_dir
                            abs_decode_dir = new_decode_dir
                    else:
                        # Target exists, so we assume we are resuming/overwriting
                        logger.info(f"   -> Folder {new_folder_name} exists. Using it.")
                        abs_snap_dir = new_snap_dir
                        abs_decode_dir = new_decode_dir

                except Exception as e:
                    logger.warning(f"Could not rename session folder: {e}")
            
            # 3. RUN GEOTAG 
            if session_gps_valid_count > 0:
                logger.info(f"   -> Launching GeoTag for {final_id}...")
                
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
                    # Finalize the decoded GPS output
                    success, count = finisher.process_gps_output(abs_decode_dir, final_id)
                    if success: 
                        sess_metrics["gps_fixes"] = count
                        stats["gps_fixes"] += count # Update Global Stats
                else:
                    err_msg = f"GeoTag Tool Failed | Session: {final_id} | Reason: {geo_msg}"
                    logger.error(f"  [CRITICAL ERROR] {err_msg}")
                    stats['errors'].append({
                        "type": "CRITICAL", 
                        "file": "External Tool", 
                        "reason": err_msg
                    })

        # SAVE SESSION STATS
        stats['sessions'].append(sess_metrics)

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