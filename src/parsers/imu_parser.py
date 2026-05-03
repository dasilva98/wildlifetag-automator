import logging
import os

import numpy as np
import pandas as pd

from src.core.binary_decoder import decode_binary_header, get_precise_start_time

logger = logging.getLogger("wildlifetag_automator")

# --- CONSTANTS ---
# True binary file header ends at byte 143.
# Bytes 144-149 are the pkt_ts field of the first data packet.
HEADER_SIZE = 144


# =============================================================================
# FORMAT CONFIGURATION REGISTRY
# =============================================================================
# Maps bitmask bit flags to packet format parameters.
# To support a new format variant, add a new block in _get_format_config()
# following the same pattern — the rest of the parser consumes the config
# dict automatically without further changes.
#
# Config keys:
#   packet_size   (int)  : Total bytes per data packet.
#   gyro_scale    (float): Divide raw gyro floats by this to get dps.
#                          1.0 = already in dps. 1000.0 = stored as mdps.
#   has_temp_pres (bool) : Whether the packet contains temperature and
#                          pressure fields after mag.
#
# Known bitmask bits:
#   Bit 0 (0x01): Accelerometer active
#   Bit 1 (0x02): Gyroscope active
#   Bit 2 (0x04): Magnetometer active
#   Bit 3 (0x08): "Extended format - 46B packets, adds temp + pressure fields",
#   Bit 5 (0x20): Standard mode flag (observed in bitmask 0x27). Exact
#                 meaning undocumented - no structural effect on packet.
#
# Packet layout (both formats):
#   pkt_ts   6B   [0-5]    Packet timestamp: sync(2) + min + sec + subsec + rollover
#   gyro    12B   [6-17]   Gyroscope X, Y, Z (float32, little-endian)
#   acc     12B  [18-29]   Accelerometer X, Y, Z (float32, little-endian)
#   mag     12B  [30-41]   Magnetometer X, Y, Z (float32, little-endian)
#   -- extended only (bit 3) --
#   temp     2B  [42-43]   Temperature uint16 (raw * 0.01 = °C)
#   pres     2B  [44-45]   Pressure uint16 (raw = hPa)
# =============================================================================


def _get_format_config(bitmask):
    """
    Derives packet format parameters from the header bitmask.

    Args:
        bitmask (int): Raw bitmask integer from the decoded header.

    Returns:
        dict: Format configuration consumed by the parser.
    """
    config = {
        "packet_size": 42,
        "gyro_scale": 1000.0,  # Always mdps regardless of bitmask
        "has_temp_pres": False,
    }
    # Bit 3 (0x08): Extended format with temperature and pressure
    if bitmask & 0x08:
        config["packet_size"] = 46
        config["has_temp_pres"] = True

    # --- Future bitmask variants: add blocks here ---
    # Example:
    # if bitmask & 0x10:  # Bit 4: hypothetical high-rate mode
    #     config['packet_size'] = 48
    #     config["has_temp_pres"] = ...
    #     ...

    return config


def _build_dtype(config):
    """
    Constructs the NumPy dtype for one data packet given a format config.

    Standard layout (42 bytes):
        pkt_ts   uint8 x6   [0-5]    Packet timestamp bytes
        gyro   float32 x3   [6-17]   Gyroscope X, Y, Z
        acc    float32 x3  [18-29]   Accelerometer X, Y, Z
        mag    float32 x3  [30-41]   Magnetometer X, Y, Z

    Extended layout (46 bytes, bit 3 set):
        pkt_ts   uint8 x6   [0-5]    Packet timestamp bytes
        gyro   float32 x3   [6-17]   Gyroscope X, Y, Z
        acc    float32 x3  [18-29]   Accelerometer X, Y, Z
        mag    float32 x3  [30-41]   Magnetometer X, Y, Z
        temp    uint16      [42-43]  Temperature (raw * 0.01 = °C)
        pres    uint16      [44-45]  Pressure (raw = hPa)
    """
    fields: list = [
        ("pkt_ts", "u1", (6,)),  # Packet timestamp — always first, always 6 bytes
        ("gyro", "<f4", (3,)),
        ("acc", "<f4", (3,)),
        ("mag", "<f4", (3,)),
    ]

    if config["has_temp_pres"]:
        fields.append(("temp", "<u2"))
        fields.append(("pres", "<u2"))

    return np.dtype(fields)


