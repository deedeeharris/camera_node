import asyncio
import websockets
import os
import json

async def receive_images(node_address, node_id, capture_interval=0):  # Added capture_interval
    """Connects to a single node, receives images, and saves them."""
    uri = f"ws://{node_address}:{5001}/ws"  # Use your actual port
    while True: # Reconnection loop
        try:
            async with websockets.connect(uri) as websocket:
                print(f"Connected to {node_id} at {uri}")

                while True:  # Image receiving loop
                    try:
                        # Send capture command
                        await websocket.send("capture")

                        metadata = await websocket.recv()
                        # Check if the received data is a string (JSON)
                        if isinstance(metadata, str):
                            metadata_json = json.loads(metadata)
                            print(f"Received metadata from {node_id}: {metadata_json}")

                            # Now receive the image data (which will be bytes)
                            image_data = await websocket.recv()
                            if isinstance(image_data, bytes):
                                print(f"Received image data from {node_id}: {len(image_data)} bytes")

                                # Save the image
                                filename = metadata_json['filename']
                                save_path = os.path.join("received_images", node_id)
                                os.makedirs(save_path, exist_ok=True)
                                filepath = os.path.join(save_path, filename)

                                with open(filepath, "wb") as image_file:
                                    image_file.write(image_data)
                                print(f"Saved image from {node_id} to {filepath}")
                            else:
                                print(f"Expected image data (bytes), but received: {type(image_data)}")
                        else:
                            print(f"Expected metadata (string), but received: {type(metadata)}")

                        if capture_interval > 0:
                            await asyncio.sleep(capture_interval)

                    except websockets.exceptions.ConnectionClosedOK:
                        print(f"Connection closed by {node_id}")
                        break  # Exit inner loop, attempt reconnection
                    except websockets.exceptions.ConnectionClosedError as e:
                        print(f"Connection closed by {node_id}: {e}")
                        break
                    except Exception as e:
                        print(f"Error receiving from {node_id}: {e}")
                        break  # Exit inner loop on any other error

        except Exception as e:
            print(f"Failed to connect to {node_id} ({uri}): {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)  # Wait before retrying connection


async def main():
    """Connects to multiple nodes concurrently."""
    # Replace with your actual Pi Zero W 2 addresses
    nodes = {
        "node_1": "192.168.195.70", # Only the working node
        "node_2": "192.168.195.56",
        # "node_3": "192.168.1.103", # Commented out
        # "node_4": "192.168.1.104", # Commented out
    }
    os.makedirs("received_images", exist_ok=True)  # Ensure directory exists

    # Create a list of tasks, one for each node
    tasks = [receive_images(address, node_id) for node_id, address in nodes.items()]

    # Run all tasks concurrently
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())