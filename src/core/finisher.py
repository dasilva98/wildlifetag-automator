import os
import logging
import pandas as pd
from scipy.io import wavfile
from datetime import timedelta

logger = logging.getLogger("wildlifetag_automator")

class FileFinisher:
    def __init__(self, processed_root):
        """
        Initialize with the root folder where organized data should go.
        e.g., ./data/processed/
        """
        self.processed_root = processed_root
        self.structure = {
            "gps": os.path.join(processed_root, "gps"),
            "imu": os.path.join(processed_root, "imu"),
            "aud": os.path.join(processed_root, "aud")
        }
        
        # Create output directories if they don't exist
        for path in self.structure.values():
            os.makedirs(path, exist_ok=True)

    def generate_metadata_file(self, meta, end_time=None, time_stamps = None):
        """
        Generates the sidecar .txt file
        Formats Configs and Bitmask as Hexadecimal to match Vesper output.
        """

        # --- Construct Filename and Path ---
        try:                                                        
            # Format: YYYYMMDD_HHMMSS
            time_fmt = "%Y%m%d_%H%M%S"
            start_str = meta['Start_Time'].strftime(time_fmt)
            
            # LOGIC CHANGE: Handle End Time for Filename
            if end_time:
                end_str = end_time.strftime(time_fmt)
                txt_filename = f"{start_str}-{end_str}_{meta['DeviceID']}.txt"
            else:
                # Fallback if no end_time provided
                txt_filename = f"{start_str}_{meta['DeviceID']}.txt"

        except AttributeError:                                   
            logger.error(f"Metadata error: Start_Time missing.")   
            return                                                 
        
        # Logic to define the specific 'metadata' subfolder path        
        if meta['Sensor'] == "IMU10":
            meta_dir = os.path.join(self.structure["imu"], "metadata") 
        elif meta['Sensor'] == "SPH0641":
            meta_dir = os.path.join(self.structure["aud"], "metadata") 
        else:
            return

        # This line ensures 'imu/metadata' exists before we try to save a file into it.
        os.makedirs(meta_dir, exist_ok=True)

        txt_path = os.path.join(meta_dir, txt_filename)

        if os.path.exists(txt_path):
            return
        
        lines = [
            f"DeviceID:{meta['DeviceID']:X}" if isinstance(meta['DeviceID'], int) else f"DeviceID:{meta['DeviceID']}",
            f"HWID:{meta['HWID']:X}",
            f"FWID:{meta['FWID']:X}",
            f"Sensor:{meta['Sensor']}",
            f"SampleRate:{meta['SampleRate']}",
            f"WinRate:{meta['WinRate']}",
            f"WinLen:{meta['WinLen']}",
            # Use :X to format as Uppercase Hex (e.g., 10 -> A)
            f"Config0:{meta['Config0']:X}",
            f"Config1:{meta['Config1']:X}",
            f"Config2:{meta['Config2']:X}",
            f"Config3:{meta['Config3']:X}",
            f"Bitmask:{meta['Bitmask']:X}"
        ]
        
        # Append Audio Drift Timestamps (If present) ---
        if time_stamps and isinstance(time_stamps, list) and len(time_stamps) > 0:
            lines.append("") # Empty line for separation
            lines.append("=== EMBEDDED BLOCK TIMESTAMPS (Audio Drift Check) ===")
            for i, ts in enumerate(time_stamps):
                lines.append(f"Block_{i+1}: {ts}")

        try:
            with open(txt_path, 'w') as f:
                f.write("\n".join(lines))
        except Exception as e:
            logger.error(f"Failed to write metadata txt: {e}")

    def save_imu_csv(self, dataframe, uid=None):
        """
        Saves the IMU DataFrame.
        Assumes the Parser has already structured the columns correctly.
        """
        if dataframe is None or dataframe.empty:
            return False

        output_path = None
        try:
            # --- GENERATE FILENAME ---
            # The 'Time' column is a DatetimeIndex or Series of datetimes
            start_dt = dataframe['Time'].iloc[0]
            end_dt = dataframe['Time'].iloc[-1]
            
            # Filename format: YYYYMMDD_HHMMSS (Standard sorting)
            time_fmt_file = "%Y%m%d_%H%M%S"
            new_filename = f"{start_dt.strftime(time_fmt_file)}-{end_dt.strftime(time_fmt_file)}_{uid}.csv"
            output_path = os.path.join(self.structure["imu"], new_filename)

            # --- FORMAT TIME COLUMN --- (Optional: Match DD/MM/YYYY format)
            # We create a copy so we don't mess up the original data if used elsewhere
            df_export = dataframe.copy()
            
            # Format: 18/09/2025 07:37:30.696
            # Faster vectorized approach
            time_str = df_export['Time'].dt.strftime('%d/%m/%Y %H:%M:%S')
            ms_str = (df_export['Time'].dt.microsecond // 1000).astype(str).str.zfill(3)
            df_export['Time'] = time_str + '.' + ms_str

            # --- SAVE ---
            df_export.to_csv(output_path, index=False, sep=',') 
            
            logger.info(f"Saved IMU CSV: {new_filename}")
            return True

        except Exception as e:
            logger.error(f"Failed to save CSV {output_path if output_path else 'Unknown'}: {e}")
            return False
        
    def save_aud_wav(self, audio_data, meta):
        """
        Saves the Audio_data to .WAV with a timestamped filename.
        
        Format: START_END_UID.WAV
        Example: 20250929-073451_20250929-074500_4764505D.csv
        """
        if audio_data is not None and len(audio_data) > 0:
            
            output_path = None
            try:
                # ---Calculate Duration and then End Time stamp---
                # Duration = Total Samples / Sample Rate
                duration_seconds = len(audio_data) / meta['SampleRate']
                start_dt = meta['Start_Time']
                end_dt = start_dt + timedelta(seconds=duration_seconds)

                # ---Construct Filename---
                # Filename Format: StartDate_TimeStart-DateEnd_TimeEnd_DeviceID.
                # Time Format: YYYYMMDD_HHMMSS
                time_fmt = "%Y%m%d_%H%M%S"
                start_string = start_dt.strftime(time_fmt)
                end_string = end_dt.strftime(time_fmt)

                new_filename = f"{start_string}-{end_string}_{meta['DeviceID']}.wav"
                output_path = os.path.join(self.structure["aud"], new_filename)

                # ---Save to WAV---
                wavfile.write(output_path, meta['SampleRate'], audio_data) 

                logger.info(f"Saved Audio WAV: {new_filename}")
                return True

            except Exception as e:
                logger.error(f"Failed to save WAV {output_path if output_path else 'Unknown'}: {e}")
                return False
        else:    
            return False