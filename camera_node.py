from fastapi import FastAPI, HTTPException
import uvicorn
import os
import datetime
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Tuple
import subprocess
import shutil
from pathlib import Path
import sys
import psutil
import json
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import socketio
import numpy as np
import re


load_dotenv()

# --- Socket.IO Setup ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI(title="Camera Node API")
socket_app = socketio.ASGIApp(sio, app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
CAPTURE_DIR = "captured_photos"
LOG_DIR = "logs"
STORAGE_LIMIT_MB = 1000
MAX_LOG_SIZE_MB = 10
MAX_LOG_FILES = 5
PORT = int(os.getenv("PORT", 5001))
NODE_ID = os.getenv("NODE_ID", f"camera_node_{os.getpid()}")
CHUNK_SIZE = 64 * 1024
DEFAULT_RESOLUTION = "2304x1296"  # Changed to 2304x1296
SUPPORTED_RESOLUTIONS = ["2304x1296", "1536x864", "1152x648"]  # Add others as needed


# --- Logging Setup ---
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, "camera_node.log")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = RotatingFileHandler(log_file, maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024, backupCount=MAX_LOG_FILES)
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger = logging.getLogger("camera_node")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# --- Global Variable to Store Camera Info ---
camera_info: Tuple[int, int, str] | None = None


def get_system_info() -> Dict:
    """Gets system information (CPU, memory, disk, temperature, uptime)."""
    cpu_temp = None
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            cpu_temp = float(f.read().strip()) / 1000
    except Exception:
        logger.exception("Failed to read CPU temperature.")  # Log but don't raise
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent,
        "cpu_temperature": cpu_temp,
        "uptime": datetime.datetime.now().timestamp() - psutil.boot_time()
    }


def get_directory_size_mb(directory: str) -> float:
    """Calculates the total size of a directory in megabytes."""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(directory):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total += os.path.getsize(fp)
    except Exception:
        logger.exception(f"Error calculating directory size for {directory}") # Log but don't raise
        return 0  # Return 0 if there's an error
    return total / (1024 * 1024)


def cleanup_old_files():
    """Removes oldest files in CAPTURE_DIR if storage exceeds limit."""
    if not os.path.exists(CAPTURE_DIR):
        return
    try:
        while get_directory_size_mb(CAPTURE_DIR) > STORAGE_LIMIT_MB:
            files = sorted(Path(CAPTURE_DIR).glob('*.raw'), key=os.path.getctime)
            if files:
                oldest_file = files[0]
                logger.info(f"Removing old file: {oldest_file}")
                os.remove(oldest_file)
    except Exception:
        logger.exception("Error during file cleanup.") # Log but don't raise


def check_camera():
    """Checks if the camera is connected and available."""
    try:
        cmd = "libcamera-still --list-cameras"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise Exception(f"libcamera-still command failed: {result.stderr}")
        cameras = result.stdout.strip().split('\n')
        if not cameras or "Available cameras" not in result.stdout:
            raise Exception("No cameras found")
        logger.info(f"Detected cameras: {cameras}")
        return True
    except subprocess.TimeoutExpired:
        logger.error("Camera check timed out.")
        return False
    except Exception as e:
        logger.error(f"Camera check failed: {e}")
        return False


def ensure_capture_dir():
    """Ensures the capture directory exists and performs cleanup."""
    try:
        # Create the directory with explicit permissions (read/write/execute for everyone)
        os.makedirs(CAPTURE_DIR, exist_ok=True, mode=0o777)
        cleanup_old_files()
    except Exception as e:
        logger.exception(f"Error creating or cleaning capture directory: {e}")


