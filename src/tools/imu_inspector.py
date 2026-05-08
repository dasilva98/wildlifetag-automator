"""
IMU BINARY FORMAT ANALYZER & DIAGNOSTIC TOOL
=============================================
Diagnostic tool for inspecting raw IMU .BIN files from Vesper Wildlife Tags.
Auto-detects packet format from the header bitmask, staying in sync with the
main parser at all times.

LOCATION:
---------
    src/tools/imu_inspector.py

USAGE (run from project root):
-------------------------------
1. Metadata Report (default):
   Prints Device ID, Firmware, Sample Rate, BCD timestamp, bitmask decoded
   bit-by-bit, and the auto-detected packet format configuration.
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN

2. Hex Dump (--hex):
   Prints the first N bytes of the file as a Hex + ASCII grid.
   Useful for spotting unexpected headers or byte patterns.
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN --hex
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN --hex 400

3. Packet Size Scanner (--scan):
   Tries packet sizes 32-60 bytes, ranks by how many packets decode to
   physically plausible sensor values. Use this to diagnose unknown or
   changed binary formats before touching the parser.
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN --scan

4. Decoded Packets (--data):
   Decodes the first N packets using the auto-detected format and prints
   them in clean, human-readable standard units. Also prints a per-sensor
   summary (min/max/mean) and a unit plausibility check.
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN --data
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN --data 25

5. Hex Packets (--hexpackets):
   Prints the first N payload packets as structured hex, one packet per row,
   split into semantic fields based on the auto-detected format config.
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN --hexpackets
   $ python -m src.tools.imu_inspector ./data/raw/00M.BIN --hexpackets 50

ARGUMENTS:
----------
    file               Path to the .BIN file.
    --hex  [N]         Hex + ASCII dump of the first N bytes (default: 200).
    --scan             Packet size hypothesis scanner.
    --data [N]         Decode and print first N packets (default: 10).
    --hexpackets [N]   Structured hex dump of first N packets (default: 20).
"""

import argparse
import os
import struct
import sys

import numpy as np

# ---------------------------------------------------------------------------
# Allow imports from project root when run as a script or via -m
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.binary_decoder import decode_binary_header
from src.parsers.imu_parser import _build_dtype, _get_format_config

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
# True header ends at byte 143. Bytes 144+ are the first data packet.
HEADER_SIZE = 144

# Known bitmask bit definitions.
# Add new entries here as they are discovered.
KNOWN_BITS = {
    0: "Accelerometer active",
    1: "Gyroscope active",
    2: "Magnetometer active",
    3: "Extended format — 46B packets, adds temp + pressure fields",
    5: "Standard mode flag (observed in 0x27 — exact function undocumented)",
}

# Config0: observed values are 0 or 1 across known recordings.
# Exact meaning undocumented. No observed effect on packet structure or output.
# Earlier hypothesis of mutual exclusivity with bitmask bit 3 was not confirmed.

# Physical plausibility limits used by --scan.
# Generous enough to not reject real saturation events.
SCAN_ABS_LIMIT = 1e6  # Any float32 beyond this is almost certainly garbage

PACKET_SIZE_MIN = 32
PACKET_SIZE_MAX = 60


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _divider(char="=", width=72):
    return char * width


