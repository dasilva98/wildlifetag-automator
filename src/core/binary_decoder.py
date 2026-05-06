import logging
import os
import struct
from datetime import datetime

import pandas as pd

logger = logging.getLogger("wildlifetag_automator")


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
    fwid = struct.unpack("<H", header[24:26])[0]  # <H = unsigned short (2 bytes)
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
    #   140-141: Subsecond resolution (uint16)
    #   142-143: Subsecond value/counter (uint16)
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
    #   - Stable across all sequential files within a single recording session
    #     (e.g. 0M, 1M, 2M, 3M, 4M all share the same value).
    #   - Can differ between sessions from the same device.
    #   - Observed values: 0x01, 0x04, 0x07 — small integers in range 1-7.
    #   - Not correlated with: device ID, calendar date, day-of-week, hour,
    #     bitmask, Config0, FWID, or subsecond resolution.
    #
    # LEADING THEORY: per-session configuration preset or schedule slot index —
    # a value locked in by the firmware at recording start, possibly set via
    # VesperDock when configuring or scheduling the recording session.
    #
    # ALTERNATIVE THEORIES (not yet ruled out):
    #   - Session sequence number: "N-th recording since last tag reset"
    #   - Schedule/program index: which timed-recording program triggered this file
    #   - An internal firmware state flag written once at boot/init
    #   - A Cell-Guide-internal calendar or GPS week fragment
    #
    # No observed effect on parsing, packet structure, or sensor output.
    # Logged here so it can be tracked across deployments for future correlation.
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


def get_precise_start_time(filepath, meta, sensor_type="STD"):
    """
    Calculates the millisecond-precise start time for ANY Vesper file.

    Args:
        sensor_type: "STD", "IMU", "AUD" (150 byte header) or "GPS" (16 byte header)
    """
    precise_time = meta["Start_Time"]

    # 1. Determine where the Subsecond bytes live
    if sensor_type == "GPS":
        offset_bytes = 12  # GPS stores it at 12-15
        header_correction = 0  # GPS fixes are usually instantaneous timestamps

    else:
        # "STD", "AUD", "IMU" - All share the standard Vesper header layout
        offset_bytes = 140  # Subsecond data at 140-143

        # Apply 1-sample correction only if SampleRate exists and is > 0
        # (Audio/IMU samples represent a duration, not an instant)
        sr = meta.get("SampleRate", 0)
        header_correction = (1.0 / sr * 1000.0) if sr > 0 else 0

    try:
        with open(filepath, "rb") as f:
            f.seek(offset_bytes)
            frac_bytes = f.read(4)  # Read 2x UInt16

            if len(frac_bytes) == 4:
                # Unpack: (Resolution, Counter)
                ss_frac, ss_val = struct.unpack("<HH", frac_bytes)

                # 2. Formula (Universal)
                denom = float(ss_frac + 1.0)
                if denom > 0:
                    base_ms = 1000.0 * (float(ss_frac - ss_val) / denom)

                    # 3. Add Correction (only if needed)
                    total_ms = base_ms + header_correction

                    if total_ms > 0:
                        precise_time += pd.Timedelta(milliseconds=total_ms)

    except Exception as e:
        logger.warning(f"Precision timing failed for {filepath}: {e}")

    return precise_time
