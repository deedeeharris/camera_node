# get_images.py (Revised for Timestamped Directories)

import asyncio
import socketio
import os
import time
import logging
import csv
from logging.handlers import RotatingFileHandler
from datetime import datetime
import numpy as np
from typing import Dict, Any, List

# --- Logging Setup ---
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, "get_images.log")

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5
)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger = logging.getLogger("get_images")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# --- CSV Logging Setup ---
CSV_FILE = os.path.join(LOG_DIR, "image_processing_times.csv")

def write_to_csv(data: Dict[str, Any]):
    """Writes data to the CSV file, with error handling."""
    file_exists = os.path.isfile(CSV_FILE)
    try:
        with open(CSV_FILE, 'a', newline='') as csvfile:
            fieldnames = ['timestamp', 'node_id', 'transfer_time', 'processing_time', 'total_time', 'capture_group']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()
            writer.writerow(data)
    except Exception as e:
        logger.exception(f"Error writing to CSV: {e}")


async def receive_images(node_address: str, node_id: str, base_save_dir: str, capture_group: List[str]) -> None:
    """Connects to a single node, receives, processes, and saves images."""
    sio = socketio.AsyncClient()
    uri = f"http://{node_address}:{5001}"
    received_data = bytearray()
    metadata: Dict[str, Any] | None = None
    start_time: float | None = None
    total_start_time: float = time.time()

    @sio.event
    async def connect():
        logger.info(f"Connected to {node_id} at {uri}")
        await sio.emit('capture', {'resolution': '1280x720'})

    @sio.event
    async def disconnect():
        logger.info(f"Disconnected from {node_id}")

    @sio.on('image_metadata')
    async def on_image_metadata(data: Dict[str, Any]):
        nonlocal metadata, start_time
        metadata = data
        start_time = time.time()
        logger.info(f"Received metadata from {node_id}: {metadata}")
        received_data.clear()

    @sio.on('image_chunk')
    async def on_image_chunk(data: bytes):
        nonlocal received_data
        received_data.extend(data)

    @sio.on('image_complete')
    async def on_image_complete():
        nonlocal metadata, received_data, start_time, total_start_time
        logger.info(f"Received complete image from {node_id}")
        if metadata and start_time:
            transfer_time = time.time() - start_time
            processing_start_time = time.time()

            try:
                # Process and save in the timestamped directory
                save_dir = process_and_save(received_data, metadata, node_id, base_save_dir)
                if save_dir: # Check if save_dir is not None
                    capture_group.append(save_dir) # Add to the capture group

            except Exception as e:
                logger.exception(f"Error processing/saving data from {node_id}: {e}")

            processing_time = time.time() - processing_start_time
            total_time = time.time() - total_start_time

            logger.info(f"Image transfer time from {node_id}: {transfer_time:.4f} seconds")
            logger.info(f"Image processing time from {node_id}: {processing_time:.4f} seconds")
            logger.info(f"Total time elapsed: {total_time:.4f} seconds")

            write_to_csv({
                'timestamp': datetime.now().isoformat(),
                'node_id': node_id,
                'transfer_time': f"{transfer_time:.4f}",
                'processing_time': f"{processing_time:.4f}",
                'total_time': f"{total_time:.4f}",
                'capture_group': os.path.basename(save_dir) if save_dir else "N/A" # Log the directory name
            })

            received_data.clear()
            metadata = None
            start_time = None
            total_start_time = time.time()

            # Only request another image if we have a full set from all nodes
            if len(set(capture_group)) >= 1: # Use set to avoid duplicates
                capture_group.clear()  # Reset for the next group
                await sio.emit('capture', {'resolution': '1280x720'})

        else:
            logger.warning("Received image_complete without metadata!")

    @sio.on('capture_error')
    async def on_capture_error(data: Dict[str, str]):
        logger.error(f"Capture error from {node_id}: {data['error']}")
        # Consider *not* requesting another image immediately on error
        # to avoid a potential error loop.  Maybe retry after a delay.
        await asyncio.sleep(1)  # Short delay before retrying
        await sio.emit('capture', {'resolution': '1280x720'})

    while True:
        try:
            await sio.connect(uri)
            await sio.wait()
        except socketio.exceptions.ConnectionError as e:
            logger.warning(f"Failed to connect to {node_id} ({uri}): {e}. Retrying...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"An unexpected error: {e}")
            await asyncio.sleep(5)

def process_and_save(data: bytearray, metadata: Dict[str, Any], node_id: str, base_save_dir: str) -> str | None:
    """Processes raw data, creates timestamped dir, and saves the image."""

    width = metadata['width']
    height = metadata['height']
    bayer_pattern = metadata['bayer_pattern']
    camera_width = metadata['camera_width']
    camera_height = metadata['camera_height']

    raw_array = np.frombuffer(data, dtype=np.uint8)

    if width != camera_width or height != camera_height:
        logger.warning(f"Captured dimensions ({width}x{height}) differ from camera dimensions ({camera_width}x{camera_height}).")
        raw_array = raw_array[:camera_width * camera_height]
        raw_image = raw_array.reshape((camera_height, camera_width))
        if height < camera_height:
            raw_image = raw_image[:height, :]
        elif height > camera_height:
            padding = np.zeros((height - camera_height, raw_image.shape[1]), dtype=np.uint8)
            raw_image = np.vstack((raw_image, padding))
        if width < camera_width:
            raw_image = raw_image[:, :width]
        elif width > camera_width:
            padding = np.zeros((raw_image.shape[0], width - camera_width), dtype=np.uint8)
            raw_image = np.hstack((raw_image, padding))
    else:
        raw_image = raw_array.reshape((height, width))

    # --- Create Timestamped Directory ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir = os.path.join(base_save_dir, timestamp)
    os.makedirs(save_dir, exist_ok=True)  # Create the directory if it doesn't exist

    if node_id == "node_1":
        if bayer_pattern == "RGGB":
            rgb_image = np.zeros((height, width, 3), dtype=np.uint8)
            rgb_image[:, :, 0] = raw_image[0::2, 0::2]
            rgb_image[:, :, 1] = raw_image[0::2, 1::2]
            rgb_image[:, :, 1] += raw_image[1::2, 0::2]
            rgb_image[:, :, 1] //= 2
            rgb_image[:, :, 2] = raw_image[1::2, 1::2]
        else:
            raise ValueError(f"Unsupported Bayer pattern: {bayer_pattern}")

        logger.info(f"Processed RGB data from {node_id}. Image shape: {rgb_image.shape}")
        filepath = os.path.join(save_dir, f"raw_rgb_{node_id}.npy")
        np.save(filepath, rgb_image)
        return save_dir

    else:  # NoIR Cameras
        noir_channel = raw_image
        logger.info(f"Processed NoIR data from {node_id}. Channel shape: {noir_channel.shape}")
        filepath = os.path.join(save_dir, f"raw_noir_{node_id}.npy")
        np.save(filepath, noir_channel)
        return save_dir

async def main():
    """Connects to multiple nodes concurrently."""
    nodes = {
        "node_1": "192.168.195.57",
        "node_2": "192.168.195.73",
        "node_3": "192.168.195.70",
        "node_4": "192.168.195.56",
    }
    base_save_dir = "received_images"  # Base directory for all captures
    os.makedirs(base_save_dir, exist_ok=True)

    capture_group: List[str] = [] # List to track captured directories

    tasks = [receive_images(address, node_id, base_save_dir, capture_group) for node_id, address in nodes.items()]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())