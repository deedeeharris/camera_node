from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import uvicorn
import os
import datetime
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List
import subprocess
import shutil
from pathlib import Path
import sys
import psutil
import json
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import socketio

load_dotenv()

# --- Socket.IO Setup ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI(title="Camera Node API")
socket_app = socketio.ASGIApp(sio, app)  # Combine Socket.IO and FastAPI

# Enable CORS for FastAPI (still needed for REST endpoints)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
CAPTURE_DIR = "captured_photos"
LOG_DIR = "logs"
STORAGE_LIMIT_MB = 1000  # 1GB storage limit
MAX_LOG_SIZE_MB = 10
MAX_LOG_FILES = 5
PORT = int(os.getenv("PORT", 5001))
NODE_ID = os.getenv("NODE_ID", f"camera_node_{os.getpid()}")
CHUNK_SIZE = 1024 * 1024  # 1MB chunks

# Set up logging
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, "camera_node.log")
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

file_handler = RotatingFileHandler(
    log_file,
    maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024,
    backupCount=MAX_LOG_FILES
)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger = logging.getLogger("camera_node")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def get_system_info() -> Dict:
    """Get system information."""
    cpu_temp = None
    try:
        # Try to get Raspberry Pi CPU temperature
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
    """Get directory size in megabytes."""
    total = 0
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total += os.path.getsize(fp)
    return total / (1024 * 1024)  # Convert to MB

def cleanup_old_files():
    """Remove oldest files if storage limit is reached."""
    if not os.path.exists(CAPTURE_DIR):
        return

    while get_directory_size_mb(CAPTURE_DIR) > STORAGE_LIMIT_MB:
        files = sorted(Path(CAPTURE_DIR).glob('*.dng'), key=os.path.getctime)
        if files:
            oldest_file = files[0]
            logger.info(f"Removing old file: {oldest_file}")
            os.remove(oldest_file)

def check_camera():
    """Check if a camera is connected and available."""
    try:
        cmd = "libcamera-still --list-cameras"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception("No cameras detected")

        cameras = result.stdout.strip().split('\n')
        if not cameras:
            raise Exception("No cameras found")

        logger.info(f"Detected cameras: {cameras}")
        return True
    except Exception as e:
        logger.error(f"Camera check failed: {str(e)}")
        return False

def ensure_capture_dir():
    """Ensure capture directory exists and has space."""
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    cleanup_old_files()

def capture_image() -> Dict:
    """Capture raw image and save locally."""
    ensure_capture_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}_{NODE_ID}.dng"
    filepath = os.path.join(CAPTURE_DIR, filename)

    try:
        cmd = f"libcamera-still --raw -o {filepath} --timeout 1000 --nopreview"
        logger.info(f"Executing capture command: {cmd}")

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"Capture failed: {result.stderr}")

        file_size = os.path.getsize(filepath)
        logger.info(f"Image captured successfully: {filename} (Size: {file_size/1024/1024:.2f}MB)")

        return {
            "filename": filename,
            "filepath": filepath,
            "timestamp": timestamp,
            "size": file_size
        }
    except Exception as e:
        logger.error(f"Capture failed: {str(e)}")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=str(e))


# --- Socket.IO Event Handlers ---

@sio.event
async def connect(sid, environ):
    """Handle client connections."""
    logger.info(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    """Handle client disconnections."""
    logger.info(f"Client disconnected: {sid}")

@sio.on('capture')
async def handle_capture(sid, data):
    """Handle image capture requests."""
    logger.info(f"Received capture request from {sid}")
    try:
        file_info = capture_image()
        await send_image(sid, file_info)
    except Exception as e:
        logger.error(f"Capture failed: {e}")
        await sio.emit('capture_error', {'error': str(e)}, room=sid)


async def send_image(sid, file_info):
    """Send image data in chunks."""
    with open(file_info["filepath"], "rb") as image_file:
        metadata = {
            "filename": file_info["filename"],
            "timestamp": file_info["timestamp"],
            "node_id": NODE_ID,
            "size": file_info["size"],
            "chunk_size": CHUNK_SIZE
        }
        await sio.emit('image_metadata', metadata, room=sid) # Send metadata

        while True:
            chunk = image_file.read(CHUNK_SIZE)
            if not chunk:
                break
            await sio.emit('image_chunk', chunk, room=sid)  # Send the chunk
        await sio.emit('image_complete', room=sid) # Signal completion
        logger.info(f"Sent image {file_info['filename']} to client: {sid}")

# --- Keep existing REST endpoints ---
@app.get("/images/{filename}")
async def get_image(filename: str):
    """Get an image file by filename."""
    try:
        filepath = os.path.join(CAPTURE_DIR, filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Image not found")

        return FileResponse(
            filepath,
            media_type="image/x-adobe-dng",
            filename=filename
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/images")
async def list_images() -> List[Dict]:
    """List all captured images with details."""
    try:
        images = []
        if os.path.exists(CAPTURE_DIR):
            for file in sorted(Path(CAPTURE_DIR).glob('*.dng'), key=os.path.getctime, reverse=True):
                stat = file.stat()
                images.append({
                    "filename": file.name,
                    "size": stat.st_size,
                    "created": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        return images
    except Exception as e:
        logger.error(f"Error listing images: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/images/{filename}")
async def delete_image(filename: str):
    """Delete an image after successful transfer."""
    try:
        filepath = os.path.join(CAPTURE_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Deleted image: {filename}")
            return {"status": "success", "message": f"Deleted {filename}"}
        return {"status": "not_found", "message": f"File {filename} not found"}
    except Exception as e:
        logger.error(f"Error deleting image {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
async def get_logs(lines: int = 100):
    """Get recent log entries."""
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                return {"logs": f.readlines()[-lines:]}
        return {"logs": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def status():
    """Return node status including storage and system info."""
    try:
        storage_used = get_directory_size_mb(CAPTURE_DIR) if os.path.exists(CAPTURE_DIR) else 0
        connected_clients = len(sio.manager.rooms.get('/', {}))  # Correct way to get connected clients
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

@app.post("/capture_rest")  # Keep the REST capture endpoint
async def handle_capture(return_file: bool = False):
    """Handle capture request. Can return either file info or the file itself."""
    try:
        file_info = capture_image()

        if return_file:
            return FileResponse(
                file_info["filepath"],
                media_type="image/x-adobe-dng",
                filename=file_info["filename"]
            )

        return {
            "status": "success",
            "file_info": file_info,
            "node_id": NODE_ID
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info(f"Starting camera node {NODE_ID}")
    ensure_capture_dir()
    if not check_camera():
        logger.error("No camera detected. Please connect a camera and restart the application.")
        sys.exit(1)
    logger.info("Camera detected, starting server...")
    uvicorn.run(socket_app, host="0.0.0.0", port=PORT)