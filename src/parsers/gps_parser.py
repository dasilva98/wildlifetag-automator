import os
import struct
import numpy as np
import logging
# [MERGE] Import the new shared utility for sub-second precision
from src.core.binary_decoder import get_precise_start_time

logger = logging.getLogger("wildlifetag_automator")

def extract_gps_snapshots(filepath, output_dir):
    """
    Writes new .DAT files (raw GPS snapshots) from GPS binaries (.BIN) 
    for the external GeoTag processing tool.
    
    Returns:
        (status, message)
        status: "SUCCESS", "EMPTY", "FAIL"
        message: Description of the result or error
    
    Includes:
    - Smart Header Detection (handling the 1024-byte 'warm-up' buffer).
    - Precision Timestamp calculation for logging.

    GPS Header: Should only be present in the first binary file 
                of a recording/session such as '0G.BIN'
    Size: 16 Bytes
    Start: 0x5AA55AA5
    Timestamp Offset: 4 (BCD), 12 (SubSec)

    HEADER DETAIL (Offsets 0 - 15)
    ----------------------------------------------------
    | Offset | Type   | Description                    |
    |--------|--------|--------------------------------|
    | 0-3    | UInt32 | Sync Word (0x5AA55AA5)         |
    | 4-6    | BCD    | HH, MM, SS                     |
    | 7-8    | Bytes  | Padding/Config (0x07 at off 8) |
    | 9-11   | BCD    | MM, DD, YY                     |
    | 12-13  | UInt16 | Subsecond Resolution           |
    | 14-15  | UInt16 | Subsecond Value                |
    ----------------------------------------------------

    """
    # Magic Word: Little Endian representation of bytes 5A A5 5A A5
    MAGIC_WORD = 0xA55AA55A
    
    if not os.path.exists(filepath):
        return "FAIL", "File Not Found"

    try:
        # --- HEADER ANALYSIS ---
        # Read 1024 bytes to cover both 'Compact' (16b) and 'Buffered' (1024b) headers
        with open(filepath, 'rb') as f:
            header_chunk = f.read(1024)
            
        if len(header_chunk) < 16:
            return "FAIL", "File too short (<16 bytes)"

        # --- Validate Magic Word ---
        magic = struct.unpack('<I', header_chunk[0:4])[0]
        if magic != MAGIC_WORD:
            return "FAIL", f"Invalid Magic Header: {magic:X}"

        # --- Extract Timestamp for Filename ---
        # [NOTE] The file stores BCD (Binary Coded Decimal).
        h, m, s = header_chunk[4], header_chunk[5], header_chunk[6]
        mon, day, yr = header_chunk[9], header_chunk[10], header_chunk[11]

        # Standard GeoTag filename format: snap.YYYY_MM_DD_HH_MM_SS_GC0.dat
        filename = f"snap.20{yr:02x}_{mon:02x}_{day:02x}_{h:02x}_{m:02x}_{s:02x}_GC0.dat"

        # --- Calculate Precision Metadata ---
        # We construct a mock metadata dictionary
        # This confirms the EXACT milliseconds (e.g. .593) for the logs
        # (We don't put ms in the filename because GeoTag might not support it)
        try:
            # Helper to quickly get BCD->Int for the utility
            def bcd(b): return (b // 16) * 10 + (b % 16)
            import pandas as pd # Import locally to avoid global dependency if mostly unused
            
            meta_lite = {
                "Start_Time": pd.Timestamp(
                    year=2000+bcd(yr), month=bcd(mon), day=bcd(day), 
                    hour=bcd(h), minute=bcd(m), second=bcd(s)
                ),
                "SampleRate": 0 # GPS is event-based
            }
            # Uses offsets 12-15 to calculate exact ms
            precise_start = get_precise_start_time(filepath, meta_lite, sensor_type="GPS")
            precise_time_str = precise_start.strftime('%H:%M:%S.%f')[:-3] # HH:MM:SS.mmm
        except Exception:
            precise_time_str = "Time_Calc_Error"

        # --- Determine Header Size (Smart Detection) ---
        # 0G.BIN fills the first flash page (1024 bytes) with zeros 
        # while waiting for the GPS radio to wake up.
        # If bytes 16 to 1023 are ALL zeros, the real data should start at 1024.
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

        # Word Swap (I/Q Correction) for GeoTag tool
        swapped_data = (raw_data << 16) | (raw_data >> 16)
        swapped_data.astype('<u4').tofile(output_path)
        
        # Return success with the precise time we calculated
        return "SUCCESS", f"Parsed (Head:{header_size}b, T:{precise_time_str})"

    except Exception as e:
        logger.error(f"GPS Crash {os.path.basename(filepath)}: {e}")
        return "FAIL", f"Crash: {str(e)}"