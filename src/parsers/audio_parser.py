import wave
import struct
import numpy as np
import os
import logging
from scipy.io import wavfile

from src.core.binary_utils import read_vesper_header 
# Note: We reuse the generate_metadata_file function from the IMU parser 
# but pass it different metadata.

logger = logging.getLogger("vesper_automator")

"""def parse_audio_file(filepath, output_wav_path, sample_rate=48000, bit_depth=16, endian='<'):
    
    Parses a raw binary Audio file (PCM data) extracted from the Vesper database.
    Based on legacy MATLAB script: PlotUltrasonicSync.m
    
    Structure:
    - Raw stream of uint16 samples (usually 12-bit effective depth).
    - DC offset removal (minus 94).

    Args:
        endian: '<' for Little Endian (default), '>' for Big Endian.
    
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

        """

def parse_audio_file(filepath, output_wav_path):
    """
    Parses a Vesper Audio file (.UBN/.MBN) to WAV.
    Auto-detects sample rate from the sidecar .txt file if available.
    """
    if not os.path.exists(filepath):
        logger.error(f"Audio file not found: {filepath}")
        return False

    # 1. Try to find metadata (Sample Rate)
    # The .txt file usually has the same name as the binary file + .txt
    meta_path = filepath + ".txt"
    sample_rate = 48000 # Default fallback
    
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r') as f:
                for line in f:
                    if "SampleRate" in line:
                        # Format: SampleRate:48000
                        parts = line.split(':')
                        if len(parts) > 1:
                            sample_rate = int(parts[1].strip())
                            logger.info(f"Detected Sample Rate: {sample_rate} Hz")
                            break
        except Exception as e:
            logger.warning(f"Could not read metadata: {e}")

    try:
        # 2. Read Raw Binary (Little Endian 16-bit)
        # Using <i2 (signed) or <u2 (unsigned) depends on the source
        # MATLAB script cast to double then subtracted 94. 
        # This implies input was unsigned (0-65535) and centered around 94? 
        # Wait, 94 is very low for 16-bit. 
        # Let's stick to the previous logic: uint16 -> minus 94 -> int16
        
        raw_data = np.fromfile(filepath, dtype='<u2')
        
        if raw_data.size == 0:
            logger.warning(f"Audio file {filepath} is empty.")
            return False

        # 3. DC Offset / Conversion
        # Center the audio. 
        # Note: If the clicking persists, it might be that the file has a 512-byte header 
        # at the start of every 32KB block.
        # Simple fix: Try skipping the first 512 bytes if it sounds like header noise.
        # raw_data = raw_data[256:] # Skip 256 samples (512 bytes)
        
        audio_data = raw_data.astype(np.int32) - 94
        final_data = audio_data.astype(np.int16)

        # 4. Save
        os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
        wavfile.write(output_wav_path, sample_rate, final_data)
        
        logger.info(f"Saved WAV: {os.path.basename(output_wav_path)}")
        return True

    except Exception as e:
        logger.error(f"Failed to parse Audio: {e}")
        return False
    



def parse_audio_file_v2(filepath):
    """
    Parses Vesper Audio Binary (.BIN) and converts it to a standard .WAV file.
    Assumes: 48 kHz Sample Rate, 16-bit depth (2 bytes/sample), Mono.
    """
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return None

    HEADER_SIZE = 150
    SAMPLE_RATE = 48000
    CHANNELS = 1     # Mono
    SAMP_WIDTH = 2   # 16-bit audio = 2 bytes

    try:
        # --- PART 1: HEADER & METADATA (Re-use IMU logic to get Time) ---
        # Note: We must call a function that gets the metadata structure (including time)
        # We need to adapt the IMU parser's header reading logic for audio data.
        
        # --- [Placeholder for Header Reading] ---
        # Assume we call a modified function that returns 'meta' structure 
        # (containing Start_Time, DeviceID, SampleRate, etc.)
        # For now, we manually create a partial meta dictionary based on our finds:
        
        # In a final tool, you'd create a core header reader function shared by IMU and Audio
        # For demonstration, we assume time and IDs are correctly read.
        
        # Example of how you would adapt the IMU logic for audio (skipping complex time decode for now):
        
        # --- PART 1: HEADER PARSING ---
        meta = read_vesper_header(filepath)
        if not meta: return None

        # 3. Read Raw Audio Data Payload
        with open(filepath, 'rb') as f:
            # Skip the 150-byte header to reach the first wave signal packet
            f.seek(HEADER_SIZE) 
            raw_struct = f.read()

        num_samples = len(raw_struct)
        if num_samples == 0:
            return None

        # 4. Write WAV File
        wav_filepath = os.path.splitext(filepath)[0] + ".wav"
        
        with wave.open(wav_filepath, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMP_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw_struct)
        
        logger.info(f"✅ Audio converted: {os.path.basename(wav_filepath)}")
        
        return wav_filepath

    except Exception as e:
        logger.error(f"Failed to parse audio file {filepath}: {e}")
        return None