"""
IMU BINARY FORMAT ANALYZER & DIAGNOSTIC TOOL
============================================

This script is a standalone diagnostic tool used to inspect raw IMU .BIN files.
It is useful for debugging corrupted files, verifying firmware versions, 
or checking if data alignment has shifted.

USAGE:
------
Run this script from the command line (terminal).

1. Basic Metadata Check (Safe):
   Prints Device ID, Firmware Version, Sample Rate, and the hidden BCD Timestamp.
   $ python tools/bin_analyzer.py ./data/raw/00M.BIN

2. Hex Dump Inspection (Deep Dive):
   Prints the first 200 bytes in Hex + ASCII format. 
   Useful for seeing "weird characters" or spotting non-standard headers.
   $ python tools/bin_analyzer.py ./data/raw/00M.BIN --hex

3. Data Packet Verification (Sanity Check):
   Decodes the first 3 data packets (Gyro, Acc, Mag) to ensure values 
   are reasonable (e.g., not 10^38 or NaN).
   $ python tools/bin_analyzer.py ./data/raw/00M.BIN --data

ARGUMENTS:
----------
file    : Path to the binary file.
--hex   : Optional. Dumps the header region as Hex/ASCII.
--data  : Optional. Parses and prints the first few data rows.

"""

import struct
import os
import sys
import argparse

# --- CONFIG ---
# The effective start of sensor data
HEADER_SIZE = 150
# Size of one data row (Gyro + Acc + Mag + Time)
PACKET_SIZE = 42

def _bcd_to_int(byte_val):
    """Helper to convert BCD byte to integer."""
    return (byte_val // 16) * 10 + (byte_val % 16)

def print_header_info(filepath):
    """Decodes standard metadata and the hidden BCD timestamp."""
    print(f"\n{'='*20} METADATA REPORT {'='*20}")
    
    try:
        with open(filepath, 'rb') as f:
            header = f.read(HEADER_SIZE)
    except IOError as e:
        print(f"Error reading file: {e}")
        return
    
    # 1. Magic & ID
    magic = header[0:4].hex().upper()
    device_id = struct.unpack('<I', header[4:8])[0]
    
    try:
        # Extract ASCII name, strip null bytes
        name = header[8:24].split(b'\x00')[0].decode('ascii')
    except: 
        name = "Unknown"
        
    # 2. Configs
    sample_rate = struct.unpack('<I', header[28:32])[0]
    bitmask = struct.unpack('<I', header[40:44])[0]
    
    # 3. BCD Timestamp (Located at offsets 132-139)
    try:
        h = _bcd_to_int(header[132])
        m = _bcd_to_int(header[133])
        s = _bcd_to_int(header[134])
        
        # Date: Pad(136), Month(137), Day(138), Year(139)
        mo = _bcd_to_int(header[137])
        da = _bcd_to_int(header[138])
        yr = 2000 + _bcd_to_int(header[139]) # Sensor stores year as '25'
        
        ts_str = f"{da:02d}.{mo:02d}.{yr} {h:02d}:{m:02d}:{s:02d}"
    except Exception:
        ts_str = "Invalid BCD Pattern or Offset mismatch"

    print(f"File:        {os.path.basename(filepath)}")
    print(f"Magic Hex:   {magic} (Should be DEAFDAC0)")
    print(f"Device ID:   {device_id:X}")
    print(f"Sensor Name: {name}")
    print(f"Sample Rate: {sample_rate} Hz")
    print(f"Bitmask:     {bitmask} (Active Sensors)")
    print(f"Start Time:  {ts_str} (Decoded from Header)")

def hex_inspector(filepath, limit=200):
    """Prints a Hex + ASCII grid view for low-level debugging."""
    print(f"\n{'='*20} HEX INSPECTOR (First {limit} bytes) {'='*20}")
    print(f"{'OFFSET':<8} | {'HEX VALUES':<48} | {'ASCII'}")
    print("-" * 75)
    
    with open(filepath, 'rb') as f:
        data = f.read(limit)
        
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = " ".join(f"{b:02X}" for b in chunk)
        # Replace non-printable chars with '.'
        ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        
        print(f"{i:<8} | {hex_str:<48} | {ascii_str}")
        
        # Visual Marker for Data Start
        if i < HEADER_SIZE and i + 16 >= HEADER_SIZE:
            print(f"{'-'*8} | {'^ DATA PAYLOAD STARTS AT OFFSET 150 ^':^48} | {'-'*5}")

def check_packet_alignment(filepath):
    """Reads the first few data packets to verify structure logic."""
    print(f"\n{'='*20} DATA PACKET CHECK {'='*20}")
    
    with open(filepath, 'rb') as f:
        f.seek(HEADER_SIZE)
        
        for i in range(3):
            raw = f.read(PACKET_SIZE)
            if len(raw) < PACKET_SIZE: 
                print("End of file reached.")
                break
            
            # Unpack Float32s (Gyro, Acc, Mag)
            # Structure: Gyro(12) + Acc(12) + Mag(12) + Time(6)
            try:
                gyro = struct.unpack('<3f', raw[0:12])
                acc = struct.unpack('<3f', raw[12:24])
                mag = struct.unpack('<3f', raw[24:36])
                
                print(f"Packet {i}:")
                print(f"  Gyro (dps):    X={gyro[0]:>10.2f}, Y={gyro[1]:>10.2f}, Z={gyro[2]:>10.2f}")
                print(f"  Acc  (mg):     X={acc[0]:>10.2f},  Y={acc[1]:>10.2f},  Z={acc[2]:>10.2f}")
                print(f"  Mag  (mGauss): X={mag[0]:>10.2f},  Y={mag[1]:>10.2f},  Z={mag[2]:>10.2f}")
                print("-" * 50)
            except Exception as e:
                print(f"Error parsing packet {i}: {e}")

def main():
    parser = argparse.ArgumentParser(description="IMU Binary Format Inspector")
    parser.add_argument("file", help="Path to .BIN file")
    parser.add_argument("--hex", action="store_true", help="Show Hex/ASCII dump")
    parser.add_argument("--data", action="store_true", help="Decode first 3 data packets")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        return

    # Always show basic metadata
    print_header_info(args.file)
    
    if args.hex:
        hex_inspector(args.file, limit=200)
        
    if args.data:
        check_packet_alignment(args.file)

if __name__ == "__main__":
    main()