# ---------------------------------------------------------------------------
# MODE 1 — METADATA REPORT (default)
# ---------------------------------------------------------------------------
def print_metadata(filepath):
    """
    Decodes and prints all header fields, the bitmask bit-by-bit, and the
    auto-detected packet format configuration derived from that bitmask.
    """
    print(f"\n{_divider()}")
    print("  METADATA REPORT")
    print(f"  {filepath}")
    print(_divider())

    meta = decode_binary_header(filepath, header_size=HEADER_SIZE)
    if not meta:
        print("ERROR: Could not decode header.")
        return

    fsize = os.path.getsize(filepath)
    payload = fsize - HEADER_SIZE

    # --- Basic fields ---
    print(f"\n{'File:':<20} {os.path.basename(filepath)}  ({fsize:,} bytes)")
    print(f"{'Device ID:':<20} {meta['DeviceID']}")
    print(f"{'Sensor Name:':<20} {meta['Sensor']}")
    print(f"{'FWID:':<20} {meta['FWID']}  (0x{meta['FWID']:04X})")
    print(f"{'HWID:':<20} {meta['HWID']}  (0x{meta['HWID']:04X})")
    print(f"{'Sample Rate:':<20} {meta['SampleRate']} Hz")
    print(f"{'WinLen / WinRate:':<20} {meta['WinLen']} / {meta['WinRate']}")
    print(
        f"{'Config 0-3:':<20} {meta['Config0']}, {meta['Config1']}, "
        f"{meta['Config2']}, {meta['Config3']}"
    )
    b136 = meta.get("Header_B136", None)
    b136_str = f"0x{b136:02X} ({b136})" if isinstance(b136, int) else "N/A"
    print(f"{'Header_B136:':<20} {b136_str}")
    print(
        f"{'  B136 note:':<20} Per-session byte, stable across all files in a session."
    )
    print(f"{'':20} Leading theory: config preset or schedule slot index.")
    print(f"{'':20} Alternatives: session counter, firmware state, schedule index.")
    print(
        f"{'Start Time (BCD):':<20} {meta['Start_Time'].strftime('%d/%m/%Y %H:%M:%S')}"
    )
    print(f"{'Payload:':<20} {payload:,} bytes")

    # --- Bitmask decoded ---
    bitmask = meta.get("Bitmask", 0)
    print(f"\n{_divider('-')}")
    print(
        f"  BITMASK:  {bitmask} decimal  |  0x{bitmask:02X} hex  |  {bitmask:08b} binary"
    )
    print(_divider("-"))
    for bit in range(8):
        state = "ON " if (bitmask >> bit) & 1 else "OFF"
        meaning = KNOWN_BITS.get(bit, "Unknown")
        marker = " <--" if (bitmask >> bit) & 1 else ""
        print(f"  Bit {bit} [{state}]  {meaning}{marker}")

    # --- pkt_ts format tag note ---
    fmt_tag = bitmask & 0x0F
    print(f"\n  pkt_ts format tag (bitmask & 0x0F): 0x{fmt_tag:02X}")
    print(f"  -> Every packet begins with [0x55][0x{fmt_tag:02X}] as a self-describing")
    print(f"     sync + format identifier. A decoder can identify packet format")
    print(f"     from any single packet without reading the file header.")

    # --- Auto-detected format config ---
    fmt = _get_format_config(bitmask)
    print(f"\n{_divider('-')}")
    print("  AUTO-DETECTED FORMAT CONFIG  (matches main parser)")
    print(_divider("-"))
    print(f"  {'Packet size:':<22} {fmt['packet_size']} bytes")
    print(
        f"  {'Gyro scale:':<22} {fmt['gyro_scale']}  "
        f"({'mdps -> divide by 1000' if fmt['gyro_scale'] != 1.0 else 'dps -> no scaling'})"
    )
    print(
        f"  {'Temp + Pressure:':<22} "
        f"{'YES — bytes 42-45 of each packet' if fmt['has_temp_pres'] else 'NO'}"
    )
    print(f"  {'pkt_ts location:':<22} bytes 0-5 of every packet (always)")

    # --- Packet count ---
    n_packets = payload // fmt["packet_size"]
    remainder = payload % fmt["packet_size"]
    duration_s = n_packets / meta["SampleRate"] if meta["SampleRate"] > 0 else 0
    print(f"\n{_divider('-')}")
    print(f"  PACKET COUNT  (using detected {fmt['packet_size']}B size)")
    print(_divider("-"))
    print(f"  {'Complete packets:':<22} {n_packets:,}")
    print(
        f"  {'Remainder bytes:':<22} {remainder}  "
        f"({'clean' if remainder == 0 else 'WARNING — not divisible'})"
    )
    print(
        f"  {'Duration:':<22} {int(duration_s // 3600)}h "
        f"{int((duration_s % 3600) // 60)}m {int(duration_s % 60)}s"
    )
    print(f"\n{_divider()}\n")


