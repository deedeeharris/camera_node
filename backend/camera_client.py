import asyncio
import socketio
from typing import Dict, List
from datetime import datetime
from PIL import Image
import os
from models import ImageSet, ImageInfo

class CameraClient:
    def __init__(self, nodes: Dict[str, str]):
        self.nodes = nodes
        self.sio_clients = {}
        self.received_images = {}
        self.image_dir = "received_images"
        os.makedirs(self.image_dir, exist_ok=True)
        # Add event queues
        self.metadata_queues = {}
        self.chunk_queues = {}
        self.complete_queues = {}

    async def connect_to_node(self, node_id: str, address: str):
        sio = socketio.AsyncClient()
        self.sio_clients[node_id] = sio
        
        # Initialize queues for this node
        self.metadata_queues[node_id] = asyncio.Queue()
        self.chunk_queues[node_id] = asyncio.Queue()
        self.complete_queues[node_id] = asyncio.Queue()

        @sio.event
        async def connect():
            print(f"Connected to {node_id}")

        @sio.event
        async def image_metadata(data):
            await self.metadata_queues[node_id].put(data)

        @sio.event
        async def image_chunk(data):
            await self.chunk_queues[node_id].put(data)

        @sio.event
        async def image_complete():
            await self.complete_queues[node_id].put(True)

        try:
            await sio.connect(f"http://{address}:5001")
            return sio
        except Exception as e:
            print(f"Failed to connect to {node_id}: {e}")
            return None

    async def capture_all(self) -> ImageSet:
        """Capture images from all nodes simultaneously"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Connect to all nodes if not connected
        for node_id, address in self.nodes.items():
            if node_id not in self.sio_clients:
                await self.connect_to_node(node_id, address)

        # Capture from all nodes
        tasks = []
        for node_id, sio in self.sio_clients.items():
            tasks.append(self.capture_from_node(node_id, sio, timestamp))
        
        images = await asyncio.gather(*tasks)
        
        return ImageSet(
            timestamp=timestamp,
            images=[img for img in images if img is not None]
        )

    async def capture_from_node(self, node_id: str, sio: socketio.AsyncClient, timestamp: str) -> ImageInfo:
        """Capture image from a single node"""
        try:
            # Clear queues
            while not self.metadata_queues[node_id].empty():
                await self.metadata_queues[node_id].get()
            while not self.chunk_queues[node_id].empty():
                await self.chunk_queues[node_id].get()
            while not self.complete_queues[node_id].empty():
                await self.complete_queues[node_id].get()

            # Request capture
            await sio.emit('capture', {'resolution': '2304x1296', 'format': 'jpg'})
            
            # Wait for metadata
            try:
                metadata = await asyncio.wait_for(self.metadata_queues[node_id].get(), timeout=10)
            except asyncio.TimeoutError:
                raise Exception("Timeout waiting for metadata")

            # Receive image data
            image_data = bytearray()
            while len(image_data) < metadata['size']:
                try:
                    chunk = await asyncio.wait_for(self.chunk_queues[node_id].get(), timeout=10)
                    image_data.extend(chunk)
                except asyncio.TimeoutError:
                    raise Exception("Timeout waiting for image chunks")

            # Wait for complete signal
            try:
                await asyncio.wait_for(self.complete_queues[node_id].get(), timeout=10)
            except asyncio.TimeoutError:
                raise Exception("Timeout waiting for completion signal")

            # Process and save image
            filename = f"image_{timestamp}_{node_id}.jpg"
            filepath = os.path.join(self.image_dir, filename)
            
            # Save and rotate if needed
            with open(filepath + '.temp', 'wb') as f:
                f.write(image_data)
            
            with Image.open(filepath + '.temp') as img:
                if node_id in ["node_1", "node_3"]:
                    img = img.rotate(180)
                img.save(filepath, 'JPEG', quality=100)
            
            os.remove(filepath + '.temp')
            
            return ImageInfo(
                node_id=node_id,
                filename=filename,
                filepath=filepath
            )

        except Exception as e:
            print(f"Error capturing from {node_id}: {e}")
            return None

    async def get_image_sets(self) -> List[ImageSet]:
        """Get all image sets from the received_images directory"""
        image_sets = {}
        
        for filename in os.listdir(self.image_dir):
            if filename.startswith("image_") and filename.endswith(".jpg"):
                # Parse timestamp and node_id from filename
                parts = filename.split("_")
                if len(parts) >= 4:
                    timestamp = f"{parts[1]}_{parts[2]}"
                    node_id = parts[3].split(".")[0]
                    
                    if timestamp not in image_sets:
                        image_sets[timestamp] = ImageSet(timestamp=timestamp, images=[])
                    
                    image_sets[timestamp].images.append(ImageInfo(
                        node_id=node_id,
                        filename=filename,
                        filepath=os.path.join(self.image_dir, filename)
                    ))
        
        return sorted(image_sets.values(), key=lambda x: x.timestamp, reverse=True) 