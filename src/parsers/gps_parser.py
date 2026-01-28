import os
import struct
import numpy as np
import logging

logger = logging.getLogger("wildlifetag_automator")

def parse_gps_file(filepath, output_root):
    """
    Parses Vesper GPS Binary (.BIN) into Snapshot (.DAT) files.
    Optimized for memory usage and correct 'Word Swap' logic.
    """

    METADATA_HEADER_SIZE = 1024
    MAGIC_WORD = 0xA55AA55A
    
    if not os.path.exists(filepath):
        logger.error(f"GPS File not found: {filepath}")
        return False

    try:
        # --- HEADER PROCESSING ---
        with open(filepath, 'rb') as f:
            header_bytes = f.read(METADATA_HEADER_SIZE)
            
            if len(header_bytes) < 16:
                logger.error(f"GPS file too short: {filepath}")
                return False

            # Validate Magic Word (First 4 bytes)
            magic = struct.unpack('<I', header_bytes[0:4])[0]
            if magic != MAGIC_WORD:
                logger.warning(f"Invalid Magic Word in {os.path.basename(filepath)}: {magic:X}")
                return False

            # Extract Timestamp (Bytes 4-12)
            # Time: Hour, Min, Sec (Offsets 4,5,6)
            h, m, s = header_bytes[4], header_bytes[5], header_bytes[6]
            
            # Date: Month, Day, Year (Offsets 9, 10, 11)
            mon, day, yr = header_bytes[9], header_bytes[10], header_bytes[11]
            full_year = 2000 + yr

            # Construct Filename
            filename = f"snap.{full_year}_{mon:02d}_{day:02d}_{h:02d}_{m:02d}_{s:02d}_GC0.dat"

            # Create Output Directory (Automatic handling)
            output_dir = os.path.join(output_root, "gps", "snapshots")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, filename)

            # Skip if already exists (Idempotency - Saves time on re-runs)
            if os.path.exists(output_path):
                logger.info(f"Skipping existing GPS file: {filename}")
                return False

        # --- PAYLOAD (EFFICIENT) PROCESSING  ---
        # Read directly to Numpy (Fast I/O, skip header)
        raw_data = np.fromfile(filepath, dtype='<u4', offset=METADATA_HEADER_SIZE)

        if raw_data.size == 0:
            logger.warning(f"GPS file empty payload: {os.path.basename(filepath)}")
            return False

        # --- Perform Word Swap (I/Q Swap) ---

        # Shift High 16 bits to Low, and Low to High
        # 0xAABBCCDD -> 0xCCDDAABB
        swapped_data = (raw_data << 16) | (raw_data >> 16)
        
        # --- Save to disk ---
        # Cast back to u4 to ensure strictly 32-bit output
        swapped_data.astype('<u4').tofile(output_path)
        
        logger.info(f"Generated GPS Snapshot: {filename}")
        return True

    except Exception as e:
        logger.error(f"GPS Parse Fail {os.path.basename(filepath)}: {e}")
        return False