# ---------------------------------------------------------------------------
# MODE 2 — HEX DUMP (--hex)
# ---------------------------------------------------------------------------
def hex_inspector(filepath, limit=200):
    """
    Prints the first `limit` bytes of the file as a Hex + ASCII grid.
    Marks the boundary where the data payload starts.
    """
    print(f"\n{_divider()}")
    print(f"  HEX INSPECTOR  —  First {limit} bytes")
    print(f"  {filepath}")
    print(_divider())
    print(f"\n{'OFFSET':<8} | {'HEX':^48} | ASCII")
    print("-" * 72)

    with open(filepath, "rb") as f:
        data = f.read(limit)

    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hex_str = " ".join(f"{b:02X}" for b in chunk)
        asc_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        print(f"{i:<8} | {hex_str:<48} | {asc_str}")
        if i < HEADER_SIZE <= i + 16:
            print(
                f"{'-' * 8} | {'^ DATA PAYLOAD STARTS AT BYTE 144 ^':^48} | {'-' * 16}"
            )

    print(f"\n{_divider()}\n")


# ---------------------------------------------------------------------------
# MODE 3 — PACKET SIZE SCANNER (--scan)
# ---------------------------------------------------------------------------
def scan_packet_size(filepath):
    """
    Tries packet sizes 32-60 bytes and ranks them by how many packets decode
    to physically plausible float32 sensor values.
    Use this to diagnose unknown or changed binary formats.
    """
    print(f"\n{_divider()}")
    print("  PACKET SIZE SCANNER")
    print(f"  {filepath}")
    print(_divider())

    with open(filepath, "rb") as f:
        f.seek(HEADER_SIZE)
        payload = f.read()

    total_bytes = len(payload)
    print(f"\n  Payload: {total_bytes:,} bytes\n")
    print(f"  Checking packet sizes {PACKET_SIZE_MIN} – {PACKET_SIZE_MAX} bytes.")
    print(
        f"  'Bad' = any of the 9 sensor float32s is NaN, Inf, or abs > {SCAN_ABS_LIMIT:.0e}\n"
    )
    print(
        f"  {'Size':>6} | {'Pkts':>7} | {'Rem':>4} | {'Bad':>7} | {'Bad %':>7} | {'Verdict'}"
    )
    print(f"  {'-' * 6}-+-{'-' * 7}-+-{'-' * 4}-+-{'-' * 7}-+-{'-' * 7}-+-{'-' * 20}")

    results = []

    for psize in range(PACKET_SIZE_MIN, PACKET_SIZE_MAX + 1):
        n = total_bytes // psize
        remainder = total_bytes % psize
        if n == 0:
            continue

        check_n = min(500, n)
        bad = 0

        for i in range(check_n):
            # pkt_ts occupies bytes 0-5 of each packet.
            # Sensor floats start at byte 6: gyro(6-17), acc(18-29), mag(30-41).
            chunk = payload[i * psize + 6 : i * psize + 42]
            try:
                vals = struct.unpack("<9f", chunk)
                if any(not (v == v) or abs(v) > SCAN_ABS_LIMIT for v in vals):
                    bad += 1
            except struct.error:
                bad += 1

        pct = bad / check_n * 100
        verdict = ""
        if pct == 0.0:
            verdict = "<<< CLEAN — strong candidate"
        elif pct < 2.0:
            verdict = "<<  likely candidate"
        elif pct < 10.0:
            verdict = "<   possible"

        results.append((psize, n, remainder, bad, pct, verdict))
        print(
            f"  {psize:>6} | {n:>7,} | {remainder:>4} | {bad:>7} | {pct:>6.1f}% | {verdict}"
        )

    # --- Summary ---
    best = [r for r in results if r[4] < 2.0]
    print(f"\n{_divider('-')}")
    if best:
        print(f"  Best candidate(s): {[r[0] for r in best]} bytes")
        print("  Re-run with --data to decode packets using the auto-detected format.")
    else:
        print(
            f"  No clean packet size found in range {PACKET_SIZE_MIN}-{PACKET_SIZE_MAX}."
        )
        print(
            "  The format may use a size outside this range, or the file may be corrupt."
        )
    print(f"\n{_divider()}\n")


