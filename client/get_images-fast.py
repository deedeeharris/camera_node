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
from PIL import Image  # Add this import for handling JPG images
from threading import Lock

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

# Add these global variables
current_batch_timestamp = None
batch_timestamp_lock = Lock()

def get_batch_timestamp() -> str:
    """Gets or creates a timestamp for the current batch."""
    global current_batch_timestamp
    with batch_timestamp_lock:
        if current_batch_timestamp is None:
            current_batch_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return current_batch_timestamp

def reset_batch_timestamp() -> None:
    """Resets the batch timestamp after all nodes have saved their images."""
    global current_batch_timestamp
    with batch_timestamp_lock:
        current_batch_timestamp = None

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
    """Connects to a single node, receives images, and processes them."""
    sio = socketio.AsyncClient()
    uri = f"http://{node_address}:{5001}"
    received_data = bytearray()
    metadata: Dict[str, Any] | None = None
    start_time: float | None = None
    total_start_time: float = time.time()

    @sio.event
    async def connect():
        logger.info(f"Connected to {node_id} at {uri}")
        # Request JPG format. For DNG, use: {'resolution': '2304x1296', 'format': 'dng'}
        await sio.emit('capture', {'resolution': '2304x1296', 'format': 'jpg'})

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
        nonlocal received_data, metadata
        if metadata:  # Only process chunks if metadata has been received
            remaining = metadata['size'] - len(received_data)
            if remaining > 0:
                received_data.extend(data[:remaining])


    @sio.on('image_complete')
    async def on_image_complete():
        nonlocal metadata, received_data, start_time, total_start_time
        logger.info(f"Received complete image from {node_id}")
        if metadata and start_time:
            transfer_time = time.time() - start_time
            processing_start_time = time.time()

            try:
                save_image(received_data, metadata, node_id)
            except Exception as e:
                logger.exception(f"Error processing image data from {node_id}: {e}")

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
            # Request next image
            await sio.emit('capture', {'resolution': '2304x1296', 'format': 'jpg'})

        else:
            logger.warning("Received image_complete without metadata!")

    @sio.on('capture_error')
    async def on_capture_error(data: Dict[str, str]):
        logger.error(f"Capture error from {node_id}: {data['error']}")
        await sio.emit('capture', {'resolution': '2304x1296', 'format': 'jpg'})

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

def save_image(data: bytearray, metadata: Dict[str, Any], node_id: str):
    """Saves the received image data with node-specific rotation."""
    format = metadata.get('format', 'jpg')
    timestamp = get_batch_timestamp()  # Use shared timestamp
    filename = f"image_{timestamp}_{node_id}.{format}"
    filepath = os.path.join("received_images", filename)

    try:
        # Write the initial data to a temporary file
        temp_filepath = filepath + '.temp'
        with open(temp_filepath, 'wb') as f:
            f.write(data)
        
        if format == 'jpg':
            # Open and potentially rotate the image
            with Image.open(temp_filepath) as img:
                # Rotate based on node_id
                if node_id in ["node_1", "node_3"]:
                    img = img.rotate(180)  # 180 degree rotation
                
                # Save the final image
                img.save(filepath, 'JPEG', quality=100)
                logger.info(f"Successfully saved JPG image: {filename}")

                # Reset timestamp if this is node_4 (last node)
                if node_id == "node_4":
                    reset_batch_timestamp()
                    
        else:  # DNG format
            # For DNG, just move the temp file to final location without rotation
            os.rename(temp_filepath, filepath)
            logger.info(f"Saved DNG image: {filename}")

            # Reset timestamp if this is node_4 (last node)
            if node_id == "node_4":
                reset_batch_timestamp()

        # Clean up temp file if it still exists
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        
        logger.info(f"Saved {format.upper()} image: {filename} (with rotation for {node_id})")
    except Exception as e:
        logger.error(f"Failed to save image: {e}")
        # Clean up temp file in case of error
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        raise

async def main():
    """Connects to multiple nodes concurrently."""
    nodes = {
        "node_1": "192.168.166.56",
        "node_2": "192.168.166.73",
        "node_3": "192.168.166.70",
        "node_4": "192.168.166.50",
    }
    os.makedirs("received_images", exist_ok=True)  # Create received_images directory
    tasks = [receive_images(address, node_id) for node_id, address in nodes.items()]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())