import numpy as np
import os 
import logging
from scipy import signal

logger = logging.getLogger("vesper_automator")

def parse_imu_file(filepath):
    """
    Parses a raw binary IMU file (Accelerometer/Gyro)
    Based on legacy MATLAB script: ParseAccMPU9.m

    Structure based on 'fread(..., '3*int16=>double', 26, 'ieee-be')':
    - 3 signed 16-bit integers (Big Endian) representing X, Y, Z
    - 26 bytes of padding/other data to skip
    """
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return None
    
    try:
        # Define the Data Type Structure
        # '>' means Big Endian
        # 'i2' means signed 16-bit integer
        # (3,) means read 3 of them
        # 'V26' means read 26 raw bytes (void) just to skip them
        dt = np.dtype([
            ('data', '>i2',(3,)),
            ('padding', 'V26')
        ])

        # Read the binary file directly
        raw_struct = np.fromfile(filepath,dtype=dt)

        # Extract the X,Y,Z columns
        # The shape is (N_samples, 3)
        raw_data = raw_struct['data']

        # Apply a Butterworth FIlter (matches the MATLAB logic)
        # MATLAB: [b,a]=butter(4,0.9); x=filter(b,a,xdata);
        # 0.9 is 90% of the Nyquist frequency (very minimal filtering)
        cutoff = 0.9
        if not (0 < cutoff < 1):
            logger.error(f"Invalid cutoff frequency: {cutoff}. Must be between 0 and 1 (normalized).")
            return None
        butter_result = signal.butter(4, cutoff, btype='low', output='ba')
        if butter_result is None or not isinstance(butter_result, tuple) or len(butter_result) != 2:
            logger.error("signal.butter did not return filter coefficients as a tuple of (b, a).")
            return None
        b, a = butter_result

        # Apply filter along axis 0 (down the columns)
        filtered_data = signal.lfilter(b, a, raw_data, axis=0)

        logger.info(f"Parsed {os.path.basename(filepath)}: {len(filtered_data)} samples.")

        return filtered_data
    
    except Exception as e:
        logger.error(f"Failed to parse IMU file {filepath}: {e}")
        return None