def parse_imu_file(filepath):
    """
    Parses IMU binary (.BIN).
    Returns DataFrame matching the structure of 'MBN.csv' files.

    FILE STRUCTURE:
    ------------------------------------------------------------
    |  HEADER (0 - 143 Bytes)                                  |
    |----------------------------------------------------------|
    | Offset  | Type     | Description                         |
    | 0-3     | UInt32   | Magic Number (0xDEAFDAC0)           |
    | 4-7     | UInt32   | Device ID                           |
    | 8-23    | String   | Sensor Name (ASCII, e.g., "IMU10")  |
    | 24-25   | UInt16   | FWID                                |
    | 26-27   | UInt16   | HWID                                |
    | 28-31   | UInt32   | Sample Rate (Hz)                    |
    | 40-43   | UInt32   | Bitmask (active sensors + format)   |
    | 128-131 | UInt32   | Timestamp Sync Word (Sentinel)      |
    | 132-135 | BCD      | Start Time (Hour, Min, Sec, Pad)    |
    | 136-139 | BCD      | Start Date (Pad, Month, Day, Year)  |
    | 140-141 | UInt16   | Subsecond Resolution                |
    | 142-143 | UInt16   | Subsecond Value (Counter)           |
    |----------------------------------------------------------|
    |  DATA PAYLOAD (Repeating packets — see _build_dtype)     |
    |----------------------------------------------------------|
    | pkt_ts  | 6 bytes  | sync(2) + min + sec + subsec + roll|
    | gyro    | 12 bytes | X, Y, Z float32                     |
    | acc     | 12 bytes | X, Y, Z float32                     |
    | mag     | 12 bytes | X, Y, Z float32                     |
    | temp*   | 2 bytes  | uint16 raw * 0.01 = °C (ext only)  |
    | pres*   | 2 bytes  | uint16 raw = hPa   (ext only)       |
    ------------------------------------------------------------

    FORMAT VARIANTS (driven by Bitmask — see _get_format_config):
    ------------------------------------------------------------
    | Bitmask 0x07 | 42B packets | gyro in dps  | no temp/pres |
    | Bitmask 0x27 | 42B packets | gyro in dps  | no temp/pres |
    | Bitmask 0x0F | 46B packets | gyro in mdps | temp + pres  |
    ------------------------------------------------------------

    pkt_ts byte map:
    ------------------------------------------------------------
    | Byte 0 | 0x55        | Fixed sync marker                 |
    | Byte 1 | bitmask&0x0F| Format tag (matches lower nibble) |
    | Byte 2 | uint8       | Minutes (raw decimal, 0-59)       |
    | Byte 3 | uint8       | Seconds (raw decimal, 0-59)       |
    | Byte 4 | uint8       | Subsecond counter (counts down)   |
    | Byte 5 | uint8       | Rollover counter                  |
    ------------------------------------------------------------

    Returns:
        (status, message, df, meta)
        status: "SUCCESS", "EMPTY", "FAIL"
        message: Description of the result or error
    """
    if not os.path.exists(filepath):
        return "FAIL", "File not found", None, None

    try:
        # --- PART 1: HEADER PARSING ---
        try:
            meta = decode_binary_header(filepath, header_size=HEADER_SIZE)
            if not meta:
                return "FAIL", "Header invalid (read returned None)", None, None
        except Exception as e:
            return "FAIL", f"Header parse error: {str(e)}", None, None

        # --- PART 2: PRECISE START TIME (for sidecar metadata and filename) ---
        # get_precise_start_time reads bytes 140-143 which are within the 144-byte header.
        # This result is stored in meta for the sidecar .txt file and CSV filename.
        # Per-packet timestamps in the CSV are derived from pkt_ts (see Part 6).
        meta["Start_Time"] = get_precise_start_time(filepath, meta, sensor_type="STD")
        meta["Start_Time_Str"] = meta["Start_Time"].strftime("%Y-%m-%d %H:%M:%S.%f")

        # --- PART 3: FORMAT DETECTION ---
        fmt = _get_format_config(meta.get("Bitmask", 0))
        dt = _build_dtype(fmt)
        logger.debug(
            f"IMU format: packet={fmt['packet_size']}B "
            f"gyro_scale={fmt['gyro_scale']} "
            f"temp_pres={fmt['has_temp_pres']} "
            f"(Bitmask=0x{meta.get('Bitmask', 0):02X})"
        )

        # --- PART 4: PARSE DATA PAYLOAD ---
        try:
            with open(filepath, "rb") as f:
                f.seek(HEADER_SIZE)
                raw_struct = np.fromfile(f, dtype=dt)
        except Exception as e:
            return "FAIL", f"Payload read error: {str(e)}", None, meta

        # --- PART 5: EMPTY CHECK ---
        num_samples = len(raw_struct)
        if num_samples == 0:
            return "EMPTY", "No sensor data rows found", None, meta

        # --- PART 6: TIMESTAMP EXTRACTION FROM pkt_ts ---
        # Minutes and seconds are read directly from each packet's pkt_ts field,
        # providing ground-truth second-level timestamps with no long-term drift.
        # Sub-second precision within each second uses period-based interpolation.
        # Hour and date come from the file header.
        pkt_ts = raw_struct["pkt_ts"]  # shape (N, 6), dtype uint8

        # Sync byte validation (sample first 20 packets, warning only)
        expected_sync1 = meta.get("Bitmask", 0) & 0x0F
        sync_ok = np.all(pkt_ts[:20, 0] == 0x55) and np.all(
            pkt_ts[:20, 1] == expected_sync1
        )
        if not sync_ok:
            logger.warning(
                f"pkt_ts sync byte mismatch in {filepath} "
                f"— expected [0x55, 0x{expected_sync1:02X}]"
            )

        pkt_min = pkt_ts[:, 2].astype(np.int64)  # minutes (0-59)
        pkt_sec = pkt_ts[:, 3].astype(np.int64)  # seconds (0-59)

        # Track hour rollovers: minute transitions 59→0 indicate a new hour.
        min_diffs = np.diff(pkt_min, prepend=pkt_min[0])
        hour_offsets = np.cumsum(min_diffs < -30).astype(np.int64)

        # Total seconds since midnight per packet.
        pkt_secs_from_midnight = (
            (meta["Start_Time"].hour + hour_offsets) * 3600 + pkt_min * 60 + pkt_sec
        )

        # Packet index within each second (resets to 0 at each second boundary).
        # Vectorized: find where the second changes, then compute offset from that boundary.
        sec_change = np.concatenate([[True], pkt_sec[1:] != pkt_sec[:-1]])
        group_start = np.where(sec_change, np.arange(num_samples, dtype=np.int64), 0)
        group_start = np.maximum.accumulate(group_start)
        pkt_in_sec = np.arange(num_samples, dtype=np.int64) - group_start

        # Sub-second offset in microseconds.
        period_us = int(round(1_000_000.0 / meta["SampleRate"]))
        sub_us = pkt_in_sec * period_us

        # Anchor the first second to the precise start time from the header.
        # This preserves sub-millisecond precision for the opening second of the file.
        start_sub_us = meta["Start_Time"].microsecond
        is_first_sec = (
            (pkt_sec == pkt_sec[0]) & (pkt_min == pkt_min[0]) & (hour_offsets == 0)
        )
        sub_us = np.where(is_first_sec, start_sub_us + sub_us, sub_us)

        # Build final timestamps from midnight of the recording date.
        base_dt = pd.Timestamp(
            year=meta["Start_Time"].year,
            month=meta["Start_Time"].month,
            day=meta["Start_Time"].day,
        )
        timestamps = base_dt + pd.to_timedelta(
            pkt_secs_from_midnight * 1_000_000 + sub_us, unit="us"
        )

        # --- PART 7: DATAFRAME CREATION ---
        acc_data = raw_struct["acc"]
        gyro_data = raw_struct["gyro"] / fmt["gyro_scale"]
        mag_data = raw_struct["mag"]

        if fmt["has_temp_pres"]:
            temp_data = np.round(raw_struct["temp"].astype(float) * 0.01, 2)
            pres_data = raw_struct["pres"].astype(float)
        else:
            temp_data = np.zeros(num_samples, dtype=float)
            pres_data = np.zeros(num_samples, dtype=float)

        minutes = timestamps.minute.astype("int8")
        seconds = timestamps.second.astype("int8")
        millis = (timestamps.microsecond // 1000).astype("int16")

        data = {
            "Time": timestamps,
            "Minute": minutes,
            "Second": seconds,
            "Millisecond": millis,
            "Acc X [mg]": acc_data[:, 0],
            "Acc Y [mg]": acc_data[:, 1],
            "Acc Z [mg]": acc_data[:, 2],
            "Gyro X [dps]": gyro_data[:, 0],
            "Gyro Y [dps]": gyro_data[:, 1],
            "Gyro Z [dps]": gyro_data[:, 2],
            "Mag X [mGauss]": mag_data[:, 0],
            "Mag Y [mGauss]": mag_data[:, 1],
            "Mag Z [mGauss]": mag_data[:, 2],
            "Temperature [C]": temp_data,
            "Bar Pressure [hPa]": pres_data,
        }

        df = pd.DataFrame(data)

        # --- ENFORCE COLUMN ORDER ---
        cols_order = [
            "Time",
            "Minute",
            "Second",
            "Millisecond",
            "Acc X [mg]",
            "Acc Y [mg]",
            "Acc Z [mg]",
            "Gyro X [dps]",
            "Gyro Y [dps]",
            "Gyro Z [dps]",
            "Mag X [mGauss]",
            "Mag Y [mGauss]",
            "Mag Z [mGauss]",
            "Temperature [C]",
            "Bar Pressure [hPa]",
        ]
        missing = [c for c in cols_order if c not in df.columns]
        if not missing:
            df = df[cols_order]

        return "SUCCESS", "Parsed Successfully", df, meta

    except Exception as e:
        return "FAIL", f"Crash: {str(e)}", None, None