# ---------------------------------------------------------------------------
# MODE 4 — DECODED PACKETS (--data)
# ---------------------------------------------------------------------------
def decode_packets(filepath, n_packets=10):
    """
    Decodes the first `n_packets` packets using the bitmask-auto-detected
    format and prints them in clean standard units.
    Follows with a per-sensor summary and a unit plausibility check.
    """
    print(f"\n{_divider()}")
    print(f"  DECODED PACKETS  —  First {n_packets} packets")
    print(f"  {filepath}")
    print(_divider())

    meta = decode_binary_header(filepath, header_size=HEADER_SIZE)
    if not meta:
        print("ERROR: Could not decode header.")
        return

    bitmask = meta.get("Bitmask", 0)
    fmt = _get_format_config(bitmask)
    dt = _build_dtype(fmt)

    with open(filepath, "rb") as f:
        f.seek(HEADER_SIZE)
        raw = np.fromfile(f, dtype=dt)

    total_available = len(raw)
    if total_available == 0:
        print("  No data packets found.")
        return

    n_show = min(n_packets, total_available)
    subset = raw[:n_show]

    pkt_ts = subset["pkt_ts"]
    gyro_data = np.round(subset["gyro"] / fmt["gyro_scale"], 2)
    acc_data = np.round(subset["acc"], 3)
    mag_data = np.round(subset["mag"], 1)

    has_tp = fmt["has_temp_pres"]
    if has_tp:
        temp_data = np.round(subset["temp"].astype(float) * 0.01, 2)
        pres_data = np.round(subset["pres"].astype(float), 0)

    # --- Format info banner ---
    print(
        f"\n  Bitmask: 0x{bitmask:02X}  |  Packet size: {fmt['packet_size']}B  |  "
        f"Gyro scale: /{fmt['gyro_scale']:.0f}  |  "
        f"Temp+Pres: {'YES' if has_tp else 'NO'}"
    )
    print(f"  Showing {n_show} of {total_available:,} available packets.\n")

    # --- Header row ---
    h = f"  {'Pkt':>4} | {'Min':>3} {'Sec':>3} {'Sub':>3} {'Rol':>3} | "
    h += f"{'Gyro X':>10} {'Gyro Y':>10} {'Gyro Z':>10} [mdps] | "
    h += f"{'Acc X':>9} {'Acc Y':>9} {'Acc Z':>9} [mg]   | "
    h += f"{'Mag X':>8} {'Mag Y':>8} {'Mag Z':>8} [mGauss]"
    if has_tp:
        h += f"  | {'Temp':>7} [C]  {'Pres':>7} [hPa]"
    print(h)
    print(f"  {'-' * (len(h) - 2)}")

    # --- Packet rows ---
    for i in range(n_show):
        ts = pkt_ts[i]
        gx, gy, gz = gyro_data[i]
        ax, ay, az = acc_data[i]
        mx, my, mz = mag_data[i]

        row = f"  {i:>4} | {ts[2]:>3} {ts[3]:>3} {ts[4]:>3} {ts[5]:>3} | "
        row += f"{gx:>10.2f} {gy:>10.2f} {gz:>10.2f}       | "
        row += f"{ax:>9.3f} {ay:>9.3f} {az:>9.3f}        | "
        row += f"{mx:>8.1f} {my:>8.1f} {mz:>8.1f}"
        if has_tp:
            row += f"          | {temp_data[i]:>7.2f}        {pres_data[i]:>7.0f}"
        print(row)

    # --- Per-sensor summary (full dataset) ---
    all_gyro = np.round(raw["gyro"] / fmt["gyro_scale"], 2)
    all_acc = np.round(raw["acc"], 3)
    all_mag = np.round(raw["mag"], 1)

    print(f"\n{_divider('-')}")
    print(f"  PER-SENSOR SUMMARY  (all {total_available:,} packets)")
    print(_divider("-"))

    def _sensor_summary(label, data, unit):
        flat = data.reshape(-1)
        valid = flat[np.isfinite(flat)]
        if len(valid) == 0:
            print(f"  {label:<8}  no finite values found")
            return
        print(
            f"  {label:<8} [{unit}]"
            f"  min={valid.min():>12.3f}"
            f"  max={valid.max():>12.3f}"
            f"  mean={valid.mean():>12.3f}"
            f"  NaN/Inf={len(flat) - len(valid)}"
        )

    _sensor_summary("Gyro", all_gyro, "mdps   ")
    _sensor_summary("Acc", all_acc, "mg     ")
    _sensor_summary("Mag", all_mag, "mGauss ")
    if has_tp:
        all_temp = np.round(raw["temp"].astype(float) * 0.01, 2)
        all_pres = np.round(raw["pres"].astype(float), 0)
        _sensor_summary("Temp", all_temp.reshape(-1, 1), "C      ")
        _sensor_summary("Pres", all_pres.reshape(-1, 1), "hPa    ")

    # --- pkt_ts summary ---
    all_pkt_ts = raw["pkt_ts"]
    mins = all_pkt_ts[:, 2]
    secs = all_pkt_ts[:, 3]
    expected_sync1 = bitmask & 0x0F
    sync_ok = np.all(all_pkt_ts[:, 0] == 0x55) and np.all(
        all_pkt_ts[:, 1] == expected_sync1
    )

    print(f"\n{_divider('-')}")
    print("  PKT_TS SUMMARY")
    print(_divider("-"))
    print(f"  Minutes range: {mins.min()} – {mins.max()}")
    print(f"  Seconds range: {secs.min()} – {secs.max()}")
    print(
        f"  Sync bytes [0x55, 0x{expected_sync1:02X}]: {'OK' if sync_ok else 'MISMATCH — check format'}"
    )

    # Startup duplicate check
    dup = np.array_equal(all_pkt_ts[0], all_pkt_ts[1]) if total_available > 1 else False
    print(
        f"  Startup duplicate:  {'YES — first packet is a duplicate (filtered by parser)' if dup else 'NO'}"
    )

    # --- Unit plausibility check ---
    print(f"\n{_divider('-')}")
    print("  UNIT PLAUSIBILITY CHECK")
    print(_divider("-"))

    gyro_flat = all_gyro.reshape(-1)
    gyro_valid = gyro_flat[np.isfinite(gyro_flat)]
    gyro_max = np.abs(gyro_valid).max() if len(gyro_valid) > 0 else 0

    if gyro_max > 5_000_000:
        print(
            f"  Gyro max abs = {gyro_max:.1f} , which is unexpectedly large even for mdps."
        )
        print("  Check bitmask and _get_format_config() in imu_parser.py.")
    elif gyro_max > 2_000_000:
        print(
            f"  Gyro max abs = {gyro_max:.1f} , which is near sensor saturation (±2000 dps = ±2,000,000 mdps), plausible."
        )
    else:
        print(
            f"  Gyro max abs = {gyro_max:.1f} , which is looks physically reasonable for mdps."
        )

    acc_flat = all_acc.reshape(-1)
    acc_valid = acc_flat[np.isfinite(acc_flat)]
    acc_max = np.abs(acc_valid).max() if len(acc_valid) > 0 else 0

    if acc_max > 20000:
        print(
            f"  Acc  max abs = {acc_max:.1f} — exceeds ±16g sensor range. Possible parsing misalignment."
        )
    else:
        print(f"  Acc  max abs = {acc_max:.1f} — looks physically reasonable for mg.")

    print(f"\n{_divider()}\n")


