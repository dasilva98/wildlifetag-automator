import numpy as np
import os
import logging
import pandas as pd
from src.core.binary_utils import read_vesper_header

logger = logging.getLogger("vesper_automator")

# --- CONSTANTS & OFFSETS ---
# The header is exactly 150 bytes long. 
# Valid sensor data begins at absolute offset 150.
HEADER_SIZE = 150 

def parse_imu_file(filepath):
    """
    Parses Vesper IMU binary (.BIN).
    Returns DataFrame matching the structure of 'MBN.csv' files.
    
    FILE STRUCTURE:
    ------------------------------------------------------------
    |  HEADER (0 - 150 Bytes)                                  |
    |----------------------------------------------------------|
    | Offset  | Type     | Description                         |
    | 0-3     | UInt32   | Magic Number (0xDEAFDAC0)           |
    | 4-7     | UInt32   | Device ID (e.g., 0x4764505D)        |
    | 8-23    | String   | Sensor Name (ASCII, e.g., "IMU10")  |
    | 28-31   | UInt32   | Sample Rate (e.g., 50 Hz)           |
    | 128-131 | UInt32   | Timestamp Sync Word (Sentinel)      |
    | 132-135 | BCD      | Start Time (Hour, Min, Sec, Pad)    |
    | 136-139 | BCD      | Start Date (Pad, Month, Day, Year)  |
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
        meta = read_vesper_header(filepath, header_size=HEADER_SIZE)
        if not meta: 
            return None, None

        # --- PART 2: PARSE DATA PAYLOAD ---
        # Map the 42-byte packet structure using NumPy dtypes.
        dt = np.dtype([
            ('gyro',  '<f4', (3,)), # Bytes 0-11
            ('acc',   '<f4', (3,)), # Bytes 12-23
            ('mag',   '<f4', (3,)), # Bytes 24-35
            ('time',  'V6'),        # Bytes 36-41
        ])

        with open(filepath, 'rb') as f:
            f.seek(HEADER_SIZE)
            raw_struct = np.fromfile(f, dtype=dt)

        num_samples = len(raw_struct)
        if num_samples == 0:
            return None, None

        # Extract sensor columns
        acc_data = raw_struct['acc']
        gyro_data = raw_struct['gyro']
        mag_data = raw_struct['mag']

        # --- PART 3: VECTORIZED TIME CALCULATION ---
        # Calculate precise Datetime objects for every row based on SampleRate
        period = 1.0 / meta['SampleRate']
        time_deltas = pd.to_timedelta(np.arange(num_samples) * period, unit='s')
        timestamps = meta["Start_Time"] + time_deltas

        # --- PART 4: EXTRACT LEGACY COMPONENTS ---
        # Matches the 'Minute', 'Second', 'Milisecond' columns from your CSV
        minutes = timestamps.minute.astype('int8')
        seconds = timestamps.second.astype('int8')
        
        # Calculate Milliseconds (Note: spelling 'Milisecond' to match CSV)
        # Using actual values (0-999) instead of hardcoded 0
        millis = (timestamps.microsecond // 1000).astype('int16')

        # --- PART 5: CREATE DATAFRAME ---
        data = {
            # 1. Time Column (First, as per CSV)
            'Time': timestamps,

            # 2. Legacy Time Components
            'Minute': minutes,
            'Second': seconds,
            'Milisecond': millis, # Sic: matches CSV header spelling

            # 3. Sensor Data
            'Acc X [mg]': acc_data[:, 0],
            'Acc Y [mg]': acc_data[:, 1],
            'Acc Z [mg]': acc_data[:, 2],
            'Gyro X [dps]': gyro_data[:, 0],
            'Gyro Y [dps]': gyro_data[:, 1],
            'Gyro Z [dps]': gyro_data[:, 2],
            'Mag X [mGauss]': mag_data[:, 0],
            'Mag Y [mGauss]': mag_data[:, 1],
            'Mag Z [mGauss]': mag_data[:, 2],
            
            # 4. Empty Placeholders (to match CSV format)
            'Temperature [C]': 0.0,
            'Bar Pressure [hPa]': 0.0
        }

        df = pd.DataFrame(data)
        
        # Ensure column order matches the provided CSV exactly
        cols_order = [
            'Time', 'Minute', 'Second', 'Milisecond', 
            'Acc X [mg]', 'Acc Y [mg]', 'Acc Z [mg]', 
            'Gyro X [dps]', 'Gyro Y [dps]', 'Gyro Z [dps]', 
            'Mag X [mGauss]', 'Mag Y [mGauss]', 'Mag Z [mGauss]', 
            'Temperature [C]', 'Bar Pressure [hPa]'
        ]
        
        # Reorder just in case dict insertion order varied
        df = df[cols_order]
        
        return df, meta

    except Exception as e:
        logger.error(f"Failed parsing {os.path.basename(filepath)}: {e}")
        return None, None