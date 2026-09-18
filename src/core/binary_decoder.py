import logging
import os
import struct
from datetime import datetime

import pandas as pd

logger = logging.getLogger("wildlifetag_automator")

# Footer constants — every IMU .BIN file ends with a 16-byte footer block.
FOOTER_SIZE = 16
FOOTER_SYNC = (
    b"\xa5\x5a\x5a\xa5"  # End-of-file sync, distinct from header sync 5A A5 5A A5
)


def bcd_to_int(byte_val):
    """Helper: Converts a binary-coded decimal (BCD) byte to an integer."""
    return (byte_val // 16) * 10 + (byte_val % 16)


def decode_binary_header(filepath, header_size):
    """
    Decodes a dynamic sized header.
    Returns a dictionary with raw common fields (IDs, SampleRate, Time, Configs).
    """
    if not os.path.exists(filepath):
        return None

    with open(filepath, "rb") as f:
        header = f.read(header_size)

    # 1. Decode IDs
    device_id = struct.unpack("<I", header[4:8])[0]
    try:
        sensor_name = header[8:24].split(b"\x00")[0].decode("ascii")
    except:
        sensor_name = "Unknown"

    # 2. Decode Basic Configs
    fwid = struct.unpack("<H", header[24:26])[0]
    hwid = struct.unpack("<H", header[26:28])[0]

    sample_rate = struct.unpack("<I", header[28:32])[0]

    win_len = struct.unpack("<I", header[32:36])[0]
    win_rate = struct.unpack("<I", header[36:40])[0]

    bitmask = struct.unpack("<I", header[40:44])[0]

    # 3. Decode Extended Configs (Offsets 44, 48, 52, 56)
    config0 = struct.unpack("<I", header[44:48])[0]
    config1 = struct.unpack("<I", header[48:52])[0]
    config2 = struct.unpack("<I", header[52:56])[0]
    config3 = struct.unpack("<I", header[56:60])[0]

    # 4. Decode BCD Timestamp
    # Header timestamp region layout (bytes 128-143):
    #   128-131: Sync word (0x5AA55AA5)
    #   132:     Hour (BCD)
    #   133:     Minute (BCD)
    #   134:     Second (BCD)
    #   135:     Always 0x00 (padding after seconds)
    #   136:     Header_B136 — see note below
    #   137:     Month (BCD)
    #   138:     Day (BCD)
    #   139:     Year (BCD, offset from 2000)
    #   140-141: Subsecond resolution (uint16, typically 1023 = 0x03FF)
    #   142-143: Subsecond value at FIRST SAMPLE (uint16)

    if len(header) < 144:
        logger.error(f"Header too short in {filepath}")
        return None

    try:
        h = bcd_to_int(header[132])
        m = bcd_to_int(header[133])
        s = bcd_to_int(header[134])
        month = bcd_to_int(header[137])
        day = bcd_to_int(header[138])
        year = 2000 + bcd_to_int(header[139])
        start_dt = datetime(year, month, day, h, m, s)
    except ValueError:
        start_dt = datetime.fromtimestamp(os.path.getmtime(filepath))

    # 5. Header_B136 — byte at offset 136, between the time pad and the date fields.
    #
    # CONFIRMED BEHAVIOUR (from multi-session, multi-device analysis):
    #   - Stable across all sequential files within a single recording session.
    #   - Mirrored in the file footer at offset 8 (footer's B8 == header's B136).
    #   - Can differ between sessions from the same device.
    #   - Observed values: 0x01, 0x04, 0x07 — small integers in range 1-7.
    #   - Not correlated with: device ID, calendar date, day-of-week, hour,
    #     bitmask, Config0, FWID, or subsecond resolution.
    #
    # LEADING THEORY: per-session configuration preset or schedule slot index.
    #
    # ALTERNATIVE THEORIES (not yet ruled out):
    #   - Session sequence number ("N-th recording since last tag reset")
    #   - Schedule/program index identifying which timed-recording program triggered the file
    #   - An internal firmware state flag written once at boot/init
    #   - A Cell-Guide-internal calendar or GPS week fragment
    #
    # No observed effect on parsing, packet structure, or sensor output.
    header_b136 = header[136]

    return {
        "DeviceID": f"{device_id:X}",
        "Sensor": sensor_name,
        "FWID": fwid,
        "HWID": hwid,
        "SampleRate": sample_rate,
        "WinLen": win_len,
        "WinRate": win_rate,
        "Bitmask": bitmask,
        "Config0": config0,
        "Config1": config1,
        "Config2": config2,
        "Config3": config3,
        "Header_B136": header_b136,
        "Start_Time": start_dt,
    }


def decode_binary_footer(filepath):
    """
    Reads and decodes the 16-byte footer at the end of an IMU .BIN file.

    Footer layout (16 bytes):
      0-3:   Sync word (A5 5A 5A A5) — bitwise complement of header sync
      4:     End Hour (BCD)
      5:     End Minute (BCD)
      6:     End Second (BCD)
      7:     Footer_B7 — varies between files, exact meaning undocumented
             (possibly a counter, checksum, or firmware state byte)
      8:     Footer_B8 — mirrors the header's Header_B136 value (per-session marker)
      9:     End Month (BCD)
      10:    End Day (BCD)
      11:    End Year (BCD, offset from 2000)
      12-13: Subsecond resolution (uint16, same as header — typically 1023)
      14-15: Subsecond value AFTER LAST SAMPLE (uint16) — represents the
             tick that the next sample WOULD have occupied, one step beyond
             the actual final packet.

    Returns:
        dict with footer fields, or None if the footer sync is invalid /
        the file is too short. A missing or invalid footer indicates the
        recording was truncated (battery died, SD full, write interrupted).
    """
    if not os.path.exists(filepath):
        return None

    file_size = os.path.getsize(filepath)
    if file_size < FOOTER_SIZE:
        return None

    with open(filepath, "rb") as f:
        f.seek(file_size - FOOTER_SIZE)
        footer = f.read(FOOTER_SIZE)

    if footer[0:4] != FOOTER_SYNC:
        # Footer sync not found — file is truncated or corrupt.
        return None

    try:
        h = bcd_to_int(footer[4])
        m = bcd_to_int(footer[5])
        s = bcd_to_int(footer[6])
        month = bcd_to_int(footer[9])
        day = bcd_to_int(footer[10])
        year = 2000 + bcd_to_int(footer[11])
        end_dt = datetime(year, month, day, h, m, s)
    except ValueError:
        return None

    ss_res = struct.unpack("<H", footer[12:14])[0]
    ss_val = struct.unpack("<H", footer[14:16])[0]

    # Time-within-second (ms) — same formula as header.
    # Footer ss_val represents the tick of the sample that WOULD HAVE been
    # the next one after the last actually-recorded sample.
    denom = float(ss_res + 1.0) if ss_res > 0 else 1.0
    end_ms = 1000.0 * (ss_res - ss_val) / denom

    end_time_precise = end_dt + pd.Timedelta(milliseconds=end_ms)

    return {
        "End_Time": end_time_precise,
        "End_Time_Coarse": end_dt,
        "End_ss_res": ss_res,
        "End_ss_val": ss_val,
        "Footer_B7": footer[7],
        "Footer_B8": footer[8],
    }


def get_precise_start_time(filepath, meta, sensor_type="STD"):
    """
    Calculates the millisecond-precise start time for ANY Vesper file.

    For IMU files, prefer reading per-packet timestamps directly from pkt_ts
    bytes 4-5 in imu_parser.py — this function is retained for AUDIO and GPS
    where per-packet timing is not available.

    Args:
        sensor_type: "STD", "IMU", "AUD" (150 byte header) or "GPS" (16 byte header)
    """
    precise_time = meta["Start_Time"]

    if sensor_type == "GPS":
        offset_bytes = 12
        header_correction = 0
    else:
        # "STD", "AUD", "IMU" — standard Vesper header layout
        offset_bytes = 140
        sr = meta.get("SampleRate", 0)
        # Apply 1-sample correction only if SampleRate exists and is > 0
        # (Audio/IMU samples represent a duration, not an instant)
        #
        # NOTE: This +1-sample correction was historically applied because the
        # header's ss_val was assumed to be "before first sample". Subsequent
        # analysis (Apr 2026) shows ss_val IS the first sample's tick on the
        # 1023-tick scale. The correction is preserved here for backward
        # compatibility with audio parsing; IMU now uses pkt_ts directly.
        header_correction = (1.0 / sr * 1000.0) if sr > 0 else 0

    try:
        with open(filepath, "rb") as f:
            f.seek(offset_bytes)
            frac_bytes = f.read(4)

            if len(frac_bytes) == 4:
                ss_frac, ss_val = struct.unpack("<HH", frac_bytes)

                denom = float(ss_frac + 1.0)
                if denom > 0:
                    base_ms = 1000.0 * (float(ss_frac - ss_val) / denom)
                    total_ms = base_ms + header_correction
                    if total_ms > 0:
                        precise_time += pd.Timedelta(milliseconds=total_ms)

    except Exception as e:
        logger.warning(f"Precision timing failed for {filepath}: {e}")

    return precise_time
