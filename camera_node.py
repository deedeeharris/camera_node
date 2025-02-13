# camera_node.py (Revised for Single-Channel NoIR Transfer)
# type: ws version: 2

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
import numpy as np  # Import NumPy

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
CAPTURE_DIR = "captured_photos"  # We'll still use this for temporary storage
LOG_DIR = "logs"
STORAGE_LIMIT_MB = 1000
MAX_LOG_SIZE_MB = 10
MAX_LOG_FILES = 5
PORT = int(os.getenv("PORT", 5001))
NODE_ID = os.getenv("NODE_ID", f"camera_node_{os.getpid()}")
CHUNK_SIZE = 64 * 1024  # 64KB chunks
DEFAULT_RESOLUTION = "1280x720"  # Start with a moderate resolution
#DEFAULT_RESOLUTION = "640x480"

# --- Logging Setup (same as before) ---
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

def get_system_info() -> Dict:
    """(Same as before)"""
    cpu_temp = None
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            cpu_temp = float(f.read().strip()) / 1000
    except:
        pass
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent,
        "cpu_temperature": cpu_temp,
        "uptime": datetime.datetime.now().timestamp() - psutil.boot_time()
    }

def get_directory_size_mb(directory: str) -> float:
    """(Same as before)"""
    total = 0
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total += os.path.getsize(fp)
    return total / (1024 * 1024)

def cleanup_old_files():
    """(Same as before, but now looks for .raw files)"""
    if not os.path.exists(CAPTURE_DIR): return
    while get_directory_size_mb(CAPTURE_DIR) > STORAGE_LIMIT_MB:
        files = sorted(Path(CAPTURE_DIR).glob('*.raw'), key=os.path.getctime)
        if files:
            oldest_file = files[0]
            logger.info(f"Removing old file: {oldest_file}")
            os.remove(oldest_file)

def check_camera():
    """(Same as before)"""
    try:
        cmd = "libcamera-still --list-cameras"  # Use still to list cameras
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0: raise Exception("No cameras detected")
        cameras = result.stdout.strip().split('\n')
        if not cameras: raise Exception("No cameras found")
        logger.info(f"Detected cameras: {cameras}")
        return True
    except Exception as e:
        logger.error(f"Camera check failed: {str(e)}")
        return False

def ensure_capture_dir():
    """(Same as before)"""
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    cleanup_old_files()

def get_camera_info() -> Tuple[int, int, str]:
    """(Same as before)"""
    try:
        cmd = "libcamera-still --list-cameras"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        result.check_returncode()

        output_lines = result.stdout.strip().split('\n')
        active_camera_line = next((line for line in output_lines if line.startswith('Available cameras')), None)
        if not active_camera_line: raise Exception("No active camera found.")
        mode_lines = [line for line in output_lines if "modes" in line]
        if not mode_lines: raise Exception("No camera modes found")
        current_mode_line = mode_lines[0]
        parts = current_mode_line.split()
        resolution_str = parts[2]
        bayer_pattern = parts[-1]
        width, height = map(int, resolution_str.split('x'))
        bayer_order = ''.join(filter(str.isalpha, bayer_pattern))
        logger.info(f"Camera Info: Resolution={width}x{height}, Bayer Pattern={bayer_order}")
        return width, height, bayer_order

    except Exception as e:
        logger.error(f"Error getting camera info: {e}")
        raise

def capture_image(resolution: str = DEFAULT_RESOLUTION) -> Dict:
    """Capture raw Bayer data, extract red channel if NoIR, and save."""
    ensure_capture_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}_{NODE_ID}.raw"
    filepath = os.path.join(CAPTURE_DIR, filename)
    width, height = map(int, resolution.split('x'))

    try:
        cmd = (f"libcamera-raw -t 1000 --nopreview -r {width}x{height} -o {filepath}")
        logger.info(f"Executing capture command: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0: raise Exception(f"Capture failed: {result.stderr}")

        file_size = os.path.getsize(filepath)
        logger.info(f"Image captured: {filename} (Size: {file_size/1024:.2f}KB)")
        camera_width, camera_height, bayer_pattern = get_camera_info()

        # --- Extract Red Channel (if NoIR) ---
        if NODE_ID != "1":  # Since "1" is the RGB camera
            with open(filepath, "rb") as f:
                raw_data = np.fromfile(f, dtype=np.uint8)
            raw_image = raw_data.reshape((height, width))

            if bayer_pattern == "RGGB":
                red_channel = raw_image[0::2, 0::2]
            elif bayer_pattern == "BGGR":
                red_channel = raw_image[1::2, 1::2]
            elif bayer_pattern == "GRBG":
                red_channel = raw_image[1::2, 0::2]
            elif bayer_pattern == "GBRG":
                red_channel = raw_image[0::2, 1::2]
            else:
                raise ValueError(f"Unsupported Bayer pattern: {bayer_pattern}")

            # Overwrite the original file with ONLY the red channel data
            with open(filepath, "wb") as f:
                red_channel.tofile(f)
            file_size = os.path.getsize(filepath) # Update file_size
            logger.info(f"Extracted red channel. New size: {file_size/1024:.2f}KB")
            # Update width and height for the red channel
            width = red_channel.shape[1]
            height = red_channel.shape[0]

        return {
            "filename": filename,
            "filepath": filepath,
            "timestamp": timestamp,
            "size": file_size,
            "width": width,
            "height": height,
            "camera_width": camera_width,
            "camera_height": camera_height,
            "bayer_pattern": bayer_pattern,  # Still send the original pattern
        }
    except Exception as e:
        logger.error(f"Capture failed: {str(e)}")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=str(e)}")

# --- Socket.IO Event Handlers (No changes needed) ---
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

# --- REST Endpoints (Simplified - Remove image serving) ---

@app.get("/status")
async def status():
    """(Same as before)"""
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
        logger.error(f"Error getting status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
async def get_logs(lines: int = 100):
    """(Same as before)"""
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
    uvicorn.run(socket_app, host="0.0.0.0", port=PORT)