import numpy as np
import os
import logging
from scipy.io import wavfile

logger = logging.getLogger("vesper_automator")

def parse_audio_file(filepath, output_wav_path, sample_rate=48000, bit_depth=16, endian='<'):
    """
    Parses a raw binary Audio file (PCM data) extracted from the Vesper database.
    Based on legacy MATLAB script: PlotUltrasonicSync.m
    
    Structure:
    - Raw stream of uint16 samples (usually 12-bit effective depth).
    - DC offset removal (minus 94).

    Args:
        endian: '<' for Little Endian (default), '>' for Big Endian.
    """
    if not os.path.exists(filepath):
        logger.error(f"Audio file not found: {filepath}")
        return False

    try:
        # Determine Data Type with Endianness
        # MATLAB script handles 8-bit (*uint8) or 12-bit (*uint16)
        if bit_depth == 8:
            dtype_str = 'u1' # 8-bit unsigned
        else:
            # Combine endianness with type
            # '<u2' = Little Endian 16-bit
            # '>u2' = Big Endian 16-bit
            dtype_str = f"{endian}u2"

        dt = np.dtype(dtype_str)

        # Read Raw Binary
        # We assume Little Endian (<) for standard PCM, but if it sounds static-y, try Big Endian (>)
        raw_data = np.fromfile(filepath, dtype=dt)
        
        if raw_data.size == 0:
            logger.warning(f"Audio file {filepath} is empty.")
            return False

        # DC Offset Correction
        # MATLAB: ddata = ddata - dclevel (94);
        # We convert to int32 first to prevent underflow (e.g., 0 - 94 = crash in uint)
        audio_data = raw_data.astype(np.int32) - 94
        
        # Data Conversion for WAV
        # WAV files expect int16 (-32768 to 32767).
        # Since Vesper data is likely 12-bit (0-4096), subtracting 94 keeps it safely within int16 range.
        # But if it was 16-bit, we might need to center it around 0 differently.
        # Let's try centering it properly if it sounds "clipped".
        # For now, stick to the MATLAB logic (just cast).
        final_data = audio_data.astype(np.int16)

        # Save as WAV
        os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
        wavfile.write(output_wav_path, sample_rate, final_data)
        
        logger.info(f"Converted {os.path.basename(filepath)} -> {os.path.basename(output_wav_path)}")
        return True

    except Exception as e:
        logger.error(f"Failed to parse Audio file {filepath}: {e}")
        return False