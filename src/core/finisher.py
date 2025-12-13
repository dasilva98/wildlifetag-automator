import os
import logging
import pandas as pd

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

    def generate_metadata_file(self, meta):
        """
        Generates the sidecar .txt file
        Formats Configs and Bitmask as Hexadecimal to match Vesper output.
        """

        #---Construct Filename and Path---
        start_time = meta['Start_Time'].strftime("%Y%m%d_%H%M%S")
        txt_filename = f"{start_time}_{meta['DeviceID']}.txt"

        txt_path = os.path.join(self.structure["imu"], txt_filename)

        # Check if already exists 
        if os.path.exists(txt_path):
            # logger.info(f"Metadata file for {meta['DeviceID']} already exists. Skipping.")
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