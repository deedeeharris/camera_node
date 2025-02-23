from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
import uvicorn
from typing import List, Dict
import os
from datetime import datetime
from camera_client import CameraClient
from models import CaptureResponse, ImageSet

# Create FastAPI app
app = FastAPI(title="Camera Control Center")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize camera client
camera_client = CameraClient({
    "node_1": "192.168.166.56",
    "node_2": "192.168.166.73",
    "node_3": "192.168.166.70",
    "node_4": "192.168.166.50",
})

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/gallery", response_class=HTMLResponse)
async def gallery(request: Request):
    return templates.TemplateResponse("gallery.html", {"request": request})

@app.post("/api/capture")
async def capture_images() -> CaptureResponse:
    try:
        image_set = await camera_client.capture_all()
        return CaptureResponse(
            success=True,
            timestamp=image_set.timestamp,
            images=image_set.images
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gallery")
async def get_gallery() -> List[ImageSet]:
    return await camera_client.get_image_sets()

# Add this to serve the received_images directory
app.mount("/received_images", StaticFiles(directory="received_images"), name="received_images") 