# ---------------------------------------------------------------------------
# MODE 5 — HEX PACKETS (--hexpackets)
# ---------------------------------------------------------------------------
def hex_packets(filepath, n_packets=20):
    """
    Prints the first N payload packets as structured hex, one packet per row,
    split into semantic fields based on the auto-detected format config.

    Packet layout shown:
        PKT_TS (0-5): [0x55][bitmask&0x0F] + min + sec + subsec + rollover
        GYRO  (6-17): X, Y, Z float32  (always mdps)
        ACC  (18-29): X, Y, Z float32  (mg)
        MAG  (30-41): X, Y, Z float32  (mGauss)
        TEMP (42-43): uint16  [extended only]
        PRES (44-45): uint16  [extended only]
    """
    print(f"\n{_divider()}")
    print(f"  HEX PACKETS  —  First {n_packets} packets (payload only)")
    print(f"  {filepath}")
    print(_divider())

    meta = decode_binary_header(filepath, header_size=HEADER_SIZE)
    if not meta:
        print("ERROR: Could not decode header.")
        return

    bitmask = meta.get("Bitmask", 0)
    fmt = _get_format_config(bitmask)
    psize = fmt["packet_size"]
    has_tp = fmt["has_temp_pres"]

    with open(filepath, "rb") as f:
        f.seek(HEADER_SIZE)
        payload = f.read()

    total = len(payload) // psize
    n_show = min(n_packets, total)

    print(
        f"\n  Bitmask: 0x{bitmask:02X}  |  pkt_ts format tag: 0x{bitmask & 0x0F:02X}  |  "
        f"Packet size: {psize}B  |  Temp+Pres: {'YES' if has_tp else 'NO'}\n"
    )

    # --- Header ---
    header = f"  {'PKT':>4} | {'PKT_TS (bytes 0-5)':<17} | {'GYRO (bytes 6-17)':<35} | {'ACC (bytes 18-29)':<35} | {'MAG (bytes 30-41)':<35}"
    if has_tp:
        header += f" | {'TEMP':<5} | {'PRES':<5}"
    print(header)
    print(f"  {'-' * (len(header) - 2)}")

    # --- Packet rows ---
    for i in range(n_show):
        chunk = payload[i * psize : i * psize + psize]
        ts_hex = chunk[0:6].hex(" ").upper()
        gyro_hex = chunk[6:18].hex(" ").upper()
        acc_hex = chunk[18:30].hex(" ").upper()
        mag_hex = chunk[30:42].hex(" ").upper()

        row = f"  {i:>4} | {ts_hex} | {gyro_hex} | {acc_hex} | {mag_hex}"

        if has_tp:
            temp_hex = chunk[42:44].hex(" ").upper()
            pres_hex = chunk[44:46].hex(" ").upper()
            row += f" | {temp_hex} | {pres_hex}"

        print(row)

    print(f"\n  Showing {n_show} of {total:,} available packets.")
    print(f"\n{_divider()}\n")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="IMU Binary Format Inspector — WildlifeTag Automator diagnostic tool.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("file", help="Path to the .BIN file to inspect.")
    parser.add_argument(
        "--hex",
        nargs="?",
        const=200,
        type=int,
        metavar="N",
        help="Hex + ASCII dump of the first N bytes (default: 200).",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help=f"Packet size hypothesis scanner (tries sizes {PACKET_SIZE_MIN}-{PACKET_SIZE_MAX} bytes).",
    )
    parser.add_argument(
        "--data",
        nargs="?",
        const=10,
        type=int,
        metavar="N",
        help="Decode and print the first N packets in standard units (default: 10).",
    )
    parser.add_argument(
        "--hexpackets",
        nargs="?",
        const=20,
        type=int,
        metavar="N",
        help="Print first N payload packets as structured hex by field (default: 20).",
    )

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"\nError: File not found: '{args.file}'\n")
        sys.exit(1)

    # Always show metadata
    print_metadata(args.file)

    if args.hex is not None:
        hex_inspector(args.file, limit=args.hex)

    if args.scan:
        scan_packet_size(args.file)

    if args.data is not None:
        decode_packets(args.file, n_packets=args.data)

    if args.hexpackets is not None:
        hex_packets(args.file, n_packets=args.hexpackets)


if __name__ == "__main__":
    main()
