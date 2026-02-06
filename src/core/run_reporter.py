import os
from datetime import datetime
from src.core.constants import FULL_APP_NAME

class RunReporter:
    """
    Manages execution statistics and generates the final Processing Report.
    Functions as the 'Single Source of Truth' for run metrics.
    """
    def __init__(self):
        # Capture start time
        self.start_time = datetime.now()
        # Initialize zeroed stats structure
        self.stats = {
            "total": 0,
            
            # IMU
            "total_imu": 0, "success_imu": 0, "warn_imu": 0, "failed_imu": 0,
            
            # Audio
            "total_aud": 0, "success_aud": 0, "warn_aud": 0, "failed_aud": 0,
            
            # GPS
            "total_gps": 0, "success_gps": 0, "warn_gps": 0, "failed_gps": 0,
            
            # Yield Metrics
            "duration_imu_sec": 0, 
            "duration_aud_sec": 0, 
            "gps_fixes": 0,
            
            # Lists
            "sessions": [],
            "errors": []
        }

    def log_file_result(self, sensor_type, status, filepath, msg=None):
        """
        Updates counters for a specific file and logs errors if needed.
        sensor_type: 'imu', 'aud', or 'gps'
        status: 'SUCCESS', 'EMPTY', or 'FAIL'
        """
        s_key = sensor_type.lower() # e.g., 'imu'
        
        # 1. Increment Total
        self.stats[f"total_{s_key}"] += 1
        self.stats["total"] += 1

        # 2. Increment Specific Status
        if status == "SUCCESS":
            self.stats[f"success_{s_key}"] += 1
        
        elif status == "EMPTY":
            self.stats[f"warn_{s_key}"] += 1
            self.stats['errors'].append({
                "type": "WARN",
                "file": filepath,
                "reason": msg or "File Empty"
            })
            
        else: # FAIL or anything else
            self.stats[f"failed_{s_key}"] += 1
            self.stats['errors'].append({
                "type": "CRITICAL",
                "file": filepath,
                "reason": msg or "Processing Failed"
            })

    def add_session(self, session_metrics):
        """Adds a completed session inventory to the report."""
        self.stats['sessions'].append(session_metrics)
        
        # Aggregate Yields (Safe get to avoid errors if keys missing)
        self.stats["gps_fixes"] += session_metrics.get("gps_fixes", 0)

        # Add IMU duration and Audio duration the the global stats
        self.stats["duration_imu_sec"] += session_metrics.get("duration_imu_sec", 0)
        self.stats["duration_aud_sec"] += session_metrics.get("aud_duration", 0)
        
        # If your session_metrics has explicit keys, sum them here:
        if "aud_duration" in session_metrics:
            self.stats["duration_aud_sec"] += session_metrics["aud_duration"]
        # Add IMU duration logic if you track it per session in main.py

    def log_external_error(self, reason):
        """Logs a generic or external tool error (like GeoTag missing)."""
        self.stats['errors'].append({
            "type": "CRITICAL",
            "file": "External Tool",
            "reason": reason
        })

    def save_report(self, processed_folder, logger):
        """
        Compiles and saves the formatted text report.
        """
        lines = []
        
        # --- HEADER ---
        lines.append("="*90)
        title = f"{FULL_APP_NAME.upper()} - PROCESSING REPORT"
        lines.append(f"{title:^90}")
        lines.append("="*90)
        
        # Calculate duration
        duration = datetime.now() - self.start_time
        s = int(duration.total_seconds())

        # Calculate hours, minutes, seconds
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)

        # Format: 01h04m36s or 22m06s
        time_str = f"{h:02}h{m:02}m{s:02}s" if h else f"{m:02}m{s:02}s"

        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # "Date: 2026-02-02 06:57:10  |  Total Files Found: 6462  |  Run Time: 22m06s"
        header_info = f"Date: {date_str}  |  Total Files Found: {self.stats['total']}  |  Run Time: {time_str}"
        lines.append(f"{header_info:^90}") # Center it for extra style, or remove :^90 to left align
        lines.append("")

        # --- SECTION 1: RAW DATA STATISTICS ---
        lines.append("RAW DATA STATISTICS:")
        lines.append("-" * 59)
        lines.append(f"| {'SENSOR':<8} | {'TOTAL':<6} | {'OK':<6} | {'WARN':<6} | {'FAIL':<6} | {'RATE (%)':<8} |")
        lines.append("-" * 59)

        def calc_pct(num, den):
            return f"{(num/den)*100:.1f}%" if den > 0 else "0.0%"

        # Define rows
        rows = [
            ("IMU", self.stats['total_imu'], self.stats['success_imu'], self.stats['warn_imu'], self.stats['failed_imu']),
            ("AUDIO", self.stats['total_aud'], self.stats['success_aud'], self.stats['warn_aud'], self.stats['failed_aud']),
            ("GPS", self.stats['total_gps'], self.stats['success_gps'], self.stats['warn_gps'], self.stats['failed_gps']),
        ]

        for label, tot, ok, warn, fail in rows:
            pct = calc_pct(ok, tot)
            lines.append(f"| {label:<8} | {tot:<6} | {ok:<6} | {warn:<6} | {fail:<6} | {pct:<8} |")

        lines.append("-" * 59)

        # TOTALS ROW
        all_tot = sum(r[1] for r in rows)
        all_ok = sum(r[2] for r in rows)
        all_warn = sum(r[3] for r in rows)
        all_fail = sum(r[4] for r in rows)
        all_pct = calc_pct(all_ok, all_tot)

        lines.append(f"| {'ALL':<8} | {all_tot:<6} | {all_ok:<6} | {all_warn:<6} | {all_fail:<6} | {all_pct:<8} |")
        lines.append("-" * 59)
        lines.append(" ")

        # --- SECTION 2: SESSIONS INVENTORY & METRICS ---
        lines.append("SESSIONS INVENTORY & METRICS:")
        lines.append("-" * 90)
        header = f"| {'DEVICE ID':<16} | {'WINDOW (Start -> End)':<22} | {'AUD (h)':<7} | {'GPS (Fix/Try)':<13} | {'FILES (I/A/G)':<16} |"
        lines.append(header)
        lines.append("-" * 90)

        for sess in self.stats['sessions']:
            d1 = "No Date"
            d2 = "No Date"
            if sess.get('start_time') and sess.get('end_time'):
                d1 = sess['start_time'].strftime("%m-%d")
                d2 = sess['end_time'].strftime("%m-%d")
                if d1 == d2:
                    t1 = sess['start_time'].strftime("%H:%M")
                    t2 = sess['end_time'].strftime("%H:%M")
                else:
                    t1 = sess['start_time'].strftime("%H:%M")
                    t2 = sess['end_time'].strftime("%H:%M (%m-%d)")
                window_str = f"{t1} -> {t2}"
            else:
                window_str = "No Data"

            aud_hrs = f"{sess.get('aud_duration', 0)/3600:.1f}"
            gps_ratio = f"{sess.get('gps_fixes',0)}/{sess.get('gps_attempts',0)}"
            files_breakdown = f"{sess.get('imu_ok',0)}/{sess.get('aud_ok',0)}/{sess.get('gps_ok',0)}"

            row = f"| {sess['id']:<8} ({d1}) | {window_str:<22} | {aud_hrs:<7} | {gps_ratio:<13} | {files_breakdown:<16} |"
            lines.append(row)
        
        lines.append("-" * 90)
        lines.append("")

        # --- SECTION 3: TOTAL DATA YIELD ---
        lines.append("TOTAL DATA YIELD:")
        def fmt_time(seconds):
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            return f"{int(h)}h {int(m)}m {int(s)}s"

        lines.append(f"   > Total IMU Duration:   {fmt_time(self.stats['duration_imu_sec'])}")
        lines.append(f"   > Total Audio Duration: {fmt_time(self.stats['duration_aud_sec'])}")
        lines.append(f"   > Total GPS Fixes:      {self.stats['gps_fixes']} valid coordinates")
        lines.append("="*90)

        # --- SECTION 4: ERRORS & WARNINGS ---
        errors = [e for e in self.stats['errors'] if e.get('type') == 'CRITICAL']
        if errors:
            lines.append(f"{'[X] CRITICAL FAILURES (Action Required)':^90}")
            lines.append("-" * 90)
            has_geotag = False
            for err in errors:
                lines.append(f"   {err['reason']}")
                if 'file' in err and err['file'] != "External Tool":
                     lines.append(f"      File: {err['file']}")
                if "GeoTag" in err['reason']: has_geotag = True
            
            if has_geotag:
                lines.append("=> Check if GeoTag.exe and its sidecar files are in the correct folder.")
                lines.append("=> Check 'config.yaml' if you forgot to update the paths.")
                lines.append("=> Target folder default location is 'external_tools/'")
            lines.append("="*90)

        warnings = [e for e in self.stats['errors'] if e.get('type') == 'WARN']
        if warnings:
            if not errors: lines.append("="*90)
            lines.append("[!] WARNINGS (Empty Files - No Data Recorded)")
            lines.append("-" * 90)
            for w in warnings[:15]:
                lines.append(f"   {os.path.basename(w['file'])}: {w['reason']}")
            if len(warnings) > 15: lines.append(f"   ... and {len(warnings)-15} more.")
            lines.append("="*90)

        lines.append("END OF REPORT")

        # --- 1. CONSOLE OUTPUT (Smart Logging) ---
        import logging # Ensure available locally if needed
        current_level = logging.INFO
        
        # Define 'safe' limit for console, but ALWAYS print errors
        console_limit = 40 
        
        for i, line in enumerate(lines):
            # Dynamic Level Switching
            if "[X] CRITICAL FAILURES" in line:
                current_level = logging.ERROR
            elif "[!] WARNINGS" in line:
                current_level = logging.WARNING
            elif "END OF REPORT" in line:
                current_level = logging.INFO
            
            # Smart Truncation: 
            # If we are in INFO mode and passed the limit, skip until we hit a warning/error
            if i > console_limit and current_level == logging.INFO:
                if i == console_limit + 1:
                    logger.info("... (Middle of report truncated for console) ...")
                continue 

            # Log with the correct color/level
            if current_level == logging.ERROR:
                logger.error(line)
            elif current_level == logging.WARNING:
                logger.warning(line)
            else:
                logger.info(line)

        # --- 2. FILE SAVE ---
        reports_dir = os.path.join(processed_folder, "report_cards")
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        report_path = os.path.join(reports_dir, filename)
        
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info(f"[Report] Saved to: {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"Failed to write summary report file: {e}")
            return None