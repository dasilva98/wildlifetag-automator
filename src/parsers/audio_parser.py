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
    - Remove 16-byte Metadata Footers inserted every 64KB.
    - Remove "Startup Pop" (sensor initialization artifacts).
    - Return cleaned PCM data ready for .WAV export.

    FILE FORMAT SPECIFICATION:
    ===========================================================================
    - Codec: Signed 16-bit PCM (Little Endian).
    - Sample Rate: 48,000 Hz.
    - Structure: 150-byte Header, followed by audio data.
    - Artifacts:
        1. 64KB Page Footers: Every 65,536 bytes, a 16-byte metadata footer is inserted.
           [Magic: 4B] [Time: 4B] [Date: 4B] [SubsecFrac: 2B] [Subsec: 2B] = 16 Bytes.
           Magic = 0xABCDEFEF (Little Endian).
        2. Startup Pop: The first ~17ms contain sensor initialization data (0x8000).

    AUDIO (.BIN) FILE STRUCTURE
    ===========================================================================
    The file consists of a 150-byte Header followed by a sequence of 64KB
    Audio Pages. Each page is terminated by a 16-byte Metadata Footer.

    GLOBAL LAYOUT:
    ---------------------------------------------------------
    |  HEADER (0 - 150 Bytes)                               |
    |-------------------------------------------------------|
    |  AUDIO DATA PAGE 1 (~65,536 Bytes)                    |
    |-------------------------------------------------------|
    |  METADATA FOOTER 1 (16 Bytes)                         |
    |-------------------------------------------------------|
    |  AUDIO DATA PAGE 2 (~65,536 Bytes)                    |
    |-------------------------------------------------------|
    |  ... (Repeats until EOF)                              |
    ---------------------------------------------------------

    1. HEADER DETAIL (Offsets 0 - 150)
    --------------------------------------------------------------
    | Offset  | Type     | Value (Hex)     | Description --------|
    |---------|----------|-----------------|---------------------|
    | 0-3     | UInt32   | C0 DA AF DE     | Magic Number        |
    | 4-7     | UInt32   | 3C 50 0E 53     | Device ID           |
    | 8-14    | String   | ASCII "SPH0641" | Sensor Name         |
    | 28-31   | UInt32   | 80 BB 00 00     | Sample Rate = 48k   |
    | 60-127  |          | FF FF FF FF     | Padding             |
    | 128-131 | UInt32   | 5A A5 5A A5     | Timestamp Sync Word |
    |--------------------| Description --------------------------|
    | 132     | BCD      | 07 (7am)        | Start Hour          |
    | 133     | BCD      | 20 (20min)      | Start Minute        |
    | 134     | BCD      | 50 (50sec)      | Start Second        |
    | 135     | Pad      | 00 (00milisec?) | Always 0x00         |
    | 136     | UInt8    | Sometimes 07    | per-session marker, |
    |         |          |                 | meaning undocumented|
    | 137     | BCD      | 08 (Sept)       | Start Month         |
    | 138     | BCD      | 18 (18th)       | Start Day           |
    | 139     | BCD      | 25 (2025)       | Start Year          |
    | 140-141 | UInt16   | FF 03           | Subsecond Resolution|
    | 142-143 | UInt16   | CA 03           | Start Subsec Value  |
    | 149     | UInt8    | 00 80 00 80     | Mic wakeup          |
    --------------------------------------------------------------

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
    | 4-7     | HH MM SS XX | Time BCD (7 = Pad)            |
    | 8-11    | XX MM DD YY | Date BCD (8 = Pad)            |
    | 12-13   | FF 03       | 03FF => 1023  (Max Tick)      |
    | 14-15   | 0F 01       | 010F => 271   (Current Tick)  |
    ---------------------------------------------------------
    """

    # --- CONSTANTS ---
    # Standard Vesper Header is 150 bytes (Universally confirmed)
    HEADER_SIZE = 150

    # Artifact Definition (64KB Page Footer)
    FOOTER_MAGIC = b'\xEF\xEF\xCD\xAB' # 0xABCDEFEF (Little Endian)
    FOOTER_LEN = 16

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
            # Footer Structure: [Magic:4] [Time:4] [Date:4] [SubsecFrac:2] [Subsec:2]
            try:
                # We extract 12 bytes starting 4 bytes after the footer magic
                # offsets relative to magic: 0-3=Magic, 4-7=Time, 8-11=Date, 12-15=Ticks
                ts_chunk = raw_bytes[next_footer+4 : next_footer+FOOTER_LEN]

                if len(ts_chunk) == FOOTER_LEN-4:
                    # Time: HH(0), MM(1), SS(2), Pad(3)
                    hh, mm, ss = ts_chunk[0], ts_chunk[1], ts_chunk[2]

                    # Date: Pad(4), Mon(5), Day(6), Year(7)
                    mon, day, yy  = ts_chunk[5], ts_chunk[6], ts_chunk[7]

                    # Ticks: SubsecFrac(8-9), Subsec(10-11)
                    subsec_frac, subsec = struct.unpack('<HH', ts_chunk[8:12])

                    # Calculate precise milliseconds using hardware math
                    if subsec_frac > 0:
                        milisecs = 1000.0 * ((subsec_frac - subsec) / (subsec_frac + 1.0))
                    else:
                        milisecs = 0.0

                    if milisecs < 0:
                        milisecs += 1000.0 # Safety net for rollover

                    # Use :02x to read BCD bytes directly as decimal strings
                    ts_str = f"20{yy:02x}-{mon:02x}-{day:02x} {hh:02x}:{mm:02x}:{ss:02x}.{int(milisecs):03d}"
                    timestamps.append(ts_str)
            except Exception:
                pass # Non-critical failure

            # --- CALCULATE CUTS ---
            # Cut point Left: Footer Start and ensure we don't cut before the current cursor (overlap check)
            cut_start = max(cursor, next_footer)

            # Append valid audio up to the cut point
            clean_byte_stream.extend(raw_bytes[cursor : cut_start])

            # Advance Cursor: Skip the 16-byte Footer
            cursor = next_footer + FOOTER_LEN

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
