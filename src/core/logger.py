import logging
import os
import sys
from datetime import datetime
from tqdm import tqdm

class TqdmLoggingHandler(logging.Handler):
    """
    Custom logging handler that uses tqdm.write to 
    ensure log messages don't break the progress bar.
    """
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)

            # tqdm.write prints safely above the progress bar
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

def setup_logger(name, log_dir="."):
    """Sets up a logger that writes to console and a file."""

    # --- 1. RENAME LEVELS ---
    logging.addLevelName(logging.WARNING, "WARN")
    logging.addLevelName(logging.CRITICAL, "CRIT")
    logging.addLevelName(logging.ERROR, "ERR")
    logging.addLevelName(logging.DEBUG, "DBUG")
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Create a unique log filename based on time
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"wildlifetag_run_{timestamp}.log")

    # Define the format
    log_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-4s | %(message)s",
        datefmt="%y-%m-%d %H:%M:%S"
    )

    # File handler (writes to disk)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(log_formatter)

    # TQDM console handler (writes to terminal safely)
    console_handler = TqdmLoggingHandler()
    console_handler.setFormatter(log_formatter)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger