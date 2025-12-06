import yaml
import os
import pandas as pd
from tqdm import tqdm
from datetime import datetime
from src.core.logger import setup_logger
from src.core.crawler import find_raw_files
from src.parsers.imu_parser import *
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
    lines.append(f"Successfully Parsed: {stats['success']}")
    lines.append(f"Failed / Skipped:  {stats['failed']}")

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
    
    # Crawl files
    raw_folder = config.get("raw_data_folder", "./data/raw")
    processed_folder = config.get("processed_folder", "./data/processed")
    finisher = FileFinisher(processed_folder)
    
    files_map = find_raw_files(raw_folder)

    # Summary stats container
    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "errors": [] # List of dicts: {'file': name, 'reason': msg}
    }

    # Process IMU files 
    imu_files = files_map['imu']
    stats['total'] += len(imu_files)

    if imu_files:
        logger.info(f"Starting IMU Parser on {len(imu_files)} files...")
        
        # Start tqdm loop (progress bar)
        for filepath in tqdm(imu_files, desc="IMU Parsing", unit="file"):
            try:
              
                df = parse_imu_file(filepath)
                
                if df is not None and not df.empty:
                    stats['success'] += 1

                    #Save the formatted CSV via finisher
                    finisher.save_imu_csv(df, filepath, uid=None)
                else:
                    stats['failed'] += 1
                    stats['errors'].append({
                        "file": filepath, 
                        "reason": "Parser returned None or Empty DF"
                    })
                    
            except Exception as e:
                # Unexpected Crash (e.g., PermissionError, MemoryError)
                stats['failed'] += 1
                stats['errors'].append({
                    "file": filepath, 
                    "reason": str(e)
                })
                logger.error(f"CRASH processing {os.path.basename(filepath)}: {e}")
    else:
        logger.warning("No IMU files foud.")


    # Process Audio Files
    audio_files = files_map['aud']
    # TODO We aren't adding these to stats['total'] yet just to keep the IMU test clean,
    # but normally you would increment stats['total'] here too.

    if audio_files:
        logger.info(f"Starting Audio Parser on {len(audio_files)} files...")   

        # Just test on the first 5 for now to avoid filling disk with WAVs
        for filepath in tqdm(audio_files[:5], desc="Audio Parsing", unit="file"):
             try:
                # Construct output path: data/processed/audio/filename.wav
                output_name = os.path.splitext(os.path.basename(filepath))[0] + ".wav"
                output_path = os.path.join(processed_folder, "audio", output_name)
                
                success = parse_audio_file(filepath, output_path) #TODO Bugfix, there is this constant (175BPM) sharp clicking noise on the audio 
                
                if success:
                     # For now, we are just testing, not adding to main stats object
                     # to avoid confusing the output until full integration
                     pass
                else:
                     logger.warning(f"Audio parse failed for {filepath}")

             except Exception as e:
                 logger.error(f"Audio CRASH: {e}")


    # Process GPS Files
    gps_files = files_map['gps']
    # TODO We aren't adding these to stats['total'] yet just to keep the IMU test clean,
    # but normally you would increment stats['total'] here too.

    if gps_files:
        logger.info(f"Starting GPS Parser on {len(gps_files)} files...")
        #TODO

        
    # FInal Report
    generate_summary(stats,logger,processed_folder)

if __name__ == "__main__":
    main()