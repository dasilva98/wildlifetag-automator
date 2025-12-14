import wave
import numpy as np
import os
import logging
from scipy.io import wavfile
from src.core.binary_utils import read_vesper_header

logger = logging.getLogger("vesper_automator")

def parse_audio_file(filepath):
    """
    Parses raw binary audio from Vesper sensors into standard WAV format.
    
    FILE FORMAT SPECIFICATION:
    - Codec: Signed 16-bit PCM (Little Endian).
    - Sample Rate: 48,000 Hz.
    - Structure: 150-byte Header, followed by audio data.
    - Artifacts: 
        1. 64KB Page Footers: Every 65,536 bytes, a 14-byte metadata footer is inserted.
           [Magic: 4B] [Time: 4B] [Date: 4B] [Pad: 2B] = 14 Bytes.
           Magic = 0xABCDEFEF (Little Endian).
        2. Startup Pop: The first ~17ms contain sensor initialization data (0x8000).

    Args:
        filepath (str): Path to the raw .BIN file.
        output_wav_path (str): Path where the .WAV should be saved.

    Returns:
        tuple: (success_bool, timestamps_list)



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
    |  METADATA FOOTER 2 (14 Bytes)                         |
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
    | 40-43   | UInt32  | 00 00 00 00     | Bitmask         |
    | ...     | ...     | 00 ...          | (Reserved/Zero) |
    | 128-131 | UInt32  | 5A A5 5A A5     | Sync Word       |
    | 132-135 | BCD     | 11 13 01 00     | Start Time      |
    | 136-139 | BCD     | 07 09 29 25     | Start Date      |
    | 141-144 | UInt32  | (Dynamic)       | Boot Timestamp  |
    | 145-148 | UInt32  | (Dynamic)       | System Ticks    |
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
    | 4-7     | 11 13 01 00 | Current Block Time (HH:MM:SS) |
    | 8-11    | 07 09 29 25 | Current Block Date (MM:DD:YY) |
    | 12-13   | FF 03       | Padding / Checksum            |
    ---------------------------------------------------------
    NOTE: This 14-byte footer interrupts the audio stream and
    causes a loud "Click" if not removed during parsing.

    """
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return False, None, None, []

    # --- CONSTANTS ---
    SAMPLE_RATE = 48000
    HEADER_SIZE = 142
    
    # Artifact Definition
    FOOTER_MAGIC = b'\xEF\xEF\xCD\xAB' # 0xABCDEFEF
    FOOTER_LEN = 14                    # 4 Magic + 4 Time + 4 Date + 2 Pad

    # Safety Margin (The "Kill Zone")
    # We remove 2 bytes (1 sample) before and 2 bytes after the footer to kill edge clicks.
    MARGIN_LEFT = 2
    MARGIN_RIGHT = 2

    timestamps = []

    try:
        # Header Parsing
        meta = read_vesper_header(filepath, header_size= HEADER_SIZE)
        if not meta: return False, None, None, []
        
        # Read Raw File
        with open(filepath, 'rb') as f:
            f.seek(HEADER_SIZE)
            raw_bytes = f.read()

        # Artifact Removal (Search & Destroy)
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
            
            # --- EXTRACT TIMESTAMP ---
            # Structure: [Magic:4] [Time:4] [Date:4] [Pad:2]
            # Offsets relative to 'next_footer': 4 to 12
            ts_chunk = raw_bytes[next_footer+4 : next_footer+12]
            if len(ts_chunk) == 8:
                try:
                    # BCD/Hex Decoding
                    hh, mm, ss = ts_chunk[0], ts_chunk[1], ts_chunk[2]
                    mon, day, yy = ts_chunk[5], ts_chunk[6], ts_chunk[7]
                    ts_str = f"20{yy:02d}-{mon:02d}-{day:02d} {hh:02d}:{mm:02d}:{ss:02d}"
                    timestamps.append(ts_str)
                except:
                    pass # Ignore parsing errors in metadata

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

        # Initial "Pop" Removal
        # The sensor outputs -32768 (0x8000) during wake-up.
        """valid_mask = audio_data != -32768
        
        if np.any(valid_mask):
            first_valid_idx = np.argmax(valid_mask)
            # Add a 100-sample (2ms) buffer to ensure the DC offset has settled
            start_idx = first_valid_idx + 100
            
            if start_idx < len(audio_data):
                audio_data = audio_data[start_idx:]
            else:
                logger.warning(f"File {os.path.basename(filepath)} contained only mute data.")
                return False, []
        else:
            logger.warning(f"File {os.path.basename(filepath)} appears to be empty/corrupt.")
            return False, []"""

        # Write WAV File
        """os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
        wavfile.write(output_wav_path, SAMPLE_RATE, audio_data)
        
        logger.info(f"✅ Converted: {os.path.basename(output_wav_path)} ({len(timestamps)} blocks cleaned)")
        """
        return True, meta, audio_data, timestamps

    except Exception as e:
        logger.error(f"Failed to parse audio {filepath}: {e}")
        return False, None, None, []