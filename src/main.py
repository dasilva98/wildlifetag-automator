import yaml
import os
import pandas as pd
import re
from tqdm import tqdm
from datetime import datetime
from src.core.logger import setup_logger
from src.core.crawler import find_raw_files
from src.parsers.imu_parser import parse_imu_file
from src.parsers.audio_parser import parse_audio_file
from src.core.finisher import FileFinisher


def load_config(config_path="config.yaml"):
    """Loads configuration from the YAML file"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def generate_summary(stats, logger, processed_folder):
    """
    Prints a summary table to the logs and writes a report file to disk after execution
    """

    # Generate report content
    lines = []
    lines.append("="*40)
    lines.append(f"VESPER AUTOMATOR - PROCESSING SUMMARY")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("="*40)
    lines.append(f"Total Files Found: {stats['total']}")
    lines.append("-"*40)
    lines.append(f"Total IMU Files Found: {stats['total_imu']}")
    lines.append(f"IMU Files Successfully Parsed: {stats['success_imu']}")
    lines.append(f"IMU Files Failed / Skipped:  {stats['failed_imu']}")
    lines.append("-"*40)
    lines.append(f"Total AUD Files Found: {stats['total_aud']}")
    lines.append(f"AUD Files Successfully Parsed: {stats['success_aud']}")
    lines.append(f"AUD Files Failed / Skipped:  {stats['failed_aud']}")
    lines.append("-"*40)
    lines.append(f"Total GPS Files Found: {stats['total_gps']}")
    lines.append(f"GPS Files Successfully Parsed: {stats['success_gps']}")
    lines.append(f"GPS Files Failed / Skipped:  {stats['failed_gps']}")
 
    if stats['errors']:
        logger.info("-"*40)
        logger.info("FAILED FILES:")
        for err in stats['errors']:
            logger.info(f"  [X] {os.path.basename(err['file'])}  -> {err['reason']}")
            
    logger.info("="*40)

    report_content = "\n".join(lines)

    # Print to logger(console)
    for line in lines:
        logger.info(line)

    # Write to a persistent text file
    # Save reports in a specific subfolder: data/processed/report_cards/
    reports_dir = os.path.join(processed_folder, "report_cards")
    os.makedirs(reports_dir, exist_ok=True)
    
    report_filename = f"processing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = os.path.join(reports_dir, report_filename)
    
    try:
        with open(report_path, "w") as f:
            f.write(report_content)
        logger.info(f"\n[Report] Detailed summary saved to: {report_path}")
    except Exception as e:
        logger.error(f"Failed to write summary report file: {e}")

def extract_file_number(filepath):
    """Helper to extract the first number from a filename for sorting."""
    # Find digits in the filename
    match = re.search(r'(\d+)', os.path.basename(filepath))
    # Return the integer value if found, otherwise 0
    return int(match.group(1)) if match else 0

def main():

    pd.set_option('display.max_columns', None)

    # Setup Logging
    logger = setup_logger("vesper_automator", log_dir="./logs")
    logger.info("--- Vesper Automator Started ---")

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
        "total_imu": 0,
        "total_aud": 0,
        "total_gps": 0,
        "success_imu": 0,
        "success_aud": 0,
        "success_gps": 0,
        "failed_imu": 0,
        "failed_aud": 0,
        "failed_gps": 0,
        "errors": [] # List of dicts: {'file': name, 'reason': msg}
    }

# --- MAIN LOOP: Iterate over each Tag/Session ---
    for session_id, files_map in all_sessions.items():
        logger.info(f"Processing Session: {session_id}")

        # ==========================================
        # 1. PROCESS IMU FILES (Merge into one CSV)
        # ==========================================
        imu_files = files_map['imu']
        stats['total_imu'] += len(imu_files)
        
        imu_files.sort(key=extract_file_number)
        imu_df = pd.DataFrame()
        session_device_id = None
        last_meta = None # Keep track of metadata for the .txt generator

        if imu_files:
            logger.info(f"Starting IMU Parser on {len(imu_files)} files...")
            
            # Start tqdm loop (progress bar)
            for filepath in tqdm(imu_files, desc=f"IMU ({session_id})", unit="file"):
                try:
                    df, meta = parse_imu_file(filepath)
                    if df is not None and not df.empty:
                        stats['success_imu'] += 1
                        
                        # Concatenate to the session master dataframe
                        imu_df = pd.concat([imu_df, df], ignore_index=True)
                        
                        # Capture Device ID/Meta from the first valid file
                        if session_device_id is None and meta:
                            session_device_id = meta.get('DeviceID', 'UnknownTag')
                            last_meta = meta
                    else:
                        stats['failed_imu'] += 1
                        stats['errors'].append({
                            "file": filepath, 
                            "reason": "IMU Parser returned None or Empty DF"
                        })
                        
                except Exception as e:
                    # Unexpected Crash (e.g., PermissionError, MemoryError)
                    stats['failed_imu'] += 1
                    stats['errors'].append({
                        "file": filepath, 
                        "reason": f"IMU Crash: {str(e)}"
                    })
                    logger.error(f"IMU Crash {os.path.basename(filepath)}: {e}")
        
            # Save the merged CSV for this specific tag
            if not imu_df.empty:
                # SAFETY NET: Ensure strict chronological order, the sorting is already done by ordering the filenames before the parsing but does is good standard
                imu_df = imu_df.sort_values(by='Time')
                # 1. Save CSV (The filename is generated inside save_imu_csv based on timestamps)
                success = finisher.save_imu_csv(imu_df, uid=session_device_id)
                
                # 2. Generate Metadata .txt (Using the utility function we moved to binary_utils)
                # We need to construct the path manually to match the CSV location or rely on finisher structure
                if success and last_meta:
                    # We create a dummy path that points to the output folder so the txt is saved next to the CSV
                    # Or simpler: we use the finisher structure directly inside generate_metadata_file logic
                    finisher.generate_metadata_file(last_meta)
        else:
            # No IMU files for this session
            logger.warning("No IMU files foud.")


        # ==========================================
        # 2. PROCESS AUDIO FILES
        # ==========================================
        audio_files = files_map['aud']
        stats['total_aud'] += len(audio_files)

        if audio_files:
            logger.info(f"Starting Audio Parser on {len(audio_files)} files...")   

            # TODO Just test on the first 5 for now to avoid filling disk with WAVs
            for filepath in tqdm(audio_files[:5], desc=f"Audio ({session_id})", unit="file"):
                try:
                    # Construct output path: data/processed/audio/filename.wav
                    output_name = os.path.splitext(os.path.basename(filepath))[0] + ".wav"
                    output_path = os.path.join(processed_folder, "aud", output_name)
                    
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)

                    # Call parser (assuming signature: parse_audio_file(input, output))
                    # Note: We need to verify if your parse_audio_file takes output_path or just input
                    # Based on standard design, usually parser takes input and returns data/success.
                    # I will assume we updated it to take output_path as per your snippet.


                    success = parse_audio_file(filepath, output_path) #TODO Bugfix, there is this constant (175BPM) sharp clicking noise on the audio 
                    
                    if success:
                        stats['success_aud'] += 1
                        # TODO Generate Metadata TXT
                        # Add the audio sync lines to the meta structure
                        # (This requires a separate function to read the sync lines if needed, or we omit them)
        
                    else:
                        stats['failed_aud'] += 1
                        stats['errors'].append({
                            "file": filepath, 
                            "reason": "AUDIO Parser returned None or Empty DF"
                        })
                        logger.warning(f"Audio parse failed for {filepath}")

                except Exception as e:
                    stats['failed_aud'] += 1
                    stats['errors'].append({
                        "file": filepath, 
                        "reason": f"AUDIO Crash: {str(e)}"
                    })
                    logger.error(f"AUDIO Crash: {os.path.basename(filepath)}: {e}")


        # ==========================================
        # 3. PROCESS GPS FILES
        # ==========================================
        gps_files = files_map['gps']
        stats['total_gps'] += len(gps_files)

        if gps_files:
            logger.info(f"  > Found {len(gps_files)} GPS files (Parser TODO)")
            # TODO: GPS Parser logic

        
    # Final Report
    stats["total"] = stats["total_imu"] + stats["total_aud"] + stats["total_gps"]
    generate_summary(stats,logger,processed_folder)

if __name__ == "__main__":
    main()