# Camera Node

This is a component of the distributed Smart Camera System that runs on individual Raspberry Pi Zero nodes. Each node operates as an independent camera server that can capture RAW images and manage its own storage and operations.

## Features

- FastAPI-based REST API
- RAW image capture (DNG format)
- Automatic storage management
- Rotating log system
- System monitoring (CPU, memory, temperature)
- Cross-origin support (CORS)
- Comprehensive error handling

## Requirements

### Hardware
- Raspberry Pi Zero W
- Camera Module
- At least 4GB SD card

### Software
- Python 3.7+
- libcamera-apps

## Installation

1. Install system dependencies:
```bash
sudo apt-get update
sudo apt-get install -y python3-pip libcamera-apps
```

2. Install Python dependencies:
```bash
pip3 install -r requirements.txt
```

## Configuration

The following environment variables can be set:
- `NODE_ID`: Unique identifier for the camera node (default: `camera_node_[pid]`)
- `PORT`: HTTP server port (default: 5003)

Other configurations in `camera_node.py`:
```python
CAPTURE_DIR = "captured_photos"  # Directory for storing images
LOG_DIR = "logs"                 # Directory for log files
STORAGE_LIMIT_MB = 1000         # Storage limit for images (1GB)
MAX_LOG_SIZE_MB = 10            # Maximum size per log file
MAX_LOG_FILES = 5               # Number of log files to keep
```

## API Endpoints

### Image Operations

#### `POST /capture`
Capture a new image.
- Query Parameters:
  - `return_file` (bool): If true, returns the image directly; if false, returns file info
- Response:
  ```json
  {
    "status": "success",
    "file_info": {
      "filename": "capture_20250130_122601.dng",
      "filepath": "/path/to/file",
      "timestamp": "20250130_122601",
      "size": 12345678
    },
    "node_id": "camera_1"
  }
  ```

#### `GET /images`
List all captured images.
- Response: Array of image details including filename, size, and timestamps

#### `GET /images/{filename}`
Download a specific image.
- Returns: Raw image file (DNG format)

#### `DELETE /images/{filename}`
Delete a specific image.
- Response: Success/failure status

### System Operations

#### `GET /status`
Get node status and system information.
- Response:
  ```json
  {
    "status": "online",
    "storage": {
      "used_mb": 123.45,
      "limit_mb": 1000,
      "available_mb": 876.55
    },
    "system": {
      "cpu_percent": 12.3,
      "memory_percent": 45.6,
      "disk_usage": 78.9,
      "cpu_temperature": 45.6,
      "uptime": 123456
    },
    "node_id": "camera_1",
    "timestamp": "2025-01-30T12:26:01"
  }
  ```

#### `GET /logs`
Get recent log entries.
- Query Parameters:
  - `lines` (int): Number of recent log lines to return (default: 100)
- Response: Array of log entries

## Directory Structure

```
camera_node/
├── camera_node.py      # Main application
├── requirements.txt    # Python dependencies
├── captured_photos/    # Image storage (created automatically)
└── logs/              # Log files (created automatically)
    └── camera_node.log
```

## Logging

Logs are stored in the `logs` directory with rotation:
- Maximum log file size: 10MB
- Maximum number of log files: 5
- Log format: `timestamp - name - level - message`

## Storage Management

- Images are stored in `captured_photos/`
- 1GB storage limit by default
- Oldest images are automatically deleted when limit is reached
- Storage status available via `/status` endpoint

## Error Handling

- All operations are logged
- Failed operations clean up temporary files
- HTTP error responses include detailed messages
- System errors are logged with stack traces

## Usage Examples

### Capture and Download Image

```python
# Capture and get file info
response = requests.post("http://pi-zero:5003/capture")
file_info = response.json()["file_info"]

# Capture and get image directly
response = requests.post("http://pi-zero:5003/capture", params={"return_file": True})
with open("image.dng", "wb") as f:
    f.write(response.content)
```

### Monitor Node Status

```python
response = requests.get("http://pi-zero:5003/status")
status = response.json()
print(f"Storage used: {status['storage']['used_mb']}MB")
print(f"CPU Temperature: {status['system']['cpu_temperature']}°C")
```

## Troubleshooting

1. Check logs:
```bash
curl http://pi-zero:5003/logs
```

2. Verify camera connection:
```bash
libcamera-still --list-cameras
```

3. Monitor system status:
```bash
curl http://pi-zero:5003/status
```

## License

MIT License

  
## Diagram

flowchart TD
    A[Client Request] --> B[FastAPI API]
    B --> C{Endpoint Type}

    %% Capture Endpoint Flow
    C -- "/capture" --> D[Capture Image]
    D --> E[Ensure Capture Directory]
    E --> F[Cleanup Old Files]
    F --> G[Check Camera Connection]
    G --> H[Execute libcamera-still]
    H --> I[Save RAW Image]
    I --> J[Return File Info or Image]

    %% List Images Flow
    C -- "GET /images" --> K[List .dng Files]
    K --> L[Extract File Metadata]
    L --> M[Return Image Details]

    %% Retrieve Specific Image Flow
    C -- "GET /images/{filename}" --> N[Locate Image File]
    N --> O[Return DNG File]

    %% Delete Image Flow
    C -- "DELETE /images/{filename}" --> P[Delete Image]
    P --> Q[Return Deletion Status]

    %% Logs Flow
    C -- "GET /logs" --> R[Read Log Entries]
    R --> S[Return Log Lines]

    %% Status Flow
    C -- "GET /status" --> T[Get System Info]
    T --> U[Calculate Storage Usage]
    U --> V[Return Node Status]
