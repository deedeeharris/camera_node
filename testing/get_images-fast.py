# get_images.py (Final Optimized Version)

import asyncio
import socketio
import os
import time
import logging
import csv
from logging.handlers import RotatingFileHandler
from datetime import datetime
import numpy as np
from typing import Dict, Any

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
            fieldnames = ['timestamp', 'node_id', 'transfer_time', 'processing_time', 'total_time']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()
            writer.writerow(data)
    except Exception as e:
        logger.exception(f"Error writing to CSV: {e}")


async def receive_images(node_address: str, node_id: str) -> None:
    """Connects to a single node, receives raw images, and processes them."""
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
                process_raw_data(received_data, metadata, node_id)
            except Exception as e:
                logger.exception(f"Error processing raw data from {node_id}: {e}")

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
                'total_time': f"{total_time:.4f}"
            })

            received_data.clear()
            metadata = None
            start_time = None
            total_start_time = time.time()
            await sio.emit('capture', {'resolution': '1280x720'})

        else:
            logger.warning("Received image_complete without metadata!")

    @sio.on('capture_error')
    async def on_capture_error(data: Dict[str, str]):
        logger.error(f"Capture error from {node_id}: {data['error']}")
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

def process_raw_data(data: bytearray, metadata: Dict[str, Any], node_id: str):
    """Processes raw data (demosaics RGB, prepares NoIR), saves without WR."""

    width = metadata['width']
    height = metadata['height']
    bayer_pattern = metadata['bayer_pattern']
    camera_width = metadata['camera_width']  # Use camera_width
    camera_height = metadata['camera_height'] # Use camera_height
    file_size = metadata['size']

    raw_array = np.frombuffer(data, dtype=np.uint8)

    # --- 10-bit Unpacking (for ALL nodes) ---
    # Calculate expected size based on 10-bit packing and CAMERA dimensions
    expected_size = (camera_width * camera_height * 5) // 4  # Use camera dimensions

    if len(raw_array) != expected_size:
      logger.error(f"Incorrect data size. Expected: {expected_size}, got: {len(raw_array)}")
      raise ValueError("Incorrect data size received from camera node.")

    # Reshape to 5 bytes for every 4 pixels, using CAMERA dimensions
    reshaped_data = raw_array.reshape((camera_height * camera_width // 4, 5)) # Use camera dimensions

    # Unpack the 10-bit data
    unpacked_data = np.zeros((camera_height * camera_width,), dtype=np.uint16) # Use camera dimensions
    unpacked_data[0::4] = ((reshaped_data[:, 0] << 2) | (reshaped_data[:, 1] >> 6)) & 0x3FF
    unpacked_data[1::4] = ((reshaped_data[:, 1] << 4) | (reshaped_data[:, 2] >> 4)) & 0x3FF
    unpacked_data[2::4] = ((reshaped_data[:, 2] << 6) | (reshaped_data[:, 3] >> 2)) & 0x3FF
    unpacked_data[3::4] = ((reshaped_data[:, 3] << 8) | reshaped_data[:, 4]) & 0x3FF

    # Reshape to image dimensions using CAMERA dimensions
    raw_image = unpacked_data.reshape((camera_height, camera_width))

    # Now, crop the image to the requested dimensions AFTER unpacking
    raw_image = raw_image[:height, :width]


    if node_id == "node_1":  # RGB Camera
        # Correct Bayer Pattern Handling
        if bayer_pattern.startswith("RGGB"):
            rgb_image = np.zeros((height, width, 3), dtype=np.uint16) # Use REQUESTED dimensions
            rgb_image[:, :, 0] = raw_image[0::2, 0::2]  # Red
            rgb_image[:, :, 1] = (raw_image[0::2, 1::2] + raw_image[1::2, 0::2]) // 2  # Green (average)
            rgb_image[:, :, 2] = raw_image[1::2, 1::2]  # Blue
        # Add other Bayer patterns as needed (BGGR, GRBG, GBRG)
        elif bayer_pattern.startswith("BGGR"):
            rgb_image = np.zeros((height, width, 3), dtype=np.uint16)
            rgb_image[:, :, 2] = raw_image[0::2, 0::2]  # Blue
            rgb_image[:, :, 1] = (raw_image[0::2, 1::2] + raw_image[1::2, 0::2]) // 2  # Green (average)
            rgb_image[:, :, 0] = raw_image[1::2, 1::2]  # Red
        elif bayer_pattern.startswith("GRBG"):
            rgb_image = np.zeros((height, width, 3), dtype=np.uint16)
            rgb_image[:, :, 1] = raw_image[0::2, 0::2]  # Green
            rgb_image[:, :, 0] = raw_image[0::2, 1::2]  # Red
            rgb_image[:, :, 2] = raw_image[1::2, 0::2]  # Blue
            rgb_image[:, :, 1] = (rgb_image[:,:,1] + raw_image[1::2, 1::2])//2 # Green
        elif bayer_pattern.startswith("GBRG"):
            rgb_image = np.zeros((height, width, 3), dtype=np.uint16)
            rgb_image[:, :, 1] = raw_image[0::2, 0::2]  # Green
            rgb_image[:, :, 2] = raw_image[0::2, 1::2]  # Blue
            rgb_image[:, :, 0] = raw_image[1::2, 0::2]  # Red
            rgb_image[:, :, 1] = (rgb_image[:,:,1] + raw_image[1::2, 1::2])//2 # Green

        else:
            raise ValueError(f"Unsupported Bayer pattern: {bayer_pattern}")

        logger.info(f"Processed RGB data from {node_id}. Image shape: {rgb_image.shape}")
        np.save(f"received_images/raw_rgb_{node_id}.npy", rgb_image)  # Save in received_images

    else:  # NoIR Cameras
        # No channel extraction needed on get_images.py anymore
        noir_channel = raw_image
        logger.info(f"Processed NoIR data from {node_id}. Channel shape: {noir_channel.shape}")
        np.save(f"received_images/raw_noir_{node_id}.npy", noir_channel)  # Save in received_images


async def main():
    """Connects to multiple nodes concurrently."""
    nodes = {
        "node_1": "192.168.47.56",
        "node_2": "192.168.195.73",
        "node_3": "192.168.195.70",
        "node_4": "192.168.195.56",
    }
    os.makedirs("received_images", exist_ok=True)  # Create received_images directory
    tasks = [receive_images(address, node_id) for node_id, address in nodes.items()]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())