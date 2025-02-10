import asyncio
import socketio
import os
import json
import time
import logging
import csv
from logging.handlers import RotatingFileHandler
from datetime import datetime

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
CSV_FILE = os.path.join(LOG_DIR, "image_transfer_times.csv")

def write_to_csv(data):
    """Writes data to the CSV file."""
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as csvfile:
        fieldnames = ['timestamp', 'node_id', 'transfer_time', 'total_time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()  # Write header only if file is new
        writer.writerow(data)


async def receive_images(node_address, node_id):
    """Connects to a single node, receives images, and saves them."""
    sio = socketio.AsyncClient()
    uri = f"http://{node_address}:{5001}"  # Use http for Socket.IO
    received_data = bytearray()  # Accumulate chunks here
    metadata = None
    start_time = None
    total_start_time = time.time()


    @sio.event
    async def connect():
        logger.info(f"Connected to {node_id} at {uri}")
        await sio.emit('capture', {})  # Send an empty dictionary as data

    @sio.event
    async def disconnect():
        logger.info(f"Disconnected from {node_id}")

    @sio.on('image_metadata')
    async def on_image_metadata(data):
        nonlocal metadata, start_time
        metadata = data
        start_time = time.time()  # Record time when metadata is received
        logger.info(f"Received metadata from {node_id}: {metadata}")
        received_data.clear()  # Clear any previous data

    @sio.on('image_chunk')
    async def on_image_chunk(data):
        nonlocal received_data
        received_data.extend(data)

    @sio.on('image_complete')
    async def on_image_complete():
        nonlocal metadata, received_data, start_time, total_start_time
        logger.info(f"Received complete image from {node_id}")
        if metadata:
            # Calculate transfer time
            transfer_time = time.time() - start_time
            total_time = time.time() - total_start_time
            logger.info(f"Image transfer time from {node_id}: {transfer_time:.4f} seconds")
            logger.info(f"Total time elapsed: {total_time:.4f} seconds")

            # Log to CSV
            write_to_csv({
                'timestamp': datetime.now().isoformat(),
                'node_id': node_id,
                'transfer_time': f"{transfer_time:.4f}",
                'total_time': f"{total_time:.4f}"
            })

            # Save the image
            filename = metadata['filename']
            save_path = os.path.join("received_images", node_id)
            os.makedirs(save_path, exist_ok=True)
            filepath = os.path.join(save_path, filename)

            with open(filepath, "wb") as image_file:
                image_file.write(received_data)
            logger.info(f"Saved image from {node_id} to {filepath}")
            received_data.clear()  # Clear data after saving
            metadata = None
            start_time = None # reset start_time
            total_start_time = time.time() # Reset total time
            await sio.emit('capture', {}) # Request another image
        else:
            logger.warning("Received image_complete without metadata!")


    @sio.on('capture_error')
    async def on_capture_error(data):
        logger.error(f"Capture error from {node_id}: {data['error']}")
        await sio.emit('capture', {}) # Request another image even after error

    while True:  # Reconnection loop
        try:
            await sio.connect(uri)
            await sio.wait()  # Keep the connection open
        except socketio.exceptions.ConnectionError as e:
            logger.warning(f"Failed to connect to {node_id} ({uri}): {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"An unexpected error: {e}") # Log full traceback
            await asyncio.sleep(5)

async def main():
    """Connects to multiple nodes concurrently."""
    # Replace with your actual Pi Zero W 2 addresses
    nodes = {
        "node_1": "192.168.195.70",
        "node_2": "192.168.195.56",
        "node_3": "192.168.1.103",
        "node_4": "192.168.1.104",
    }
    os.makedirs("received_images", exist_ok=True)  # Ensure directory exists

    # Create a list of tasks, one for each node
    tasks = [receive_images(address, node_id) for node_id, address in nodes.items()]

    # Run all tasks concurrently
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())