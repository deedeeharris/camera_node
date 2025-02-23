from pydantic import BaseModel
from typing import List

class ImageInfo(BaseModel):
    node_id: str
    filename: str
    filepath: str

class ImageSet(BaseModel):
    timestamp: str
    images: List[ImageInfo]

class CaptureResponse(BaseModel):
    success: bool
    timestamp: str
    images: List[ImageInfo] 