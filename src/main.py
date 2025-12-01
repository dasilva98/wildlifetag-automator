import yaml
import os
from tqdm import tqdm
from datetime import datetime
from src.core.logger import setup_logger
from src.core.crawler import find_raw_files
from src.parsers.imu_parser import parse_imu_file

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
        
        # We store valid results here
        valid_data = []

        # Start tqdm loop (progress bar)
        for filepath in tqdm(imu_files, desc="IMU Parsing", unit="file"):
            try:
                # Run the parser
                data = parse_imu_file(filepath)
                
                if data is not None: # Success case
                    valid_data.append(data) # TODO: Here we would normally save 'data' to a CSV (file_finisher section to be implemented) to avoid filling up RAM
                    stats['success'] += 1
                else: # Failure case (logic handled inside parser, returned None)
                    stats['failed'] += 1
                    stats['errors'].append({
                        "file": filepath,
                        "reason": "Parser returned None (check logs)"
                    })
                    
            except Exception as e:
                # Unexpected Crash (e.g., PermissionError, MemoryError)
                # We catch it here so the loop DOES NOT BREAK
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


    # Process GPS Files
    gps_files = files_map['gps']
    # We aren't adding these to stats['total'] yet just to keep the IMU test clean,
    # but normally you would increment stats['total'] here too.

    if gps_files:
        logger.info(f"Starting GPS Parser on {len(gps_files)} files...")

        
    # FInal Report
    generate_summary(stats,logger,processed_folder)

if __name__ == "__main__":
    main()