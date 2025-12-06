import numpy as np
import os
import logging
import pandas as pd
import struct
from scipy import signal
from datetime import datetime, timedelta

logger = logging.getLogger("vesper_automator")

# --- CONSTANTS & OFFSETS ---
# The header is exactly 150 bytes long. 
# Valid sensor data begins at absolute offset 150.
HEADER_SIZE = 150 

def _bcd_to_int(byte_val):
    """Helper: Converts a BCD (Binary Coded Decimal) byte to an integer."""
    return (byte_val // 16) * 10 + (byte_val % 16)

def generate_metadata_file(filepath, meta):
    """
    Generates the sidecar .txt file required to replace VesperApp.
    """
    txt_path = os.path.splitext(filepath)[0] + ".txt"
    
    lines = [
        f"DeviceID:{meta['DeviceID']}",
        "HWID:0",
        "FWID:112",
        f"Sensor:{meta['Sensor']}",
        f"SampleRate:{meta['SampleRate']}",
        "WinRate:0",
        "WinLen:0",
        f"Config0:{meta['Config0']}",
        "Config1:0", "Config2:0", "Config3:0",
        f"Bitmask:{meta['Bitmask']:X}"
    ]
    
    try:
        with open(txt_path, 'w') as f:
            f.write("\n".join(lines))
    except Exception as e:
        logger.error(f"Failed to write metadata txt: {e}")

def parse_imu_file(filepath):
    """
    Parses Vesper IMU binary (.BIN).
    
    FILE STRUCTURE:
    ---------------------------------------------------------
    |  HEADER (0 - 150 Bytes)                               |
    |-------------------------------------------------------|
    | Offset  | Type    | Description                       |
    | 0-3     | UInt32  | Magic Number (0xDEAFDAC0)         |
    | 4-7     | UInt32  | Device ID (e.g., 0x4764505D)      |
    | 8-23    | String  | Sensor Name (ASCII, e.g., "IMU10")|
    | 28-31   | UInt32  | Sample Rate (e.g., 50 Hz)         |
    | 40-43   | UInt32  | Bitmask (Active Sensors)          |
    | 44-47   | UInt32  | Config0                           |
    | 132-135 | BCD     | Start Time (Hour, Min, Sec, Pad)  |
    | 136-139 | BCD     | Start Date (Pad, Month, Day, Year)|
    |-------------------------------------------------------|
    |  DATA PAYLOAD (Repeats every 42 Bytes)                |
    |-------------------------------------------------------|
    | Rel Byte| Type    | Description                       |
    | 0-11    | Float32 | Gyroscope X, Y, Z (Little Endian) |
    | 12-23   | Float32 | Accelerometer X, Y, Z             |
    | 24-35   | Float32 | Magnetometer X, Y, Z              |
    | 36-41   | 6 Bytes | Timestamp/Counter/Padding         |
    ---------------------------------------------------------
    """
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return None

    try:
        # --- PART 1: HEADER PARSING ---
        with open(filepath, 'rb') as f:
            header = f.read(HEADER_SIZE)

        # 1. Decode IDs (Offsets 4 and 8)
        device_id = struct.unpack('<I', header[4:8])[0]
        try:
            # Read 16 bytes for name, split at null terminator
            sensor_name = header[8:24].split(b'\x00')[0].decode('ascii')
        except:
            sensor_name = "IMU10"

        # 2. Decode Configuration (Offsets 28, 40, 44)
        sample_rate = struct.unpack('<I', header[28:32])[0]
        bitmask = struct.unpack('<I', header[40:44])[0]
        config0 = struct.unpack('<I', header[44:48])[0]

        # 3. Decode Timestamp (BCD Format at Offset 132)
        # BCD means Hex 0x34 represents Decimal 34.
        h = _bcd_to_int(header[132])
        m = _bcd_to_int(header[133])
        s = _bcd_to_int(header[134])
        
        # Decode Date (BCD Format at Offset 136)
        # Format map: Byte 137=Month, 138=Day, 139=Year
        month = _bcd_to_int(header[137])
        day   = _bcd_to_int(header[138])
        year  = 2000 + _bcd_to_int(header[139]) # Sensor stores '25', we make it '2025'

        try:
            start_dt = datetime(year, month, day, h, m, s)
        except ValueError:
            logger.warning(f"Invalid BCD Timestamp in {os.path.basename(filepath)}. Using file time.")
            start_dt = datetime.fromtimestamp(os.path.getmtime(filepath))

        # Pack metadata for the .txt generator
        meta = {
            "DeviceID": f"{device_id:X}",
            "Sensor": sensor_name,
            "SampleRate": sample_rate if sample_rate > 0 else 50,
            "Bitmask": bitmask,
            "Config0": config0,
            "Start_Time": start_dt
        }

        # --- PART 2: GENERATE TXT METADATA ---
        generate_metadata_file(filepath, meta)

        # --- PART 3: PARSE DATA PAYLOAD ---
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
            return None

        # Extract columns
        acc_data = raw_struct['acc']
        gyro_data = raw_struct['gyro']
        mag_data = raw_struct['mag']

        # Vectorized Time Calculation
        # Create a time range starting from 'start_dt' with '1/SampleRate' steps
        period = 1.0 / meta['SampleRate']
        time_deltas = pd.to_timedelta(np.arange(num_samples) * period, unit='s')
        timestamps = start_dt + time_deltas

        # --- PART 4: CREATE DATAFRAME ---
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
        return df

    except Exception as e:
        logger.error(f"Failed parsing {os.path.basename(filepath)}: {e}")
        return None