import os
import struct
import numpy as np
import logging

logger = logging.getLogger("wildlifetag_automator")

def parse_gps_file(filepath, output_dir):
    """
    Parses Vesper GPS Binary (.BIN) into Snapshot (.DAT) files.
    
    Returns:
        (status, message)
        status: "SUCCESS", "EMPTY", "FAIL"
        message: Description of the result or error
    """
    MAGIC_WORD = 0xA55AA55A
    
    if not os.path.exists(filepath):
        return "FAIL", "File Not Found"

    try:
        # --- HEADER ANALYSIS ---
        # We read 1024 bytes initially to check for padding
        with open(filepath, 'rb') as f:
            header_chunk = f.read(1024)
            
        if len(header_chunk) < 16:
            return "FAIL", "File too short (<16 bytes)"

        # ---Validate Magic Word---
        magic = struct.unpack('<I', header_chunk[0:4])[0]
        if magic != MAGIC_WORD:
            return "FAIL", f"Invalid Magic Header: {magic:X}"

        # ---Extract Timestamp---
        h, m, s = header_chunk[4], header_chunk[5], header_chunk[6]
        mon, day, yr = header_chunk[9], header_chunk[10], header_chunk[11]

        filename = f"snap.20{yr:02x}_{mon:02x}_{day:02x}_{h:02x}_{m:02x}_{s:02x}_GC0.dat"

        # ---Determine Header Size--- (Smart Detection)
        # 0G.BIN usually has 1024 bytes (mostly padding).
        # Others have 16 bytes.
        # We check if bytes 16 to 1024 are ALL zeros.
        # If true -> Header is 1024. If false -> Data starts at 16.
        if len(header_chunk) == 1024 and all(b == 0 for b in header_chunk[16:]):
            header_size = 1024
        else:
            header_size = 16

        # --- OUTPUT SETUP ---
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)

        if os.path.exists(output_path):
            return "SUCCESS", "Skipped (Already Exists)"

        # --- PAYLOAD PROCESSING ---
        # Read file using the calculated header offset
        raw_data = np.fromfile(filepath, dtype='<u4', offset=header_size)

        if raw_data.size == 0:
            return "EMPTY", "Payload is empty (No GPS fixes)"

        # Word Swap (I/Q Correction)
        swapped_data = (raw_data << 16) | (raw_data >> 16)
        swapped_data.astype('<u4').tofile(output_path)
        
        return "SUCCESS", f"Parsed (Header: {header_size}b)"

    except Exception as e:
        logger.error(f"GPS Crash {os.path.basename(filepath)}: {e}")
        return "FAIL", f"Crash: {str(e)}"