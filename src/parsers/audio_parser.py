import numpy as np
import os
import logging
import struct
from datetime import datetime
from src.core.binary_utils import read_vesper_header

logger = logging.getLogger("wildlifetag_automator")

def parse_audio_file(filepath):
    """
    Parses raw binary audio from Vesper sensors into standard WAV format.
    Includes artifact removal and BCD (Binary Coded Decimal) timestamp decoding.

    FILE FORMAT SPECIFICATION:
    - Codec: Signed 16-bit PCM (Little Endian).
    - Sample Rate: 48,000 Hz.
    - Structure: 150-byte Header, followed by audio data.
    - Artifacts: 
        1. 64KB Page Footers: Every 65,536 bytes, a 14-byte metadata footer is inserted.
           [Magic: 4B] [Time: 4B] [Date: 4B] [Pad: 2B] = 14 Bytes.
           Magic = 0xABCDEFEF (Little Endian).
        2. Startup Pop: The first ~17ms contain sensor initialization data (0x8000).

    VESPER AUDIO (.BIN) FILE STRUCTURE
    ===========================================================================
    The file consists of a 150-byte Header followed by a sequence of 64KB
    Audio Pages. Each page is terminated by a 14-byte Metadata Footer.

    GLOBAL LAYOUT:
    ---------------------------------------------------------
    |  HEADER (0 - 150 Bytes)                               |
    |-------------------------------------------------------|
    |  AUDIO DATA PAGE 1 (~65,536 Bytes)                    |
    |-------------------------------------------------------|
    |  METADATA FOOTER 1 (14 Bytes)                         |
    |-------------------------------------------------------|
    |  AUDIO DATA PAGE 2 (~65,536 Bytes)                    |
    |-------------------------------------------------------|
    |  ... (Repeats until EOF)                              |
    ---------------------------------------------------------

    1. HEADER DETAIL (Offsets 0 - 150)
    ---------------------------------------------------------
    | Offset  | Type    | Value (Hex)     | Description     |
    |---------|---------|-----------------|-----------------|
    | 0-3     | UInt32  | C0 DA AF DE     | Magic Number    |
    | 4-7     | UInt32  | 3C 50 0E 53     | Device ID       |
    | 8-23    | String  | "SPH0641..."    | Sensor Name     |
    | 28-31   | UInt32  | 00 BB 80 00     | Sample Rate (48k)|
    | 128-131 | UInt32  | 5A A5 5A A5     | Sync Word       |
    | 149     | UInt8   | 80              | Padding         |
    ---------------------------------------------------------

    2. AUDIO PAYLOAD (Signed 16-bit PCM, Little Endian)
    ---------------------------------------------------------
    | Rel Byte| Value (Hex) | Int16 Val   | Description     |
    |---------|-------------|-------------|-----------------|
    | 0-1695  | 00 80       | -32768      | MUTE / STARTUP  |
    |         |             |             | (Sensor Wakeup) |
    | 1696+   | (Var)       | (Var)       | VALID AUDIO     |
    ---------------------------------------------------------

    3. BLOCK ARTIFACT (Inserted every ~64KB)
    ---------------------------------------------------------
    | Rel Byte| Value (Hex) | Description                   |
    |---------|-------------|-------------------------------|
    | 0-3     | EF EF CD AB | Footer Magic (Marker)         |
    | 4-7     | HH MM SS XX | Time (BCD Encoded)            |
    | 8-11    | MM DD YY XX | Date (BCD Encoded)            |
    | 12-13   | FF 03       | Padding / Checksum            |
    ---------------------------------------------------------
    """
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return False, None, None, []

    # --- CONSTANTS ---
    SAMPLE_RATE = 48000
    HEADER_SIZE = 142
    
    # Artifact Definition
    FOOTER_MAGIC = b'\xEF\xEF\xCD\xAB' # 0xABCDEFEF (Little Endian)
    FOOTER_LEN = 14                    
    
    # Safety Margin (The "Kill Zone")
    # We remove 2 bytes (1 sample) before and 2 bytes after the footer to kill edge clicks.
    MARGIN_LEFT = 2
    MARGIN_RIGHT = 2

    timestamps = []

    try:
        # Header Parsing
        meta = read_vesper_header(filepath, header_size=HEADER_SIZE)
        if not meta: return False, None, None, []
        
        # Read Raw File
        with open(filepath, 'rb') as f:
            f.seek(HEADER_SIZE)
            raw_bytes = f.read()

        clean_byte_stream = bytearray()
        cursor = 0
        file_len = len(raw_bytes)
        
        while cursor < file_len:
            # Search for the next metadata footer
            next_footer = raw_bytes.find(FOOTER_MAGIC, cursor)
            
            # If no footer found, append the rest of the file and finish
            if next_footer == -1:
                clean_byte_stream.extend(raw_bytes[cursor:])
                break
            
            # --- EXTRACT TIMESTAMP (Validated against Hex Dump) ---
            # Hex Sequence Example: 07 34 51 00 04 09 29 25
            # Time (Offsets 0-3): [07:HH] [34:MM] [51:SS] [00:Pad]
            # Date (Offsets 4-7): [04:Pad] [09:Mon] [29:Day] [25:Year]
            try:
                # We extract 8 bytes starting 4 bytes after the footer magic
                ts_chunk = raw_bytes[next_footer+4 : next_footer+12]
                
                if len(ts_chunk) == 8:
                    # Parse Time (Indices 0, 1, 2)
                    hh = ts_chunk[0]
                    mm = ts_chunk[1]
                    ss = ts_chunk[2]
                    
                    # Parse Date (Indices 5, 6, 7)
                    # Index 4 is padding (Value '04' in your image)
                    mon = ts_chunk[5]  # 0x09 -> Month
                    day = ts_chunk[6]  # 0x29 -> Day
                    yy  = ts_chunk[7]  # 0x25 -> Year (2025)

                    # Validation
                    # Check if BCD/Hex values are within reasonable calendar ranges
                    if 1 <= mon <= 0x12 and 1 <= day <= 0x31:
                        # Use :02x to read bytes strictly as Hex digits
                        ts_str = f"20{yy:02x}-{mon:02x}-{day:02x} {hh:02x}:{mm:02x}:{ss:02x}"
                        timestamps.append(ts_str)
            except Exception:
                pass

            # --- CALCULATE CUTS ---
            # Cut point Left: Footer Start - Margin
            # We must ensure we don't cut before the current cursor (overlap check)
            cut_start = max(cursor, next_footer - MARGIN_LEFT)
            
            # Append valid audio up to the cut point
            clean_byte_stream.extend(raw_bytes[cursor : cut_start])
            
            # Advance Cursor: Skip Footer + Right Margin
            cursor = next_footer + FOOTER_LEN + MARGIN_RIGHT

        # Convert to Numpy Array (Signed 16-bit)
        audio_data = np.frombuffer(clean_byte_stream, dtype='<i2')
        
        return True, meta, audio_data, timestamps

    except Exception as e:
        logger.error(f"Failed to parse audio {filepath}: {e}")
        return False, None, None, []