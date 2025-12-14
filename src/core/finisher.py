import os
import logging
import pandas as pd
from scipy.io import wavfile

logger = logging.getLogger("vesper_automator")

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

    def generate_metadata_file(self, meta, time_stamps = None):
        """
        Generates the sidecar .txt file
        Formats Configs and Bitmask as Hexadecimal to match Vesper output.
        """
    # --- Construct Filename and Path ---
        try:                                                        
            start_time = meta['Start_Time'].strftime("%Y%m%d_%H%M%S")
        except AttributeError:                                   
            logger.error(f"Metadata error: Start_Time missing.")   
            return                                                  

        txt_filename = f"{start_time}_{meta['DeviceID']}.txt"
        
        # CHANGE 3: Logic to define the specific 'metadata' subfolder path
        if meta['Sensor'] == "IMU10":
            # We join the 'imu' path with a new folder 'metadata'
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
            f"DeviceID:{meta['DeviceID']}",
            "HWID:0", # TODO We need to find this byte
            "FWID:112", # TODO We need to find this byte
            f"Sensor:{meta['Sensor']}",
            f"SampleRate:{meta['SampleRate']}",
            "WinRate:0", # TODO We need to find this byte
            "WinLen:0", # TODO We need to find this byte
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
        Saves the IMU DataFrame to CSV with a timestamped filename.
        
        Format: START_END_UID.csv
        Example: 20250929-073451_20250929-074500_4764505D.csv
        """
        if dataframe is None or dataframe.empty:
            return False


        output_path = None
        try:
            #---Extract Start and End times from the Data---
            # dataframe['Time'] contains datetime objects from the parser
            start_dt = dataframe['Time'].iloc[0]
            end_dt = dataframe['Time'].iloc[-1]
            
            # Format: YYYYMMDD-HHMMSS
            time_fmt = "%Y%m%d_%H%M%S"
            start_str = start_dt.strftime(time_fmt)
            end_str = end_dt.strftime(time_fmt)

            #---Construct Filename---
            # VesperApp style: Start-End_DeviceID.csv
            new_filename = f"{start_str}-{end_str}_{uid}.csv"
            output_path = os.path.join(self.structure["imu"], new_filename)

            #---Save to CSV---
            # Note: Using comma (,) as separator is standard for data analysis.
            # If you specifically need Semicolon for Excel in Europe, change sep=';'
            dataframe.to_csv(output_path, index=False, sep=',') 
            
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
                
                # Format: YYYYMMDD-HHMMSS
                start_time = meta['Start_Time'].strftime("%Y%m%d_%H%M%S")
                print("meta['Start_Time']:", meta['Start_Time'])
                #---Construct Filename---
                # VesperApp style: Start-End_DeviceID.wav
                new_filename = f"{start_time}_{meta['DeviceID']}.wav" # TODO add end_time to the name of the file
                output_path = os.path.join(self.structure["aud"], new_filename)
                print("INSIDE CHECK 1-------------------")
                #---Save to WAV---
                wavfile.write(output_path, meta['SampleRate'], audio_data) 
                print("INSIDE CHECK 2-------------------")
                logger.info(f"Saved Audio WAV: {new_filename}")
                return True

            except Exception as e:
                logger.error(f"Failed to save WAV {output_path if output_path else 'Unknown'}: {e}")
                return False
        else:    
            return False