def get_camera_info() -> Tuple[int, int, str]:
    """Gets camera resolution and Bayer pattern (called only once)."""
    global camera_info
    if camera_info is not None:
        return camera_info

    try:
        cmd = "libcamera-still --list-cameras"
        logger.info(f"Running command: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        logger.debug(f"Command output: {result.stdout}")  # Debug level for full output
        logger.info(f"Command return code: {result.returncode}")
        result.check_returncode()

        output_text = result.stdout

        # Regular expressions to match the resolution and Bayer pattern
        resolution_regex = re.compile(r"(\d+)x(\d+)")  # Matches "1234x5678"
        bayer_regex = re.compile(r"(RGGB|BGGR|GRBG|GBRG)")  # Matches Bayer patterns

        # Find the camera mode lines.  We'll look for lines that contain *both*
        # a resolution *and* a Bayer pattern.
        mode_lines = []
        for line in output_text.splitlines():
            if resolution_regex.search(line) and bayer_regex.search(line):
                mode_lines.append(line)

        if not mode_lines:
            logger.error("No camera modes found in output.")
            raise Exception("No camera modes found")

        # Use the *first* mode line
        current_mode_line = mode_lines[0]
        logger.info(f"current_mode_line: {current_mode_line}")

        # Extract resolution
        resolution_match = resolution_regex.search(current_mode_line)
        if not resolution_match:
            raise Exception("Could not find resolution in mode line.")
        width = int(resolution_match.group(1))
        height = int(resolution_match.group(2))

        # Extract Bayer pattern
        bayer_match = bayer_regex.search(current_mode_line)
        if not bayer_match:
            raise Exception("Could not find Bayer pattern in mode line.")
        bayer_order = bayer_match.group(1)

        logger.info(f"Camera Info: Resolution={width}x{height}, Bayer Pattern={bayer_order}")
        camera_info = (width, height, bayer_order)  # Assign to the global variable
        return camera_info

    except subprocess.CalledProcessError as e:
        logger.error(f"Error running libcamera-still: {e}")
        logger.error(f"Return code: {e.returncode}")
        logger.error(f"Output: {e.output}")
        raise
    except subprocess.TimeoutExpired:
        logger.error("libcamera-still command timed out.")
        raise
    except Exception as e:
        logger.error(f"Error getting camera info: {e}")
        raise



def capture_image(resolution: str = DEFAULT_RESOLUTION) -> Dict:
    """Capture raw Bayer data, extract red channel if NoIR, and save."""
    global camera_info
    if camera_info is not None:
        camera_info = get_camera_info()  # Ensure camera_info is initialized

    ensure_capture_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}_{NODE_ID}.raw"
    filepath = os.path.join(CAPTURE_DIR, filename)
    logger.info(f"Camera info: {camera_info}")
    width, height = map(int, resolution.split('x'))  # Requested width/height
    camera_width, camera_height, bayer_pattern = camera_info

    try:
        # Use the FULL sensor resolution in --mode, and crop with --width/--height
        mode_string = f"{camera_width}:{camera_height}:10:P"  # Full resolution

        cmd = (
            f"libcamera-raw -t 1000 --nopreview --width {width} --height {height} -o {filepath} --mode {mode_string}"
        )
        logger.info(f"Executing capture command: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)

        # IMPORTANT: Check for errors *before* getting the file size.
        if result.returncode != 0:
            raise Exception(f"Capture failed: {result.stderr}")

        # Wait for the file to be fully written.  libcamera-raw might
        # still be writing in the background even after subprocess.run
        # returns.  We'll check the file size repeatedly until it
        # stabilizes.
        previous_size = -1
        current_size = 0
        while current_size != previous_size:
            previous_size = current_size
            time.sleep(0.1)  # Wait a short time
            with open(filepath, "rb") as f:
                f.flush()
                os.fsync(f.fileno())  # Force synchronization
            current_size = os.path.getsize(filepath)

        file_size = current_size # Use the final, stable size

        logger.info(f"Image captured: {filename} (Size: {file_size/1024:.2f}KB)")
        logger.info(f"File size immediately after capture: {file_size}")

        # No channel extraction needed for node_1

        logger.info(f"Final file size before return: {file_size}")

        return {
            "filename": filename,
            "filepath": filepath,
            "timestamp": timestamp,
            "size": file_size,
            "width": width,
            "height": height,
            "camera_width": camera_width,
            "camera_height": camera_height,
            "bayer_pattern": bayer_pattern,
        }
    except subprocess.TimeoutExpired:
        logger.error("Image capture timed out.")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=504, detail="Capture timed out")
    except Exception as e:
        logger.error(f"Capture failed: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=str(e))

# --- Socket.IO Event Handlers ---
@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")


@sio.on('capture')
async def handle_capture(sid, data):
    logger.info(f"Received capture request from {sid}")
    requested_resolution = data.get('resolution', DEFAULT_RESOLUTION) if isinstance(data, dict) else DEFAULT_RESOLUTION

    # Validate the resolution
    if requested_resolution not in SUPPORTED_RESOLUTIONS:
        logger.warning(f"Unsupported resolution requested: {requested_resolution}. Using default: {DEFAULT_RESOLUTION}")
        resolution = DEFAULT_RESOLUTION
    else:
        resolution = requested_resolution

    try:
        file_info = capture_image(resolution=resolution)
        await send_image(sid, file_info)
    except Exception as e:
        logger.error(f"Capture failed: {e}")
        await sio.emit('capture_error', {'error': str(e)}, room=sid)


async def send_image(sid, file_info):
    """Send raw image data in chunks."""
    try:
        with open(file_info["filepath"], "rb") as image_file:
            metadata = {
                "filename": file_info["filename"],
                "timestamp": file_info["timestamp"],
                "node_id": NODE_ID,
                "size": file_info["size"],
                "chunk_size": CHUNK_SIZE,
                "width": file_info["width"],
                "height": file_info["height"],
                "camera_width": file_info["camera_width"],
                "camera_height": file_info["camera_height"],
                "bayer_pattern": file_info["bayer_pattern"],
            }
            await sio.emit('image_metadata', metadata, room=sid)

            while True:
                chunk = image_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                await sio.emit('image_chunk', chunk, room=sid)
            await sio.emit('image_complete', room=sid)
            logger.info(f"Sent image {file_info['filename']} to client: {sid}")
    except Exception as e:
        logger.exception(f"Error sending image to client: {sid}")
        await sio.emit('capture_error', {'error': str(e)}, room=sid)

# --- REST Endpoints ---
@app.get("/status")
async def status():
    """Returns the current status of the camera node."""
    try:
        storage_used = get_directory_size_mb(CAPTURE_DIR) if os.path.exists(CAPTURE_DIR) else 0
        connected_clients = len(sio.manager.rooms.get('/', {}))
        return {
            "status": "online",
            "storage": {
                "used_mb": storage_used,
                "limit_mb": STORAGE_LIMIT_MB,
                "available_mb": STORAGE_LIMIT_MB - storage_used
            },
            "system": get_system_info(),
            "node_id": NODE_ID,
            "timestamp": datetime.datetime.now().isoformat(),
            "connected_clients": connected_clients
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs")
async def get_logs(lines: int = 100):
    """Retrieves the last 'lines' lines from the log file."""
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                return {"logs": f.readlines()[-lines:]}
        return {"logs": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    logger.info(f"Starting camera node {NODE_ID}")
    ensure_capture_dir()  # Call with explicit permissions
    if not check_camera():
        logger.error("No camera detected.  Please connect a camera and restart.")
        sys.exit(1)
    logger.info("Camera detected, starting server...")

    # --- Get Camera Info at Startup ---
    camera_info = get_camera_info()  # Initialize camera_info

    uvicorn.run(socket_app, host="0.0.0.0", port=PORT)