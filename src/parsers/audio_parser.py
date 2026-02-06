import os
import struct
import logging
import numpy as np

from datetime import datetime
from src.core.binary_decoder import decode_binary_header, get_precise_start_time

logger = logging.getLogger("wildlifetag_automator")

def parse_audio_file(filepath):
    """
    Parses raw binary audio into standard WAV format.
    Includes artifact removal and BCD (Binary Coded Decimal) timestamp decoding.

    Returns:
        (status, message, audio_data, meta)
        status: "SUCCESS", "EMPTY", "FAIL"
        message: Description of the result or error

    Includes:
    - Decode 150-byte Universal Header with Precision Timing.
    - Remove 14-byte Metadata Footers inserted every 64KB.
    - Remove "Startup Pop" (sensor initialization artifacts).
    - Return cleaned PCM data ready for .WAV export.

    FILE FORMAT SPECIFICATION:
    ===========================================================================
    - Codec: Signed 16-bit PCM (Little Endian).
    - Sample Rate: 48,000 Hz.
    - Structure: 150-byte Header, followed by audio data.
    - Artifacts: 
        1. 64KB Page Footers: Every 65,536 bytes, a 14-byte metadata footer is inserted.
           [Magic: 4B] [Time: 4B] [Date: 4B] [Pad: 2B] = 14 Bytes.
           Magic = 0xABCDEFEF (Little Endian).
        2. Startup Pop: The first ~17ms contain sensor initialization data (0x8000).

    AUDIO (.BIN) FILE STRUCTURE
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
    
    # --- CONSTANTS ---
    # Standard Vesper Header is 150 bytes (Universally confirmed)
    HEADER_SIZE = 150
    
    # Artifact Definition (64KB Page Footer)
    FOOTER_MAGIC = b'\xEF\xEF\xCD\xAB' # 0xABCDEFEF (Little Endian)
    FOOTER_LEN = 14                    
    
    # Safety Margin (The "Kill Zone")
    # We remove 2 bytes (1 sample) before and 2 bytes after the footer to kill edge clicks.
    MARGIN_LEFT = 2
    MARGIN_RIGHT = 2

    if not os.path.exists(filepath):
        # Return format: Status, Msg, Meta, AudioData, FooterTimestamps
        return "FAIL", "File not found", None, None, []

    try:
        # --- PART 1: HEADER PARSING & PRECISION TIME ---
        # Decode standard metadata (IDs, SampleRate, Coarse Time)
        meta = decode_binary_header(filepath, header_size=HEADER_SIZE)

        if not meta: 
            return "FAIL", "Header invalid/unreadable", None, None, []
            
        # Calculate Precision Start Time (Sub-millisecond) 
        # It uses the shared logic for Offset 140-143 + 1-sample correction
        meta['Start_Time'] = get_precise_start_time(filepath, meta, sensor_type="AUD")
        meta['Start_Time_Str'] = meta['Start_Time'].strftime('%Y-%m-%d %H:%M:%S.%f')
        
        # --- PART 2: READ RAW FILE ---
        with open(filepath, 'rb') as f:
            f.seek(HEADER_SIZE)
            raw_bytes = f.read()

        if len(raw_bytes) == 0:
            return "EMPTY", "File has header but 0 bytes of audio", meta, None, []

        clean_byte_stream = bytearray()
        cursor = 0
        file_len = len(raw_bytes)
        timestamps = [] # Store timestamps found in footers for debugging/validation
        
        # --- PART 3: ARTIFACT REMOVAL LOOP ---
        while cursor < file_len:
            # Search for the next metadata footer
            next_footer = raw_bytes.find(FOOTER_MAGIC, cursor)
            
            # If no footer found, append the rest of the file and finish
            if next_footer == -1:
                clean_byte_stream.extend(raw_bytes[cursor:])
                break
            
            # --- EXTRACT FOOTER TIMESTAMP (For Logging/Validation) ---
            # Footer Structure: [Magic:4] [Time:4] [Date:4] [Pad:2]
            try:
                # We extract 8 bytes starting 4 bytes after the footer magic
                # offsets relative to magic: 0-3=Magic, 4-7=Time, 8-11=Date
                ts_chunk = raw_bytes[next_footer+4 : next_footer+12]
                
                if len(ts_chunk) == 8:
                    # Time: HH(0), MM(1), SS(2), Pad(3)
                    hh, mm, ss = ts_chunk[0], ts_chunk[1], ts_chunk[2]
                    
                    # Date: Mon(5), Day(6), Year(7)
                    mon, day, yy  = ts_chunk[5], ts_chunk[6], ts_chunk[7]

                    # Use :02x to read bytes strictly as Hex digits
                    ts_str = f"20{yy:02x}-{mon:02x}-{day:02x} {hh:02x}:{mm:02x}:{ss:02x}"
                    timestamps.append(ts_str)
            except Exception:
                pass # Non-critical failure

            # --- CALCULATE CUTS ---
            # Cut point Left: Footer Start - Margin
            # Ensure we don't cut before the current cursor (overlap check)
            cut_start = max(cursor, next_footer - MARGIN_LEFT)
            
            # Append valid audio up to the cut point
            clean_byte_stream.extend(raw_bytes[cursor : cut_start])
            
            # Advance Cursor: Skip Footer + Right Margin (The "Kill Zone")
            cursor = next_footer + FOOTER_LEN + MARGIN_RIGHT

        # --- PART 4: FINALIZE AUDIO ---
        # Convert to Numpy Array (Signed 16-bit PCM)
        audio_data = np.frombuffer(clean_byte_stream, dtype='<i2')
        
        # --- PART 5: MUTE STARTUP ARTIFACTS (The "Pop") ---
        # The first ~17ms (approx 800 samples at 48k) often contain DC offset/wake-up noise.
        # We mute the first 1000 samples to be safe.
        
        #if len(audio_data) > 1000:
        #    audio_data[:1000] = 0
        
        # FINAL CHECK: Did we end up with valid data?
        if len(audio_data) == 0:
            return "EMPTY", "Silent (0 samples after processing)", meta, audio_data, timestamps

        # Calculate Duration for Meta
        if meta.get('SampleRate', 0) > 0:
            meta['Duration'] = len(audio_data) / meta['SampleRate']

        return "SUCCESS", "Parsed Successfully", meta, audio_data, timestamps

    except Exception as e:
        return "FAIL", f"Crash: {str(e)}", None, None, []