import os
import subprocess
import time
import logging
from logging.handlers import RotatingFileHandler

# --- Configuration ---
CAPTURE_DIR = "captured_photos"
LOG_DIR = "logs"
DEFAULT_RESOLUTION = "2304x1296"

# --- Logging Setup ---
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, "camera_node_debug.log")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(formatter)
logger = logging.getLogger("camera_node_debug")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

def ensure_capture_dir():
    """Ensures the capture directory exists."""
    try:
        os.makedirs(CAPTURE_DIR, exist_ok=True, mode=0o777)
    except Exception as e:
        logger.exception(f"Error creating capture directory: {e}")

def capture_image(resolution: str = DEFAULT_RESOLUTION):
    """Capture raw Bayer data and log file sizes."""
    ensure_capture_dir()
    filename = "test_capture.raw"
    filepath = os.path.join(CAPTURE_DIR, filename)
    width, height = map(int, resolution.split('x'))
    camera_width, camera_height = (4608, 2592)  # Hardcoded for simplicity

    try:
        mode_string = f"{camera_width}:{camera_height}:10:P"
        cmd = (
            f"libcamera-raw -t 1000 --nopreview --width {width} --height {height} -o {filepath} --mode {mode_string}"
        )
        logger.info(f"Executing capture command: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)

        if result.returncode != 0:
            raise Exception(f"Capture failed: {result.stderr}")

        # Calculate the *correct* file size.
        stride = (camera_width // 4) * 5
        calculated_size = stride * height
        logger.info(f"Calculated size: {calculated_size}")

        # Wait for file size to stabilize (as before).
        previous_size = -1
        current_size = 0
        while current_size != previous_size:
            previous_size = current_size
            time.sleep(0.1)
            with open(filepath, "rb") as f:
                f.flush()
                os.fsync(f.fileno())
            current_size = os.path.getsize(filepath)

        logger.info(f"Actual file size (after sync): {current_size}")


    except Exception as e:
        logger.error(f"Capture failed: {e}")

if __name__ == "__main__":
    logger.info(f"Starting simplified camera node")
    capture_image()