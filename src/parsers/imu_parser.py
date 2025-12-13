import numpy as np
import os
import logging
import pandas as pd
import struct
from scipy import signal
from datetime import datetime, timedelta
from src.core.binary_utils import read_vesper_header

logger = logging.getLogger("vesper_automator")

# --- CONSTANTS & OFFSETS ---
# The header is exactly 150 bytes long. 
# Valid sensor data begins at absolute offset 150.
HEADER_SIZE = 150 

def parse_imu_file(filepath):
    """
    Parses Vesper IMU binary (.BIN).
    
    FILE STRUCTURE:
    ------------------------------------------------------------
    |  HEADER (0 - 150 Bytes)                                  |
    |----------------------------------------------------------|
    | Offset  | Type     | Description                         |
    | 0-3     | UInt32   | Magic Number (0xDEAFDAC0)           |
    | 4-7     | UInt32   | Device ID (e.g., 0x4764505D)        |
    | 8-23    | String   | Sensor Name (ASCII, e.g., "IMU10")  |
    | 28-31   | UInt32   | Sample Rate (e.g., 50 Hz)           |
    | 40-43   | UInt32   | Bitmask (Active Sensors)            |
    | 44-47   | UInt32   | Config0                             |
    | 48-51   | UInt32   | Config1                             |
    | 52-55   | UInt32   | Config2                             |
    | 56-59   | UInt32   | Config3                             |
    | 60-127  | (N/A)    | Padding/reserved bytes              |
    | 128-131 | UInt32   | Timestamp Sync Word (Sentinel)      |
    | 132-135 | BCD      | Start Time (Hour, Min, Sec, Pad)    |
    | 136-139 | BCD      | Start Date (Pad, Month, Day, Year)  |
    | 140-144 | UInt32(?)| Boot Timestamp (Pad,Epoch Time)     |
    | 145-148 | UInt32(?)| System Ticks (internal clock cycles)|
    | 149     | UInt8(?) | Padding                             |
    |----------------------------------------------------------|
    |  DATA PAYLOAD (Repeats every 42 Bytes)                   |
    |----------------------------------------------------------|
    | Rel Byte| Type    | Description                          |
    | 0-11    | Float32 | Gyroscope X, Y, Z (Little Endian)    |
    | 12-23   | Float32 | Accelerometer X, Y, Z                |
    | 24-35   | Float32 | Magnetometer X, Y, Z                 |
    | 36-41   | 6 Bytes | Timestamp/Counter/Padding            |
    ------------------------------------------------------------
    """
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return None, None

    try:
        # --- PART 1: HEADER PARSING ---
        meta = read_vesper_header(filepath)
        if not meta: return None, None

        # --- PART 2: PARSE DATA PAYLOAD ---
        # We map the 42-byte packet structure using NumPy dtypes.
        # Note: 'gyro' comes BEFORE 'acc' in this binary format.
        dt = np.dtype([
            ('gyro',  '<f4', (3,)), # Bytes 0-11  (Absolute Offset 150)
            ('acc',   '<f4', (3,)), # Bytes 12-23 (Absolute Offset 162)
            ('mag',   '<f4', (3,)), # Bytes 24-35 (Absolute Offset 174)
            ('time',  'V6'),        # Bytes 36-41 (Absolute Offset 186)
        ])

        with open(filepath, 'rb') as f:
            # Skip the 150-byte header to reach the first Gyro packet
            f.seek(HEADER_SIZE)
            raw_struct = np.fromfile(f, dtype=dt)

        num_samples = len(raw_struct)
        if num_samples == 0:
            return None, None

        # Extract columns
        acc_data = raw_struct['acc']
        gyro_data = raw_struct['gyro']
        mag_data = raw_struct['mag']

        # Vectorized Time Calculation
        # Create a time range starting from 'start_dt' with '1/SampleRate' steps
        period = 1.0 / meta['SampleRate']
        time_deltas = pd.to_timedelta(np.arange(num_samples) * period, unit='s')
        timestamps = meta["Start_Time"] + time_deltas

        # --- PART 3: CREATE DATAFRAME ---
        # Data is already in correct units (Float32), no scaling needed.
        data = {
            'Time': timestamps,
            'Acc X [mg]': acc_data[:, 0],
            'Acc Y [mg]': acc_data[:, 1],
            'Acc Z [mg]': acc_data[:, 2],
            'Gyro X [dps]': gyro_data[:, 0],
            'Gyro Y [dps]': gyro_data[:, 1],
            'Gyro Z [dps]': gyro_data[:, 2],
            'Mag X [mGauss]': mag_data[:, 0],
            'Mag Y [mGauss]': mag_data[:, 1],
            'Mag Z [mGauss]': mag_data[:, 2],
            # Fill disabled sensors with 0.0 to match legacy CSV format
            'Temperature [C]': 0.0,
            'Bar Pressure [hPa]': 0.0
        }

        df = pd.DataFrame(data)
        return df, meta

    except Exception as e:
        logger.error(f"Failed parsing {os.path.basename(filepath)}: {e}")
        return None, None