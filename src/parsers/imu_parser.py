import os
import struct
import logging
import numpy as np
import pandas as pd

from src.core.binary_decoder import decode_binary_header, get_precise_start_time

logger = logging.getLogger("wildlifetag_automator")

# --- CONSTANTS & OFFSETS ---
# The header is exactly 150 bytes long (offset 149). 
# Valid sensor data begins at absolute offset 150.
HEADER_SIZE = 150 
TIMESTAMP_OFFSET_BYTES = 140

def parse_imu_file(filepath):
    """
    Parses IMU binary (.BIN).
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
    | 140-141 | UInt16   | Subsecond Resolution (e.g., 1023)   |
    | 142-143 | UInt16   | Subsecond Value (Counter)           |
    | 144     | Byte     | Sync Marker (Fixed 0x55)            |
    | 145     | Byte     | Config/Format ID (Fixed 0x07)       |
    | 146-147 | UInt16   | Mirror: Minutes/Seconds (Integer)   |
    | 148-149 | UInt16   | Mirror: Subsecond Value             |
    |----------------------------------------------------------|
    |  DATA PAYLOAD (Repeats every 42 Bytes)                   |
    |----------------------------------------------------------|
    | Rel Byte| Type    | Description                          |
    | 0-11    | Float32 | Gyroscope X, Y, Z (Little Endian)    |
    | 12-23   | Float32 | Accelerometer X, Y, Z                |
    | 24-35   | Float32 | Magnetometer X, Y, Z                 |
    | 36-41   | 6 Bytes | Timestamp/Counter/Padding            |
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

        # --- PART 2: PRECISION TIMING CORRECTION ---
        # "STD" = Standard 150-byte header logic (Offsets 140-143)
        meta['Start_Time'] = get_precise_start_time(filepath, meta, sensor_type="STD")
        
        # Update string representation for logs/metadata file
        meta['Start_Time_Str'] = meta['Start_Time'].strftime('%Y-%m-%d %H:%M:%S.%f')

        # --- PART 3: PARSE DATA PAYLOAD ---
        # Map the 42-byte packet structure using NumPy dtypes.
        dt = np.dtype([
            ('gyro',  '<f4', (3,)), # Bytes 0-11
            ('acc',   '<f4', (3,)), # Bytes 12-23
            ('mag',   '<f4', (3,)), # Bytes 24-35
            ('time',  'V6'),        # Bytes 36-41
        ])

        try:
            with open(filepath, 'rb') as f:
                f.seek(HEADER_SIZE)
                raw_struct = np.fromfile(f, dtype=dt)
        except Exception as e:
            return "FAIL", f"Payload read error: {str(e)}", None, meta

        # --- PART 4: EMPTY CHECK ---
        num_samples = len(raw_struct)
        if num_samples == 0:
            return "EMPTY", "No sensor data rows found", None, meta

        # --- PART 5: DATAFRAME CREATION ---
        # Extract sensor columns
        acc_data = raw_struct['acc']
        gyro_data = raw_struct['gyro']
        mag_data = raw_struct['mag']

        # --- VECTORIZED TIME CALCULATION ---
        # Now uses the UPDATED meta['Start_Time'] containing the milliseconds
        period = 1.0 / meta['SampleRate']
        time_deltas = pd.to_timedelta(np.arange(num_samples) * period, unit='s')
        timestamps = meta["Start_Time"] + time_deltas

        # --- EXTRACT LEGACY COMPONENTS ---
        minutes = timestamps.minute.astype('int8')
        seconds = timestamps.second.astype('int8')
        
        # Calculate Milliseconds
        millis = (timestamps.microsecond // 1000).astype('int16')

        data = {
            # Time Column
            'Time': timestamps,

            # Legacy Time Components
            'Minute': minutes,
            'Second': seconds,
            'Millisecond': millis, 

            # Sensor Data
            'Acc X [mg]': acc_data[:, 0], 
            'Acc Y [mg]': acc_data[:, 1], 
            'Acc Z [mg]': acc_data[:, 2],
            'Gyro X [dps]': gyro_data[:, 0], 
            'Gyro Y [dps]': gyro_data[:, 1], 
            'Gyro Z [dps]': gyro_data[:, 2],
            'Mag X [mGauss]': mag_data[:, 0], 
            'Mag Y [mGauss]': mag_data[:, 1], 
            'Mag Z [mGauss]': mag_data[:, 2],
            
            # Empty Placeholders
            'Temperature [C]': 0.0, 
            'Bar Pressure [hPa]': 0.0
        }

        df = pd.DataFrame(data)
        
        # --- ENFORCE COLUMN ORDER ---
        cols_order = [
            'Time', 'Minute', 'Second', 'Millisecond', 
            'Acc X [mg]', 'Acc Y [mg]', 'Acc Z [mg]', 
            'Gyro X [dps]', 'Gyro Y [dps]', 'Gyro Z [dps]', 
            'Mag X [mGauss]', 'Mag Y [mGauss]', 'Mag Z [mGauss]', 
            'Temperature [C]', 'Bar Pressure [hPa]'
        ]
        
        # Reorder just in case dict insertion order varied
        missing = [c for c in cols_order if c not in df.columns]
        if not missing:
            df = df[cols_order]
        
        return "SUCCESS", "Parsed Successfully", df, meta

    except Exception as e:
        return "FAIL", f"Crash: {str(e)}", None, None