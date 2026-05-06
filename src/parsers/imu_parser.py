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

# Sensor output rounding — matches actual hardware resolution.
# Values beyond these decimal places are float32 noise, not real data.
#   Acc:  ±16g range, ~0.5 mg/LSB   → 3dp (0.001 mg)
#   Gyro: mdps/1000, 0.00125 dps/LSB → 5dp (0.00001 dps)
#   Mag:  1.5 mGauss steps           → 1dp (0.1 mGauss)
#   Temp: raw * 0.01                 → 2dp (handled at extraction)
#   Pres: integer hPa                → 0dp
ACC_DECIMALS = 3
GYRO_DECIMALS = 5
MAG_DECIMALS = 1
PRES_DECIMALS = 0


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
#                          Gyro is always stored in mdps — always 1000.0.
#   has_temp_pres (bool) : Whether the packet contains temperature and
#                          pressure fields after mag.
#
# Known bitmask bits:
#   Bit 0 (0x01): Accelerometer active
#   Bit 1 (0x02): Gyroscope active
#   Bit 2 (0x04): Magnetometer active
#   Bit 3 (0x08): Extended format — adds 2B temperature + 2B pressure per
#                 packet. Packet grows from 42 to 46 bytes.
#   Bit 5 (0x20): Standard mode flag (observed in bitmask 0x27). Exact
#                 meaning undocumented — no structural effect on packet.
#
# Packet layout (both formats):
#   pkt_ts   6B   [0-5]    Packet timestamp: sync(2) + min + sec + subsec + rollover
#   gyro    12B   [6-17]   Gyroscope X, Y, Z (float32, little-endian, always mdps)
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
        "gyro_scale": 1000.0,  # Gyro always stored as mdps regardless of bitmask
        "has_temp_pres": False,
    }

    # Bit 3 (0x08): Extended format — adds temperature and pressure fields.
    if bitmask & 0x08:
        config["packet_size"] = 46
        config["has_temp_pres"] = True

    # --- Future bitmask variants: add blocks here ---
    # Example:
    # if bitmask & 0x10:  # Bit 4: hypothetical high-rate mode
    #     config['packet_size'] = 48
    #     ...

    return config


