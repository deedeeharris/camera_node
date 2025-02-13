# camera_node.py (Final Optimized Version)

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
DEFAULT_RESOLUTION = "1280x720"
# DEFAULT_RESOLUTION = "640x480"  # Lower resolution option

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
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    cleanup_old_files()


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

        output_lines = result.stdout.strip().split('\n')
        # Find the line indicating the available camera (should be the first non-empty line)
        active_camera_line_index = next((i for i, line in enumerate(output_lines) if line.startswith('0')), None)

        if active_camera_line_index is None:
            logger.error("No active camera found in output.")
            raise Exception("No active camera found.")

        # --- CORRECTED MODE LINE PARSING ---
        mode_lines = []
        for line in output_lines[active_camera_line_index + 1:]:
            if any(x in line for x in ["x64", "x1296", "x2592"]):  # Look for resolution strings
                if any(bp in line for bp in ["RGGB", "BGGR", "GRBG", "GBRG"]):
                    mode_lines.append(line)

        if not mode_lines:
            logger.error("No camera modes found in output.")
            raise Exception("No camera modes found")

        # Use the *first* mode line to get the resolution and Bayer pattern
        current_mode_line = mode_lines[0].strip()
        logger.info(f"current_mode_line: {current_mode_line}")

        parts = current_mode_line.split()

        # Extract resolution
        resolution_str = next((part for part in parts if 'x' in part and part.split('x')[0].isdigit() and part.split('x')[1].isdigit()), None)
        if not resolution_str:
            raise Exception("Could not find resolution string in mode line.")
        width, height = map(int, resolution_str.split('x'))

        # Extract Bayer pattern
        bayer_pattern_full = next((part for part in parts if any(bp in part for bp in ["RGGB", "BGGR", "GRBG", "GBRG"])), None)

        if not bayer_pattern_full:
            raise Exception("Could not find Bayer pattern string in mode line.")

        bayer_order = ''.join(filter(str.isalpha, bayer_pattern_full))

        logger.info(f"Camera Info: Resolution={width}x{height}, Bayer Pattern={bayer_order}")
        camera_info = (width, height, bayer_order) # Store globally
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
    if camera_info is None:
        camera_info = get_camera_info()  # Ensure camera_info is initialized

    ensure_capture_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}_{NODE_ID}.raw"
    filepath = os.path.join(CAPTURE_DIR, filename)
    width, height = map(int, resolution.split('x'))
    camera_width, camera_height, bayer_pattern = camera_info

    try:
        # Construct the --mode string.  Assume 10-bit packed data ("P").
        mode_string = f"{width}:{height}:10:P"

        cmd = (
            f"libcamera-raw -t 1000 --nopreview --width {width} --height {height} -o {filepath} --mode {mode_string}"
        )
        logger.info(f"Executing capture command: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            raise Exception(f"Capture failed: {result.stderr}")

        file_size = os.path.getsize(filepath)
        logger.info(f"Image captured: {filename} (Size: {file_size/1024:.2f}KB)")

        if NODE_ID != "1":  # NoIR cameras - extract red channel
            with open(filepath, "rb") as f:
                # Read as 8-bit initially. We'll handle unpacking in get_images.py
                raw_data = np.fromfile(f, dtype=np.uint8)


            raw_image = raw_data.reshape((height, width)) # Keep original resolution

            if bayer_pattern.startswith("RGGB"):
                red_channel = raw_image[0::2, 0::2]
            elif bayer_pattern.startswith("BGGR"):
                red_channel = raw_image[1::2, 1::2]
            elif bayer_pattern.startswith("GRBG"):
                red_channel = raw_image[1::2, 0::2]
            elif bayer_pattern.startswith("GBRG"):
                red_channel = raw_image[0::2, 1::2]
            else:
                raise ValueError(f"Unsupported Bayer pattern: {bayer_pattern}")

            with open(filepath, "wb") as f:
                red_channel.tofile(f)
            file_size = os.path.getsize(filepath)
            logger.info(f"Extracted red channel. New size: {file_size/1024:.2f}KB")
            width, height = red_channel.shape[1], red_channel.shape[0]

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
    resolution = data.get('resolution', DEFAULT_RESOLUTION) if isinstance(data, dict) else DEFAULT_RESOLUTION
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
    ensure_capture_dir()
    if not check_camera():
        logger.error("No camera detected.  Please connect a camera and restart.")
        sys.exit(1)
    logger.info("Camera detected, starting server...")

    # --- Get Camera Info at Startup ---
    camera_info = get_camera_info()  # Initialize camera_info

    uvicorn.run(socket_app, host="0.0.0.0", port=PORT)