def _build_dtype(config):
    """
    Constructs the NumPy dtype for one data packet given a format config.

    Standard layout (42 bytes):
        pkt_ts   uint8 x6   [0-5]    Packet timestamp bytes
        gyro   float32 x3   [6-17]   Gyroscope X, Y, Z  (mdps)
        acc    float32 x3  [18-29]   Accelerometer X, Y, Z  (mg)
        mag    float32 x3  [30-41]   Magnetometer X, Y, Z  (mGauss)

    Extended layout (46 bytes, bit 3 set):
        pkt_ts   uint8 x6   [0-5]    Packet timestamp bytes
        gyro   float32 x3   [6-17]   Gyroscope X, Y, Z  (mdps)
        acc    float32 x3  [18-29]   Accelerometer X, Y, Z  (mg)
        mag    float32 x3  [30-41]   Magnetometer X, Y, Z  (mGauss)
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
    | 8-12    | String   | Sensor Name (ASCII, e.g., "IMU10")  |
    | 13-23   | Pad      | Padding (= '00')                    |
    | 24-25   | UInt16   | FWID                                |
    | 26-27   | UInt16   | HWID                                |
    | 28      | UInt32   | Sample Rate (Hz)                    |
    | 29-39   | UInt32   | Padding (= '00')                    |
    | 40-41   | UInt32   | Bitmask (active sensors + format)   |
    | 128-131 | UInt32   | Timestamp Sync Word (Sentinel)      |
    | 132-135 | BCD      | Start Time (Hour, Min, Sec, Pad)    |
    | 136-139 | BCD      | Start Date (Pad, Month, Day, Year)  |
    | 140-141 | UInt16   | Subsecond Resolution                |
    | 142-143 | UInt16   | Subsecond Value (Counter)           |
    |----------------------------------------------------------|
    |  DATA PAYLOAD (Repeating packets — see _build_dtype)     |
    |----------------------------------------------------------|
    | pkt_ts  | 6 bytes  | sync(2) + min + sec + subsec + roll |
    | gyro    | 12 bytes | X, Y, Z float32 (mdps)              |
    | acc     | 12 bytes | X, Y, Z float32 (mg)                |
    | mag     | 12 bytes | X, Y, Z float32 (mGauss)            |
    | temp*   | 2 bytes  | uint16 raw * 0.01 = °C (ext only)   |
    | pres*   | 2 bytes  | uint16 raw = hPa   (ext only)       |
    ------------------------------------------------------------

    FORMAT VARIANTS (driven by Bitmask — see _get_format_config):
    ------------------------------------------------------------
    | Bitmask 0x07 | 42B packets | no temp/pres               |
    | Bitmask 0x27 | 42B packets | no temp/pres               |
    | Bitmask 0x0F | 46B packets | temp + pres                |
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

        # --- PART 2: PRECISE START TIME ---
        # get_precise_start_time reads bytes 140-143, within the 144-byte header.
        # Used for the sidecar .txt filename and CSV filename only.
        # Per-packet timestamps in the CSV are derived from pkt_ts (see Part 6).
        meta["Start_Time"] = get_precise_start_time(filepath, meta, sensor_type="STD")
        meta["Start_Time_Str"] = meta["Start_Time"].strftime("%Y-%m-%d %H:%M:%S.%f")

        # --- PART 3: FORMAT DETECTION ---
        fmt = _get_format_config(meta.get("Bitmask", 0))
        dt = _build_dtype(fmt)
        logger.debug(
            f"IMU format: packet={fmt['packet_size']}B "
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

        # --- PART 5b: STARTUP DUPLICATE FILTER ---
        # The firmware writes the first packet twice at startup (identical pkt_ts
        # bytes and sensor values). Detect and drop the duplicate if present.
        if num_samples > 1 and np.array_equal(
            raw_struct["pkt_ts"][0], raw_struct["pkt_ts"][1]
        ):
            raw_struct = raw_struct[1:]
            num_samples -= 1
            logger.debug(f"Startup duplicate packet removed from {filepath}")

        # --- PART 6: TIMESTAMP EXTRACTION FROM pkt_ts ---
        # Minutes and seconds are read directly from each packet's pkt_ts field.
        # Sub-second precision is derived from the global packet index anchored to
        # start_sub_us — this preserves the correct sub-second offset through all
        # second boundaries (e.g. 982ms → 2ms, not 982ms → 0ms).
        pkt_ts = raw_struct["pkt_ts"]  # shape (N, 6), dtype uint8

        # Sync byte validation (warning only — does not abort)
        expected_sync1 = meta.get("Bitmask", 0) & 0x0F
        if not (
            np.all(pkt_ts[:20, 0] == 0x55) and np.all(pkt_ts[:20, 1] == expected_sync1)
        ):
            logger.warning(
                f"pkt_ts sync byte mismatch in {filepath} "
                f"— expected [0x55, 0x{expected_sync1:02X}]"
            )

        pkt_min = pkt_ts[:, 2].astype(np.int64)  # minutes (0-59)
        pkt_sec = pkt_ts[:, 3].astype(np.int64)  # seconds (0-59)

        # Hour rollover detection: minute transitions 59→0 indicate a new hour.
        min_diffs = np.diff(pkt_min, prepend=pkt_min[0])
        hour_offsets = np.cumsum(min_diffs < -30).astype(np.int64)

        # Non-contiguous session detection: warn if there are large forward jumps
        # (more than 2 minutes) within a single file, which would indicate the
        # file spans multiple non-contiguous recording windows.
        forward_jumps = np.where(min_diffs > 2)[0]
        if len(forward_jumps) > 0:
            gap_min = int(min_diffs[forward_jumps[0]])
            logger.warning(
                f"Non-contiguous recording detected in {os.path.basename(filepath)}: "
                f"~{gap_min} minute gap at packet {forward_jumps[0]}. "
                f"This file may span multiple recording sessions."
            )

        # Total seconds since midnight per packet.
        pkt_secs_from_midnight = (
            (meta["Start_Time"].hour + hour_offsets) * 3600 + pkt_min * 60 + pkt_sec
        )

        # Sub-second offset: use global packet index anchored to start_sub_us.
        # FIX: previously used pkt_in_sec * period_us which reset to 0ms at every
        # second boundary. Global index preserves the correct sub-second rhythm
        # (e.g. 982ms → 2ms on the next second, not 0ms).
        period_us = int(round(1_000_000.0 / meta["SampleRate"]))
        start_sub_us = meta["Start_Time"].microsecond
        sub_us_global = (
            np.arange(num_samples, dtype=np.int64) * period_us + start_sub_us
        )
        sub_us = sub_us_global % 1_000_000

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
        # Extract and scale sensor data.
        # Round to physically meaningful precision — values beyond these decimal
        # places are float32 representation noise, not real sensor data.
        acc_data = np.round(raw_struct["acc"] / 1.0, ACC_DECIMALS)
        gyro_data = np.round(raw_struct["gyro"] / fmt["gyro_scale"], GYRO_DECIMALS)
        mag_data = np.round(raw_struct["mag"] / 1.0, MAG_DECIMALS)

        if fmt["has_temp_pres"]:
            temp_data = np.round(raw_struct["temp"].astype(float) * 0.01, 2)
            pres_data = np.round(raw_struct["pres"].astype(float), PRES_DECIMALS)
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
